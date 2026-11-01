import pytest

from app.pipeline.candidates import box_iou, build
from app.schemas import Candidate


def sam(label, box, score=0.9):
    return Candidate(source="sam", sam_label=label, box=box, mask_rle="x", score=score)


def line(text, box):
    return Candidate(source="ocr", text=text, box=box, score=0.95)


def test_marks_follow_reading_order_and_inputs_untouched():
    a = sam("whiteboard", [0, 100, 500, 400])
    b = line("PWD: hunter2", [50, 20, 300, 60])
    c = line("standup 9am", [400, 20, 600, 60])
    out = build([a], [c, b])
    assert [(x.mark, x.kind) for x in out] == [(1, "text"), (2, "text"), (3, "whiteboard")]
    assert out[0].text == "PWD: hunter2" and out[1].text == "standup 9am"
    assert a.mark is None and b.mark is None


def test_same_object_from_two_phrases_keeps_the_more_confident():
    monitor = sam("computer monitor", [100, 100, 500, 400], score=0.62)
    laptop = sam("laptop screen", [105, 102, 498, 405], score=0.88)
    [kept] = build([monitor, laptop], [])
    assert kept.sam_label == "laptop screen" and kept.mark == 1


def test_fail_closed_label_beats_street_sign():
    sign = sam("street sign", [10, 10, 110, 60], score=0.95)
    number = sam("house number", [12, 10, 110, 62], score=0.40)
    [kept] = build([sign, number], [])
    assert kept.sam_label == "house number"


def test_nested_regions_and_ocr_lines_never_merged():
    board = sam("whiteboard", [0, 0, 1000, 800])
    note = sam("sticky note", [100, 100, 300, 300])
    text_on_note = line("Orlandodlpz05", [100, 100, 300, 300])  # same box as the note
    out = build([board, note], [text_on_note])
    assert sorted(c.kind for c in out) == ["sticky note", "text", "whiteboard"]
    assert [c.mark for c in out] == [1, 2, 3]


def test_missing_score_ranks_last():
    a = sam("face", [0, 0, 100, 100], score=None)
    b = sam("face", [0, 0, 100, 100], score=0.3)
    [kept] = build([a, b], [])
    assert kept.score == 0.3


def test_empty():
    assert build([], []) == []


def test_box_iou():
    assert box_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1
    assert box_iou([0, 0, 10, 10], [10, 0, 20, 10]) == 0  # half-open: touching isn't overlap
    assert box_iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(50 / 150)
    assert box_iou([0, 0, 0, 0], [0, 0, 10, 10]) == 0
