# Deploying the demo

Backend on Render from `deploy/Dockerfile`, frontend on Vercel from `frontend/`. The
two have to name each other, which is the only fiddly part.

Everything in here was checked by building the image and running the container locally.
The hosted services do not exist yet; creating them needs accounts, which is Victor's.

## What needs a person

1. A Render account and a Vercel account.
2. Victor's `META_API_KEY`. The team decided Oct 26 that the hosted demo runs on
   Victor's key, so abuse can only burn that budget.
3. A passcode. Anything unguessable. It goes on the submission page so judges can get in.

## Backend, on Render

Render reads `deploy/render.yaml` as a blueprint. Create the service from it, then set
the three secrets in the dashboard; they are `sync: false` so they never live in git.

| Variable | Value |
|---|---|
| `META_API_KEY` | Victor's key |
| `DEMO_PASSCODE` | the passcode |
| `FRONTEND_ORIGIN` | the Vercel URL, once it exists |

The blueprint sets the rest: `TRUST_PROXY_HEADER=on` because Render terminates TLS in
front of the app, `LOG_REQUEST_BODIES=off`, `PREMASK=off`, the model IDs, and the two
caps.

Two things in the blueprint that are deliberate and should not be changed casually:

- **`numInstances: 1`.** The rate limit and the day cap are counters in the process
  (`backend/app/demo_gate.py`). Two instances means two sets of limits, so the budget
  guard quietly doubles.
- **`--no-access-log`** in the Dockerfile's command. Access logs are the one place a URL
  gets written down. There is nothing in a URL here to leak, and this keeps it that way.

## Frontend, on Vercel

Root directory `frontend`. Vercel detects Next.js. Environment variables:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_BASE` | the Render service URL, no trailing slash |
| `NEXT_PUBLIC_REQUIRE_PASSCODE` | `on` |

`frontend/vercel.json` sets `Cache-Control: no-store` and `Referrer-Policy: no-referrer`
on every response.

## The order that works

1. Deploy the backend with `FRONTEND_ORIGIN` set to anything valid, say
   `http://localhost:3000`. Note its URL.
2. Deploy the frontend with `NEXT_PUBLIC_API_BASE` set to that URL. Note its URL.
3. Set `FRONTEND_ORIGIN` on Render to the Vercel URL and redeploy.

Step 3 is not optional. The server refuses `*` at startup, so there is no shortcut, and
without it the browser's preflight fails and every upload looks broken.

## Checks after deploying

Run these and read the output. Each one is checking a hard constraint, not a feature.

```bash
API=https://redact-api.onrender.com
PASS=the-passcode

# 1. It is alive, and no model ID contains "contributor".
curl -s $API/health

# 2. Nothing is cached anywhere along the way.
curl -sI $API/health | grep -i cache-control        # expect no-store

# 3. The gate is on.
curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/analyze \
  -F image=@some.jpg -F destination=public          # expect 401

# 4. It serves with the passcode.
curl -s -X POST $API/analyze -H "X-Redact-Passcode: $PASS" \
  -F image=@some.jpg -F destination=public | head -c 400

# 5. Only the frontend's origin is allowed.
curl -sI -X OPTIONS $API/analyze \
  -H 'Origin: https://evil.example' \
  -H 'Access-Control-Request-Method: POST' | grep -i access-control-allow-origin
# expect nothing, or anything other than evil.example
```

### Request body logging, by hand, at every hop

The startup check only sees this process (gotcha 20). These two it cannot see:

- **Render**: Logs tab. Confirm no request bodies appear. With `--no-access-log` there
  should be no per request line at all, only our own warnings, which carry a type name
  and never any content.
- **Vercel**: Project settings. Confirm no log drain and no observability integration
  is forwarding request bodies anywhere.

Do this once after the first deploy and once more before the demo video.

## Cold start

Measured locally: a built image goes from `docker run` to a 200 on `/health` in about
4 seconds. The OCR models ship inside the image (3 ONNX files under
`rapidocr/models/`), so there is no download on the first request. The first build is
slower because Docker unpacks the image.

Render's free tier spins a service down when idle and the wake up is slower than that.
The blueprint asks for `starter`, which does not spin down. If the plan changes, open
the demo once before recording or presenting.

## The one that already bit us

The service writes one line of metadata per API call to `logs/cost.jsonl`. In the
container that directory did not exist and the non root user could not create it, so
every API call raised `PermissionError` and the request died as a 500. In a browser that
shows up as a CORS error, because an exception escaping the route builds its response
outside the CORS middleware, so the real problem never reaches anyone. The Dockerfile
creates and chowns `/app/logs` now, and the routes turn an unexpected exception into a
clean 500 instead of letting it escape.

Worth checking after any deploy, because a platform that mounts a read only filesystem
brings it straight back:

```bash
docker exec <container> sh -c 'touch /app/logs/probe && rm /app/logs/probe && echo ok'
```

And confirm the log holds metadata only, never image bytes:

```bash
docker exec <container> sh -c 'head -1 /app/logs/cost.jsonl'
# model, kind, ok, latency, tokens, cost, error, step, phrase. Nothing else.
```

## Building and running the image locally

```bash
docker build -f deploy/Dockerfile -t redact-api .
docker run --rm -p 8000:8000 \
  -e META_API_KEY=... -e DEMO_PASSCODE=test-pass \
  -e FRONTEND_ORIGIN=http://localhost:3000 \
  redact-api
```

## What is still open

- The services themselves. Nothing is hosted yet.
- The by hand body logging check at the Render and Vercel hops, which can only be done
  once they exist.
- A real end to end run. No image has been through the pipeline with live model calls,
  so the first deploy is also the first time the judge is called for real.
