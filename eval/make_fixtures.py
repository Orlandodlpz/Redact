"""Build the judge inputs for the bake off: numbered candidates and the marked overlay.
Owner: Carlos.

Runs the same steps as run.analyze up to the judge (ingest, OCR plus SAM sweep,
candidates, marks), so the bake off judges exactly what the pipeline would hand it.
Writes eval/data/fixtures/<id>.candidates.json and <id>.marked.png (gitignored).

This calls SAM: 16 requests per image at about $0.0025 each. Existing fixtures are
kept unless --force, so a rerun after a crash costs nothing for finished images.

Usage: uv run python eval/make_fixtures.py [--ids s01,s02] [--force]
"""

import argparse
import asyncio
import json
from pathlib import Path

from check_shot_list import parse_rows
from app.config import get_settings
from app.pipeline.candidates import build
from app.pipeline.ingest import ingest
from app.pipeline.marks import render
from app.pipeline.ocr import ocr
from app.pipeline.sweep import sweep
from app.providers.meta_api import MetaClient

DATA = Path(__file__).parent / "data"
EXTS = ("jpg", "jpeg", "png", "webp", "heic")
CONCURRENCY = 2  # images at once; each already fans out to 16 SAM requests


async def make_one(client, image_id: str, path: Path, out: Path) -> str:
    r = ingest(path.read_bytes())
    lines = ocr(r.ocr_image, scale=r.ocr_scale, bounds=(r.width, r.height))
    sam = await sweep(r.image, client, run="fixtures", img=image_id)
    cands = build(sam, lines)
    render(r.image, cands).save(out / f"{image_id}.marked.png")
    (out / f"{image_id}.candidates.json").write_text(
        json.dumps([c.model_dump(exclude={"mask_rle"}) for c in cands]))
    return f"{image_id}: {r.width}x{r.height}, {len(lines)} OCR lines, {len(sam)} SAM matches, {len(cands)} marks"


async def main(ids: list[str] | None, force: bool) -> None:
    ids = ids or [r["id"] for r in parse_rows() if r["bake_off"]]
    out = DATA / "fixtures"
    out.mkdir(parents=True, exist_ok=True)
    todo = []
    for i in ids:
        path = next((p for e in EXTS if (p := DATA / "images" / f"{i}.{e}").exists()), None)
        if path is None:
            print(f"{i}: no image, skipped")
        elif not force and (out / f"{i}.candidates.json").exists() and (out / f"{i}.marked.png").exists():
            print(f"{i}: fixtures exist, skipped")
        else:
            todo.append((i, path))
    client = MetaClient(get_settings())
    sem = asyncio.Semaphore(CONCURRENCY)

    async def guarded(i, p):
        async with sem:
            try:
                print(await make_one(client, i, p, out), flush=True)
            except Exception as e:  # SweepError means the scan was incomplete; never fake a fixture
                print(f"{i}: FAILED {type(e).__name__}", flush=True)

    try:
        await asyncio.gather(*[guarded(i, p) for i, p in todo])
    finally:
        await client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.ids.split(",") if a.ids else None, a.force))
