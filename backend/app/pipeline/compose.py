"""Mask union, dilation, solid fill, flatten, re-encode with zero metadata. Owner: Orlando. Phase 2."""

from PIL import Image

from app.schemas import Finding


def compose(image: Image.Image, findings: list[Finding]) -> bytes:
    """Returns PNG bytes."""
    raise NotImplementedError
