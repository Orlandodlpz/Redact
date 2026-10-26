"""Build the judge request, strict schema, validate, one retry. Owner: Carlos. Phase 2."""

from PIL import Image

from app.schemas import Candidate, Destination, JudgeOutput


def judge(
    image: Image.Image,
    marked_image: Image.Image,
    candidates: list[Candidate],
    destination: Destination,
) -> JudgeOutput | None:
    """Returns None after one failed retry; merge.py takes the fail closed path."""
    raise NotImplementedError
