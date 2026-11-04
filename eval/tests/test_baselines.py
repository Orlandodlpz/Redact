import asyncio
import json
from types import SimpleNamespace

import pytest
from PIL import Image

import run_eval
from baselines import b1_sam, b2_presidio, b3_muse
from app.providers.meta_api import CallStats


def test_b3_parse_clamps_and_drops_bad_boxes():
    text = json.dumps({"findings": [
        {"box": [90, 90, 120, 130], "category": "credential"},  # runs off the image
        {"box": [30, 30, 10, 10], "category": "face"},  # reversed corners
        {"box": [5, 5, 5, 20], "category": "payment"},  # empty
        {"box": [0, 0, 5, 5], "category": "benign"},  # not a category the baseline may report
    ]})
    assert b3_muse.parse(text, 100, 100) == [("credential", [90, 90, 100, 100]), ("face", [10, 10, 30, 30])]


@pytest.mark.parametrize("bad", ["not json", "{}", '{"findings": [{"box": [1, 2], "category": "face"}]}'])
def test_b3_parse_rejects_malformed_output(bad):
    with pytest.raises((ValueError, KeyError, IndexError)):
        b3_muse.parse(bad, 100, 100)


def test_b3_prompt_hash_is_recorded_and_stable():
    assert len(b3_muse.PROMPT_SHA) == 12 and "benign" not in b3_muse.CATEGORIES


class FakeEngine:
    def __init__(self, hits):
        self.hits = hits

    def analyze(self, text, language):
        return [SimpleNamespace(entity_type=e, score=s) for e, s in self.hits.get(text, [])]


def line(text, box):
    return SimpleNamespace(text=text, box=box)


def test_b2_flags_by_threshold_and_names_the_best_entity():
    engine = FakeEngine({"4242": [("CREDIT_CARD", 0.9), ("PHONE_NUMBER", 0.5)], "maybe": [("PERSON", 0.1)],
                         "odd": [("SOMETHING_NEW", 0.8)]})
    lines = [line("4242", [0, 0, 5, 5]), line("maybe", [0, 6, 5, 9]), line("odd", [0, 10, 5, 12]), line("hello", [0, 13, 5, 15])]
    out = b2_presidio.flag_lines(lines, engine)
    assert [(c.text, cat) for c, cat in out] == [("4242", "payment"), ("odd", "other_sensitive")]


def png_bytes():
    import io

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_b3_is_a_system_and_reports_cost_and_destination():
    class FakeClient:
        async def chat_json(self, *a, **k):
            body = json.dumps({"findings": [{"box": [1, 1, 9, 9], "category": "credential"}]})
            return SimpleNamespace(text=body, stats=CallStats("m", "chat", True, 5, est_cost_usd=0.02))

    out = asyncio.run(b3_muse.run(FakeClient(), png_bytes(), "team"))
    assert out.judge_status == "ok" and [f.category for f in out.findings] == ["credential"]
    assert out.est_cost_usd == 0.02 and out.destination == "team" and out.findings[0].source == "extra"


def test_b3_fails_closed_status_when_both_attempts_return_junk():
    class Junk:
        async def chat_json(self, *a, **k):
            return SimpleNamespace(text="nope", stats=CallStats("m", "chat", True, 5))

    out = asyncio.run(b3_muse.run(Junk(), png_bytes(), "public"))
    assert out.judge_status == "failed_closed" and out.findings == []


def test_b1_asks_sam_only_for_faces_and_plates_and_keeps_masks(monkeypatch):
    from app.schemas import Candidate

    asked = {}

    async def fake_sweep(image, client, *, phrases, **meta):
        asked["phrases"] = phrases
        return [Candidate(source="sam", sam_label="face", box=[4, 4, 20, 20], mask_rle="rle"),
                Candidate(source="sam", sam_label="license plate", box=[30, 30, 50, 40])]

    monkeypatch.setattr(b1_sam, "sweep", fake_sweep)
    out = asyncio.run(b1_sam.run(object(), png_bytes(), "ai_assistant"))
    assert asked["phrases"] == ("face", "license plate")
    assert [(f.category, f.mask_rle) for f in out.findings] == [("face", "rle"), ("license_plate", None)]


def test_baselines_are_registered_with_run_eval():
    assert {"redact", "b1", "b2", "b3"} <= set(run_eval.CONFIGS)
