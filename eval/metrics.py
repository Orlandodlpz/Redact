"""Eval metrics. Owner: Carlos.

Definitions here are fixed before the first full run and never changed after
seeing results (docs/CLAUDE.md, Provisional Values). Change one only with a
recorded team decision made before a run.

Two families: box functions (baselines that only produce boxes) and pixel functions
(`*_px`, used for Redact, scoring the same dilated union mask that compose fills).
"""

import math
from collections import defaultdict
from collections.abc import Sequence

import numpy as np

from app.schemas import Finding

Box = Sequence[int]

# An item is caught if the final masks cover at least this share of its labeled box.
CAUGHT_THRESHOLD = 0.90


def _area(box: Box) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def union_area(boxes: Sequence[Box]) -> int:
    """Exact area of a union of boxes by coordinate compression."""
    boxes = [b for b in boxes if _area(b) > 0]
    if not boxes:
        return 0
    xs = sorted({v for b in boxes for v in (b[0], b[2])})
    total = 0
    for x1, x2 in zip(xs, xs[1:]):
        spans = sorted((b[1], b[3]) for b in boxes if b[0] <= x1 and b[2] >= x2)
        covered, end = 0, None
        start = None
        for y1, y2 in spans:
            if end is None or y1 > end:
                if end is not None:
                    covered += end - start
                start, end = y1, y2
            else:
                end = max(end, y2)
        if end is not None:
            covered += end - start
        total += covered * (x2 - x1)
    return total


def _intersect(a: Box, b: Box) -> list[int]:
    return [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]


def coverage(item: Box, masks: Sequence[Box]) -> float:
    """Share of the item's box area covered by the union of masks."""
    item_area = _area(item)
    if item_area == 0:
        return 0.0
    clipped = [_intersect(item, m) for m in masks]
    return union_area(clipped) / item_area


def is_caught(item: Box, masks: Sequence[Box]) -> bool:
    return coverage(item, masks) >= CAUGHT_THRESHOLD


def masked_boxes(findings: Sequence[Finding]) -> list[list[int]]:
    return [f.box for f in findings if f.masked and f.box is not None]


def recall_by_category(
    truth: Sequence[Finding], predicted: Sequence[Finding]
) -> dict[str, tuple[int, int]]:
    """category -> (caught, total) over labeled items. Metadata findings are skipped."""
    masks = masked_boxes(predicted)
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for t in truth:
        if t.box is None:
            continue
        out[t.category][1] += 1
        out[t.category][0] += is_caught(t.box, masks)
    return {k: (v[0], v[1]) for k, v in out.items()}


def over_redaction(truth: Sequence[Finding], predicted: Sequence[Finding], width: int, height: int) -> float:
    """Share of image area masked outside every labeled item box.
    Proposed definition, team to confirm before the first full run."""
    masks = masked_boxes(predicted)
    total = union_area(masks)
    if total == 0:
        return 0.0
    inside = union_area([_intersect(m, t.box) for m in masks for t in truth if t.box])
    return (total - inside) / (width * height)


def hard_negative_false_positive(predicted: Sequence[Finding]) -> bool:
    """On a hard negative image any mask is a false positive."""
    return any(f.masked and f.box is not None for f in predicted)


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest rank percentile, p in 0..100."""
    if not values:
        raise ValueError("no values")
    s = sorted(values)
    k = max(0, min(len(s) - 1, math.ceil(p / 100 * len(s)) - 1))
    return s[k]


# Pixel versions. The eval scores the same mask compose fills (union of masked findings,
# dilated), so it measures what a user downloads rather than the findings' boxes.


def mask_coverage(item: Box, mask: "np.ndarray") -> float:
    """Share of the item's box area that the boolean (height, width) mask covers."""
    x1, y1, x2, y2 = item
    h, w = mask.shape
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
    if _area(item) == 0 or x2 <= x1 or y2 <= y1:
        return 0.0
    return float(mask[y1:y2, x1:x2].sum()) / _area(item)


def recall_by_category_px(truth: Sequence[Finding], mask: "np.ndarray") -> dict[str, tuple[int, int]]:
    """category -> (caught, total). Metadata findings are skipped."""
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for t in truth:
        if t.box is None:
            continue
        out[t.category][1] += 1
        out[t.category][0] += mask_coverage(t.box, mask) >= CAUGHT_THRESHOLD
    return {k: (v[0], v[1]) for k, v in out.items()}


def over_redaction_px(truth: Sequence[Finding], mask: "np.ndarray") -> float:
    """Share of image pixels masked outside every labeled item box."""
    h, w = mask.shape
    labeled = np.zeros_like(mask)
    for t in truth:
        if t.box is not None:
            x1, y1, x2, y2 = t.box
            labeled[max(0, y1):min(h, y2), max(0, x1):min(w, x2)] = True
    return float((mask & ~labeled).sum()) / (w * h)
