"""Pydantic models for the contracts in docs/BRIEFING.md §2.

Shared file: change only after the team agrees, and say so in the PR.
Boxes are integer pixels [x1, y1, x2, y2] in the ingested image's coordinates.
mask_rle is a COCO compressed RLE string.
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

Destination = Literal["public", "team", "ai_assistant"]

Category = Literal[
    "credential",
    "payment",
    "government_id",
    "personal_account",
    "contact_info",
    "home_location",
    "face",
    "license_plate",
    "internal_data",
    "other_sensitive",
    "benign",
]


def _four_ints(box: list[int]) -> list[int]:
    if len(box) != 4:
        raise ValueError("box must have 4 values [x1, y1, x2, y2]")
    return box


def _ordered_box(box: list[int]) -> list[int]:
    x1, y1, x2, y2 = _four_ints(box)
    if min(box) < 0 or x2 < x1 or y2 < y1:
        raise ValueError("box must be non-negative with x1 <= x2 and y1 <= y2")
    return box


# Our own boxes are always valid. Model boxes only get a length check here;
# judge.py clamps them to the image instead of rejecting the whole output.
Box = Annotated[list[int], AfterValidator(_ordered_box)]
ModelBox = Annotated[list[int], AfterValidator(_four_ints)]


class Candidate(BaseModel):
    """A region that could matter, from the SAM sweep or OCR.

    mark is None until candidates.build numbers the merged list.
    """

    mark: int | None = None
    source: Literal["sam", "ocr"]
    sam_label: str | None = None
    text: str | None = None
    box: Box
    mask_rle: str | None = None
    score: float | None = None

    @model_validator(mode="after")
    def _source_fields(self) -> "Candidate":
        if self.source == "sam" and not self.sam_label:
            raise ValueError("sam candidates need sam_label")
        if self.source == "ocr" and self.text is None:
            raise ValueError("ocr candidates need text")
        return self

    @property
    def kind(self) -> str:
        """What the judge request calls this candidate."""
        return self.sam_label if self.source == "sam" else "text"


# JudgeOutput models forbid extra keys so their JSON schema carries
# additionalProperties: false, which strict structured output requires.


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mark: int
    sensitive: bool
    category: Category
    reason: str
    confidence: Literal["high", "medium", "low"]


class ExtraFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category
    reason: str
    box: ModelBox


class CombinedLeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marks: list[int]
    category: Category
    reason: str


class InstructionText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mark: int
    text: str


class JudgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[Verdict]
    extra_findings: list[ExtraFinding]
    combined_leaks: list[CombinedLeak]
    instruction_text: list[InstructionText]


class Finding(BaseModel):
    """One API response item, what the review editor shows.

    locked means a floor hit. metadata findings (GPS in EXIF) have no box or mask.
    """

    id: str
    marks: list[int]
    category: Category
    reason: str
    source: Literal["floor", "judge", "combined", "extra", "metadata"]
    masked: bool
    locked: bool
    box: Box | None = None
    mask_rle: str | None = None

    @model_validator(mode="after")
    def _box_unless_metadata(self) -> "Finding":
        if self.source != "metadata" and self.box is None:
            raise ValueError(f"{self.source} findings need a box")
        return self


class AnalyzeResponse(BaseModel):
    image_id: str
    width: int
    height: int
    destination: Destination
    findings: list[Finding]
    judge_status: Literal["ok", "failed_closed"]
    prompt_version: str
    model_ids: dict[str, str]
    timings_ms: dict[str, int]
    est_cost_usd: float
