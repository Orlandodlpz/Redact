"""Decode, EXIF/GPS detect and strip, resize, sha256. Owner: Orlando.

Everything stays in memory. The returned images are rebuilt from raw pixels, so no
EXIF, XMP, ICC or other metadata survives into any later step or API call.
"""

import hashlib
import io
from dataclasses import dataclass

import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings

pillow_heif.register_heif_opener()

ALLOWED_FORMATS = {"JPEG", "MPO", "PNG", "HEIF", "WEBP"}
# iPhone JPEGs open as MPO (extra embedded frames such as depth or gain maps), and
# HEIC can hold several images. Both are stills: frame 0 is the photo.
_STILL_MULTI_FRAME = {"MPO", "HEIF"}

_GPS_IFD = 0x8825
_GPS_LATITUDE, _GPS_LONGITUDE = 2, 4


class IngestError(ValueError):
    """The upload can't be processed. The message is safe to show the user."""


@dataclass
class IngestResult:
    # Working image: upright, RGB, long edge <= max_image_edge_px. Every box,
    # mask and API call uses its coordinates.
    image: Image.Image
    width: int
    height: int
    # sha256 of the uploaded bytes, for caching by image plus prompt version.
    sha256: str
    had_gps: bool
    # Larger copy for local OCR only (long edge <= ocr_max_edge_px). Never sent
    # to any API. Multiply OCR boxes by ocr_scale to get working image coordinates.
    ocr_image: Image.Image
    ocr_scale: float


def ingest(image_bytes: bytes) -> IngestResult:
    settings = get_settings()
    if len(image_bytes) > settings.max_upload_bytes:
        raise IngestError(f"Image is larger than {settings.max_upload_bytes // (1024 * 1024)} MB")

    try:
        source = Image.open(io.BytesIO(image_bytes))
        source.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise IngestError("Couldn't read this file as an image") from e
    if source.format not in ALLOWED_FORMATS:
        raise IngestError(f"Unsupported image type {source.format}; use JPEG, PNG, HEIC or WebP")
    if getattr(source, "n_frames", 1) > 1:
        if source.format not in _STILL_MULTI_FRAME:
            raise IngestError("Animated images aren't supported")
        source.seek(0)

    had_gps = _has_gps(source)
    upright = _strip(_flatten(ImageOps.exif_transpose(source)))

    ocr_image = _fit(upright, settings.ocr_max_edge_px)
    image = _fit(ocr_image, settings.max_image_edge_px)
    return IngestResult(
        image=image,
        width=image.width,
        height=image.height,
        sha256=hashlib.sha256(image_bytes).hexdigest(),
        had_gps=had_gps,
        ocr_image=ocr_image,
        ocr_scale=image.width / ocr_image.width,
    )


def _has_gps(im: Image.Image) -> bool:
    gps = im.getexif().get_ifd(_GPS_IFD)
    if _GPS_LATITUDE in gps or _GPS_LONGITUDE in gps:
        return True
    xmp = im.info.get("xmp") or im.info.get("XML:com.adobe.xmp") or b""
    if isinstance(xmp, str):
        xmp = xmp.encode()
    return b"GPSLatitude" in xmp or b"GPSLongitude" in xmp


def _flatten(im: Image.Image) -> Image.Image:
    """Transparent pixels become white instead of whatever color hides under them."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return im.convert("RGB")


def _strip(im: Image.Image) -> Image.Image:
    # A new image from raw pixels carries no info dict: no EXIF, XMP or ICC.
    return Image.frombytes("RGB", im.size, im.tobytes())


def _fit(im: Image.Image, max_edge: int) -> Image.Image:
    if max(im.size) <= max_edge:
        return im
    scale = max_edge / max(im.size)
    size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
    return im.resize(size, Image.Resampling.LANCZOS)
