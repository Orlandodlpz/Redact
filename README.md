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
