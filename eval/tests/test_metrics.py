import pytest

import metrics
from app.schemas import Finding
from schemas import Label, ManifestRow


def f(box, category="credential", masked=True):
    return Finding(id="f", marks=[], category=category, reason="r", source="judge",
                   masked=masked, locked=False, box=box)


def test_union_area_overlap_and_disjoint():
    assert metrics.union_area([[0, 0, 10, 10], [5, 5, 15, 15]]) == 175
    assert metrics.union_area([[0, 0, 2, 2], [10, 10, 12, 12]]) == 8
    assert metrics.union_area([]) == 0


def test_coverage_threshold_is_ninety_percent():
    item = [0, 0, 10, 10]
    assert metrics.is_caught(item, [[0, 0, 10, 9]])  # exactly 90%
    assert not metrics.is_caught(item, [[0, 0, 10, 8]])
    assert metrics.is_caught(item, [[0, 0, 5, 10], [5, 0, 10, 10]])  # two masks union


def test_recall_by_category_skips_metadata_and_unmasked():
    truth = [f([0, 0, 10, 10]), f([20, 20, 30, 30], "face")]
    pred = [f([0, 0, 10, 10]), f([20, 20, 30, 30], "face", masked=False)]
    assert metrics.recall_by_category(truth, pred) == {"credential": (1, 1), "face": (0, 1)}


def test_over_redaction_counts_only_area_outside_labels():
    truth = [f([0, 0, 10, 10])]
    pred = [f([0, 0, 20, 10])]  # 100 inside, 100 outside
    assert metrics.over_redaction(truth, pred, 100, 100) == pytest.approx(0.01)
    assert metrics.over_redaction([], [], 100, 100) == 0.0


def test_hard_negative_fp():
    assert metrics.hard_negative_false_positive([f([0, 0, 1, 1])])
    assert not metrics.hard_negative_false_positive([f([0, 0, 1, 1], masked=False)])


def test_percentile():
    assert metrics.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5
    assert metrics.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90) == 9


def test_manifest_requires_webpii_attribution():
    base = dict(image_id="a", source="webpii", license="CC BY 4.0", split="dev",
                categories=[], destinations_labeled=["public"])
    with pytest.raises(ValueError):
        ManifestRow(**base)
    ManifestRow(**base, attribution="WebPII, CC BY 4.0")


def test_label_empty_is_valid_for_hard_negative():
    Label(image_id="hn_01", width=10, height=10, destinations={"public": []})
