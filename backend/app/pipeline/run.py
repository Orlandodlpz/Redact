"""Calls every pipeline step in order. Owner: Orlando. Phase 2.

Order must allow OCR and the text floor rules to run before the sweep,
because Tier 2 pre-masking fills those pixels before any Meta API call.
"""

from app.schemas import AnalyzeResponse, Destination


def analyze(image_bytes: bytes, destination: Destination) -> AnalyzeResponse:
    raise NotImplementedError
