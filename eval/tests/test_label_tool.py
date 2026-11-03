import pytest

import label_tool as L
import make_manifest
from schemas import ManifestRow


def box(b, cat="credential", dests=("public",), note=""):
    return {"box": list(b), "category": cat, "dests": list(dests), "note": note}


def test_to_label_only_writes_required_destinations():
    lab = L.to_label("s01", 100, 80, [box([5, 5, 50, 40], "face", ["public", "team"])], ["public"])
    assert list(lab.destinations) == ["public"] and lab.destinations["public"][0].box == [5, 5, 50, 40]
    assert (lab.width, lab.height) == (100, 80)


def test_triple_labeling_puts_each_box_only_where_it_is_masked():
    boxes = [box([0, 0, 10, 10], "face", ["public"]), box([20, 0, 30, 10], "credential", L.DESTINATIONS)]
    lab = L.to_label("s42", 100, 80, boxes, L.DESTINATIONS)
    assert [len(lab.destinations[d]) for d in L.DESTINATIONS] == [2, 1, 1]


def test_boxes_are_clamped_swapped_and_rounded_and_empty_ones_rejected():
    lab = L.to_label("s01", 100, 80, [box([-5, 90, 120.4, 10])], ["public"])
    assert lab.destinations["public"][0].box == [0, 10, 100, 80]
    with pytest.raises(ValueError):
        L.to_label("s01", 100, 80, [box([10, 10, 11, 50])], ["public"])
    with pytest.raises(ValueError):
        L.to_label("s01", 100, 80, [box([0, 0, 9, 9], "benign")], ["public"])  # benign is not labeled


def test_empty_label_is_valid_for_a_hard_negative():
    assert L.to_label("hn_01", 100, 80, [], ["public"]).destinations == {"public": []}


def test_round_trip_merges_destinations_back_into_one_box():
    boxes = [box([0, 0, 10, 10], "credential", L.DESTINATIONS, "pw line")]
    back = L.from_label(L.to_label("s02", 100, 80, boxes, L.DESTINATIONS))
    assert back == [{"box": [0, 0, 10, 10], "category": "credential", "dests": L.DESTINATIONS, "note": "pw line"}]


def test_only_known_ids_map_to_files_under_the_images_folder():
    assert L.image_path("../../etc/passwd") is None
    assert L.image_path("s01; rm -rf") is None
    assert L.image_path("nope_not_there") is None


def test_triple_images_require_all_destinations():
    assert L.required_destinations("s42") == L.DESTINATIONS
    assert L.required_destinations("s01") == ["public"]
    assert L.required_destinations("webpii_001") == ["public"]


def test_manifest_rows_follow_labels_when_they_exist():
    lab = L.to_label("s42", 100, 80, [box([0, 0, 10, 10], "face", ["public"])], L.DESTINATIONS)
    rows = make_manifest.build_rows({"s42", "s01"}, {"s42": "photo", "s01": "synthetic"}, {"s42": lab})
    by = {r.image_id: r for r in rows}
    assert by["s42"].categories == ["face"] and by["s42"].destinations_labeled == L.DESTINATIONS
    assert by["s01"].provenance == "synthetic" and by["s01"].destinations_labeled == ["public"]
    assert all(isinstance(r, ManifestRow) for r in rows)
