"""B1: SAM 3.1 for faces and license plates only, masked as found. Owner: Carlos.

What a team gets from a single off the shelf segmenter and no reading of text at all.
Two sweep requests per image, no OCR, no judge, no floor rules.
"""

import asyncio
import time

from baselines.common import Tally, finding, response
from app.pipeline.ingest import ingest
from app.pipeline.sweep import sweep

PHRASES = ("face", "license plate")
CATEGORY = {"face": "face", "license plate": "license_plate"}


async def run(client, image_bytes, destination):
    started = time.perf_counter()
    r = await asyncio.to_thread(ingest, image_bytes)
    tally = Tally(client)
    cands = await sweep(r.image, tally, phrases=PHRASES, run="b1")
    findings = [finding(n, CATEGORY[c.sam_label], c.box, c.mask_rle) for n, c in enumerate(cands, 1)]
    return response(r, destination, findings, started, cost=tally.cost, models={"sam": "sam-3.1"}, version="b1")
