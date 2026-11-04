"""Shared pieces for the baselines. Owner: Carlos.

A baseline is a System for run_eval: async (client, image_bytes, destination) -> AnalyzeResponse.
Every baseline ignores the destination on purpose. They are the "no policy" comparison, so
destination accuracy shows what the destination toggle adds.
Baseline findings use source "extra" and are never locked: they are not Redact output.
"""

import time

from app.pipeline.ingest import IngestResult
from app.providers.meta_api import CallStats
from app.schemas import AnalyzeResponse, Category, Destination, Finding

REASON = "baseline detection"


class Tally:
    """Adds up a baseline's API calls for est_cost_usd. Same shape the pipeline's wrapper has."""

    def __init__(self, client):
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


def finding(n: int, category: Category, box: list[int], mask_rle: str | None = None) -> Finding:
    return Finding(id=f"b_{n:02d}", marks=[], category=category, reason=REASON, source="extra",
                   masked=True, locked=False, box=box, mask_rle=mask_rle)


def response(r: IngestResult, destination: Destination, findings: list[Finding], started: float, *,
             cost: float = 0.0, ok: bool = True, models: dict[str, str] | None = None,
             version: str = "baseline") -> AnalyzeResponse:
    total = round((time.perf_counter() - started) * 1000)
    return AnalyzeResponse(
        image_id=r.sha256[:16], width=r.width, height=r.height, destination=destination,
        findings=findings, judge_status="ok" if ok else "failed_closed", prompt_version=version,
        model_ids=models or {}, timings_ms={"total": total}, est_cost_usd=round(cost, 5),
    )
