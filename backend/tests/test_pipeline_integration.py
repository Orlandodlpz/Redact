"""The whole pipeline, every real module, only the network faked.

Why this file exists. Two bugs got six days into this project because every test that
touched a step replaced the step next to it:

- Gotcha 40: run.py catches any judge exception and fails closed, so a judge with the
  wrong signature looked like a working fail closed run.
- Gotcha 41: floor.find_floor_hits raised NotImplementedError and run.py calls it
  outside any try, so every real analyze crashed. 155 tests passed anyway, because the
  only test that reaches it monkeypatches it.

Both are the same failure: a green suite over a pipeline that cannot run. The fix is a
test that fakes exactly one thing, the two network calls, and runs everything else for
real: ingest, OCR, candidates, floor, marks, merge, compose and the routes. If a
signature drifts or a step raises, it fails here.

What this does not do is check that the models are any good. The judge's answers are
written by hand. Accuracy is the eval's job.
"""

import io
import json
import pathlib

import pytest
from fastapi.testclient import TestClient
from meta_sam_parser import SegmentationMask
from PIL import Image, ImageDraw, ImageFont

from app import main
from app.config import get_settings
from app.pipeline import sweep as sweep_module
from app.pipeline.run import analyze
from app.providers.meta_api import CallStats, ChatResult, SamMatch, SamResult
from app.schemas import AnalyzeResponse

FONTS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

# Where each line is drawn, so the fake SAM can return boxes that sit on real content.
LINES = {
    "notes": (40, 40, "Sprint notes: ship the export path"),
    "wifi": (40, 130, "wifi password: guest2026"),
    "card": (40, 220, "card 4532 0151 1283 0366"),
    "demo": (40, 310, "demo at 3pm in room 204"),
}
CARD_REGION = [20, 200, 700, 290]
MONITOR_REGION = [760, 60, 1160, 420]


@pytest.fixture(autouse=True)
def fake_mask_wire_format(monkeypatch):
    """SAM's mask payload is a range coded wire format, so a hand built one cannot be
    decoded. Faking the network means faking its encoding too: here a payload is just
    its bytes, one per pixel. Everything the pipeline does with the decoded raster,
    scaling it to the box and pasting it on the full canvas, still runs for real."""
    monkeypatch.setattr(sweep_module, "decode_mask_to_raster",
                        lambda m: m.payload.encode("latin-1"))
    monkeypatch.setattr(sweep_module, "RETRY_DELAY_S", 0)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "test-key-not-real")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")
    monkeypatch.setenv("PREMASK", "off")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def font_or_skip() -> ImageFont.FreeTypeFont:
    path = next((p for p in FONTS if pathlib.Path(p).exists()), None)
    if path is None:
        pytest.skip("no TrueType font available to draw readable text for OCR")
    return ImageFont.truetype(path, 44)


@pytest.fixture(scope="module")
def photo() -> bytes:
    """A drawn stand in for a desk photo. Nothing here is real: the password is made up
    and the card number is a published test number that belongs to no account.

    Drawn rather than photographed so the repo holds no staged image, and drawn large
    enough that RapidOCR reads every line, which is what makes the floor rules below a
    real check instead of a mocked one.
    """
    font = font_or_skip()
    img = Image.new("RGB", (1200, 500), (250, 250, 248))
    d = ImageDraw.Draw(img)
    for x, y, text in LINES.values():
        d.text((x, y), text, fill=(20, 20, 20), font=font)
    d.rectangle(MONITOR_REGION, outline=(60, 60, 70), width=6)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def plain_photo() -> bytes:
    """No text at all, so the only candidate is whatever the fake SAM returns and its
    mark is 1. Marks are numbered in reading order across OCR lines and SAM regions
    together, so a test that hardcodes one has to control what else is in the image."""
    buf = io.BytesIO()
    Image.new("RGB", (1200, 500), (236, 234, 230)).save(buf, format="PNG")
    return buf.getvalue()


def sam_match(box, object_id="1", confidence=0.9) -> SamMatch:
    """A match whose mask fills its whole box, which is what a solid object looks like."""
    mask = SegmentationMask(encoding="lossless", payload="\x01" * 16, width=4, height=4)
    # payload is read by the fake decoder above: 16 bytes for a 4 by 4 raster, all set.
    return SamMatch(object_id=object_id, box=list(box), confidence=confidence, mask=mask)


class StubMeta:
    """Stands in for MetaClient. Only sam() and chat_json() are faked, because only
    those two cross the network. Everything that calls them is the real thing."""

    def __init__(self, *, matches=None, judge=None, judge_fails=False):
        self.matches = matches or {}
        self.judge = judge
        self.judge_fails = judge_fails
        self.sam_calls: list[str] = []
        self.judge_calls = 0

    async def sam(self, image, text, **meta) -> SamResult:
        self.sam_calls.append(text)
        return SamResult(
            matches=self.matches.get(text, []),
            stats=CallStats(model="sam-3.1", kind="sam", ok=True, latency_ms=5,
                            est_cost_usd=0.0025),
        )

    async def chat_json(self, *args, **kwargs) -> ChatResult:
        self.judge_calls += 1
        text = "not json at all" if self.judge_fails else json.dumps(self.judge)
        return ChatResult(
            text=text,
            stats=CallStats(model="muse-spark-1.3", kind="chat", ok=True, latency_ms=9,
                            input_tokens=8000, output_tokens=400, est_cost_usd=0.0129),
        )

    async def close(self):
        pass


def judge_says(verdicts, **rest) -> dict:
    return {
        "verdicts": verdicts,
        "extra_findings": rest.get("extra_findings", []),
        "combined_leaks": rest.get("combined_leaks", []),
        "instruction_text": rest.get("instruction_text", []),
    }


def all_benign(candidate_count: int = 40) -> dict:
    """Every mark called harmless. A judge that says this must not clear a floor hit."""
    return judge_says([
        {"mark": n, "sensitive": False, "category": "benign",
         "reason": "nothing here", "confidence": "high"}
        for n in range(1, candidate_count + 1)
    ])


# --- the whole chain ----------------------------------------------------------


@pytest.mark.anyio
async def test_whole_pipeline_runs_with_only_the_network_faked(photo):
    """Ingest, OCR, candidates, floor, marks, judge, merge, for real, in order."""
    client = StubMeta(
        matches={"credit card": [sam_match(CARD_REGION)],
                 "computer monitor": [sam_match(MONITOR_REGION, object_id="2")]},
        judge=all_benign(),
    )
    result = await analyze(photo, "public", client=client)

    assert isinstance(result, AnalyzeResponse)
    assert result.judge_status == "ok", "the judge ran, so this is not the fail closed path"
    assert client.judge_calls == 1, "one judge call per image"
    assert len(client.sam_calls) == 16, "the sweep sends one request per phrase"
    assert set(result.timings_ms) >= {"ingest", "ocr", "sweep", "candidates", "floor",
                                      "marks", "judge", "merge", "total"}
    assert result.est_cost_usd > 0
    assert result.prompt_version != "unset", "judge.py exports PROMPT_VERSION"


@pytest.mark.anyio
async def test_floor_hits_survive_a_judge_that_calls_everything_benign(photo):
    """The hard constraint: the model cannot clear a floor item, only the user can."""
    client = StubMeta(
        matches={"credit card": [sam_match(CARD_REGION)]},
        judge=all_benign(),
    )
    result = await analyze(photo, "public", client=client)

    floor = [f for f in result.findings if f.source == "floor"]
    assert floor, "a credit card region and a password line are both floor hits"
    assert all(f.masked and f.locked for f in floor)

    categories = {f.category for f in floor}
    assert "payment" in categories, "the SAM credit card class, or the card number line"
    assert "credential" in categories, "the wifi password line OCR read"


@pytest.mark.anyio
async def test_the_password_line_is_found_by_reading_the_image(photo):
    """OCR to candidates to floor, with no help: the password line is only in pixels."""
    client = StubMeta(judge=all_benign())
    result = await analyze(photo, "public", client=client)

    credential = [f for f in result.findings
                  if f.source == "floor" and f.category == "credential"]
    assert credential, "OCR read the line and a floor rule fired on it"
    assert credential[0].box is not None
    x1, y1, x2, y2 = credential[0].box
    assert y1 < 200 and x1 < 100, "the box sits on the line that was drawn there"
    # The reason must not carry the secret back out to the user.
    assert "guest2026" not in credential[0].reason


@pytest.mark.anyio
async def test_a_broken_judge_fails_closed_and_says_so(photo):
    """Invalid output twice means no verdicts, so everything high risk masks."""
    client = StubMeta(
        matches={"computer monitor": [sam_match(MONITOR_REGION)],
                 "credit card": [sam_match(CARD_REGION)]},
        judge_fails=True,
    )
    result = await analyze(photo, "public", client=client)

    assert result.judge_status == "failed_closed"
    assert client.judge_calls == 2, "one retry, then give up"
    assert [f for f in result.findings if f.source == "floor" and f.locked]
    reasons = " ".join(f.reason for f in result.findings)
    assert "unavailable" in reasons.lower(), "the user is told the judge was down"


@pytest.mark.anyio
async def test_an_incomplete_scan_raises_instead_of_returning_fewer_masks(photo):
    """A phrase that never succeeds must not come back as a result with less in it."""
    from app.pipeline.sweep import SweepError

    class Failing(StubMeta):
        async def sam(self, image, text, **meta):
            self.sam_calls.append(text)
            if text == "face":
                return SamResult(matches=[], stats=CallStats(
                    model="sam-3.1", kind="sam", ok=False, latency_ms=5, error="boom"))
            return await super().sam(image, text, **meta)

    with pytest.raises(SweepError):
        await analyze(photo, "public", client=Failing(judge=all_benign()))


@pytest.mark.anyio
async def test_the_destination_changes_what_is_masked(plain_photo):
    """A face is masked for a public post and kept for a team chat. Same image.

    This is the claim the whole project rests on, so it is checked against the real
    policy table through the real merge, not against a mock of either.
    """
    face_box = [800, 100, 1000, 300]
    verdict = judge_says([{"mark": 1, "sensitive": False, "category": "face",
                           "reason": "a colleague", "confidence": "high"}])

    def run_for(destination):
        return analyze(plain_photo, destination, client=StubMeta(
            matches={"face": [sam_match(face_box)]}, judge=verdict))

    public = await run_for("public")
    team = await run_for("team")
    faces_public = [f for f in public.findings if f.category == "face"]
    faces_team = [f for f in team.findings if f.category == "face"]
    assert faces_public and faces_public[0].masked, "public post masks faces"
    assert not any(f.masked for f in faces_team), "team chat keeps them"


# --- through the routes, to a file --------------------------------------------


@pytest.mark.anyio
async def test_analyze_then_export_through_the_routes(photo, monkeypatch):
    """The path a user takes: POST the image, edit nothing, POST it back, get a PNG."""
    client = StubMeta(matches={"credit card": [sam_match(CARD_REGION)]}, judge=all_benign())
    monkeypatch.setattr(main, "MetaClient", lambda settings: client)

    with TestClient(main.create_app()) as http:
        analyzed = http.post(
            "/analyze",
            files={"image": ("desk.png", io.BytesIO(photo), "image/png")},
            data={"destination": "public"},
        )
        assert analyzed.status_code == 200, analyzed.text
        body = analyzed.json()
        assert body["judge_status"] == "ok"
        assert body["findings"], "something on this desk is worth masking"

        exported = http.post(
            "/export",
            files={"image": ("desk.png", io.BytesIO(photo), "image/png")},
            data={"findings": json.dumps(body["findings"])},
        )
        assert exported.status_code == 200
        out = Image.open(io.BytesIO(exported.content))

    assert out.format == "PNG"
    assert out.info == {} and not out.getexif(), "no metadata survives the export"
    assert (out.width, out.height) == (body["width"], body["height"])

    # The card line was drawn at y 220 to 270 in the source. Check it went black in the
    # exported file, at the exported file's scale.
    scale = out.width / 1200
    assert out.getpixel((int(200 * scale), int(240 * scale))) == (0, 0, 0)


@pytest.fixture
def anyio_backend():
    return "asyncio"
