from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.pipeline import ocr as ocr_module
from app.pipeline.ocr import ocr


def fake_engine(boxes, txts, scores):
    out = SimpleNamespace(boxes=None if boxes is None else np.array(boxes, dtype=float),
                          txts=txts, scores=scores)
    return lambda _img: out


@pytest.fixture
def engine(monkeypatch):
    def install(boxes, txts, scores):
        monkeypatch.setattr(ocr_module, "_engine", lambda: fake_engine(boxes, txts, scores))
    return install


def test_rotated_quad_becomes_scaled_axis_aligned_box(engine):
    # A tilted line in a 4096 px OCR image; the working image is half that.
    engine([[[243, 1034], [811, 926], [839, 1069], [271, 1177]]], ["Redact1234!"], [0.99])
    [c] = ocr(Image.new("RGB", (4096, 3072)), scale=0.5, bounds=(2048, 1536))
    assert c.source == "ocr" and c.text == "Redact1234!" and c.sam_label is None
    assert c.box == [121, 463, 420, 589]  # floor of mins, ceil of maxes
    assert c.mark is None and c.kind == "text"
    assert c.score == pytest.approx(0.99)


def test_boxes_clamped_to_bounds(engine):
    engine([[[-10, -5], [120, -5], [120, 40], [-10, 40]]], ["edge"], [0.9])
    [c] = ocr(Image.new("RGB", (100, 30)), bounds=(100, 30))
    assert c.box == [0, 0, 100, 30]


def test_blank_text_and_empty_boxes_dropped(engine):
    engine(
        [[[0, 0], [10, 0], [10, 10], [0, 10]], [[5, 5], [5, 5], [5, 5], [5, 5]]],
        ["   ", "dot"],
        [0.9, 0.9],
    )
    assert ocr(Image.new("RGB", (20, 20))) == []


def test_no_text_found(engine):
    engine(None, None, None)
    assert ocr(Image.new("RGB", (20, 20))) == []


def test_default_bounds_follow_scale(engine):
    engine([[[0, 0], [400, 0], [400, 100], [0, 100]]], ["wide"], [0.8])
    [c] = ocr(Image.new("RGB", (400, 100)), scale=0.5)
    assert c.box == [0, 0, 200, 50]


def test_real_engine_reads_printed_password():
    """Runs the real RapidOCR models locally on a rendered image."""
    im = Image.new("RGB", (900, 300), "white")
    ImageDraw.Draw(im).text((60, 110), "PWD: Redact1234!", fill="black",
                            font=ImageFont.load_default(size=72))
    found = ocr(im)
    assert any("Redact1234" in c.text for c in found)
    hit = next(c for c in found if "Redact1234" in c.text)
    x1, y1, x2, y2 = hit.box
    assert x1 < 450 and x2 > 600 and y1 < 140 and y2 > 160
