"""Which labeled items could ANY judge catch, given the candidates the pipeline found?
Owner: Carlos.

For each labeled item, coverage of its box by the union of every candidate box (an
oracle that masks everything it found). Below the caught threshold means the item is
unreachable: a loose label or a candidate gap, not a judge decision. Run this on every
new label set before reading a recall number (docs/CLAUDE.md gotcha 41).

Needs eval/data/fixtures from make_fixtures.py. No API calls.

Usage: uv run python eval/oracle_check.py
"""

import json
from pathlib import Path

import metrics
from schemas import Label

EVAL = Path(__file__).parent


def main() -> None:
    rows = []
    for p in sorted((EVAL / "labels").glob("*.json")):
        fx = EVAL / "data" / "fixtures" / f"{p.stem}.candidates.json"
        if not fx.exists():
            print(f"{p.stem}: no fixtures, skipped")
            continue
        boxes = [c["box"] for c in json.loads(fx.read_text())]
        seen = set()
        for fs in Label.model_validate_json(p.read_text()).destinations.values():
            for f in fs:
                if (key := (tuple(f.box), f.category)) not in seen:
                    seen.add(key)
                    rows.append((p.stem, f.category, f.box, metrics.coverage(f.box, boxes)))
    bad = [r for r in rows if r[3] < metrics.CAUGHT_THRESHOLD]
    print(f"{len(rows)} distinct labeled items, {len(rows) - len(bad)} reachable, {len(bad)} unreachable")
    for iid, cat, box, cov in bad:
        print(f"  {iid} {cat:16} oracle coverage {cov:.2f}  box {box}")


if __name__ == "__main__":
    main()
