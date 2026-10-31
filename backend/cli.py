"""Run any pipeline stage on one image and write debug overlays to out/debug/.
Owner: Orlando.

    uv run python backend/cli.py candidates IMG [--no-sweep]
        ingest, OCR, SAM sweep, candidates, marks. Writes _ocr.png, _sweep.png,
        _marks.png and _candidates.json. --no-sweep stays local: no API call at all.
    uv run python backend/cli.py analyze IMG --dest public
        The whole pipeline. Writes _analyze.json and _masked.png (the export).

out/ is gitignored; overlays and JSON hold image content and OCR text, so keep them there.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from app.config import assert_startup_safe, get_settings
from app.pipeline.candidates import build
from app.pipeline.compose import compose
from app.pipeline.ingest import ingest
from app.pipeline.marks import render
from app.pipeline.ocr import ocr
from app.pipeline.run import analyze
from app.pipeline.sweep import decode_rle, sweep
from app.providers.meta_api import MetaClient
from app.schemas import Candidate

OUT = Path("out/debug")
TINT = np.array([255, 0, 160])


async def candidates_cmd(path: Path, no_sweep: bool) -> None:
    r = ingest(path.read_bytes())
    lines = ocr(r.ocr_image, scale=r.ocr_scale, bounds=(r.width, r.height))
    sam: list[Candidate] = []
    if not no_sweep:
        client = MetaClient(get_settings())
        try:
            sam = await sweep(r.image, client, run="cli", img=path.stem)
        finally:
            await client.close()
    cands = build(sam, lines)

    stem = OUT / path.stem
    boxes(r.image, lines).save(f"{stem}_ocr.png")
    if not no_sweep:
        masks(r.image, sam).save(f"{stem}_sweep.png")
    render(r.image, cands).save(f"{stem}_marks.png")
    Path(f"{stem}_candidates.json").write_text(
        json.dumps([c.model_dump(exclude={"mask_rle"}) for c in cands], indent=1)
    )
    print(f"{path.name}: {r.width}x{r.height}, gps {r.had_gps}, "
          f"{len(lines)} OCR lines, {len(sam)} SAM matches, {len(cands)} marks")
    print(f"wrote {stem}_*.png and _candidates.json")


async def analyze_cmd(path: Path, dest: str) -> None:
    result = await analyze(path.read_bytes(), dest)
    stem = OUT / path.stem
    Path(f"{stem}_analyze.json").write_text(result.model_dump_json(indent=1))
    image = ingest(path.read_bytes()).image
    Path(f"{stem}_masked.png").write_bytes(compose(image, result.findings))
    masked = sum(f.masked for f in result.findings)
    print(f"{path.name} [{dest}]: judge {result.judge_status}, {len(result.findings)} findings, "
          f"{masked} masked, ~${result.est_cost_usd:.3f}")
    print("timings ms:", result.timings_ms)
    print(f"wrote {stem}_analyze.json and _masked.png")


def boxes(image: Image.Image, cands: list[Candidate]) -> Image.Image:
    out = image.convert("RGB")
    draw = ImageDraw.Draw(out)
    for c in cands:
        draw.rectangle([c.box[0], c.box[1], c.box[2] - 1, c.box[3] - 1], outline=(255, 0, 160), width=3)
    return out


def masks(image: Image.Image, cands: list[Candidate]) -> Image.Image:
    pixels = np.array(image.convert("RGB"))
    for c in cands:
        if c.mask_rle:
            m = decode_rle(c.mask_rle, image.width, image.height).astype(bool)
            pixels[m] = (pixels[m] * 0.55 + TINT * 0.45).astype(np.uint8)
    return boxes(Image.fromarray(pixels), cands)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates", help="ingest through marks, with debug overlays")
    c.add_argument("image", type=Path)
    c.add_argument("--no-sweep", action="store_true", help="skip SAM; nothing leaves the machine")
    a = sub.add_parser("analyze", help="the whole pipeline")
    a.add_argument("image", type=Path)
    a.add_argument("--dest", choices=["public", "team", "ai_assistant"], required=True)
    args = parser.parse_args()

    assert_startup_safe(get_settings())
    OUT.mkdir(parents=True, exist_ok=True)
    if args.cmd == "candidates":
        asyncio.run(candidates_cmd(args.image, args.no_sweep))
    else:
        asyncio.run(analyze_cmd(args.image, args.dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
