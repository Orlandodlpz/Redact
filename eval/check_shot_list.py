"""Parse eval/SHOT_LIST.md and check it against the plan: 80 rows, 20 bake off
(all dev), 30 triple labeled. Other eval scripts import parse_rows from here."""

import re
import sys
from pathlib import Path

SHOT_LIST = Path(__file__).parent / "SHOT_LIST.md"

CATEGORIES = {"credential", "payment", "government_id", "personal_account", "contact_info",
              "home_location", "face", "license_plate", "internal_data", "other_sensitive"}


def parse_rows(path: Path = SHOT_LIST) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if re.fullmatch(r"s\d\d", cells[0]) and len(cells) == 5:
            flags = cells[4].split()
            rows.append({
                "id": cells[0],
                "categories": [c.strip() for c in cells[3].split(",")],
                "bake_off": "B" in flags,
                "triple": "3" in flags,
                "split": "test" if "test" in flags else "dev" if "dev" in flags else None,
            })
    return rows


def check(rows: list[dict]) -> list[str]:
    problems = []
    if [r["id"] for r in rows] != [f"s{i:02d}" for i in range(1, 81)]:
        problems.append(f"expected s01 to s80 in order, got {len(rows)} rows")
    bake = [r for r in rows if r["bake_off"]]
    if len(bake) != 20:
        problems.append(f"{len(bake)} bake off images, want 20")
    if any(r["split"] != "dev" for r in bake):
        problems.append("a bake off image is not in the dev split")
    triple = [r for r in rows if r["triple"]]
    if len(triple) != 30:
        problems.append(f"{len(triple)} triple labeled, want 30")
    if any(r["split"] is None for r in rows):
        problems.append("every row needs exactly one of dev or test")
    missing = CATEGORIES - {c for r in rows for c in r["categories"]}
    if missing:
        problems.append(f"categories never shot: {sorted(missing)}")
    return problems


if __name__ == "__main__":
    rows = parse_rows()
    problems = check(rows)
    count = lambda key: sum(bool(r[key]) for r in rows)  # noqa: E731
    print(f"rows {len(rows)}, dev {sum(r['split'] == 'dev' for r in rows)}, "
          f"test {sum(r['split'] == 'test' for r in rows)}, bake off {count('bake_off')}, triple {count('triple')}")
    for p in problems:
        print("PROBLEM:", p)
    sys.exit(1 if problems else 0)
