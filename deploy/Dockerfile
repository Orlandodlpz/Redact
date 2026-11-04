# Backend image for the hosted demo. Built from the repo root:
#   docker build -f deploy/Dockerfile -t redact-api .
#
# CPU only on purpose. SAM 3.1 and Muse Spark are API calls, and RapidOCR runs on CPU
# in well under a second, so there is no GPU in this picture.
FROM python:3.12-slim

# RapidOCR's ONNX runtime wants libgomp; opencv wants libgl and libglib.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY pyproject.toml uv.lock README.md ./
COPY backend/app ./backend/app
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Never root. The service writes no user data to disk, but it does append one line of
# metadata per API call to logs/cost.jsonl, so that one directory has to exist and be
# writable by this user. Without it every API call raises PermissionError and the
# request dies as a 500, which in a browser shows up as a confusing CORS error rather
# than the real problem. Found by running this container, not by reading it.
RUN useradd --create-home --uid 10001 redact \
 && mkdir -p /app/logs \
 && chown -R redact:redact /app/logs
USER redact

EXPOSE 8000

# One worker. The rate limit and the day cap are counters in this process, so a second
# worker would mean two sets of limits (app/demo_gate.py). Judge latency is the wait,
# and that is spent in await, so one worker still serves several people at once.
#
# --no-access-log is not optional. Access logs are the one place a URL would be written
# down, and the hard constraint is that no image or finding ever reaches a log line.
# There is nothing in a URL here to leak, and this keeps it that way.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
