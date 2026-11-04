import error_analysis as ea

ITEM = [0, 0, 10, 10]


def test_candidate_gap_when_no_candidate_covers_the_item():
    assert ea.classify(ITEM, [[0, 0, 4, 10]], [], [])[0] == "candidate_gap"


def test_partial_when_masks_cover_half_to_ninety_percent():
    assert ea.classify(ITEM, [[0, 0, 10, 10]], [[0, 0, 7, 10]], [])[0] == "partial"


def test_kept_by_system_when_an_unmasked_finding_covers_it():
    assert ea.classify(ITEM, [[0, 0, 10, 10]], [], [[0, 0, 10, 10]])[0] == "kept_by_system"


def test_not_flagged_when_nothing_covers_it():
    assert ea.classify(ITEM, [[0, 0, 10, 10]], [], [])[0] == "not_flagged"
