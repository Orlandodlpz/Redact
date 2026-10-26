"""Merge sweep and OCR candidates, IoU dedupe, assign mark numbers. Owner: Orlando. Phase 2."""

from app.schemas import Candidate


def build(sam: list[Candidate], ocr: list[Candidate]) -> list[Candidate]:
    raise NotImplementedError
