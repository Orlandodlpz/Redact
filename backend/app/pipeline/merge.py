"""floor ∪ judge ∪ combined leaks, policy, fail closed. Owner: Carlos. Phase 2.

Choices that are not in BRIEFING.md yet, proposed for the team (see the PR):
- A sensitive verdict on a keep cell masks it (escalation); never the reverse.
- A verdict marked sensitive with category benign is honored as other_sensitive.
- A SAM region in HIGH_RISK_SAM_CLASSES with no verdict is masked (the judge said nothing).
- Combined leaks mask each mark with its own tight mask, not one union box.
- Kept non benign items stay in the list unmasked, so the user can mask them.
- Text addressed to an AI is reported as an unmasked finding and never obeyed.
- Ids are renumbered f_01, f_02 ... across the whole list so floor ids cannot collide.
"""

from app.config import HIGH_RISK_SAM_CLASSES
from app.policy import category_for_sam_label, decide
from app.schemas import Candidate, Category, Destination, Finding, JudgeOutput


def _finding(source, candidate: Candidate, category: Category, reason: str, *, masked=True,
             marks=None) -> Finding:
    return Finding(
        id="",
        marks=[candidate.mark] if marks is None else marks,
        category=category,
        reason=reason,
        source=source,
        masked=masked,
        locked=False,
        box=candidate.box,
        mask_rle=candidate.mask_rle,
    )


def _high_risk(c: Candidate) -> bool:
    return c.source == "sam" and c.sam_label in HIGH_RISK_SAM_CLASSES


def merge(
    candidates: list[Candidate],
    floor_hits: list[Finding],
    judge_output: JudgeOutput | None,
    destination: Destination,
) -> list[Finding]:
    """judge_output None means fail closed: floor hits plus every HIGH_RISK_SAM_CLASSES candidate."""
    numbered = [c for c in candidates if c.mark is not None]
    by_mark = {c.mark: c for c in numbered}

    # Floor hits always mask and stay locked, whatever else happens below.
    out: list[Finding] = [f.model_copy(update={"masked": True, "locked": True}) for f in floor_hits]
    floor_marks = {m for f in floor_hits for m in f.marks}

    if judge_output is None:
        for c in numbered:
            if _high_risk(c) and c.mark not in floor_marks:
                out.append(_finding(
                    "judge", c, category_for_sam_label(c.sam_label),
                    f"Judge unavailable: masked because this {c.sam_label} region is high risk",
                ))
        return _renumber(out)

    masked_marks = set(floor_marks)
    pending: dict[int, Finding] = {}  # judged but kept, so a later leak can upgrade it

    for v in judge_output.verdicts:
        c = by_mark.get(v.mark)
        if c is None or v.mark in floor_marks:
            continue
        category = "other_sensitive" if v.sensitive and v.category == "benign" else v.category
        if category == "benign":
            continue
        masked = decide(category, destination, v.sensitive)
        f = _finding("judge", c, category, v.reason, masked=masked)
        if masked:
            out.append(f)
            masked_marks.add(v.mark)
        else:
            pending[v.mark] = f

    judged = {v.mark for v in judge_output.verdicts}
    for c in numbered:
        if _high_risk(c) and c.mark not in judged and c.mark not in floor_marks:
            out.append(_finding("judge", c, category_for_sam_label(c.sam_label),
                                "Judge gave no verdict on this high risk region, so it is masked"))
            masked_marks.add(c.mark)

    for leak in judge_output.combined_leaks:
        category = "other_sensitive" if leak.category == "benign" else leak.category
        for m in leak.marks:
            if m in masked_marks or m not in by_mark:
                continue
            pending.pop(m, None)
            out.append(_finding("combined", by_mark[m], category, leak.reason, marks=leak.marks))
            masked_marks.add(m)

    for e in judge_output.extra_findings:
        if e.category == "benign":
            continue
        # An extra is something the judge found that no mark covers, so it is sensitive by
        # definition. The loose judge box stays until refine tightens it.
        out.append(Finding(
            id="", marks=[], category=e.category, reason=e.reason, source="extra",
            masked=True, locked=False, box=e.box,
        ))

    out.extend(f for m, f in pending.items() if m not in masked_marks)

    for i in judge_output.instruction_text:
        c = by_mark.get(i.mark)
        if c is not None and i.mark not in masked_marks:
            out.append(_finding("judge", c, "other_sensitive",
                                "Text in the image is addressed to an AI system; it was ignored",
                                masked=False))
    return _renumber(out)


def _renumber(findings: list[Finding]) -> list[Finding]:
    return [f.model_copy(update={"id": f"f_{n:02d}"}) for n, f in enumerate(findings, 1)]
