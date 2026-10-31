import asyncio
import io

import pytest
from PIL import Image

from app.config import Settings
from app.pipeline import run as run_module
from app.pipeline.sweep import SweepError
from app.providers.meta_api import CallStats, ChatResult, SamResult
from app.schemas import Candidate, Finding, JudgeOutput


def jpeg(gps=False) -> bytes:
    exif = Image.Exif()
    if gps:
        exif[0x8825] = {2: (26.0, 18.0, 0.0), 4: (98.0, 10.0, 0.0)}
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), "white").save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


class FakeClient:
    def __init__(self):
        self.closed = False

    async def sam(self, image, text, **meta):
        return SamResult([], CallStats("sam-3.1", "sam", True, 5, est_cost_usd=0.0025))

    async def chat_json(self, *args, **meta):
        return ChatResult("{}", CallStats("muse", "chat", True, 5, est_cost_usd=0.013))

    async def close(self):
        self.closed = True


EMPTY = JudgeOutput(verdicts=[], extra_findings=[], combined_leaks=[], instruction_text=[])


@pytest.fixture
def steps(monkeypatch):
    """Fakes for every step after ingest; records what merge received."""
    seen = {}
    monkeypatch.setattr(run_module, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(run_module, "ocr", lambda image, **kw: [
        Candidate(source="ocr", text="PWD: x", box=[1, 1, 30, 10])])

    async def fake_sweep(image, client, **meta):
        await client.sam("url", "face")
        return [Candidate(source="sam", sam_label="face", box=[0, 20, 20, 40], score=0.9)]

    async def fake_judge(image, marked, candidates, destination, client):
        seen["marked_size"] = marked.size
        await client.chat_json("muse", [], {})
        return seen.get("judge_returns", EMPTY)

    def fake_merge(candidates, floor_hits, judge_output, destination):
        seen.update(candidates=candidates, judge_output=judge_output, floor=floor_hits)
        return [Finding(id="1", marks=[1], category="credential", reason="r", source="floor",
                        masked=True, locked=True, box=[1, 1, 30, 10])]

    monkeypatch.setattr(run_module, "sweep", fake_sweep)
    monkeypatch.setattr(run_module, "judge", fake_judge)
    monkeypatch.setattr(run_module, "merge", fake_merge)
    monkeypatch.setattr(run_module, "find_floor_hits", lambda cands: ["floor"])
    return seen


def analyze(data, client, dest="public"):
    return asyncio.run(run_module.analyze(data, dest, client=client))


def test_full_run_wires_every_step(steps):
    client = FakeClient()
    res = analyze(jpeg(), client, "team")
    assert res.judge_status == "ok" and res.destination == "team"
    assert (res.width, res.height) == (64, 48) and len(res.image_id) == 16
    assert [c.mark for c in steps["candidates"]] == [1, 2]  # numbered before floor and judge
    assert steps["floor"] == ["floor"] and steps["marked_size"] == (64, 48)
    assert res.est_cost_usd == pytest.approx(0.0155)
    assert set(res.timings_ms) == {"ingest", "ocr", "sweep", "candidates", "floor", "marks", "judge", "merge", "total"}
    assert res.model_ids == {"judge": "muse-spark-1.3", "sam": "sam-3.1"}
    assert not client.closed  # the caller's client stays open


@pytest.mark.parametrize("judge_returns", [None, "raise"])
def test_judge_failure_fails_closed(steps, monkeypatch, judge_returns):
    if judge_returns == "raise":
        async def broken(*a, **k):
            raise TimeoutError
        monkeypatch.setattr(run_module, "judge", broken)
    else:
        steps["judge_returns"] = None
    res = analyze(jpeg(), FakeClient())
    assert res.judge_status == "failed_closed" and steps["judge_output"] is None
    assert res.findings  # merge still ran


def test_gps_reported_as_locked_metadata_finding(steps):
    res = analyze(jpeg(gps=True), FakeClient())
    assert res.findings[0].source == "metadata" and res.findings[0].locked
    assert res.findings[0].box is None


def test_sweep_error_propagates_and_own_client_is_closed(steps, monkeypatch):
    made = FakeClient()
    monkeypatch.setattr(run_module, "MetaClient", lambda settings: made)

    async def failing(*a, **k):
        raise SweepError(["face"])
    monkeypatch.setattr(run_module, "sweep", failing)
    with pytest.raises(SweepError):
        analyze(jpeg(), None)
    assert made.closed


def test_premask_on_is_refused_not_ignored(monkeypatch):
    monkeypatch.setattr(run_module, "get_settings", lambda: Settings(_env_file=None, premask=True))
    with pytest.raises(NotImplementedError):
        analyze(jpeg(), FakeClient())
