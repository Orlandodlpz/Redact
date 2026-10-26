"""Check eval/SHOT_LIST.md against the plan: 80 rows, 20 bake off (all dev), 30 triple labeled."""

import re
import sys
from pathlib import Path

CATEGORIES = {"credential", "payment", "government_id", "personal_account", "contact_info",
              "home_location", "face", "license_plate", "internal_data", "other_sensitive"}

rows = []
for line in (Path(__file__).parent / "SHOT_LIST.md").read_text().splitlines():
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if re.fullmatch(r"s\d\d", cells[0]) and len(cells) == 5:
        rows.append(cells)

problems = []
ids = [r[0] for r in rows]
if ids != [f"s{i:02d}" for i in range(1, 81)]:
    problems.append(f"expected s01 to s80 in order, got {len(ids)} rows")
flags = [r[4].split() for r in rows]
bake = [r[0] for r, f in zip(rows, flags) if "B" in f]
triple = [r for r, f in zip(rows, flags) if "3" in f]
test = [r[0] for r, f in zip(rows, flags) if "test" in f]
dev = [r[0] for r, f in zip(rows, flags) if "dev" in f]
if len(bake) != 20:
    problems.append(f"{len(bake)} bake off images, want 20")
if any(i in test for i in bake):
    problems.append("a bake off image is in the test split")
if len(triple) != 30:
    problems.append(f"{len(triple)} triple labeled, want 30")
if len(dev) + len(test) != 80:
    problems.append("every row needs exactly one of dev or test")
missing = CATEGORIES - {c.strip() for r in rows for c in r[3].split(",")}
if missing:
    problems.append(f"categories never shot: {sorted(missing)}")

print(f"rows {len(rows)}, dev {len(dev)}, test {len(test)}, bake off {len(bake)}, triple {len(triple)}")
for p in problems:
    print("PROBLEM:", p)
sys.exit(1 if problems else 0)
