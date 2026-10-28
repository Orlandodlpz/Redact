"""Calls every pipeline step in order. Owner: Orlando.

Order: ingest, then OCR (local, in a thread) and the SAM sweep at the same time,
then candidates, floor rules, marks, judge, merge. Tier 2 pre-masking (Phase 4)
will instead finish OCR and the text floor rules before the sweep starts, then
fill those pixels; until it exists, PREMASK=on is refused rather than ignored.

Refine (Phase 3) isn't wired in yet: extra_findings keep the judge's loose box.
"""

import asyncio
import logging
import time
import uuid
from contextlib import contextmanager

from app.config import get_settings
from app.pipeline import judge as judge_step
from app.pipeline.candidates import build
from app.pipeline.floor import find_floor_hits
from app.pipeline.ingest import ingest
from app.pipeline.judge import judge
from app.pipeline.marks import render
from app.pipeline.merge import merge
from app.pipeline.ocr import ocr
from app.pipeline.sweep import sweep
from app.providers.meta_api import CallStats, MetaClient
from app.schemas import AnalyzeResponse, Destination, Finding

logger = logging.getLogger(__name__)


async def analyze(
    image_bytes: bytes,
    destination: Destination,
    *,
    client: MetaClient | None = None,
) -> AnalyzeResponse:
    """Raises IngestError for a bad upload and SweepError when the image couldn't be
    fully scanned; both mean no result, never a result with fewer masks.

    Pass the app's long lived client; without one, a client is made and closed here.
    """
    settings = get_settings()
    if settings.premask:
        raise NotImplementedError("PREMASK=on is Phase 4 and not built yet; set PREMASK=off")

    own_client = client is None
    tally = _Tally(client or MetaClient(settings))
    ms: dict[str, int] = {}
    start = time.perf_counter()
    run_id = uuid.uuid4().hex[:12]
    try:
        with _timed(ms, "ingest"):
            r = await asyncio.to_thread(ingest, image_bytes)

        async def timed_ocr():
            with _timed(ms, "ocr"):
                return await asyncio.to_thread(
                    ocr, r.ocr_image, scale=r.ocr_scale, bounds=(r.width, r.height)
                )

        async def timed_sweep():
            with _timed(ms, "sweep"):
                return await sweep(r.image, tally, run=run_id)

        lines, sam = await asyncio.gather(timed_ocr(), timed_sweep())

        with _timed(ms, "candidates"):
            candidates = build(sam, lines)
        with _timed(ms, "floor"):
            floor_hits = find_floor_hits(candidates)
        with _timed(ms, "marks"):
            marked = render(r.image, candidates)
        with _timed(ms, "judge"):
            try:
                judge_output = await judge(r.image, marked, candidates, destination, client=tally)
            except Exception as e:
                # Any judge failure takes the fail closed path in merge, never fewer masks.
                logger.warning("judge raised %s; failing closed", type(e).__name__)
                judge_output = None
        with _timed(ms, "merge"):
            findings = merge(candidates, floor_hits, judge_output, destination)
    finally:
        if own_client:
            await tally.close()

    if r.had_gps:
        findings = [_gps_finding(), *findings]
    # OCR and sweep overlap, so total is wall time, not the sum of steps.
    ms["total"] = round((time.perf_counter() - start) * 1000)
    return AnalyzeResponse(
        image_id=r.sha256[:16],
        width=r.width,
        height=r.height,
        destination=destination,
        findings=findings,
        judge_status="ok" if judge_output is not None else "failed_closed",
        prompt_version=getattr(judge_step, "PROMPT_VERSION", "unset"),
        model_ids=settings.model_ids(),
        timings_ms=ms,
        est_cost_usd=round(tally.cost, 5),
    )


def _gps_finding() -> Finding:
    # Ingest already stripped it and compose rebuilds from pixels, so it can't be unmasked.
    return Finding(
        id="gps",
        marks=[],
        category="home_location",
        reason="The photo's metadata held GPS coordinates of where it was taken; removed",
        source="metadata",
        masked=True,
        locked=True,
    )


class _Tally:
    """Wraps the shared client to add up this request's calls for est_cost_usd."""

    def __init__(self, client: MetaClient):
        self._client = client
        self.stats: list[CallStats] = []

    async def sam(self, *args, **kwargs):
        result = await self._client.sam(*args, **kwargs)
        self.stats.append(result.stats)
        return result

    async def chat_json(self, *args, **kwargs):
        result = await self._client.chat_json(*args, **kwargs)
        self.stats.append(result.stats)
        return result

    @property
    def cost(self) -> float:
        return sum(s.est_cost_usd or 0.0 for s in self.stats)

    async def close(self) -> None:
        await self._client.close()


@contextmanager
def _timed(ms: dict[str, int], name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        ms[name] = round((time.perf_counter() - start) * 1000)
