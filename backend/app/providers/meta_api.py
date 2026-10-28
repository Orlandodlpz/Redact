"""Meta Model API client: OpenAI compatible calls, SAM output parsing, cost log.
Owner: Orlando.

Every call appends metadata to logs/cost.jsonl. Never log image bytes, data URLs,
prompts or request bodies anywhere in this module.
"""

import base64
import io
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import openai
from meta_sam_parser import (
    SegmentationBoxRecord,
    SegmentationMask,
    SegmentationMaskRecord,
    image_segmentation_format,
    parse_responses_stream,
)
from PIL import Image

from app.config import Settings

# Estimates from docs/CLAUDE.md Environment, not invoices.
MUSE_SPARK_USD_PER_M_INPUT = 1.25
MUSE_SPARK_USD_PER_M_OUTPUT = 4.25  # reasoning tokens bill as output
SAM_USD_PER_REQUEST = 2.50 / 1000

DEFAULT_COST_LOG = Path("logs/cost.jsonl")


@dataclass
class CallStats:
    model: str
    kind: str
    ok: bool
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    est_cost_usd: float | None = None
    error: str | None = None


class CostLog:
    def __init__(self, path: Path = DEFAULT_COST_LOG):
        self.path = path

    def write(self, stats: CallStats, **meta: Any) -> None:
        """meta must be small labels (run id, phrase, effort), never image data."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.time(), **asdict(stats), **meta}
        with self.path.open("a") as f:
            f.write(json.dumps(row) + "\n")


def image_data_url(image: Image.Image, fmt: str = "JPEG", quality: int = 90) -> str:
    """Re-encodes without metadata, so EXIF and GPS never leave the server."""
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format=fmt, quality=quality)
    mime = "image/jpeg" if fmt == "JPEG" else f"image/{fmt.lower()}"
    return f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode()}"


def _usage_tokens(usage: Any) -> tuple[int | None, int | None, int | None]:
    """Reads Chat Completions or Responses usage objects."""
    if usage is None:
        return None, None, None
    inp = _first_set(usage, "input_tokens", "prompt_tokens")
    out = _first_set(usage, "output_tokens", "completion_tokens")
    details = _first_set(usage, "output_tokens_details", "completion_tokens_details")
    reasoning = getattr(details, "reasoning_tokens", None) if details else None
    return inp, out, reasoning


def _first_set(obj: Any, *names: str) -> Any:
    # Not `or`: a count of 0 is a real value.
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _spark_cost(inp: int | None, out: int | None) -> float | None:
    if inp is None or out is None:
        return None
    return inp * MUSE_SPARK_USD_PER_M_INPUT / 1e6 + out * MUSE_SPARK_USD_PER_M_OUTPUT / 1e6


@dataclass
class SamMatch:
    object_id: str
    # Half-open pixel box [left, top, right, bottom] in the sent image's coordinates.
    box: list[int]
    confidence: float | None
    # Raster covering box only, not the full image.
    mask: SegmentationMask


@dataclass
class SamResult:
    matches: list[SamMatch]
    stats: CallStats
    diagnostics: list[str] = field(default_factory=list)
    text: list[str] = field(default_factory=list)


@dataclass
class ChatResult:
    text: str | None
    stats: CallStats


class MetaClient:
    def __init__(self, settings: Settings, cost_log: CostLog | None = None):
        if settings.meta_api_key is None:
            raise ValueError("META_API_KEY is not set")
        self.settings = settings
        self.cost_log = cost_log or CostLog()
        self._client = openai.AsyncOpenAI(
            api_key=settings.meta_api_key.get_secret_value(),
            base_url=settings.meta_base_url,
            max_retries=0,  # retries are a pipeline decision, and they hide latency
        )

    async def sam(
        self,
        image: Image.Image | str,
        text: str,
        *,
        model: str | None = None,
        include_confidence: bool = True,
        **meta: Any,
    ) -> SamResult:
        """One SAM 3.1 request. text is a noun phrase or build_object_prompt() output.

        image may be an image_data_url() string, so a sweep encodes once, not per phrase.
        """
        model = model or self.settings.sam_model
        url = image if isinstance(image, str) else image_data_url(image)
        usage_box: dict[str, Any] = {}
        start = time.perf_counter()
        try:
            stream = await self._client.responses.create(
                model=model,
                input=[{
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": url},
                        {"type": "input_text", "text": text},
                    ],
                }],
                metadata={"include_confidence": "true"} if include_confidence else openai.NOT_GIVEN,
                stream=True,
            )

            async def events():
                try:
                    async for event in stream:
                        if event.type == "response.completed":
                            usage_box["usage"] = event.response.usage
                        yield event
                finally:
                    await stream.close()

            result = await parse_responses_stream(events(), image_segmentation_format()).final_result()
        except Exception as e:
            stats = CallStats(model, "sam", False, _ms(start), est_cost_usd=0.0, error=_err(e))
            self.cost_log.write(stats, **meta)
            return SamResult([], stats)

        inp, out, reasoning = _usage_tokens(usage_box.get("usage"))
        stats = CallStats(model, "sam", True, _ms(start), inp, out, reasoning, SAM_USD_PER_REQUEST)
        self.cost_log.write(stats, **meta)

        boxes = {r.object_id: r for r in result.records if isinstance(r, SegmentationBoxRecord)}
        matches = [
            SamMatch(
                object_id=r.object_id,
                box=[r.bounds.left, r.bounds.top, r.bounds.right, r.bounds.bottom],
                confidence=r.confidence if r.confidence is not None else boxes[r.object_id].confidence,
                mask=r.mask,
            )
            for r in result.records
            if isinstance(r, SegmentationMaskRecord)
        ]
        return SamResult(
            matches,
            stats,
            diagnostics=[f"{d.severity}:{d.code}" for d in result.diagnostics],
            text=[r.text for r in result.records if getattr(r, "kind", None) == "text"],
        )

    async def chat_json(
        self,
        model: str,
        messages: list[dict],
        schema: dict,
        *,
        schema_name: str = "output",
        reasoning_effort: str | None = None,
        **meta: Any,
    ) -> ChatResult:
        """Chat Completions with strict structured output. Returns raw text; callers validate."""
        start = time.perf_counter()
        kwargs: dict[str, Any] = {}
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        try:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                },
                **kwargs,
            )
        except Exception as e:
            stats = CallStats(model, "chat", False, _ms(start), est_cost_usd=0.0, error=_err(e))
            self.cost_log.write(stats, reasoning_effort=reasoning_effort, **meta)
            return ChatResult(None, stats)

        inp, out, reasoning = _usage_tokens(resp.usage)
        stats = CallStats(model, "chat", True, _ms(start), inp, out, reasoning, _spark_cost(inp, out))
        self.cost_log.write(stats, reasoning_effort=reasoning_effort, **meta)
        return ChatResult(resp.choices[0].message.content, stats)

    async def close(self) -> None:
        await self._client.close()


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _err(e: Exception) -> str:
    # Type and status only: API error bodies can echo parts of the request.
    status = getattr(e, "status_code", None)
    return f"{type(e).__name__}" + (f" {status}" if status else "")
