import numpy as np
import pytest
from PIL import Image, ImageFont

from app.pipeline.candidates import build
from app.pipeline.marks import _overlap, layout, render
from app.schemas import Candidate

FONT = ImageFont.load_default(size=27)


def line(text, box):
    return Candidate(source="ocr", text=text, box=box)


def sam(label, box):
    return Candidate(source="sam", sam_label=label, box=box, score=0.9)


def test_render_returns_new_image_and_leaves_input_alone():
    im = Image.new("RGB", (400, 300), "white")
    out = render(im, build([sam("face", [100, 100, 200, 200])], []))
    assert out is not im and out.size == im.size and out.mode == "RGB"
    assert np.asarray(im).min() == 255  # untouched
    assert np.asarray(out).min() < 255  # something drawn


def test_unnumbered_candidates_refused():
    with pytest.raises(ValueError):
        render(Image.new("RGB", (100, 100)), [sam("face", [0, 0, 10, 10])])


def test_tag_goes_above_the_box_when_there_is_room():
    [c] = build([], [line("PWD", [100, 200, 300, 240])])
    [tag] = layout((800, 600), [c], FONT)
    assert tag[3] <= 200 and tag[0] == 100  # above, left aligned, not covering the text


def test_tags_stay_inside_the_image():
    cands = build([sam("face", [0, 0, 30, 30]), sam("QR code", [770, 570, 800, 600])], [])
    for x1, y1, x2, y2 in layout((800, 600), cands, FONT):
        assert x1 >= 0 and y1 >= 0 and x2 <= 800 and y2 <= 600


def test_dense_text_lines_get_tags_that_do_not_overlap():
    # 100 lines like an exam page: two columns of 50 lines, 36 px apart.
    lines = [line(f"q{i}", [40 + 700 * (i % 2), 40 + 36 * (i // 2), 640 + 700 * (i % 2), 70 + 36 * (i // 2)])
             for i in range(100)]
    cands = build([], lines)
    tags = layout((1500, 2000), cands, FONT)
    overlaps = sum(_overlap(a, b) > 0 for i, a in enumerate(tags) for b in tags[i + 1:])
    assert overlaps == 0


def test_tag_color_matches_its_outline():
    im = Image.new("RGB", (400, 300), "white")
    [c] = build([sam("face", [100, 100, 300, 250])], [])
    out = np.asarray(render(im, [c]))
    outline = tuple(out[250 - 1, 200])  # bottom edge, away from the tag
    [tag] = layout(im.size, [c], ImageFont.load_default(size=12))
    assert tuple(out[tag[1] + 2, tag[0] + 2]) == outline
