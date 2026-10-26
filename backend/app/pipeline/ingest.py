"""Decode, EXIF/GPS detect and strip, resize, sha256. Owner: Orlando. Phase 2."""

from dataclasses import dataclass

from PIL import Image


@dataclass
class IngestResult:
    image: Image.Image
    width: int
    height: int
    sha256: str
    had_gps: bool


def ingest(image_bytes: bytes) -> IngestResult:
    raise NotImplementedError
