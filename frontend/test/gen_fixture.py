"""Build the offline fixture: a clearly fake image plus the AnalyzeResponse for it.

Run from the repo root: uv run python frontend/test/gen_fixture.py

The fixture is what the review editor renders when the backend is not running, so the
UI can be built and demonstrated on its own. The image is drawn here rather than
photographed, so there is no real person, document or card in the repo, and the boxes
in the JSON are the same numbers the drawing used. Nothing in it is a measurement:
timings and cost are zeros, because no model ran.
"""

import json
import pathlib

from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent
PUBLIC = HERE.parent / "public"
WIDTH, HEIGHT = 800, 600

WHITEBOARD = (60, 70, 520, 330)
STICKY = (570, 120, 740, 280)
CARD = (90, 400, 420, 540)
LINES = {
    "goals": (84, 110, 420, 138),
    "wifi": (84, 160, 470, 190),
    "demo": (84, 212, 330, 240),
    "key": (586, 180, 730, 206),
    "card_number": (112, 470, 390, 500),
}


def draw() -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), (214, 212, 206))
    d = ImageDraw.Draw(img)
    d.rectangle(WHITEBOARD, fill=(248, 248, 246), outline=(150, 150, 146), width=3)
    d.text((84, 82), "SPRINT 14", fill=(60, 60, 64))
    d.text((LINES["goals"][0], LINES["goals"][1]), "Goals: ship the export path", fill=(40, 40, 48))
    d.text((LINES["wifi"][0], LINES["wifi"][1]), "wifi password: guest2026!", fill=(176, 36, 36))
    d.text((LINES["demo"][0], LINES["demo"][1]), "demo at 3pm, room 204", fill=(40, 40, 48))

    d.rectangle(STICKY, fill=(252, 226, 120), outline=(214, 186, 80), width=2)
    d.text((586, 150), "deploy key", fill=(70, 60, 20))
    d.text((LINES["key"][0], LINES["key"][1]), "AKIAIOSFODNN7EXAMPLE", fill=(70, 60, 20))

    d.rectangle(CARD, fill=(46, 84, 150), outline=(30, 58, 110), width=3)
    d.rectangle((112, 430, 168, 462), fill=(214, 186, 90))
    d.text((LINES["card_number"][0], LINES["card_number"][1]),
           "4532 0151 1283 0366", fill=(240, 242, 248))
    d.text((112, 512), "VALID THRU 12/28", fill=(210, 216, 230))
    return img


def finding(fid, marks, category, reason, source, masked, locked, box):
    return {"id": fid, "marks": marks, "category": category, "reason": reason,
            "source": source, "masked": masked, "locked": locked,
            "box": list(box), "mask_rle": None}


def response() -> dict:
    return {
        "image_id": "fixture000000000",
        "width": WIDTH,
        "height": HEIGHT,
        "destination": "public",
        "findings": [
            finding("f_01", [4], "credential",
                    "This line puts a value next to a password or key label, so it is masked for every destination",
                    "floor", True, True, LINES["wifi"]),
            finding("f_02", [9], "credential",
                    "This line matches a known API key or token format, so it is masked for every destination",
                    "floor", True, True, LINES["key"]),
            finding("f_03", [11], "payment",
                    "A number on this line passes the card checksum, so it is masked for every destination",
                    "floor", True, True, LINES["card_number"]),
            finding("f_04", [10], "payment",
                    "A payment card is in this region, so it is masked for every destination",
                    "floor", True, True, CARD),
            finding("f_05", [3], "internal_data",
                    "A sprint goal naming unreleased work, masked because this is going to a public post",
                    "judge", True, False, LINES["goals"]),
            finding("f_06", [5], "benign",
                    "A meeting time and a room number, kept because neither identifies a person",
                    "judge", False, False, LINES["demo"]),
        ],
        "judge_status": "ok",
        "prompt_version": "judge_v1",
        "model_ids": {"judge": "muse-spark-1.3", "sam": "sam-3.1"},
        # No model ran to make this file, so there is nothing to time or bill.
        "timings_ms": {"ingest": 0, "ocr": 0, "sweep": 0, "candidates": 0, "floor": 0,
                       "marks": 0, "judge": 0, "merge": 0, "total": 0},
        "est_cost_usd": 0.0,
    }


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    draw().save(PUBLIC / "fixture.png", format="PNG")
    (HERE.parent / "fixtures").mkdir(exist_ok=True)
    (HERE.parent / "fixtures" / "analyze.sample.json").write_text(
        json.dumps(response(), indent=2) + "\n"
    )
    print("wrote public/fixture.png and fixtures/analyze.sample.json")


if __name__ == "__main__":
    main()
