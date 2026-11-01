"""Manifest and label formats for the eval. Owner: Carlos.

Images never go in git. The repo holds manifest.jsonl and labels/<image_id>.json only.
A label is the Finding list the review editor exports, one list per labeled destination,
so ground truth and system output are compared in the same shape.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

# Imported from the backend so labels cannot drift from the contract.
from app.schemas import Destination, Finding

Source = Literal["webpii", "staged", "hard_negative"]
# dev is for prompt and threshold tuning. test is frozen before any tuning and only
# scored in the final runs. Headline numbers come from test.
Split = Literal["dev", "test"]


class ManifestRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str
    source: Source
    license: str  # "CC BY 4.0" for WebPII, "team staged, fake data" for staged
    attribution: str | None = None  # required for WebPII, credited in the README
    split: Split
    categories: list[str]  # categories present in the image, for slicing
    destinations_labeled: list[Destination]

    @model_validator(mode="after")
    def _checks(self) -> "ManifestRow":
        if self.source == "webpii" and not self.attribution:
            raise ValueError("webpii rows need attribution (CC BY 4.0)")
        if not self.destinations_labeled:
            raise ValueError("label at least one destination")
        return self


class Label(BaseModel):
    """Ground truth for one image. Each Finding is an item that should be masked
    for that destination. An empty list is a valid label (hard negatives)."""

    model_config = ConfigDict(extra="forbid")

    image_id: str
    width: int
    height: int
    destinations: dict[Destination, list[Finding]]
