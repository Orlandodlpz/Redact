"""Run a config over labeled images and write eval/results/<date>_<commit>/. Owner: Carlos.

A config is an async function (client, image_bytes, destination) -> AnalyzeResponse, so
Redact and the baselines are scored the same way, from the same labels, with the same
metrics. Redact is scored on the pixels compose would fill (union of masked findings,
dilated), which is what a user downloads.

Guards that keep the eval honest:
- Default split is dev. The test split is frozen for the final runs and needs
  --final, a clean git tree, and the floor rules switched on.
- --no-floor exists only so the judge path can be run before the floor rules land.
  It is recorded in the results and refused with --final.
- SAM costs 16 requests per image and the rate limit is shared by the whole team
  (gotcha 29), so images start at most RATE_IMAGES_PER_MIN per minute.

Usage:
  uv run python eval/run_eval.py --config redact --split dev
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import metrics
from schemas import Label, ManifestRow
from app.config import SWEEP_PHRASES, Settings, get_settings
from app.pipeline import judge as judge_step
from app.pipeline.compose import dilate, union_mask
from app.providers.meta_api import MetaClient
from app.schemas import AnalyzeResponse, Destination

EVAL = Path(__file__).parent
IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "heic")
RATE_IMAGES_PER_MIN = 100  # SAM shares 3,000 requests per minute across the team
CONCURRENCY = 3

System = Callable[[MetaClient, bytes, Destination], Awaitable[AnalyzeResponse]]


async def run_redact(client: MetaClient, image_bytes: bytes, destination: Destination) -> AnalyzeResponse:
    from app.pipeline.run import analyze

    return await analyze(image_bytes, destination, client=client)


def _baseline(name: str) -> System:
    """Baselines import lazily so a missing optional dependency (B2) only fails B2."""

    async def run(client, image_bytes, destination):
        import importlib

        return await importlib.import_module(f"baselines.{name}").run(client, image_bytes, destination)

    return run


CONFIGS: dict[str, System] = {
    "redact": run_redact, "b1": _baseline("b1_sam"), "b2": _baseline("b2_presidio"), "b3": _baseline("b3_muse"),
}


@dataclass
class Record:
    image_id: str
    source: str
    split: str
    destination: str
    error: str | None = None
    judge_status: str | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    caught: int = 0
    total: int = 0
    by_category: dict[str, tuple[int, int]] = field(default_factory=dict)
    over_redaction: float | None = None
    hard_negative_fp: bool | None = None
    decisions: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)


def score(row: ManifestRow, label: Label, destination: Destination, resp: AnalyzeResponse,
          dilation_px: int) -> Record:
    rec = Record(row.image_id, row.source, row.split, destination, judge_status=resp.judge_status,
                 latency_ms=resp.timings_ms.get("total"), cost_usd=resp.est_cost_usd)
    if (resp.width, resp.height) != (label.width, label.height):
        # Labels must be drawn on the ingested image (long edge capped at 2048 px).
        rec.error = f"size_mismatch response {resp.width}x{resp.height} label {label.width}x{label.height}"
        return rec
    mask = dilate(union_mask(resp.width, resp.height, resp.findings), dilation_px)
    truth = label.destinations[destination]
    rec.by_category = metrics.recall_by_category_px(truth, mask)
    rec.caught = sum(c for c, _ in rec.by_category.values())
    rec.total = sum(t for _, t in rec.by_category.values())
    rec.over_redaction = metrics.over_redaction_px(truth, mask)
    rec.decisions = metrics.destination_decisions_px(label.destinations, destination, mask)
    if row.source == "hard_negative":
        rec.hard_negative_fp = metrics.hard_negative_false_positive(resp.findings)
    rec.findings = [{"source": f.source, "category": f.category, "masked": f.masked, "locked": f.locked,
                     "marks": f.marks, "box": f.box} for f in resp.findings]
    return rec


def _rate(records: list[Record]) -> dict:
    caught, total = sum(r.caught for r in records), sum(r.total for r in records)
    return {"caught": caught, "total": total, "recall": round(caught / total, 4) if total else None}


def _accuracy(decisions: list[dict]) -> dict:
    right = sum(d["should_mask"] == d["masked"] for d in decisions)
    return {"right": right, "total": len(decisions), "accuracy": round(right / len(decisions), 4) if decisions else None}


def destination_accuracy(scored: list[Record]) -> dict | None:
    """None when no labeled image has two or more destinations."""
    rows = [(r.destination, d) for r in scored for d in r.decisions]
    if not rows:
        return None
    return {
        "overall": _accuracy([d for _, d in rows]),
        "keep_cells": _accuracy([d for _, d in rows if not d["should_mask"]]),
        "mask_cells": _accuracy([d for _, d in rows if d["should_mask"]]),
        "by_destination": {dest: _accuracy([d for k, d in rows if k == dest])
                           for dest in sorted({k for k, _ in rows})},
        "images": len({r.image_id for r in scored if r.decisions}),
    }


def summarize(records: list[Record]) -> dict:
    scored = [r for r in records if r.error is None]
    out: dict = {
        "image_runs": len(records),
        "errors": {},
        "scored_runs": len(scored),
    }
    for r in records:
        if r.error:
            key = r.error.split(" ")[0]
            out["errors"][key] = out["errors"].get(key, 0) + 1
    if not scored:
        return out
    cats: dict[str, list[int]] = {}
    for r in scored:
        for k, (c, t) in r.by_category.items():
            cats.setdefault(k, [0, 0])
            cats[k][0] += c
            cats[k][1] += t
    lat = [r.latency_ms for r in scored if r.latency_ms is not None]
    hn = [r for r in scored if r.hard_negative_fp is not None]
    out.update({
        "overall": _rate(scored),
        "recall_by_category": {k: {"caught": c, "total": t, "recall": round(c / t, 4)}
                               for k, (c, t) in sorted(cats.items())},
        "recall_by_source": {s: _rate([r for r in scored if r.source == s])
                             for s in sorted({r.source for r in scored})},
        "recall_by_destination": {d: _rate([r for r in scored if r.destination == d])
                                  for d in sorted({r.destination for r in scored})},
        "destination_accuracy": destination_accuracy(scored),
        "mean_over_redaction": round(sum(r.over_redaction for r in scored) / len(scored), 5),
        "hard_negative_false_positives": {"images": len(hn), "with_masks": sum(bool(r.hard_negative_fp) for r in hn)},
        "failed_closed_runs": sum(r.judge_status == "failed_closed" for r in scored),
        "latency_ms": {"p50": metrics.percentile(lat, 50), "p90": metrics.percentile(lat, 90)} if lat else None,
        "cost_usd": {"total": round(sum(r.cost_usd or 0 for r in scored), 4),
                     "per_image_run": round(sum(r.cost_usd or 0 for r in scored) / len(scored), 5)},
    })
    return out


class Pacer:
    """Starts at most `per_min` image runs per minute."""

    def __init__(self, per_min: float):
        self.gap = 60.0 / per_min
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.gap
        if delay:
            await asyncio.sleep(delay)


def load_manifest(path: Path = EVAL / "manifest.jsonl") -> list[ManifestRow]:
    return [ManifestRow.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]


def find_image(data: Path, image_id: str) -> Path | None:
    return next((p for ext in IMAGE_EXTS if (p := data / "images" / f"{image_id}.{ext}").exists()), None)


async def evaluate(
    rows: list[ManifestRow],
    system: System,
    client,
    *,
    data: Path = EVAL / "data",
    labels: Path = EVAL / "labels",
    dilation_px: int,
    pacer: Pacer | None = None,
    concurrency: int = CONCURRENCY,
) -> tuple[list[Record], list[str]]:
    """Runs every labeled destination of every row. Returns records and skipped image ids."""
    sem = asyncio.Semaphore(concurrency)
    pacer = pacer or Pacer(RATE_IMAGES_PER_MIN)
    skipped: list[str] = []
    jobs = []

    async def one(row, label, image_bytes, dest):
        async with sem:
            await pacer.wait()
            try:
                resp = await system(client, image_bytes, dest)
            except Exception as e:  # a crash is a result, not a reason to stop the run
                return Record(row.image_id, row.source, row.split, dest, error=f"crash:{type(e).__name__}")
        return score(row, label, dest, resp, dilation_px)

    for row in rows:
        img, lab = find_image(data, row.image_id), labels / f"{row.image_id}.json"
        if img is None or not lab.exists():
            skipped.append(row.image_id)
            continue
        label = Label.model_validate_json(lab.read_text())
        image_bytes = img.read_bytes()
        for dest in row.destinations_labeled:
            if dest not in label.destinations:
                skipped.append(f"{row.image_id}:{dest}")
                continue
            jobs.append(one(row, label, image_bytes, dest))
    return list(await asyncio.gather(*jobs)), skipped


def git_state() -> tuple[str, bool]:
    def run(*a):
        return subprocess.check_output(["git", *a], text=True).strip()

    try:
        return run("rev-parse", "--short", "HEAD"), bool(run("status", "--porcelain", "--untracked-files=no"))
    except Exception:
        return "unknown", True


def baseline_notes(config: str) -> dict | None:
    """Settings fixed before the first run, recorded with the results."""
    if config == "b2":
        from baselines import b2_presidio

        return {"score_threshold": b2_presidio.SCORE_THRESHOLD}
    if config == "b3":
        from baselines import b3_muse

        return {"prompt_sha256": b3_muse.PROMPT_SHA}
    if config == "b1":
        from baselines import b1_sam

        return {"phrases": list(b1_sam.PHRASES)}
    return None


def config_hash(settings: Settings, no_floor: bool) -> str:
    cfg = {
        "judge_model": settings.judge_model, "effort": settings.judge_reasoning_effort,
        "sam_model": settings.sam_model, "phrases": SWEEP_PHRASES, "dilation": settings.mask_dilation_px,
        "max_edge": settings.max_image_edge_px, "premask": settings.premask,
        "caught_threshold": metrics.CAUGHT_THRESHOLD, "no_floor": no_floor,
        "prompt_sha256": hashlib.sha256(judge_step.load_system_prompt().encode()).hexdigest(),
    }
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]


async def main(args) -> None:
    commit, dirty = git_state()
    if args.split in ("test", "all") and not args.final:
        raise SystemExit("the test split is frozen for the final runs; pass --final")
    if args.final:
        if dirty:
            raise SystemExit("--final needs a clean git tree so the commit hash means something")
        if args.no_floor:
            raise SystemExit("--final cannot run with --no-floor")
    settings = get_settings()
    if args.no_floor:
        from app.pipeline import run as run_module

        run_module.find_floor_hits = lambda candidates: []

    rows = [r for r in load_manifest() if args.split == "all" or r.split == args.split]
    client = MetaClient(settings)
    start = time.perf_counter()
    try:
        records, skipped = await evaluate(rows, CONFIGS[args.config], client,
                                          dilation_px=settings.mask_dilation_px)
    finally:
        await client.close()

    if not records:
        raise SystemExit(f"nothing to score: {len(rows)} manifest rows, skipped {skipped}. "
                         "Add images under eval/data/images/ and labels under eval/labels/.")
    summary = summarize(records)
    meta = {
        "config": args.config, "split": args.split, "commit": commit, "dirty_tree": dirty,
        "floor": "n/a" if args.config != "redact" else "off" if args.no_floor else "on",
        "baseline": baseline_notes(args.config), "prompt_version": judge_step.PROMPT_VERSION,
        "model_ids": settings.model_ids(), "judge_effort": settings.judge_reasoning_effort,
        "config_hash": config_hash(settings, args.no_floor),
        "caught_threshold": metrics.CAUGHT_THRESHOLD, "skipped": skipped,
        "wall_s": round(time.perf_counter() - start, 1),
    }
    folder = EVAL / "results" / f"{datetime.now(timezone.utc):%Y-%m-%d}_{commit}" / args.config
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results.json").write_text(json.dumps({"meta": meta, "summary": summary}, indent=2))
    (folder / "per_image.jsonl").write_text("\n".join(json.dumps(r.__dict__) for r in records) + "\n")
    print(json.dumps({"meta": meta, "summary": summary}, indent=2))
    print(f"wrote {folder}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=sorted(CONFIGS), default="redact")
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--final", action="store_true", help="allow the test split, for frozen final runs")
    ap.add_argument("--no-floor", action="store_true", help="dev only: skip floor rules until they land")
    asyncio.run(main(ap.parse_args()))
