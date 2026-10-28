import io

import numpy as np
from PIL import Image, PngImagePlugin

from app.pipeline.compose import FILL, compose, dilate
from app.pipeline.sweep import encode_rle
from app.schemas import Finding


def finding(box, masked=True, mask_rle=None, source="judge"):
    return Finding(id="f", marks=[1], category="credential", reason="r", source=source,
                   masked=masked, locked=False, box=box, mask_rle=mask_rle)


def open_png(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def test_export_carries_no_metadata():
    im = Image.new("RGB", (64, 48), "white")
    exif = Image.Exif()
    exif[0x8825] = {2: (26.0, 18.0, 0.0)}
    im.info.update(exif=exif.tobytes(), icc_profile=b"fake", dpi=(300, 300))
    im.info["XML:com.adobe.xmp"] = "<x:xmpmeta/>"
    out = open_png(compose(im, [finding([4, 4, 20, 20])]))
    assert out.format == "PNG" and out.mode == "RGB"
    assert not out.getexif()
    assert not out.info  # no exif, xmp, icc, dpi or text chunks
    assert not getattr(out, "text", {})


def test_masked_box_is_one_solid_color_and_dilated():
    im = Image.new("RGB", (100, 100), (200, 180, 160))
    px = np.asarray(open_png(compose(im, [finding([40, 40, 60, 60])])))
    region = px[36:64, 36:64]  # box grown by the 4 px default dilation
    assert (region == FILL).all()
    assert (px[34, 50] == (200, 180, 160)).all() and (px[50, 65] == (200, 180, 160)).all()


def test_mask_rle_used_instead_of_box():
    im = Image.new("RGB", (100, 100), "white")
    m = np.zeros((100, 100), dtype=np.uint8)
    m[50:52, 50:52] = 1
    px = np.asarray(open_png(compose(im, [finding([10, 10, 90, 90], mask_rle=encode_rle(m))])))
    filled = (px == FILL).all(axis=2)
    assert filled[46:56, 46:56].all() and filled.sum() == 10 * 10


def test_unmasked_and_metadata_findings_draw_nothing():
    im = Image.new("RGB", (30, 30), "white")
    meta = Finding(id="gps", marks=[], category="home_location", reason="r", source="metadata",
                   masked=True, locked=True)
    px = np.asarray(open_png(compose(im, [finding([0, 0, 30, 30], masked=False), meta])))
    assert (px == 255).all()


def test_input_image_untouched():
    im = Image.new("RGB", (30, 30), "white")
    compose(im, [finding([0, 0, 30, 30])])
    assert np.asarray(im).min() == 255


def test_dilate_square_and_clipped_at_edges():
    m = np.zeros((10, 10), dtype=bool)
    m[5, 5] = m[0, 0] = True
    out = dilate(m, 2)
    assert out[3:8, 3:8].all() and out[:3, :3].all()
    assert out.sum() == 25 + 9
    assert (dilate(m, 0) == m).all()
