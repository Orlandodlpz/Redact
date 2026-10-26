"""SAM 3.1 concept sweep over the Meta Model API. Owner: Orlando. Phase 2."""

from PIL import Image

from app.schemas import Candidate


def sweep(image: Image.Image) -> list[Candidate]:
    raise NotImplementedError
