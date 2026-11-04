"""B2: Microsoft Presidio over our OCR text. Owner: Carlos.

What a text only PII tool gets on photographs. Our local OCR (RapidOCR) reads the lines,
Presidio flags a line, and the whole line box is masked, the same as the floor rules do.
It sees no faces, plates or scene, and costs no API calls.

Pre-registered, not tuned: default recognizers, English, SCORE_THRESHOLD below. The
threshold is a proposal and is fixed before the first run.

Not a project dependency (pyproject.toml is shared, so adding one needs the team). If the
import fails the baseline raises, and run_eval records a crash for every image.
"""

import asyncio
import time

from baselines.common import finding, response
from app.pipeline.ingest import ingest
from app.pipeline.ocr import ocr

SCORE_THRESHOLD = 0.4
CATEGORY = {
    "CREDIT_CARD": "payment", "IBAN_CODE": "payment", "CRYPTO": "payment",
    "US_SSN": "government_id", "US_PASSPORT": "government_id", "US_DRIVER_LICENSE": "government_id",
    "US_ITIN": "government_id", "UK_NHS": "government_id", "MEDICAL_LICENSE": "other_sensitive",
    "EMAIL_ADDRESS": "contact_info", "PHONE_NUMBER": "contact_info", "PERSON": "personal_account",
    "LOCATION": "home_location", "IP_ADDRESS": "other_sensitive", "URL": "other_sensitive",
    "DATE_TIME": "other_sensitive", "NRP": "other_sensitive",
}

_engine = None


def analyzer():
    global _engine
    if _engine is None:
        try:
            from presidio_analyzer import AnalyzerEngine
        except ImportError as e:
            raise RuntimeError("B2 needs presidio-analyzer and a spaCy English model; see baselines/b2_presidio.py") from e
        _engine = AnalyzerEngine()
    return _engine


def flag_lines(lines, engine, threshold: float = SCORE_THRESHOLD):
    """(line, category) for each OCR line the engine flags. The best scoring entity names the category."""
    out = []
    for c in lines:
        hits = [h for h in engine.analyze(text=c.text or "", language="en") if h.score >= threshold]
        if hits:
            best = max(hits, key=lambda h: h.score)
            out.append((c, CATEGORY.get(best.entity_type, "other_sensitive")))
    return out


async def run(client, image_bytes, destination):
    started = time.perf_counter()
    r = await asyncio.to_thread(ingest, image_bytes)
    lines = await asyncio.to_thread(ocr, r.ocr_image, scale=r.ocr_scale, bounds=(r.width, r.height))
    engine = analyzer()
    flagged = await asyncio.to_thread(flag_lines, lines, engine)
    findings = [finding(n, cat, c.box) for n, (c, cat) in enumerate(flagged, 1)]
    return response(r, destination, findings, started, version="b2")
