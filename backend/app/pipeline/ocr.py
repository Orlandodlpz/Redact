"""Text line boxes with text, from RapidOCR running locally. Owner: Orlando.

Nothing here touches the network. Pass ingest's ocr_image with scale=ocr_scale and
bounds=(width, height) to get boxes in working image coordinates.
"""

import logging
import math
from functools import lru_cache

import numpy as np
from PIL import Image
from rapidocr import RapidOCR

from app.config import OCR_ENGINE_PARAMS
from app.schemas import Candidate

@lru_cache(maxsize=1)
def _engine() -> RapidOCR:
    # Loading the ONNX models takes about a second, so build once per process.
    engine = RapidOCR(params=dict(OCR_ENGINE_PARAMS))
    # RapidOCR sets its own logger to INFO while building, and warns on every image
    # without text. Quiet it afterwards.
    logging.getLogger("RapidOCR").setLevel(logging.ERROR)
    return engine


def ocr(
    image: Image.Image,
    *,
    scale: float = 1.0,
    bounds: tuple[int, int] | None = None,
) -> list[Candidate]:
    """One candidate per text line, in the engine's reading order.

    RapidOCR returns rotated four point boxes. Each becomes the axis aligned box
    around it, which over-covers angled text a little; for masking that's the safe
    direction. bounds is the (width, height) boxes get clamped to after scaling.
    """
    result = _engine()(np.asarray(image.convert("RGB")))
    if result.boxes is None or not result.txts:
        return []
    width, height = bounds or (round(image.width * scale), round(image.height * scale))

    candidates = []
    for quad, text, score in zip(result.boxes, result.txts, result.scores):
        text = text.strip()
        box = _box(quad, scale, width, height)
        if not text or box is None:
            continue
        candidates.append(Candidate(source="ocr", text=text, box=box, score=round(float(score), 4)))
    return candidates


def _box(quad, scale: float, width: int, height: int) -> list[int] | None:
    """Axis aligned, half-open, scaled and clamped. None if nothing is left."""
    xs = [float(p[0]) * scale for p in quad]
    ys = [float(p[1]) * scale for p in quad]
    x1, y1 = max(0, math.floor(min(xs))), max(0, math.floor(min(ys)))
    x2, y2 = min(width, math.ceil(max(xs))), min(height, math.ceil(max(ys)))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]
