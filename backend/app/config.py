"""Model IDs, sweep phrases, thresholds and the startup safety checks.

Values marked provisional come from the Provisional Values table in docs/CLAUDE.md
and get replaced by measurements. Change them there first, then here.
"""

import logging
import os
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

VERSION = "0.1.0"

# SAM 3.1 concept sweep vocabulary (provisional, 16 phrases).
SWEEP_PHRASES: tuple[str, ...] = (
    "face",
    "license plate",
    "ID card",
    "credit card",
    "paper document",
    "envelope",
    "name badge",
    "computer monitor",
    "laptop screen",
    "phone screen",
    "whiteboard",
    "sticky note",
    "QR code",
    "barcode",
    "house number",
    "street sign",
)

# SAM classes masked on the fail closed path when the judge is unavailable.
# Every sweep class except street sign: screens, documents, whiteboards and
# sticky notes are where text secrets live. Confirmed by the team Oct 26.
HIGH_RISK_SAM_CLASSES: frozenset[str] = frozenset(SWEEP_PHRASES) - {"street sign"}

# Two SAM matches whose boxes overlap at least this much are one object (provisional).
CANDIDATE_DEDUPE_IOU = 0.8

# RapidOCR detection thresholds (provisional, loose). Looser than the library
# defaults so handwritten lines get a box even when the text reads badly (gotcha 31).
OCR_ENGINE_PARAMS: dict[str, float] = {
    "Det.thresh": 0.2,
    "Det.box_thresh": 0.4,
    "Det.unclip_ratio": 2.0,
    "Global.text_score": 0.4,
}

# Loggers that write request bodies (base64 images included) at DEBUG.
# The openai SDK logs full request options at DEBUG.
_BODY_LOGGING_LOGGERS = ("openai", "httpx", "httpcore")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    meta_api_key: SecretStr | None = None
    meta_base_url: str = "https://api.meta.ai/v1"

    # Provisional until the Oct 27 judge bake off.
    judge_model: str = "muse-spark-1.3"
    judge_reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh"] = "low"
    # Unverified ID string until the Phase 1 smoke test.
    sam_model: str = "sam-3.1"

    premask: bool = False
    log_request_bodies: bool = False

    # Provisional, see docs/CLAUDE.md Provisional Values.
    max_image_edge_px: int = 2048
    # OCR is local, so it reads a larger copy than the API ever sees (gotcha 33).
    ocr_max_edge_px: int = 4096
    mask_dilation_px: int = 4
    max_upload_bytes: int = 20 * 1024 * 1024

    def model_ids(self) -> dict[str, str]:
        return {"judge": self.judge_model, "sam": self.sam_model}


class StartupError(RuntimeError):
    pass


def startup_problems(settings: Settings) -> list[str]:
    """Every reason the service must not start. Empty list means safe."""
    problems = []
    for role, model_id in settings.model_ids().items():
        if "contributor" in model_id.lower():
            problems.append(
                f"{role} model '{model_id}' is a contributor tier ID; that tier trains on our inputs"
            )
    if settings.log_request_bodies:
        problems.append("LOG_REQUEST_BODIES is on; request bodies carry user images")
    if os.environ.get("OPENAI_LOG", "").lower() == "debug":
        problems.append("OPENAI_LOG=debug makes the openai SDK log request bodies")
    for name in _BODY_LOGGING_LOGGERS:
        if logging.getLogger(name).isEnabledFor(logging.DEBUG):
            problems.append(f"logger '{name}' is at DEBUG and can log request bodies")
    return problems


def assert_startup_safe(settings: Settings) -> None:
    problems = startup_problems(settings)
    if problems:
        raise StartupError("Refusing to start: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
