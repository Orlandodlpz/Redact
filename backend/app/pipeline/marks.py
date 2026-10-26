"""Render the numbered overlay image the judge sees. Owner: Orlando. Phase 2."""

from PIL import Image

from app.schemas import Candidate


def render(image: Image.Image, candidates: list[Candidate]) -> Image.Image:
    raise NotImplementedError
