"""Word and line boxes with text. Owner: Orlando. Phase 2."""

from PIL import Image

from app.schemas import Candidate


def ocr(image: Image.Image) -> list[Candidate]:
    raise NotImplementedError
