import pytest

from app import policy
from app.schemas import Category, Destination
from typing import get_args

CATEGORIES = get_args(Category)


def test_table_covers_every_category_and_destination():
    assert set(policy.TABLE) == set(CATEGORIES)
    assert all(set(row) == set(get_args(Destination)) for row in policy.TABLE.values())


def test_table_matches_briefing():
    keep = {("face", "team"), ("face", "ai_assistant"), ("license_plate", "team"),
            ("license_plate", "ai_assistant"), ("internal_data", "team")}
    for cat in CATEGORIES:
        for dest in get_args(Destination):
            if cat == "benign" or (cat, dest) in keep:
                assert not policy.baseline_masks(cat, dest), (cat, dest)
            else:
                assert policy.baseline_masks(cat, dest), (cat, dest)


@pytest.mark.parametrize("cat", CATEGORIES)
@pytest.mark.parametrize("dest", get_args(Destination))
def test_judge_can_escalate_but_never_lower(cat, dest):
    assert policy.decide(cat, dest, True)
    assert policy.decide(cat, dest, False) == policy.baseline_masks(cat, dest)


def test_sam_label_categories():
    assert policy.category_for_sam_label("ID card") == "government_id"
    assert policy.category_for_sam_label("whiteboard") == "other_sensitive"
    assert policy.category_for_sam_label(None) == "other_sensitive"
