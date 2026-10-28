"""Mask union, dilation, solid fill, flatten, re-encode with zero metadata. Owner: Orlando.

Solid fill only: blur and pixelation can be reversed on text (gotcha 10). The PNG is
built from raw pixels, so no EXIF, XMP, ICC or text chunk can ride along (gotcha 11).
"""

import io

import numpy as np
from PIL import Image

from app.config import get_settings
from app.pipeline.sweep import decode_rle
from app.schemas import Finding

FILL = (0, 0, 0)


def compose(image: Image.Image, findings: list[Finding]) -> bytes:
    """Returns PNG bytes. Every finding with masked=True is filled; a finding
    without mask_rle fills its box. Metadata findings have nothing to draw."""
    mask = union_mask(image.width, image.height, findings)
    mask = dilate(mask, get_settings().mask_dilation_px)

    pixels = np.array(image.convert("RGB"))
    pixels[mask] = FILL
    clean = Image.frombytes("RGB", (image.width, image.height), pixels.tobytes())
    buf = io.BytesIO()
    clean.save(buf, format="PNG")
    return buf.getvalue()


def union_mask(width: int, height: int, findings: list[Finding]) -> np.ndarray:
    """(height, width) bool array of every masked finding."""
    mask = np.zeros((height, width), dtype=bool)
    for f in findings:
        if not f.masked or f.box is None:
            continue
        if f.mask_rle:
            mask |= decode_rle(f.mask_rle, width, height).astype(bool)
        else:
            x1, y1, x2, y2 = f.box
            mask[y1:y2, x1:x2] = True
    return mask


def dilate(mask: np.ndarray, px: int) -> np.ndarray:
    """Grow the mask by px in every direction (square kernel), so edge pixels and
    antialiased stroke ends get covered. Separable: rows, then columns."""
    if px <= 0:
        return mask
    out = mask.copy()
    for shift in range(1, px + 1):
        out[:, shift:] |= mask[:, :-shift]
        out[:, :-shift] |= mask[:, shift:]
    rows = out.copy()
    for shift in range(1, px + 1):
        out[shift:, :] |= rows[:-shift, :]
        out[:-shift, :] |= rows[shift:, :]
    return out
