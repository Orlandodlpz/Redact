"""FastAPI service. Owner: Victor (POST /analyze and POST /export land here).

Never log request bodies at any layer: they carry user images.

Nothing is stored between the two routes. /analyze returns findings and keeps no copy
of the image, so the editor re sends the image to /export along with the final finding
list. That is the whole reason export takes an upload instead of an image id.

Two things in here exist for the "never store user images" constraint rather than for
the feature. Starlette spools a multipart upload to a temporary file on disk once it
passes 1 MB, which almost every photo does, so the spool limit is raised above our own
upload limit to keep uploads in memory. And an oversized request is refused from its
Content-Length before the body is read, so a 2 GB post cannot be parsed into memory
just to be rejected by ingest afterwards.
"""

import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated, get_args

from fastapi import (
    APIRouter,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from starlette.formparsers import MultiPartParser

from app.config import VERSION, StartupError, assert_startup_safe, get_settings
from app.demo_gate import GATED_PATHS, PASSCODE_HEADER, DemoGate
from app.pipeline.compose import compose
from app.pipeline.ingest import IngestError, ingest
from app.pipeline.run import analyze
from app.pipeline.sweep import SweepError
from app.providers.meta_api import MetaClient
from app.schemas import AnalyzeResponse, Destination, Finding

logger = logging.getLogger(__name__)

DESTINATIONS = get_args(Destination)
# Room for the multipart envelope, the destination field and the findings JSON on top
# of a max size image. Only the image is capped by max_upload_bytes itself, in ingest.
_FORM_OVERHEAD_BYTES = 4 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A failure here makes uvicorn exit non-zero before serving anything.
    settings = get_settings()
    assert_startup_safe(settings)
    # One client for the process, so connections are reused across requests. Built here
    # rather than lazily on the first upload: a server with no key can analyze nothing,
    # and a deploy should fail at boot instead of on a judge's first try.
    if settings.meta_api_key is None:
        raise StartupError("META_API_KEY is not set, so no image could be analyzed")
    # Starlette's default rolls an upload over to a SpooledTemporaryFile on disk at
    # 1 MB, which would write user images to the filesystem. Keep every accepted
    # upload in memory; the Content-Length guard below bounds how much that can be.
    MultiPartParser.spool_max_size = settings.max_upload_bytes + _FORM_OVERHEAD_BYTES
    app.state.gate = DemoGate(settings)
    app.state.client = MetaClient(settings)
    try:
        yield
    finally:
        await app.state.client.close()


async def front_door(request: Request, call_next):
    """Size guard, demo gate, and no caching, in that order.

    Size first because it is free and refuses a body before it is read. The gate next,
    so a request that will not be served never reaches the pipeline. Findings name what
    is sensitive in an image, so nothing downstream of here may hold a copy.
    """
    settings = get_settings()
    limit = settings.max_upload_bytes + _FORM_OVERHEAD_BYTES
    declared = request.headers.get("content-length")
    if request.method == "POST" and any(request.url.path.startswith(p) for p in GATED_PATHS):
        mb = settings.max_upload_bytes // (1024 * 1024)
        if declared is None or not declared.isdigit():
            # Without a length there is nothing to check, and Starlette would spool the
            # body to a temporary file once it passed the in memory limit, putting image
            # bytes on disk. Every browser sends a length for a FormData post.
            return _refusal(411, "This request needs a Content-Length.")
        if int(declared) > limit:
            return _refusal(413, f"Image is larger than {mb} MB")

    gate: DemoGate | None = getattr(request.app.state, "gate", None)
    ip = None
    if gate is not None and request.method != "OPTIONS":
        ip = gate.client_ip(
            request.headers.get("x-forwarded-for"),
            request.client.host if request.client else None,
        )
        decision = gate.check(request.url.path, request.headers.get(PASSCODE_HEADER), ip)
        if not decision.allowed:
            headers = {}
            if decision.retry_after_s is not None:
                headers["Retry-After"] = str(max(1, decision.retry_after_s))
            return _refusal(decision.status, decision.detail, headers)

    response = await call_next(request)
    # Counted after the fact, and only when the call was served. A 422 for a missing
    # field costs nothing, so it should not cost the visitor one of their twelve.
    # Requests in flight at the same moment all pass the check before any of them is
    # counted, so the limit can be overshot by roughly the number of concurrent calls.
    # One instance serving a demo makes that a handful, which is inside the day cap.
    if gate is not None and ip is not None and response.status_code < 400:
        gate.record(request.url.path, ip)
    response.headers["Cache-Control"] = "no-store"
    return response


def _refusal(status: int, detail: str, headers: dict[str, str] | None = None) -> Response:
    return Response(
        content=json.dumps({"detail": detail}),
        status_code=status,
        media_type="application/json",
        headers={"Cache-Control": "no-store", **(headers or {})},
    )


router = APIRouter()


def create_app() -> FastAPI:
    """Middleware is configured from settings, which a factory reads at build time.

    Module level `app` is what uvicorn serves. Tests build their own so the CORS
    allowlist under test is the one they set, not whatever the defaults happen to be.
    """
    built = FastAPI(
        title="Redact",
        version=VERSION,
        lifespan=lifespan,
        # The demo is public. Nothing here is secret, but there is no reason to hand
        # out an interactive schema browser with it.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Order matters. add_middleware inserts at the front, so the last one registered is
    # the outermost. CORS has to be outside front_door: the gate answers a bad passcode
    # itself, and a response built inside CORS is the only kind that carries an
    # Access-Control-Allow-Origin header. Registered the other way round, a judge who
    # mistypes the passcode sees a CORS error instead of "This demo needs a passcode".
    built.middleware("http")(front_door)
    built.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().allowed_origins(),
        # No cookies or sessions, so the browser never needs to send credentials.
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    built.include_router(router)
    return built


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": VERSION,
        "model_ids": settings.model_ids(),
        "premask": "on" if settings.premask else "off",
    }


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_route(
    request: Request,
    image: Annotated[UploadFile, File()],
    destination: Annotated[str, Form()],
) -> AnalyzeResponse:
    """Findings for one image and one destination. Nothing is kept afterwards."""
    dest = _destination(destination)
    image_bytes = await _read_upload(image)
    try:
        return await analyze(image_bytes, dest, client=request.app.state.client)
    except IngestError as e:
        # ingest raises with a message written for the user.
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SweepError as e:
        # The scan was incomplete, so a result would have fewer masks than it should.
        logger.warning("sweep failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=503, detail="Couldn't fully scan this image. Try again."
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        # Anything unexpected becomes a 500 here rather than escaping the route. Letting
        # it escape means the error response is built outside the CORS middleware, so
        # the browser reports a CORS failure and the real problem never reaches anyone.
        #
        # The type only, with no traceback and no message. A pydantic ValidationError
        # puts the offending value in its message as `input_value=`, and on this
        # pipeline that value can be a line of text read off the user's image, so
        # logger.exception here would write image content to a log file.
        logger.error("analyze failed with %s", type(e).__name__)
        raise HTTPException(
            status_code=500, detail="Something went wrong on our side. Try again."
        ) from e


@router.post("/export", response_class=Response)
async def export_route(
    image: Annotated[UploadFile, File()],
    findings: Annotated[str, Form()],
) -> Response:
    """The final PNG: solid fill over every masked finding, no metadata.

    `findings` is the JSON list the editor holds after the user's edits, so it carries
    their unmasks and any mask they drew by hand. The server trusts `masked` as sent,
    because unmasking a locked finding is the user's call to make.
    """
    final = _findings(findings)
    image_bytes = await _read_upload(image)
    try:
        # The same ingest the analyze run used, so the findings' coordinates line up
        # and the pixels we encode carry no metadata from the upload.
        result = ingest(image_bytes)
        png = compose(result.image, final)
    except IngestError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (ValueError, KeyError, IndexError) as e:
        # A mask that doesn't decode is a bad request, not a server fault.
        logger.warning("export failed to compose: %s", type(e).__name__)
        raise HTTPException(status_code=400, detail="A mask in this request is malformed") from e
    except Exception as e:
        logger.error("export failed with %s", type(e).__name__)  # type only, see above
        raise HTTPException(
            status_code=500, detail="Something went wrong on our side. Try again."
        ) from e
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": 'attachment; filename="redacted.png"',
            "Cache-Control": "no-store",
        },
    )


def _destination(value: str) -> Destination:
    if value not in DESTINATIONS:
        raise HTTPException(
            status_code=422, detail=f"destination must be one of {', '.join(DESTINATIONS)}"
        )
    return value  # type: ignore[return-value]


async def _read_upload(upload: UploadFile) -> bytes:
    settings = get_settings()
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="No image was uploaded")
    if len(data) > settings.max_upload_bytes:
        mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"Image is larger than {mb} MB")
    return data


def _findings(raw: str) -> list[Finding]:
    """Parse the editor's finding list. Never echo the input back in an error."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail="findings is not valid JSON") from e
    if not isinstance(parsed, list):
        raise HTTPException(status_code=422, detail="findings must be a list")
    try:
        return [Finding.model_validate(f) for f in parsed]
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"findings has {e.error_count()} bad entries") from e


# What uvicorn serves: `uvicorn app.main:app`.
app = create_app()
