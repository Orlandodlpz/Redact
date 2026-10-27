"""SAM 3.1 concept sweep over the Meta Model API. Owner: Orlando.

One request per phrase, all in parallel: batched phrases lose their labels (gotcha 23).
SAM returns each mask cropped to its box at lower resolution (gotcha 22), so every
mask is scaled to its box, pasted into a canvas the size of the image, and stored
as COCO RLE counts for the full image.
"""

import asyncio

import numpy as np
from meta_sam_parser import decode_mask_to_raster
from PIL import Image
from pycocotools import mask as mask_utils

from app.config import SWEEP_PHRASES
from app.providers.meta_api import MetaClient, SamMatch, image_data_url
from app.schemas import Candidate

RETRY_DELAY_S = 0.5


class SweepError(RuntimeError):
    """A phrase failed twice. The image wasn't fully scanned, so it must not come
    back looking clean; run.py turns this into an error, not fewer masks."""

    def __init__(self, phrases: list[str]):
        self.phrases = phrases
        super().__init__("SAM sweep failed for: " + ", ".join(phrases))


async def sweep(
    image: Image.Image,
    client: MetaClient,
    *,
    phrases: tuple[str, ...] = SWEEP_PHRASES,
    **meta,
) -> list[Candidate]:
    """SAM candidates for every phrase, in phrase order. meta labels the cost log rows."""
    url = image_data_url(image)  # encode once, not once per phrase
    found = await asyncio.gather(*[
        _phrase(client, url, phrase, image.width, image.height, meta) for phrase in phrases
    ])
    failed = [phrase for phrase, cands in zip(phrases, found) if cands is None]
    if failed:
        raise SweepError(failed)
    return [c for cands in found for c in cands]


async def _phrase(
    client: MetaClient, url: str, phrase: str, width: int, height: int, meta: dict
) -> list[Candidate] | None:
    """None if both attempts failed. The client never retries on its own."""
    for attempt in range(2):
        if attempt:
            await asyncio.sleep(RETRY_DELAY_S)
        result = await client.sam(url, phrase, step="sweep", phrase=phrase, attempt=attempt, **meta)
        if result.stats.ok:
            return [c for m in result.matches if (c := _candidate(m, phrase, width, height))]
    return None


def _candidate(match: SamMatch, label: str, width: int, height: int) -> Candidate | None:
    x1, y1, x2, y2 = match.box
    box = [max(0, x1), max(0, y1), min(width, x2), min(height, y2)]
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    full = _full_mask(match, width, height)
    # An empty mask would fill nothing; leaving mask_rle unset makes compose fill
    # the box instead, which errs toward masking.
    rle = encode_rle(full) if full.any() else None
    score = round(match.confidence, 4) if match.confidence is not None else None
    return Candidate(source="sam", sam_label=label, box=box, mask_rle=rle, score=score)


def _full_mask(match: SamMatch, width: int, height: int) -> np.ndarray:
    """The match's mask on a (height, width) canvas of 0 and 1."""
    x1, y1, x2, y2 = match.box
    raw = np.frombuffer(decode_mask_to_raster(match.mask), dtype=np.uint8)
    small = Image.fromarray((raw.reshape(match.mask.height, match.mask.width) > 0).astype(np.uint8) * 255)
    scaled = np.asarray(small.resize((x2 - x1, y2 - y1), Image.Resampling.BILINEAR)) >= 128

    full = np.zeros((height, width), dtype=np.uint8)
    # Keep only the part of the box inside the image.
    cx1, cy1, cx2, cy2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
    full[cy1:cy2, cx1:cx2] = scaled[cy1 - y1:cy2 - y1, cx1 - x1:cx2 - x1]
    return full


def encode_rle(mask: np.ndarray) -> str:
    """COCO compressed RLE counts for a (height, width) 0/1 mask. The size is the
    image's, so only counts are stored; decode with decode_rle(counts, w, h)."""
    return mask_utils.encode(np.asfortranarray(mask, dtype=np.uint8))["counts"].decode("ascii")


def decode_rle(counts: str, width: int, height: int) -> np.ndarray:
    return mask_utils.decode({"size": [height, width], "counts": counts.encode("ascii")})
