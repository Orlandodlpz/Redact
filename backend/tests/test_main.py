"""Route tests. No API calls: analyze is faked, export runs the real ingest and compose."""

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.formparsers import MultiPartParser

from app import main
from app.config import get_settings
from app.pipeline.ingest import IngestError
from app.pipeline.sweep import SweepError
from app.schemas import AnalyzeResponse, Finding

ORIGIN = "http://localhost:3000"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "test-key-not-real")
    monkeypatch.setenv("FRONTEND_ORIGIN", ORIGIN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(monkeypatch):
    async def never_called(*a, **k):
        raise AssertionError("the pipeline should be faked in this test")

    monkeypatch.setattr(main, "analyze", never_called)
    monkeypatch.setattr(main, "MetaClient", lambda settings: _FakeClient())
    # Built here, not imported, so the CORS allowlist comes from this test's env.
    with TestClient(main.create_app()) as c:
        yield c


@pytest.fixture
def stranger_client(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://redact-demo.vercel.app")
    monkeypatch.setattr(main, "MetaClient", lambda settings: _FakeClient())
    get_settings.cache_clear()
    with TestClient(main.create_app()) as c:
        yield c


class _FakeClient:
    async def close(self):
        pass


def png_bytes(width=80, height=60, color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def upload(data: bytes | None = None, name="photo.png"):
    return {"image": (name, io.BytesIO(data if data is not None else png_bytes()), "image/png")}


def fake_response(**over) -> AnalyzeResponse:
    base = dict(
        image_id="abc123", width=80, height=60, destination="public",
        findings=[], judge_status="ok", prompt_version="judge_v1",
        model_ids={"judge": "muse-spark-1.3", "sam": "sam-3.1"},
        timings_ms={"total": 10}, est_cost_usd=0.05,
    )
    return AnalyzeResponse(**{**base, **over})


def finding(**over) -> dict:
    base = dict(id="f_01", marks=[1], category="credential", reason="r",
                source="floor", masked=True, locked=True, box=[10, 10, 40, 30])
    return Finding(**{**base, **over}).model_dump()


# --- health and startup -------------------------------------------------------


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model_ids"]["sam"] and body["premask"] in ("on", "off")


def test_uploads_stay_in_memory(client):
    """Starlette spools a multipart upload to disk past 1 MB, which would write user
    images to the filesystem. Lifespan raises the limit above our own upload cap."""
    assert MultiPartParser.spool_max_size > get_settings().max_upload_bytes


# --- analyze ------------------------------------------------------------------


def test_analyze_returns_findings(client, monkeypatch):
    seen = {}

    async def fake(image_bytes, destination, *, client=None):
        seen.update(size=len(image_bytes), destination=destination, client=client)
        return fake_response(destination=destination)

    monkeypatch.setattr(main, "analyze", fake)
    r = client.post("/analyze", files=upload(), data={"destination": "team"})
    assert r.status_code == 200
    assert r.json()["destination"] == "team"
    assert seen["destination"] == "team" and seen["size"] > 0
    assert seen["client"] is not None  # the app's shared client, not a new one per request


@pytest.mark.parametrize("dest", ["public", "team", "ai_assistant"])
def test_every_destination_is_accepted(client, monkeypatch, dest):
    monkeypatch.setattr(main, "analyze", lambda b, d, *, client=None: _async(fake_response(destination=d)))
    assert client.post("/analyze", files=upload(), data={"destination": dest}).status_code == 200


def test_unknown_destination_is_refused(client):
    r = client.post("/analyze", files=upload(), data={"destination": "everyone"})
    assert r.status_code == 422


def test_missing_destination_is_refused(client):
    assert client.post("/analyze", files=upload()).status_code == 422


def test_empty_upload_is_refused(client):
    r = client.post("/analyze", files=upload(b""), data={"destination": "public"})
    assert r.status_code == 400


def test_bad_upload_maps_to_400_with_the_users_message(client, monkeypatch):
    async def fake(*a, **k):
        raise IngestError("Unsupported image type GIF; use JPEG, PNG, HEIC or WebP")

    monkeypatch.setattr(main, "analyze", fake)
    r = client.post("/analyze", files=upload(), data={"destination": "public"})
    assert r.status_code == 400 and "Unsupported image type" in r.json()["detail"]


def test_incomplete_scan_maps_to_503_and_never_partial_findings(client, monkeypatch):
    async def fake(*a, **k):
        raise SweepError("phrase 'face' failed twice")

    monkeypatch.setattr(main, "analyze", fake)
    r = client.post("/analyze", files=upload(), data={"destination": "public"})
    assert r.status_code == 503
    assert "findings" not in r.json()
    # The user sees a plain message, not the provider's error text.
    assert "face" not in r.json()["detail"]


def test_oversize_upload_is_refused_without_reading_the_body(client):
    limit = get_settings().max_upload_bytes + main._FORM_OVERHEAD_BYTES
    r = client.post(
        "/analyze",
        content=b"",
        headers={"content-length": str(limit + 1), "content-type": "application/octet-stream"},
    )
    assert r.status_code == 413


def test_oversize_image_inside_a_normal_sized_request_is_refused(client):
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (get_settings().max_upload_bytes + 1)
    r = client.post("/analyze", files=upload(big), data={"destination": "public"})
    assert r.status_code == 413


# --- export -------------------------------------------------------------------


def test_export_fills_masked_regions_solid_and_strips_metadata(client):
    r = client.post(
        "/export",
        files=upload(png_bytes()),
        data={"findings": json.dumps([finding(box=[10, 10, 40, 30])])},
    )
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    out = Image.open(io.BytesIO(r.content))
    assert out.format == "PNG"
    assert not out.info.get("exif") and not out.info.get("XML:com.adobe.xmp")
    assert out.getpixel((20, 20)) == (0, 0, 0)  # inside the mask
    assert out.getpixel((70, 50)) == (200, 30, 30)  # untouched


def test_export_honours_an_unmasked_floor_finding(client):
    """A locked finding the user chose to unmask is not filled. That choice is theirs."""
    r = client.post(
        "/export",
        files=upload(png_bytes()),
        data={"findings": json.dumps([finding(masked=False, box=[10, 10, 40, 30])])},
    )
    assert Image.open(io.BytesIO(r.content)).getpixel((20, 20)) == (200, 30, 30)


def test_export_accepts_a_mask_the_user_drew(client):
    r = client.post(
        "/export",
        files=upload(png_bytes()),
        data={"findings": json.dumps([finding(
            id="f_09", marks=[], source="manual", locked=False,
            category="other_sensitive", reason="Masked by hand", box=[0, 0, 20, 20])])},
    )
    assert r.status_code == 200
    assert Image.open(io.BytesIO(r.content)).getpixel((5, 5)) == (0, 0, 0)


def test_export_with_no_findings_returns_the_image_unmasked(client):
    r = client.post("/export", files=upload(png_bytes()), data={"findings": "[]"})
    assert r.status_code == 200
    assert Image.open(io.BytesIO(r.content)).getpixel((40, 30)) == (200, 30, 30)


def test_export_refuses_bad_findings_json(client):
    r = client.post("/export", files=upload(), data={"findings": "{not json"})
    assert r.status_code == 422


def test_export_refuses_findings_that_are_not_a_list(client):
    r = client.post("/export", files=upload(), data={"findings": '{"id": "f_01"}'})
    assert r.status_code == 422


def test_export_refuses_a_finding_that_breaks_the_contract(client):
    bad = finding()
    bad["box"] = [50, 50, 10, 10]  # x2 before x1
    r = client.post("/export", files=upload(), data={"findings": json.dumps([bad])})
    assert r.status_code == 422


def test_export_refuses_a_malformed_mask_instead_of_crashing(client):
    r = client.post(
        "/export",
        files=upload(),
        data={"findings": json.dumps([finding(mask_rle="not-an-rle-string")])},
    )
    assert r.status_code == 400


def test_export_refuses_a_file_that_is_not_an_image(client):
    r = client.post(
        "/export",
        files={"image": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"findings": "[]"},
    )
    assert r.status_code == 400


# --- headers and CORS ---------------------------------------------------------


def test_responses_are_never_cached(client):
    """Findings say what is sensitive in someone's image. No proxy keeps a copy."""
    assert client.get("/health").headers["cache-control"] == "no-store"
    r = client.post("/export", files=upload(), data={"findings": "[]"})
    assert r.headers["cache-control"] == "no-store"


def test_the_frontend_origin_is_allowed(client):
    r = client.options(
        "/analyze",
        headers={"origin": ORIGIN, "access-control-request-method": "POST"},
    )
    assert r.headers.get("access-control-allow-origin") == ORIGIN


def test_only_the_configured_origin_is_granted(stranger_client):
    """The allowlist under test is the one this test set, not the default."""
    allowed = stranger_client.options(
        "/analyze",
        headers={"origin": "https://redact-demo.vercel.app",
                 "access-control-request-method": "POST"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "https://redact-demo.vercel.app"
    for origin in ("https://evil.example", ORIGIN):
        blocked = stranger_client.options(
            "/analyze",
            headers={"origin": origin, "access-control-request-method": "POST"},
        )
        assert blocked.headers.get("access-control-allow-origin") != origin


def test_no_credentials_are_granted_to_the_browser(client):
    r = client.options(
        "/analyze", headers={"origin": ORIGIN, "access-control-request-method": "POST"}
    )
    assert "access-control-allow-credentials" not in r.headers


def test_startup_refuses_a_wildcard_origin(monkeypatch):
    from app.config import Settings, startup_problems

    monkeypatch.setenv("FRONTEND_ORIGIN", "*")
    get_settings.cache_clear()
    assert any("any page on the web" in p for p in startup_problems(Settings()))


def _async(value):
    async def run():
        return value

    return run()
