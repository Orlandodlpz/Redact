"""Merge sweep and OCR candidates, IoU dedupe, assign mark numbers. Owner: Orlando.

Only SAM candidates are deduped, against each other: two phrases often hit the same
object (one screen as "computer monitor" and "laptop screen"). OCR lines are never
merged into SAM regions, because the password line on a sticky note is what the
judge decides on, separately from the note.
"""

from app.config import CANDIDATE_DEDUPE_IOU, HIGH_RISK_SAM_CLASSES
from app.schemas import Candidate


def build(sam: list[Candidate], ocr: list[Candidate]) -> list[Candidate]:
    """Deduped candidates numbered 1..n in reading order (top, then left). Inputs aren't changed."""
    ordered = sorted(_dedupe(sam) + list(ocr), key=lambda c: (c.box[1], c.box[0]))
    return [c.model_copy(update={"mark": n}) for n, c in enumerate(ordered, start=1)]


def _dedupe(sam: list[Candidate]) -> list[Candidate]:
    # Best first, so a duplicate always loses to the candidate already kept.
    kept: list[Candidate] = []
    for c in sorted(sam, key=_rank, reverse=True):
        if all(box_iou(c.box, k.box) < CANDIDATE_DEDUPE_IOU for k in kept):
            kept.append(c)
    return kept


def _rank(c: Candidate) -> tuple[bool, float]:
    # A fail closed label beats street sign, so a duplicate never lowers what
    # fail closed masks; then the more confident match wins.
    return c.sam_label in HIGH_RISK_SAM_CLASSES, c.score if c.score is not None else 0.0


def box_iou(a: list[int], b: list[int]) -> float:
    """IoU of two half-open boxes."""
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union
