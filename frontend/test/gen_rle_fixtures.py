"""Regenerate frontend/test/rle.fixtures.json from the encoder the backend uses.

Run from the repo root: uv run python frontend/test/gen_rle_fixtures.py

The browser decoder in lib/rle.ts is checked against pycocotools' own output rather
than against itself, so a change to either side shows up as a failing test.
"""

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
from app.pipeline.sweep import encode_rle  # noqa: E402

OUT = pathlib.Path(__file__).with_name("rle.fixtures.json")


def main() -> None:
    rng = np.random.default_rng(7)
    cases: list[dict] = []

    def add(name: str, mask: np.ndarray) -> None:
        h, w = mask.shape
        cases.append({
            "name": name, "width": int(w), "height": int(h),
            "counts": encode_rle(mask),
            "rows": [[int(v) for v in row] for row in mask],
        })

    m = np.zeros((6, 9), dtype=np.uint8); m[1:4, 2:7] = 1; add("rectangle", m)
    add("empty", np.zeros((5, 5), dtype=np.uint8))
    add("full", np.ones((4, 7), dtype=np.uint8))
    m = np.zeros((7, 5), dtype=np.uint8); m[0, 0] = 1; m[6, 4] = 1; add("corners", m)
    add("speckle", (rng.random((23, 31)) > 0.6).astype(np.uint8))
    y, x = np.ogrid[:40, :57]
    add("disc", (((y - 20) ** 2 + (x - 28) ** 2) < 150).astype(np.uint8))
    m = np.zeros((60, 3), dtype=np.uint8); m[:, 1] = 1; add("tall_stripe", m)

    OUT.write_text(json.dumps(cases))
    print(f"wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
