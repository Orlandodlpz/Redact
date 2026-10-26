import base64
import io
import json
from types import SimpleNamespace

from PIL import Image

from app.providers.meta_api import CallStats, CostLog, _usage_tokens, image_data_url


def test_data_url_strips_exif_and_gps():
    exif = Image.Exif()
    exif[0x8825] = {2: (26.0, 18.0, 0.0)}  # GPSInfo with a latitude
    exif[0x010F] = "PhoneMaker"
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="JPEG", exif=exif)
    assert Image.open(io.BytesIO(buf.getvalue())).getexif()  # fixture really has EXIF

    url = image_data_url(Image.open(io.BytesIO(buf.getvalue())))
    sent = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert url.startswith("data:image/jpeg;base64,")
    assert not sent.getexif()
    assert "exif" not in sent.info


def test_usage_zero_counts_are_kept():
    responses = SimpleNamespace(input_tokens=0, output_tokens=12,
                                output_tokens_details=SimpleNamespace(reasoning_tokens=0))
    assert _usage_tokens(responses) == (0, 12, 0)
    chat = SimpleNamespace(prompt_tokens=8753, completion_tokens=454,
                           completion_tokens_details=SimpleNamespace(reasoning_tokens=248))
    assert _usage_tokens(chat) == (8753, 454, 248)
    assert _usage_tokens(None) == (None, None, None)


def test_cost_log_writes_metadata_rows(tmp_path):
    log = CostLog(tmp_path / "logs" / "cost.jsonl")
    log.write(CallStats("sam-3.1", "sam", True, 1201, est_cost_usd=0.0025), run="t", phrase="face")
    row = json.loads((tmp_path / "logs" / "cost.jsonl").read_text())
    assert row["model"] == "sam-3.1" and row["phrase"] == "face" and row["latency_ms"] == 1201
