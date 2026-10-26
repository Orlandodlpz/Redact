"""Oct 27 judge bake off: muse-spark-1.3 vs 1.2, minimal vs low. Owner: Carlos.

Runs the judge alone (no floor rules, no policy table) on the 20 bake off images
from SHOT_LIST.md, all dev split, and scores it against the labels. Judge only recall
is the right number for this decision: floor rules and policy are the same for every
config, so they cannot change which config wins.

Inputs (all under eval/data/, gitignored):
  images/<id>.jpg|jpeg|png           the staged photo (convert HEIC first)
  fixtures/<id>.candidates.json      list[Candidate], marks already numbered
  fixtures/<id>.marked.png           the numbered overlay the judge sees
Orlando's sweep, OCR and marks steps will write the fixtures. Until they exist,
nobody can run this on real images.
Labels are eval/labels/<id>.json (eval/schemas.py Label).

Pre-registered before the first run, never changed after seeing results:
  Pick the config with the highest total caught items. Configs within TIE_ITEMS
  caught items of the best are tied, and the lowest p50 latency wins the tie.

Usage:
  uv run python eval/bakeoff.py --repeats 2
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

import metrics
from check_shot_list import parse_rows
from schemas import Label
from app.config import Settings
from app.pipeline import judge as J
from app.providers.meta_api import MetaClient
from app.schemas import Candidate, Finding

MODELS = ("muse-spark-1.3", "muse-spark-1.2")
EFFORTS = ("minimal", "low")
TIE_ITEMS = 2  # proposal, team confirms before the run
CONCURRENCY = 4  # judge calls in flight; same as the smoke test
DATA = Path(__file__).parent / "data"
LABELS = Path(__file__).parent / "labels"
RESULTS = Path(__file__).parent / "results"


def judge_findings(result: J.JudgeResult, candidates: list[Candidate]) -> list[Finding]:
    """What the judge alone would mask, as Findings with the candidate's box.
    Candidate boxes stand in for SAM masks; extra findings use the judge's own box."""
    if result.output is None:
        return []
    by_mark = {c.mark: c for c in candidates}
    out: list[Finding] = []

    def add(source, marks, category, reason, box):
        out.append(Finding(id=f"f_{len(out):02d}", marks=marks, category=category, reason=reason,
                           source=source, masked=True, locked=False, box=box))

    for v in result.output.verdicts:
        if v.sensitive and v.category != "benign":
            add("judge", [v.mark], v.category, v.reason, by_mark[v.mark].box)
    for leak in result.output.combined_leaks:
        for m in leak.marks:
            add("combined", leak.marks, leak.category, leak.reason, by_mark[m].box)
    for e in result.output.extra_findings:
        add("extra", [], e.category, e.reason, e.box)
    return out


@dataclass
class Run:
    image_id: str
    destination: str
    repeat: int
    ok: bool
    latency_ms: int
    cost_usd: float
    caught: int
    total: int
    by_category: dict[str, tuple[int, int]]
    over_redaction: float
    unjudged: int
    dropped: dict[str, int]
    attempts: int


def score(image_id, destination, repeat, result, candidates, label) -> Run:
    truth = label.destinations[destination]
    predicted = judge_findings(result, candidates)
    by_cat = metrics.recall_by_category(truth, predicted)
    return Run(
        image_id, destination, repeat, result.output is not None,
        sum(a.latency_ms for a in result.attempts),
        sum(a.est_cost_usd or 0.0 for a in result.attempts),
        sum(c for c, _ in by_cat.values()), sum(t for _, t in by_cat.values()), by_cat,
        metrics.over_redaction(truth, predicted, label.width, label.height),
        len(result.unjudged), result.dropped, len(result.attempts),
    )


def summarize(runs: list[Run]) -> dict:
    lat = [r.latency_ms for r in runs]
    # A failed judge output counts as zero caught but its items stay in the total.
    caught, total = sum(r.caught for r in runs), sum(r.total for r in runs)
    cats: dict[str, list[int]] = {}
    for r in runs:
        for k, (c, t) in r.by_category.items():
            cats.setdefault(k, [0, 0])
            cats[k][0] += c
            cats[k][1] += t
    return {
        "runs": len(runs),
        "failed_runs": sum(not r.ok for r in runs),
        "caught": caught,
        "total": total,
        "recall": round(caught / total, 4) if total else None,
        "recall_by_category": {k: f"{c}/{t}" for k, (c, t) in sorted(cats.items())},
        "mean_over_redaction": round(sum(r.over_redaction for r in runs) / len(runs), 5),
        "p50_ms": metrics.percentile(lat, 50),
        "p90_ms": metrics.percentile(lat, 90),
        "cost_usd": round(sum(r.cost_usd for r in runs), 4),
        "unjudged_marks": sum(r.unjudged for r in runs),
        "retries_used": sum(r.attempts > 1 for r in runs),
    }


def pick(summaries: dict[str, dict]) -> str:
    """Highest caught, ties within TIE_ITEMS broken by lowest p50."""
    best = max(s["caught"] for s in summaries.values())
    tied = {k: s for k, s in summaries.items() if best - s["caught"] <= TIE_ITEMS}
    return min(tied, key=lambda k: (tied[k]["p50_ms"], -tied[k]["caught"]))


def find_image(image_id: str) -> Image.Image:
    for ext in ("jpg", "jpeg", "png"):
        p = DATA / "images" / f"{image_id}.{ext}"
        if p.exists():
            return Image.open(p).convert("RGB")
    raise FileNotFoundError(f"no image for {image_id} under {DATA / 'images'}")


def load_case(image_id: str):
    image = find_image(image_id)
    marked = Image.open(DATA / "fixtures" / f"{image_id}.marked.png").convert("RGB")
    raw = json.loads((DATA / "fixtures" / f"{image_id}.candidates.json").read_text())
    candidates = [Candidate.model_validate(c) for c in raw]
    label = Label.model_validate_json((LABELS / f"{image_id}.json").read_text())
    return image, marked, candidates, label


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


async def main(repeats: int, ids: list[str] | None) -> None:
    rows = parse_rows()
    allowed = {r["id"] for r in rows if r["bake_off"]}
    ids = ids or sorted(allowed)
    if not set(ids) <= allowed:
        raise SystemExit(f"not bake off dev images: {sorted(set(ids) - allowed)}")
    cases = {i: load_case(i) for i in ids}

    settings = Settings()
    client = MetaClient(settings)
    sem = asyncio.Semaphore(CONCURRENCY)
    configs = [(m, e) for m in MODELS for e in EFFORTS]

    async def one(model, effort, image_id, dest, rep):
        image, marked, candidates, label = cases[image_id]
        async with sem:
            result = await J.ajudge(image, marked, candidates, dest, client=client, settings=settings,
                                    model=model, reasoning_effort=effort,
                                    run="bakeoff", img=image_id, dest=dest, rep=rep)
        return score(image_id, dest, rep, result, candidates, label)

    start = time.perf_counter()
    jobs = {
        (m, e): [one(m, e, i, d, r) for i in ids for d in cases[i][3].destinations for r in range(repeats)]
        for m, e in configs
    }
    print(f"{sum(len(j) for j in jobs.values())} judge calls ...", flush=True)
    done = {k: await asyncio.gather(*v) for k, v in jobs.items()}
    await client.close()

    summaries = {f"{m} @ {e}": summarize(runs) for (m, e), runs in done.items()}
    winner = pick(summaries)
    prompt = J.load_system_prompt()
    config = {"models": MODELS, "efforts": EFFORTS, "repeats": repeats, "tie_items": TIE_ITEMS, "ids": ids}
    out = {
        "commit": git_commit(),
        "prompt_version": J.PROMPT_VERSION,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()[:12],
        "config_hash": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12],
        "config": config,
        "summaries": summaries,
        "winner": winner,
        "wall_s": round(time.perf_counter() - start, 1),
        "runs": {f"{m} @ {e}": [r.__dict__ for r in runs] for (m, e), runs in done.items()},
    }
    folder = RESULTS / f"{datetime.now(timezone.utc):%Y-%m-%d}_{out['commit']}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bakeoff.json").write_text(json.dumps(out, indent=2))

    for k, s in summaries.items():
        print(f"{k:24} recall {s['caught']}/{s['total']}  p50 {s['p50_ms']} ms  p90 {s['p90_ms']} ms  "
              f"${s['cost_usd']}  failed {s['failed_runs']}")
    print(f"winner by the pre-registered rule: {winner}\nwrote {folder / 'bakeoff.json'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--ids", help="comma separated subset of the bake off ids, for a trial run")
    a = ap.parse_args()
    asyncio.run(main(a.repeats, a.ids.split(",") if a.ids else None))
