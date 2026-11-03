# The first live run

**Last Updated:** 2026-11-02 (Victor)

No image has ever been through this pipeline with real model calls. Every module exists,
327 unit tests pass, and an integration test runs the whole chain with the network faked,
but `judge_status` has never been `ok` outside a stub. Gotchas 40 and 41 are both that
failure mode, so until this is done, nothing else is really known.

This is written to take about ten minutes and to be done first thing, ahead of the
deploy, the eval and the video.

## Before you start

You need a `META_API_KEY` with a credit card on the account (gotcha 18) in a `.env` at
the repo root. `.env` is gitignored.

```bash
cp .env.example .env
# put the key in, leave the rest alone
uv sync
```

## 1. The pipeline, on one image, from the CLI

```bash
uv run python backend/cli.py analyze threats/inj_01_drawn.png --dest public
```

If `threats/inj_01_drawn.png` is not there, run `uv run python threats/build_cases.py`
first. Better still, use a real photo of your own desk with a fake password written on a
sticky note.

**Read the output for these, in this order:**

| What | Where | What it means if it is wrong |
|---|---|---|
| `judge_status` | the JSON | `failed_closed` means the judge call did not work. Not a fail closed success story, a broken judge (gotcha 40). |
| `prompt_version` | the JSON | `unset` means judge.py is not exporting `PROMPT_VERSION`. |
| findings with `source: "floor"` | the JSON | None at all, on an image with a password line, means OCR or the floor rules did not see it. |
| findings with `source: "judge"` | the JSON | None at all means the judge returned no verdicts, which with a working call means the prompt is not landing. |
| `timings_ms.total` | the JSON | The first real latency number anyone has. Write it down. |
| `est_cost_usd` | the JSON | Should be near the Phase 1 estimate of about six cents. Much higher means something is being called more than once. |
| `out/debug/*_analyze.json` and the masked PNG | on disk | Open the PNG. The masks should sit on the things the reasons describe. |

**Known rough edge:** a failure here prints a Python traceback rather than a message.
`SweepError: SAM sweep failed for: face, license plate, ...` with every phrase listed
almost always means the key is wrong or has no card on it, not sixteen separate
failures. Checked Nov 2 with a deliberately bad key. Worth a line in `cli.py`, which is
Orlando's.

## 2. The same thing through the API

```bash
uv run uvicorn app.main:app --port 8000
```

In another shell:

```bash
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/analyze \
  -F image=@threats/inj_01_drawn.png -F destination=public | head -c 600
```

Then the same image at `destination=team` and compare. If the two finding lists are
identical on an image with a face in it, the destination policy is not reaching the
output.

## 3. The whole thing in a browser

```bash
cd frontend && npm install && npm run dev
```

Open `http://localhost:3000`, upload the image, pick a destination, review, download.
Then open the downloaded PNG and confirm it has no metadata:

```bash
uv run python -c "
from PIL import Image
im = Image.open('redacted.png')
print('metadata:', im.info, 'exif:', bool(im.getexif()))
print('format:', im.format, im.size)
"
```

## 4. The injection set, for real

```bash
uv run python threats/run_threats.py
```

Thirty analyze calls, so roughly two dollars at the Phase 1 estimate. It prints a pass
or fail per case and writes a report to `threats/reports/`.

On drawn images with a stubbed model, floor kept passed 15 of 15 and no verdict flipped
passed 15 of 15 (Nov 2). The third check, instruction reported, has never been exercised
against a real judge, so that is the interesting column.

Use `--only inj_01` first if you want to spend twelve cents before two dollars.

## 5. Tell the others

Whatever happens, put the result in the team channel, because the bake off, the eval,
the deploy and the video are all waiting behind it:

- `judge_status` on a real image
- `timings_ms.total` and `est_cost_usd`
- whether the destination actually changed the output
- the first failure, if there is one

## If the judge comes back failed_closed

Narrow it before changing anything:

```bash
uv run python -c "
import asyncio, sys
sys.path.insert(0, 'backend')
from app.config import get_settings
from app.providers.meta_api import MetaClient

SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
          'required': ['ok'], 'additionalProperties': False}

async def main():
    s = get_settings()
    c = MetaClient(s)
    try:
        r = await c.chat_json(s.judge_model,
                              [{'role': 'user', 'content': 'Reply with ok true.'}],
                              SCHEMA, schema_name='probe')
        print('reachable:', r.stats.ok, '|', r.text, '|', r.stats.error or 'no error')
    finally:
        await c.close()

asyncio.run(main())
"
```

That is the smallest possible judge call: the real client, the real model ID, strict
structured output, and nothing of ours in the way.

If that works and the pipeline still fails closed, the problem is in the judge request
or its schema, not the key. `run.py` swallows the exception by design, so read the
warning line it logs: it prints the exception type.
