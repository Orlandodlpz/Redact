import hashlib
import io

import pytest
from PIL import Image

from app.pipeline.ingest import IngestError, ingest

GPS_IFD = 0x8825
ORIENTATION = 0x0112


def encode(im: Image.Image, fmt: str = "JPEG", **save_kwargs) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format=fmt, **save_kwargs)
    return buf.getvalue()


def jpeg_with_gps(size=(64, 48)) -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    exif[GPS_IFD] = {1: "N", 2: (26.0, 18.0, 5.5), 3: "W", 4: (98.0, 10.0, 1.2)}
    return encode(Image.new("RGB", size, "red"), exif=exif)


def assert_no_metadata(im: Image.Image) -> None:
    assert not im.getexif()
    assert im.info == {}


def test_gps_detected_and_stripped():
    result = ingest(jpeg_with_gps())
    assert result.had_gps is True
    assert_no_metadata(result.image)
    assert_no_metadata(result.ocr_image)


def test_no_gps():
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    result = ingest(encode(Image.new("RGB", (64, 48)), exif=exif))
    assert result.had_gps is False
    assert_no_metadata(result.image)


def test_empty_gps_block_is_not_gps():
    exif = Image.Exif()
    exif[GPS_IFD] = {0: b"\x02\x02\x00\x00"}  # GPSVersionID only, no position
    assert ingest(encode(Image.new("RGB", (8, 8)), exif=exif)).had_gps is False


def test_gps_in_xmp_detected():
    xmp = b'<x:xmpmeta><rdf:Description exif:GPSLatitude="26,18.1N"/></x:xmpmeta>'
    assert ingest(encode(Image.new("RGB", (8, 8)), xmp=xmp)).had_gps is True


def test_exif_rotation_applied():
    exif = Image.Exif()
    exif[ORIENTATION] = 6  # stored sideways, displayed rotated 90 degrees
    result = ingest(encode(Image.new("RGB", (40, 20)), exif=exif))
    assert (result.width, result.height) == (20, 40)


def test_two_sizes_and_scale():
    result = ingest(encode(Image.new("RGB", (5000, 3000), "white")))
    assert result.image.size == (2048, 1229)
    assert result.ocr_image.size == (4096, 2458)
    assert result.ocr_scale == pytest.approx(0.5)
    assert (result.width, result.height) == result.image.size


def test_small_image_not_upscaled():
    result = ingest(encode(Image.new("RGB", (300, 400))))
    assert result.image.size == result.ocr_image.size == (300, 400)
    assert result.ocr_scale == 1.0


def test_transparent_png_flattened_to_white():
    im = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    result = ingest(encode(im, "PNG"))
    assert result.image.mode == "RGB"
    assert result.image.getpixel((5, 5)) == (255, 255, 255)


def test_sha256_of_upload_bytes():
    data = jpeg_with_gps()
    assert ingest(data).sha256 == hashlib.sha256(data).hexdigest()


def test_too_large_rejected(monkeypatch):
    from app import config

    monkeypatch.setenv("MAX_UPLOAD_BYTES", "100")
    config.get_settings.cache_clear()
    try:
        with pytest.raises(IngestError, match="larger than"):
            ingest(jpeg_with_gps())
    finally:
        config.get_settings.cache_clear()


@pytest.mark.parametrize("data", [b"", b"not an image at all", b"\xff\xd8\xff\xe0broken jpeg"])
def test_garbage_rejected(data):
    with pytest.raises(IngestError):
        ingest(data)


def test_unsupported_format_rejected():
    with pytest.raises(IngestError, match="Unsupported"):
        ingest(encode(Image.new("RGB", (8, 8)), "TIFF"))


def test_animated_gif_rejected():
    frames = [Image.new("RGB", (8, 8), c) for c in ("red", "blue")]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:])
    with pytest.raises(IngestError):
        ingest(buf.getvalue())


def test_iphone_style_mpo_accepted():
    # iPhone JPEGs carry extra frames and open as MPO; frame 0 is the photo.
    exif = Image.Exif()
    exif[GPS_IFD] = {2: (26.0, 18.0, 5.5), 4: (98.0, 10.0, 1.2)}
    primary, depth = Image.new("RGB", (64, 48), "red"), Image.new("RGB", (32, 24), "gray")
    buf = io.BytesIO()
    primary.save(buf, format="MPO", save_all=True, append_images=[depth], exif=exif)
    assert Image.open(io.BytesIO(buf.getvalue())).format == "MPO"
    result = ingest(buf.getvalue())
    assert result.image.size == (64, 48)
    assert result.had_gps is True
    assert_no_metadata(result.image)


def test_heic_decoded():
    try:
        data = encode(Image.new("RGB", (64, 48), "blue"), "HEIF")
    except (KeyError, OSError) as e:
        pytest.skip(f"no HEIF encoder here: {e}")
    result = ingest(data)
    assert result.image.size == (64, 48)
    assert_no_metadata(result.image)
