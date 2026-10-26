"""Floor rules: Luhn, key/password patterns, entropy, class rules. Owner: Victor. Phase 2.

Floor hits are always masked and the model cannot override them.
"""

from app.schemas import Candidate, Finding


def find_floor_hits(candidates: list[Candidate]) -> list[Finding]:
    """Returns findings with locked=True."""
    raise NotImplementedError
