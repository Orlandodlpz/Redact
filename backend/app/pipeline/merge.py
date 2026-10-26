"""floor ∪ judge ∪ combined leaks, policy, fail closed. Owner: Carlos. Phase 2."""

from app.schemas import Candidate, Destination, Finding, JudgeOutput


def merge(
    candidates: list[Candidate],
    floor_hits: list[Finding],
    judge_output: JudgeOutput | None,
    destination: Destination,
) -> list[Finding]:
    """judge_output None means fail closed: floor hits plus every HIGH_RISK_SAM_CLASSES candidate."""
    raise NotImplementedError
