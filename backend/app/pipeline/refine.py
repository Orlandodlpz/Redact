"""SAM 3.1 box prompts turn judge extra_findings into tight masks. Owner: Orlando. Phase 3."""

from PIL import Image

from app.schemas import Finding


def refine(image: Image.Image, findings: list[Finding]) -> list[Finding]:
    raise NotImplementedError
