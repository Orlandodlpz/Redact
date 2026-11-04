"""Why did a labeled item go uncaught? Owner: Carlos.

Reads a finished run (eval/results/<run>/<config>/per_image.jsonl) and sorts every miss by
cause, using the labels and the candidate fixtures. No API calls, no image bytes.

Causes, in order (the first that applies):
  candidate_gap    no judge could catch it: the union of every candidate covers < 90% of its box
  pixel_rule_only  the masked findings' boxes cover it but the pixel mask does not (gotcha 51)
  partial          reachable, box union covers 50 to 90%: right region, mask too small or split
  kept_by_system   reachable, under 50%, and a finding that was left unmasked covers it
                   (the judge or the policy table chose to keep it)
  not_flagged      reachable, under 50%, nothing covers it: the judge did not mark it sensitive

Usage: uv run python eval/error_analysis.py eval/results/2026-11-04_879bdcf redact
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import metrics
from schemas import Label

EVAL = Path(__file__).parent
CAUSES = ("candidate_gap", "pixel_rule_only", "partial", "kept_by_system", "not_flagged")


def classify(item_box, cands, masked_boxes, kept_boxes) -> tuple[str, float]:
    """(cause, box union coverage) for an item the box union did not catch."""
    cov = metrics.coverage(item_box, masked_boxes)
    if metrics.coverage(item_box, cands) < metrics.CAUGHT_THRESHOLD:
        return "candidate_gap", cov
    if cov >= 0.5:
        return "partial", cov
    if metrics.coverage(item_box, kept_boxes) >= 0.5:
        return "kept_by_system", cov
    return "not_flagged", cov


def analyze(run_dir: Path, config: str) -> tuple[list[dict], Counter]:
    """(box misses with a cause, pixel rule only counts by category).

    The run stores pixel counts per category, not per item, so pixel_rule_only is a count:
    every item the box union misses is also missed by the pixel mask (the mask lies inside
    the boxes), so pixel misses minus box misses in a group are items only the pixel rule lost.
    """
    rows = [json.loads(l) for l in (run_dir / config / "per_image.jsonl").read_text().splitlines() if l]
    misses: list[dict] = []
    pixel_only: Counter = Counter()
    for r in rows:
        if r.get("error"):
            continue
        label = Label.model_validate_json((EVAL / "labels" / f"{r['image_id']}.json").read_text())
        cands = [c["box"] for c in json.loads(
            (EVAL / "data" / "fixtures" / f"{r['image_id']}.candidates.json").read_text())]
        masked = [f["box"] for f in r["findings"] if f["masked"] and f["box"]]
        kept = [f["box"] for f in r["findings"] if not f["masked"] and f["box"]]
        box_missed: dict[str, int] = Counter()
        for t in label.destinations[r["destination"]]:
            if metrics.coverage(t.box, masked) >= metrics.CAUGHT_THRESHOLD:
                continue
            cause, cov = classify(t.box, cands, masked, kept)
            box_missed[t.category] += 1
            misses.append({"image_id": r["image_id"], "destination": r["destination"],
                           "category": t.category, "box": t.box, "cause": cause, "box_coverage": round(cov, 2)})
        for cat, (caught, total) in r["by_category"].items():
            extra = (total - caught) - box_missed.get(cat, 0)
            if extra > 0:
                pixel_only[cat] += extra
    return misses, pixel_only


def main(run_dir: Path, config: str) -> None:
    misses, pixel_only = analyze(run_dir, config)
    by_cause = Counter(m["cause"] for m in misses)
    by_cause["pixel_rule_only"] = sum(pixel_only.values())
    print(f"{config}: {sum(by_cause.values())} missed (image, destination, item) rows")
    for c in CAUSES:
        print(f"  {c:16} {by_cause.get(c, 0)}")
    cat = defaultdict(Counter)
    for m in misses:
        cat[m["category"]][m["cause"]] += 1
    for k, n in pixel_only.items():
        cat[k]["pixel_rule_only"] += n
    print("by category:")
    for k, v in sorted(cat.items()):
        print(f"  {k:17}", dict(v))
    reachable = [m for m in misses if m["cause"] in ("kept_by_system", "not_flagged", "partial")]
    items: dict[tuple, dict] = {}
    for m in reachable:  # one row per labeled item, with every destination it was missed at
        it = items.setdefault((m["image_id"], tuple(m["box"]), m["category"]), {**m, "destinations": []})
        it["destinations"].append(m["destination"])
        it["box_coverage"] = min(it["box_coverage"], m["box_coverage"])
    worst = sorted(items.values(), key=lambda m: (m["box_coverage"], -len(m["destinations"]), m["image_id"]))
    print(f"10 worst of {len(worst)} distinct reachable items (judge or policy, lowest coverage first):")
    for m in worst[:10]:
        print(f"  {m['image_id']} {m['category']:16} coverage {m['box_coverage']:.2f}  {m['cause']:14} missed at {','.join(m['destinations'])}")
    (run_dir / config / "error_analysis.json").write_text(
        json.dumps({"misses": misses, "pixel_rule_only_by_category": dict(pixel_only)}, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
