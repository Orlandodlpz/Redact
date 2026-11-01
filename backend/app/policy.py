"""Category x destination table (docs/BRIEFING.md §2). Owner: Carlos. Phase 2.

The judge may escalate keep to mask with a reason, never mask to keep.
Floor rules sit outside this table: they mask for every destination.
"""

from typing import get_args

from app.schemas import Category, Destination

DESTINATIONS: tuple[Destination, ...] = get_args(Destination)

# True means mask. Rows and columns follow the BRIEFING.md table. Provisional until
# destination accuracy is measured on the 30 triple labeled images.
_MASK, _KEEP = True, False
TABLE: dict[Category, dict[Destination, bool]] = {
    "credential": {"public": _MASK, "team": _MASK, "ai_assistant": _MASK},
    "payment": {"public": _MASK, "team": _MASK, "ai_assistant": _MASK},
    "government_id": {"public": _MASK, "team": _MASK, "ai_assistant": _MASK},
    "personal_account": {"public": _MASK, "team": _MASK, "ai_assistant": _MASK},
    "contact_info": {"public": _MASK, "team": _MASK, "ai_assistant": _MASK},
    "home_location": {"public": _MASK, "team": _MASK, "ai_assistant": _MASK},
    "face": {"public": _MASK, "team": _KEEP, "ai_assistant": _KEEP},
    "license_plate": {"public": _MASK, "team": _KEEP, "ai_assistant": _KEEP},
    "internal_data": {"public": _MASK, "team": _KEEP, "ai_assistant": _MASK},
    "other_sensitive": {"public": _MASK, "team": _MASK, "ai_assistant": _MASK},
    "benign": {"public": _KEEP, "team": _KEEP, "ai_assistant": _KEEP},
}

# Category for a region masked only because its SAM class is high risk (fail closed,
# or no verdict). Classes with no clear category fall back to other_sensitive.
SAM_LABEL_CATEGORY: dict[str, Category] = {
    "face": "face",
    "license plate": "license_plate",
    "ID card": "government_id",
    "credit card": "payment",
}


def baseline_masks(category: Category, destination: Destination) -> bool:
    return TABLE[category][destination]


def decide(category: Category, destination: Destination, judge_sensitive: bool) -> bool:
    """Mask if the table says mask, or if the judge calls it sensitive.

    A sensitive verdict on a keep cell is an escalation and masks. A not sensitive
    verdict never lowers a mask cell, so the result is never below the table.
    """
    return baseline_masks(category, destination) or judge_sensitive


def category_for_sam_label(label: str | None) -> Category:
    return SAM_LABEL_CATEGORY.get(label or "", "other_sensitive")
