import asyncio

import numpy as np
import pytest
from meta_sam_parser import SegmentationMask
from PIL import Image

from app.pipeline import sweep as sweep_module
from app.pipeline.sweep import SweepError, decode_rle, encode_rle, sweep
from app.providers.meta_api import CallStats, SamMatch, SamResult


@pytest.fixture(autouse=True)
def fake_decoder(monkeypatch):
    # Test masks carry their raster in payload, one character per pixel.
    monkeypatch.setattr(sweep_module, "decode_mask_to_raster", lambda m: m.payload.encode("latin-1"))
    monkeypatch.setattr(sweep_module, "RETRY_DELAY_S", 0)


def match(box, rows, confidence=0.9):
    """rows like ["11", "01"]: the raster SAM sent, before scaling to box."""
    payload = "".join(rows).replace("1", "\x01").replace("0", "\x00")
    mask = SegmentationMask(encoding="lossless", payload=payload, width=len(rows[0]), height=len(rows))
    return SamMatch(object_id="1", box=box, confidence=confidence, mask=mask)


class FakeClient:
    def __init__(self, matches=None, fail=None):
        self.matches = matches or {}  # phrase -> list[SamMatch]
        self.fail = fail or {}  # phrase -> how many calls fail before one succeeds
        self.calls = []

    async def sam(self, image, text, **meta):
        self.calls.append((image, text, meta))
        ok = self.fail.get(text, 0) <= 0
        self.fail[text] = self.fail.get(text, 0) - 1
        stats = CallStats("sam-3.1", "sam", ok, 10)
        return SamResult(self.matches.get(text, []) if ok else [], stats)


def run(image, client, **kw):
    return asyncio.run(sweep(image, client, **kw))


def test_mask_scaled_to_box_and_placed_on_full_canvas():
    client = FakeClient({"face": [match([10, 20, 30, 40], ["11", "11"], 0.91234)]})
    [c] = run(Image.new("RGB", (100, 80)), client, phrases=("face",))
    assert c.source == "sam" and c.sam_label == "face" and c.kind == "face"
    assert c.box == [10, 20, 30, 40] and c.score == 0.9123 and c.mark is None
    full = decode_rle(c.mask_rle, 100, 80)
    assert full.shape == (80, 100)
    assert full[20:40, 10:30].all() and full.sum() == 20 * 20


def test_low_res_raster_upscaled_to_box():
    # Left half on, sent at 2 x 1 for a 40 x 10 box.
    client = FakeClient({"sticky note": [match([0, 0, 40, 10], ["10"])]})
    [c] = run(Image.new("RGB", (50, 10)), client, phrases=("sticky note",))
    full = decode_rle(c.mask_rle, 50, 10)
    assert full[:, :18].all() and not full[:, 22:].any()


def test_box_past_the_edge_is_clamped():
    client = FakeClient({"face": [match([-5, -5, 10, 10], ["1"])]})
    [c] = run(Image.new("RGB", (20, 20)), client, phrases=("face",))
    assert c.box == [0, 0, 10, 10]
    assert decode_rle(c.mask_rle, 20, 20).sum() == 100


def test_box_outside_image_dropped_and_empty_mask_left_unset():
    client = FakeClient({"face": [match([30, 30, 40, 40], ["1"]), match([0, 0, 4, 4], ["0"])]})
    [c] = run(Image.new("RGB", (20, 20)), client, phrases=("face",))
    assert c.box == [0, 0, 4, 4] and c.mask_rle is None


def test_one_request_per_phrase_with_one_encoded_image():
    client = FakeClient({"face": [match([0, 0, 2, 2], ["1"])], "QR code": [match([2, 2, 4, 4], ["1"])]})
    out = run(Image.new("RGB", (8, 8)), client, phrases=("face", "QR code", "envelope"), run="t", img="a")
    assert [c.sam_label for c in out] == ["face", "QR code"]
    assert [text for _, text, _ in client.calls] == ["face", "QR code", "envelope"]
    images = {image for image, _, _ in client.calls}
    assert len(images) == 1 and next(iter(images)).startswith("data:image/jpeg;base64,")
    assert all(m["run"] == "t" and m["img"] == "a" and m["step"] == "sweep" for _, _, m in client.calls)


def test_failed_phrase_retried_once():
    client = FakeClient({"face": [match([0, 0, 2, 2], ["1"])]}, fail={"face": 1})
    [c] = run(Image.new("RGB", (8, 8)), client, phrases=("face", "envelope"))
    assert c.sam_label == "face"
    assert [m["attempt"] for _, text, m in client.calls if text == "face"] == [0, 1]


def test_phrase_failing_twice_raises_instead_of_returning_fewer_masks():
    client = FakeClient({"face": [match([0, 0, 2, 2], ["1"])]}, fail={"house number": 2, "QR code": 5})
    with pytest.raises(SweepError) as e:
        run(Image.new("RGB", (8, 8)), client, phrases=("face", "house number", "QR code"))
    assert e.value.phrases == ["house number", "QR code"]


def test_rle_round_trip_matches_pycocotools_layout():
    mask = np.zeros((3, 4), dtype=np.uint8)
    mask[0, 1] = mask[2, 3] = 1
    counts = encode_rle(mask)
    assert isinstance(counts, str)
    assert (decode_rle(counts, 4, 3) == mask).all()
