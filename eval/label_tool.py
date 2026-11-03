"""Local labeling tool for the eval. Owner: Carlos.

    uv run python eval/label_tool.py            # then open http://127.0.0.1:8765

Why it exists: labels must be in the pipeline's coordinates. Phone photos are resized to
2048 px on ingest, so a box drawn on the original would not line up. The tool serves each
image at ingest size and writes eval/labels/<id>.json (eval/schemas.py Label).

Rules it follows:
- Listens on 127.0.0.1 only. Serves only files under eval/data/images. Logs no bodies.
- Boxes should be tight around the item. The 90 percent coverage rule is measured
  against the box area, so a loose box makes the item harder to catch.
- Each box says which destinations must mask it. The table pre-fills this to save clicks,
  but ground truth is a human decision: confirm it, especially on the triple labeled
  images, or destination accuracy only measures how well we match our own table.
- OCR line boxes are shown as faint suggestions (local OCR, nothing leaves the machine).
"""

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import get_args

from check_shot_list import parse_rows
from schemas import Label
from app.pipeline.ingest import ingest
from app.pipeline.ocr import ocr
from app.policy import TABLE
from app.schemas import Category, Destination, Finding

EVAL = Path(__file__).parent
IMAGES = EVAL / "data" / "images"
LABELS = EVAL / "labels"
HTML = EVAL / "label_tool.html"
DESTINATIONS: list[str] = list(get_args(Destination))
CATEGORIES: list[str] = [c for c in get_args(Category) if c != "benign"]
ID_RE = re.compile(r"^[A-Za-z0-9_]{1,40}$")
EXTS = ("jpg", "jpeg", "png", "webp", "heic")

_cache: dict[str, dict] = {}


def image_path(image_id: str) -> Path | None:
    if not ID_RE.match(image_id):
        return None
    return next((p for e in EXTS if (p := IMAGES / f"{image_id}.{e}").exists()), None)


def required_destinations(image_id: str) -> list[str]:
    """Triple labeled images (shot list flag 3) need every destination; the rest need public."""
    triple = {r["id"] for r in parse_rows() if r["triple"]}
    return DESTINATIONS if image_id in triple else ["public"]


def load_work(image_id: str) -> dict:
    """Ingested image as JPEG bytes for the browser, its size, and OCR suggestions."""
    if image_id not in _cache:
        r = ingest(image_path(image_id).read_bytes())
        buf = BytesIO()
        r.image.convert("RGB").save(buf, format="JPEG", quality=90)
        lines = ocr(r.ocr_image, scale=r.ocr_scale, bounds=(r.width, r.height))
        _cache[image_id] = {
            "jpeg": buf.getvalue(), "width": r.width, "height": r.height,
            "ocr": [{"box": c.box, "text": c.text} for c in lines],
        }
    return _cache[image_id]


def to_label(image_id: str, width: int, height: int, boxes: list[dict], required: list[str]) -> Label:
    """UI boxes [{box, category, dests, note}] -> Label. Raises ValueError on bad input."""
    per_dest: dict[str, list[Finding]] = {d: [] for d in required}
    for n, b in enumerate(boxes, 1):
        x1, y1, x2, y2 = (int(round(v)) for v in b["box"])
        x1, x2, y1, y2 = max(0, min(x1, x2)), min(width, max(x1, x2)), max(0, min(y1, y2)), min(height, max(y1, y2))
        if x2 - x1 < 2 or y2 - y1 < 2:
            raise ValueError(f"box {n} is empty")
        if b["category"] not in CATEGORIES:
            raise ValueError(f"box {n} has category {b['category']!r}")
        for d in b["dests"]:
            if d not in required:
                continue  # a destination this image is not labeled for
            per_dest[d].append(Finding(
                id=f"l_{n:02d}", marks=[], category=b["category"], reason=(b.get("note") or "labeled").strip(),
                source="judge", masked=True, locked=False, box=[x1, y1, x2, y2]))
    return Label(image_id=image_id, width=width, height=height, destinations=per_dest)


def from_label(label: Label) -> list[dict]:
    """Label -> UI boxes, merging the same box and category across destinations."""
    merged: dict[tuple, dict] = {}
    for dest, findings in label.destinations.items():
        for f in findings:
            key = (tuple(f.box), f.category)
            b = merged.setdefault(key, {"box": list(f.box), "category": f.category, "dests": [], "note": f.reason})
            b["dests"].append(dest)
    return list(merged.values())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # no request logging, bodies included
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        parts = self.path.split("?")[0].strip("/").split("/")
        if self.path == "/" or self.path.startswith("/?"):
            return self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
        if parts == ["api", "meta"]:
            return self._json({
                "categories": CATEGORIES, "destinations": DESTINATIONS,
                "baseline": {c: [d for d in DESTINATIONS if TABLE[c][d]] for c in CATEGORIES},
            })
        if parts == ["api", "images"]:
            ids = sorted({p.stem for p in IMAGES.glob("*.*") if ID_RE.match(p.stem)})
            return self._json([{"id": i, "labeled": (LABELS / f"{i}.json").exists(),
                                "required": required_destinations(i)} for i in ids])
        if len(parts) == 3 and parts[0] == "api" and image_path(parts[2]):
            work = load_work(parts[2])
            if parts[1] == "image":
                return self._send(200, work["jpeg"], "image/jpeg")
            if parts[1] == "image_info":
                lab = LABELS / f"{parts[2]}.json"
                boxes = from_label(Label.model_validate_json(lab.read_text())) if lab.exists() else []
                return self._json({"width": work["width"], "height": work["height"], "ocr": work["ocr"],
                                   "boxes": boxes, "required": required_destinations(parts[2])})
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        parts = self.path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "save"] and image_path(parts[2]):
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                work = load_work(parts[2])
                label = to_label(parts[2], work["width"], work["height"], body["boxes"],
                                 required_destinations(parts[2]))
            except (ValueError, KeyError, TypeError) as e:
                return self._json({"error": str(e)[:200]}, 400)
            LABELS.mkdir(exist_ok=True)
            (LABELS / f"{parts[2]}.json").write_text(label.model_dump_json(indent=1))
            return self._json({"saved": parts[2], "boxes": len(body["boxes"])})
        self._send(404, b"not found", "text/plain")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    print(f"labeling tool on http://127.0.0.1:{a.port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
