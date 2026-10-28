# Redact

Privacy scrubber for photos and screenshots. Meta Global AI Developer Hackathon 2026, Indie developer track. Team COV: Carlos, Orlando, Victor.

Start with docs/CLAUDE.md, then docs/BRIEFING.md. Each person runs Claude Code with their own prompt, shared outside the repo.

Branches:
- `Vision-Pipeline`: Orlando
- `Judge-Eval`: Carlos
- `Web-App`: Victor

`main` changes only through pull requests the team has looked at. Orlando merges.

## Run the backend

Needs [uv](https://docs.astral.sh/uv/) (`brew install uv`). uv installs Python 3.12 from `.python-version`.

```bash
cp .env.example .env          # then add your META_API_KEY
uv sync                       # creates .venv and installs everything
uv run pytest                 # all tests
uv run uvicorn app.main:app --reload
curl localhost:8000/health
```

The server refuses to start if any model ID contains `contributor` or if request body logging is on.

Keep the repo outside iCloud synced folders (macOS Desktop and Documents); iCloud breaks the `.venv`.

## Run one image from the CLI

```bash
uv run python backend/cli.py candidates path/to/img.jpg --no-sweep   # local only: OCR, marks
uv run python backend/cli.py candidates path/to/img.jpg              # adds the SAM sweep (~$0.04)
uv run python backend/cli.py analyze path/to/img.jpg --dest public   # whole pipeline, needs judge, merge and floor
```

Overlays (`_ocr.png`, `_sweep.png`, `_marks.png`), candidate JSON, findings JSON and the masked export (`_masked.png`) go to `out/debug/`, which is gitignored. They hold image content and OCR text, so never move them into the repo.

## Smoke test

Calls the real API (about $0.72 per run at list prices). Use clearly fake images or consenting teammates only, kept outside the repo, as JPEG or PNG.

```bash
uv run python scripts/smoke_test.py --images /path/to/fake/images
```

Prints the latency, token and cost table, writes debug overlays to `out/debug/` and logs every call to `logs/cost.jsonl` (both gitignored).
