"""A fake model, so the harness can be exercised without a key or a bill.

This calls nothing. SAM returns no matches, which leaves OCR lines as the only
candidates, and the judge calls every one of them harmless. That is the worst honest
case for the floor: a model that agrees with the injected note on every single mark.

What a stub run proves: the harness reads both images, lines the two runs up, and the
floor survives a model that says nothing is sensitive. What it cannot prove is anything
about the real judge. For that the run needs a key and no --stub.
"""

import json

from app.providers.meta_api import CallStats, ChatResult, SamResult

MAX_MARKS = 200


class StubClient:
    def __init__(self) -> None:
        self.sam_calls = 0
        self.judge_calls = 0

    async def sam(self, image, text, **meta) -> SamResult:
        self.sam_calls += 1
        return SamResult(
            matches=[],
            stats=CallStats(model="stub", kind="sam", ok=True, latency_ms=0,
                            est_cost_usd=0.0),
        )

    async def chat_json(self, *args, **kwargs) -> ChatResult:
        self.judge_calls += 1
        verdicts = [
            {"mark": n, "sensitive": False, "category": "benign",
             "reason": "stub says nothing here", "confidence": "high"}
            for n in range(1, MAX_MARKS + 1)
        ]
        body = {"verdicts": verdicts, "extra_findings": [], "combined_leaks": [],
                "instruction_text": []}
        return ChatResult(
            text=json.dumps(body),
            stats=CallStats(model="stub", kind="chat", ok=True, latency_ms=0,
                            est_cost_usd=0.0),
        )

    async def close(self) -> None:
        pass
