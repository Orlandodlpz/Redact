"""Phase 2 OCR engine test: RapidOCR vs Tesseract on staged photos.

    uv run python scripts/ocr_engine_test.py --images /path/to/photos --truth /path/to/truth.json

Runs locally; nothing is sent to any API. The truth file lists key strings per image
file name, split into "sensitive" (what Redact must find) and "other". Keep it outside
the repo: it holds whatever the photos say. A key counts as found when some stretch of
the engine's text matches it at >= MATCH_THRESHOLD similarity, because handwriting is
rarely read exactly. Only counts go to logs/; OCR text is printed, never saved.
"""

import argparse
import json
import statistics
import time
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image, ImageDraw, ImageOps
from rapidocr import RapidOCR

from app.config import get_settings

MATCH_THRESHOLD = 0.8
DEBUG_DIR = Path("out/debug")


def normalize(text: str) -> str:
    return "".join(text.lower().split())


def best_match(key: str, text: str) -> float:
    """Best similarity between key and any window of text near the key's length."""
    k, t = normalize(key), normalize(text)
    if not k or not t:
        return 0.0
    best = 0.0
    for size in {len(k) - 1, len(k), len(k) + 1}:
        if size <= 0:
            continue
        for start in range(max(1, len(t) - size + 1)):
            best = max(best, SequenceMatcher(None, k, t[start:start + size]).ratio())
            if best == 1.0:
                return best
    return best


def run_rapid(engine: RapidOCR, image: Image.Image) -> list[dict]:
    out = engine(np.array(image))
    lines = []
    for quad, text, score in zip(out.boxes if out.boxes is not None else [], out.txts or [], out.scores or []):
        lines.append({"text": text, "score": float(score), "quad": [tuple(map(int, p)) for p in quad]})
    return lines


def run_tesseract(image: Image.Image) -> list[dict]:
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    grouped: dict[tuple, dict] = {}
    for i, word in enumerate(data["text"]):
        if float(data["conf"][i]) < 0 or not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        line = grouped.setdefault(key, {"words": [], "scores": [], "box": [x, y, x + w, y + h]})
        line["words"].append(word)
        line["scores"].append(float(data["conf"][i]) / 100)
        b = line["box"]
        line["box"] = [min(b[0], x), min(b[1], y), max(b[2], x + w), max(b[3], y + h)]
    return [
        {"text": " ".join(v["words"]), "score": statistics.mean(v["scores"]),
         "quad": [(v["box"][0], v["box"][1]), (v["box"][2], v["box"][1]),
                  (v["box"][2], v["box"][3]), (v["box"][0], v["box"][3])]}
        for v in grouped.values()
    ]


def draw(image: Image.Image, lines: list[dict]) -> Image.Image:
    out = image.copy()
    d = ImageDraw.Draw(out)
    for line in lines:
        d.polygon(line["quad"], outline=(255, 0, 160), width=3)
    return out


def score_keys(keys: list[str], text: str) -> tuple[int, list[str]]:
    missed = [k for k in keys if best_match(k, text) < MATCH_THRESHOLD]
    return len(keys) - len(missed), missed


def main(folder: Path, truth_path: Path, max_edge: int, det_params: dict) -> None:
    truth = {k: v for k, v in json.loads(truth_path.read_text()).items() if not k.startswith("_")}
    rapid = RapidOCR(params=det_params)
    rapid(np.zeros((64, 64, 3), dtype=np.uint8))  # load models before timing
    engines = {"rapidocr": lambda im: run_rapid(rapid, im), "tesseract": run_tesseract}
    run = time.strftime("ocr_%Y%m%d_%H%M%S")
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    rows, totals = [], {name: {"sens": [0, 0], "other": [0, 0], "secs": []} for name in engines}
    for name, spec in truth.items():
        path = folder / name
        if not path.exists():
            print(f"skip {name}: not found")
            continue
        image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        image.thumbnail((max_edge, max_edge))
        for engine_name, fn in engines.items():
            start = time.perf_counter()
            lines = fn(image)
            secs = time.perf_counter() - start
            text = " ".join(line["text"] for line in lines)
            sens_found, sens_missed = score_keys(spec["sensitive"], text)
            other_found, other_missed = score_keys(spec["other"], text)
            t = totals[engine_name]
            t["sens"][0] += sens_found; t["sens"][1] += len(spec["sensitive"])
            t["other"][0] += other_found; t["other"][1] += len(spec["other"])
            t["secs"].append(secs)
            rows.append((name, engine_name, len(lines), f"{sens_found}/{len(spec['sensitive'])}",
                         f"{other_found}/{len(spec['other'])}", f"{secs:.2f}", sens_missed))
            draw(image, lines).save(DEBUG_DIR / f"{run}_{engine_name}_{path.stem}.png")

    print(f"\n{'image':<24}{'engine':<11}{'lines':>6}{'sensitive':>11}{'other':>8}{'secs':>7}  missed sensitive")
    for name, engine_name, n, sens, other, secs, missed in rows:
        print(f"{name:<24}{engine_name:<11}{n:>6}{sens:>11}{other:>8}{secs:>7}  {', '.join(missed)}")

    summary = {"run": run, "max_edge": max_edge, "threshold": MATCH_THRESHOLD, "rapidocr_params": det_params, "engines": {}}
    print("\ntotals")
    for engine_name, t in totals.items():
        s = {
            "sensitive_found": t["sens"][0], "sensitive_total": t["sens"][1],
            "other_found": t["other"][0], "other_total": t["other"][1],
            "mean_secs": round(statistics.mean(t["secs"]), 2), "max_secs": round(max(t["secs"]), 2),
        }
        summary["engines"][engine_name] = s
        print(f"{engine_name:<11} sensitive {s['sensitive_found']}/{s['sensitive_total']}, "
              f"other {s['other_found']}/{s['other_total']}, mean {s['mean_secs']} s, max {s['max_secs']} s per image")
    out = Path("logs") / f"{run}_summary.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nsummary (counts only): {out}\noverlays: {DEBUG_DIR}/{run}_*.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--max-edge", type=int, default=get_settings().max_image_edge_px)
    parser.add_argument("--rapid-params", type=json.loads, default={},
                        help='RapidOCR params as JSON, e.g. \'{"Det.box_thresh": 0.4}\'')
    args = parser.parse_args()
    main(args.images, args.truth, args.max_edge, args.rapid_params)
