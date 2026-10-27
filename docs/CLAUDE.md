# CLAUDE.md: Redact

Project context and conventions. Read this first in every session, then read docs/BRIEFING.md.
**Last Updated:** 2026-10-26 (OCR engine test done: RapidOCR kept, Tesseract dropped)

## Interaction Mode: Always On

**Use calibrated honesty for all work on this project, at all times, no exceptions.** Agree when the approach is right, push back plainly when it isn't, and don't manufacture agreement or hedge to avoid friction. This applies to code review, architecture decisions, data quality, eval numbers, and any claims made in docs, commit messages, the README or the demo script, including anything already written in this file. If something in this plan is flawed, say so directly instead of deferring to what's documented.

Working preferences for every session:
- Explain the why alongside the how.
- Flag gotchas proactively and record new ones in "Known gotchas" below.
- No filler, no preamble. Direct, casual tone.
- Never use em dashes or hyphens as dashes in any deliverable (docs, README, UI copy, video script).

## Project Overview

Redact is a privacy scrubber for photos and screenshots, built by a three person team for the Meta Global AI Developer Hackathon (Indie developer track, Oct 26 to Nov 4, 2026). Before a user shares an image to a public post, a team chat, or an AI assistant, Redact finds what should not be in it and masks it. Basic PII detection in screenshots already exists (Redaktr, SnapShield AI, BlurData, CaseGuard, Presidio Image Redactor), so Redact competes on three things those tools don't do: judging sensitivity from context in photos of real spaces (one password line among harmless whiteboard notes), flagging leaks that only appear when two clues combine (house number plus street sign), and changing what gets masked based on who will see the image. Every mask comes with a one line reason.

Pitch line: *Pattern tools find text that looks like PII. Redact decides what is sensitive in this photo, for whoever will see it, and explains every mask.*

Problem statement: **Build for Your World** (decided Oct 26). The other option, Push the Frontier, targets science and physical systems and fits worse.

Judging (Official Rules, read Oct 26):
- **Stage One, pass/fail:** the project reasonably fits the theme and reasonably uses the Meta Model API or Meta open weights models.
- **Stage Two, 0 to 10 per category:** Impact 30%, Use of Meta AI Tooling 25%, Technical Depth and Execution 20%, Demo 25%.
- **Stage Three:** top 5 per track; final round judges watch the demo videos live and rank them with the same rubric.
- The demo video, the code and the live product are the primary artifacts judges use.

Team and ownership:
- **Orlando:** vision pipeline. SAM 3.1 sweep and refine, OCR, mark rendering, mask composition, latency, pre-masking before cloud calls.
- **Carlos:** judge and evaluation. Judge prompt and schema, destination policy, multi-clue leaks, dataset, eval harness, baselines.
- **Victor:** app and threats. FastAPI service, Next.js upload and review editor, export, injection test set, deployment, demo access gate.

**Hard constraints (never violate, never soften):**
- **Deadline:** submission closes Wed Nov 4, 9:00 PM ET (8:00 PM Central) on the CV platform. Late submissions are not considered. Team target is 6:00 PM ET. Feature freeze is end of Mon Nov 2.
- **Submission rules (Official Rules, read Oct 26):** one submission per team, entered by one appointed Representative (Orlando, decided Oct 26). Repo must be public. Every team member is listed on the submission page. A three minute demo video is required and must show only features, code and functionality built during the event. Judges must be able to tell what was built during the event; failing that is grounds for disqualification.
- **Meta models are the core.** Every sensitivity judgment comes from a Meta model (Muse Spark). Every mask's geometry comes from SAM 3.1 or OCR. Non-Meta components (OCR, regex checks) are plumbing, never the decision maker.
- **Never use a `-contributor` model ID** anywhere in the app or the eval. The Contributor tier trains on prompts and completions, which would donate user images and teammates' faces to Meta training. The server refuses to start if any configured model ID contains `contributor`.
- **Never store or log user images.** Process in memory. No request body logging at any hop (app server, reverse proxy, hosting platform). No images in URLs or query strings.
- **Masks are solid fill.** Never blur or pixelate as the privacy mechanism; both can be reversed on text. Export is a newly encoded, flattened PNG with all metadata removed, GPS included.
- **Floor items cannot be unmasked by the model.** Final mask set = floor rule hits ∪ judge's sensitive verdicts. Only the user can unmask a floor item, by hand, in the review editor.
- **Fail closed.** If the judge call fails or returns invalid output after one retry, mask every floor hit plus every candidate from a high risk SAM class and tell the user the judge was unavailable. Never return an image with fewer masks because a call failed.
- **No real PII in any dataset.** Staged photos use consenting team members, fake documents, fake passwords, fake addresses. No real IDs, cards, passwords or bystanders.
- **No eval images in git.** Repo holds manifests and labels only; images live in team private storage. A handful of clearly fake demo images may be committed.
- **No reuse** of code, data or assets from any other team project, including HaloAI or Victor and Carlos's lab research. The rules require that what we present was built during the event and that the submission makes this clear. The guide lists the building period as Oct 27 to Nov 4; the team confirmed on Oct 26 that code may start after the Oct 26 kickoff. The README states that the planning docs predate the event and that all code was written during it.
- **No code, data or assets we lack the rights to** (Official Rules, grounds for disqualification). Every third party library, model and dataset must be compatible with a public repo.
- **No unearned numbers.** Every metric in the README, slides or video comes from `eval/run_eval.py` output with the commit hash and model IDs recorded. Estimates are labeled as estimates.

## Environment

- **Meta Model API:** base URL `https://api.meta.ai/v1`, OpenAI compatible, `Authorization: Bearer $META_API_KEY`. Supports Chat Completions and Responses APIs. Keys are created at dev.meta.ai.
- **Muse Spark:** `muse-spark-1.3` (Standard tier, current) and `muse-spark-1.2`. Input: text, image, video, PDF. Output: text. Structured output (strict JSON schema), tool calling, `reasoning_effort` from `minimal` to `xhigh`. Reasoning tokens are billed as output. Price: $1.25 per million input tokens, $4.25 per million output. Proprietary, API only.
- **SAM 3.1 on the API:** reached over the Responses API (`POST /v1/responses`). Send an image plus one short text phrase; returns a box and a pixel mask per match as special token text in one `output_text` lane. The `meta-sam-parser` PyPI package parses that format. Price: $2.50 per 1,000 images. Model ID **`sam-3.1`** (confirmed with `GET /v1/models`, Oct 26). Request shape that works: `responses.create(stream=True)` with an `input_image` data URL plus one `input_text` holding a noun phrase or `build_object_prompt()` box prompts; `metadata={"include_confidence": "true"}` adds a confidence per match. See `providers/meta_api.py`.
- **SAM 3.1 text prompts:** 32 token limit per phrase. Open weights exist (SAM License) but need a GPU the team doesn't have, so the API is the only path.
- **No local inference.** Local mode was cut on Oct 24: no team member has a 24 to 32 GB GPU or a large memory Mac, which Muse Glimmer 30B (Meta's open weights multimodal model) needs even at 4 bit. Every model call goes to the Meta Model API. Don't reintroduce local inference without a confirmed hardware answer.
- **Rate limits:** published as 3,000 requests per minute and 4,000,000 tokens per minute per model, **per team**. All keys on the same team share the pool. SAM 3.1: 3,000 requests per minute (`x-ratelimit-limit-requests` header, Oct 26), no token limit header.
- **Keys (decided Oct 26):** Carlos's key runs every eval, so eval cost sits in one log. Victor's key runs the hosted demo, so abuse can only burn that budget. Orlando's key is for development and smoke tests. Separate budgets, shared rate limits.
- **Credits (Official Rules):** each participant claims $150 in Meta Model API credits individually through the credits form by Nov 4, 9:00 PM ET. Credits are per account and cannot be claimed for someone else. A credit card must be on the account before any API call works, and adding it triggers a temporary preauthorization charge. Credits arrive in batches; check the Billing page. Set a Spend Limit notification there.
- **Partner inference for open weights:** Baseten ($100 per individual plus a 2M TPM limit, reviewed), Modal ($100, first 1,000 participants) and Fireworks ($25 per team, shortlist) can host Muse Glimmer and Muse Spark Open. This is hosted inference on a third party, not local inference, so it does not restore the on device privacy story. It matters only for the Best Build on Meta Open Weight Models bonus prize, which is a Tier 3 item: attempt it only if everything else is done.
- **Proposed stack (confirm Oct 26):** Python 3.11+ FastAPI backend (pipeline, OCR, floor rules, compose). Next.js frontend (upload, review editor, export). No database: the service is stateless.
- **Hosting (proposed):** frontend on Vercel, backend on a small CPU host. No GPU needed because SAM 3.1 and Muse Spark are API calls.

## Locked Decisions

Do not re-litigate unless new evidence is presented. If one is reopened, say so explicitly and record the outcome here.

Made by the team before Oct 24:
- **Indie developer track, team entry, software only.** About a week of build time rules out hardware.
- **Project is Redact.** Chosen over Sim2Task, Acceso and FixIt as the best balance of buildability, a measurable result, and even work split.
- **Roles as listed in Project Overview.** Matches each member's background and the application answers.
- **Public or staged data only.** No lab data from any team member's research.

Made in the Oct 24 design review (evidence in BRIEFING.md and the review page):
- **Positioning is context, multi-clue leaks and destination.** The application's claim that "nothing understands context" is false; several shipped tools detect PII in images.
- **Candidate generation = SAM 3.1 concept sweep + OCR.** SAM 3.1 finds every match for a short phrase; the hosted API has no documented segment everything mode and cannot isolate one text line.
- **One judge call per image over a numbered overlay (set of marks).** One call per region would cost 30+ reasoning calls per cluttered photo at roughly 23 s each.
- **The VLM decides, SAM 3.1 and OCR draw the edges.** Muse Spark 1.3 scores 58.6% mAP@50 on Roboflow's detection eval; its own boxes are too loose to be final masks. Judge boxes for missed items only seed a SAM box prompt in the refine step.
- **Destination handling = deterministic policy table over judge categories.** The judge assigns sensitivity and category in context; `policy.py` maps category × destination to mask or keep. The judge may escalate (mask more) with a reason but cannot de-escalate below the table. Keeps destination behavior testable.
- **Floor rules run beside the judge** and cannot be overridden by it: Luhn valid card numbers, API key and password patterns plus entropy, SAM classes `ID card` and `credit card`, QR codes, barcodes.
- **OCR text goes to the judge as quoted data** under a system rule that nothing in the image is an instruction. Instruction-like text is returned as a finding.
- **Standard tier only, nothing stored, solid fill export** (see Hard constraints).
- **Evaluation includes a public slice and real baselines:** 50 WebPII screenshots plus B1 (faces and plates), B2 (Presidio Image Redactor), B3 (Muse Spark alone).
- **Local mode is cut (Oct 24).** No team hardware can run Muse Glimmer 30B. The API is the only mode, so privacy claims are limited to what the Standard tier and our own handling guarantee.
- **Scope is tiered.** Tier 1 ships regardless. Tier 2 (pre-masking text floor hits on our server before any Meta API call) is gated on Nov 1. Tier 3 only if ahead.

## Provisional Values

Not validated. Each names what replaces it.

| Value | Current setting | Replaced by |
|---|---|---|
| Judge model | `muse-spark-1.3`, `reasoning_effort: low` | Oct 27 bake off vs `muse-spark-1.2` and `minimal` on 20 staged images, recall first then latency |
| Sweep vocabulary | 16 phrases: face, license plate, ID card, credit card, paper document, envelope, name badge, computer monitor, laptop screen, phone screen, whiteboard, sticky note, QR code, barcode, house number, street sign | Per phrase recall and false positive counts after the Oct 29 gate |
| OCR engine | RapidOCR (PP-OCRv6 small models, ONNX), CPU. Engine test Oct 26 on 10 photos: 8 of 12 sensitive strings found vs Tesseract 0 of 12, mean 0.65 s per image. Tesseract dropped as fallback | Box coverage per labeled text item at the Oct 29 gate |
| Max image size | 2048 px long edge for everything sent to the API | Latency and small text recall at the Oct 29 gate |
| OCR input size | Up to 4096 px long edge, run locally on the pre-resize image; boxes scaled down to the 2048 px working image. Engine test: 8 of 12 at 4096 vs 7 of 12 at 2048, same speed | Oct 29 gate |
| OCR detection thresholds | Loose: `Det.thresh` 0.2, `Det.box_thresh` 0.4, `Det.unclip_ratio` 2.0, `Global.text_score` 0.4. Finds handwritten lines the defaults skip, at 5 to 30% more lines per image | Box coverage and candidate count at the Oct 29 gate |
| Mask dilation | 4 px | Visual check plus coverage metric on 30 images |
| Caught threshold (eval) | Mask covers ≥ 90% of a labeled item's box | Agreed by team before the first full run; never changed after seeing results |
| Latency targets | Candidates on screen < 3 s, verdicts < 15 s p50. Smoke test (Oct 26, 3 images): the 16 phrase sweep alone took 2.7 to 4.1 s wall, so < 3 s is at risk; judge p50 was 3.1 to 9.9 s depending on config, so < 15 s looks reachable | Oct 29 gate measurements on 30 images, with OCR and refine in the path |
| Cost per image | Est. ~$0.06 from measured requests and tokens at list prices: sweep 16 × $0.0025 = $0.040, judge $0.013 to $0.017 (8.3k to 8.8k input tokens for two 2048 px images), refine ≤ 3 × $0.0025 | Billing page check after the first full eval run |
| Destination policy table | See BRIEFING.md §2 | Destination accuracy on 30 triple labeled images |
| Pre-mask recall tolerance | Ship Tier 2 only if recall drops ≤ 2 points on the 30 image subset | Team agrees on the number before the Nov 1 dry run, never after seeing it |
| Dataset size | 150 images: 50 WebPII, 80 staged, 20 hard negatives; 15 injection images | Revisit only if labeling falls behind on Oct 30 |

## Verification Rules

- Every configuration change ships with its verification command.
- Every phase ends with its gate check (see BRIEFING.md) before the next phase starts.
- Every pipeline stage runs standalone on one image from the CLI and writes a debug overlay PNG to `out/debug/`.
- Every eval number comes from `eval/run_eval.py`, saved under `eval/results/<date>_<commit>/` with model IDs, prompt version and config hash.
- Before any prompt, model or threshold change merges, run the 30 image regression subset. Block the merge if floor recall drops, if any injection test fails, or if hard negative false positives rise without a recorded reason.
- Pre-masking (Tier 2) gets two checks before it ships: a unit test proving floor text pixels are filled in every image passed to a provider client, and a recall comparison on the 30 image subset with pre-masking on versus off. Report the recall change as measured.
- Export check on every build: re-open the exported PNG, assert zero EXIF/XMP/IPTC blocks and assert masked pixels are a single solid color.
- Startup check: server exits non-zero if any model ID contains `contributor` or if request body logging is enabled.
- Cost log: every API call records model, input tokens, output tokens, reasoning tokens, latency and estimated cost to `logs/cost.jsonl` (metadata only, never image bytes).

## Current Status

- **Phase:** Phase 1 DONE (Oct 26). Official Rules read, code started Oct 26, credits claimed, smoke test measured both models (BRIEFING.md Phase 1 results).
- **Done:** Local mode cut (Oct 24, no hardware). Design review (Oct 24). Twelve checks run; four parts of the application plan rewritten (pitch, pipeline, privacy, safety) and the eval strengthened. Results summarized in BRIEFING.md Phase 0. Official Rules read and recorded (Oct 26).
- **Next:** Phase 2. Oct 27 judge bake off (Carlos) now has measured latency to compare against; OCR engine test done (RapidOCR); Orlando starts ingest, sweep, ocr.py and candidates.
- **Known gotchas discovered so far:**
  1. SAM 3.1 on the hosted API is phrase driven. No documented segment everything mode. One phrase per request until proven otherwise.
  2. SAM will not isolate a single line of text inside a whiteboard or document. Text lines come from OCR.
  3. Muse Spark's own bounding boxes are loose (58.6% mAP@50, Roboflow). Never ship them as final masks.
  4. Muse Spark 1.3 averaged 23.1 s per sample on Roboflow's vision evals. Higher reasoning effort did not help detection there (2 points lower at 1.5x cost and latency). Our smoke test (Oct 26, our judge request shape, 10 calls per config) measured p50 3.1 s at `minimal` and 5.8 s at `low`.
  5. Muse Spark 1.2 scored slightly higher than 1.3 on Roboflow's vision average and ran faster. Test both. In our smoke test 1.2 was slower than 1.3 at both efforts (p50 4.5 vs 3.1 s minimal, 9.9 vs 5.8 s low) and spent more reasoning tokens. Accuracy is the Oct 27 bake off's job.
  6. `-contributor` model IDs are 12x to 21x cheaper because Meta trains on the prompts. Forbidden here.
  7. Standard tier: no training on inputs, but zero data retention is not on by default (abuse monitoring). The privacy pitch must say this accurately. There is no local mode to point to.
  8. Rate limits are per team and shared by every key on that team.
  9. Reasoning tokens bill as output tokens. Budget for them.
  10. Blur and pixelation can be reversed on text. Solid fill only.
  11. Photos carry GPS in EXIF. Strip on ingest, report it as a finding, strip again on export.
  12. Any text in the image is an injection vector into the judge.
  13. "Redact" collides with Redact.dev and several App Store apps. Team kept the name anyway (Oct 26); the pitch and README must make the context and destination angle obvious so judges don't mistake us for those.
  14. WebPII is CC BY 4.0; attribution required in the README.
  15. Submission deadline is ET. 9 PM ET is 8 PM Central.
  16. The guide lists the building period as Oct 27 to Nov 4, but the event starts with the Oct 26 kickoff. Git timestamps are public evidence of when code was written. Team confirmed Oct 26 that code may start after kickoff. (Orlando, Oct 26)
  20. The openai Python SDK logs full request bodies, base64 images included, when `OPENAI_LOG=debug` or its logger is at DEBUG. The startup check refuses both, plus `httpx` and `httpcore` at DEBUG. It cannot see proxy or hosting platform logs; those are checked by hand at deploy. (Orlando, Oct 26)
  21. When the startup check fails, uvicorn exits with code 3 ("Application startup failed"), not 1. Any non-zero code means refused. (Orlando, Oct 26)
  22. SAM masks come back cropped to their box and at lower resolution (a 1466 × 1018 box came with a 1024 × 711 raster). Scale each mask to its box and paste it at the box corner before compose, IoU or RLE for the full image. Boxes are half-open. (Orlando, Oct 26)
  23. One SAM request accepts several phrases ("face, computer monitor" returned 1 + 8 = 9 matches; "face. computer monitor" lost the face), but matches carry no phrase label. Floor rules and fail closed need the label, so the sweep stays one phrase per request. One image tested. (Orlando, Oct 26)
  24. SAM false positives seen in the smoke test: "whiteboard" matched a white desk, "face" matched the engraved portrait on a card, "computer monitor" matched a glasses lens reflection and monitor backs. Fail closed will over-mask these; the judge must clear them. (Orlando, Oct 26)
  25. Muse Spark strict structured output accepts Pydantic's `$ref`/`$defs` schema as is: 40 of 40 smoke test outputs validated against `JudgeOutput`. Valid is not correct. (Orlando, Oct 26)
  26. Don't keep the repo in an iCloud synced folder (macOS "Desktop & Documents"). iCloud set the hidden flag on `.venv` files and Python 3.12 skips hidden `.pth` files, so `import app` broke. Orlando's repo moved to `~/dev/Redact`. (Orlando, Oct 26)
  27. iPhone ProRAW photos are DNG, 10 to 43 MB: over the 20 MB upload limit and unreadable by Pillow. Shoot staged photos as HEIC or JPEG. (Orlando, Oct 26)
  28. SAM Responses usage reports no input tokens; it bills per request, so cost is counted per request. (Orlando, Oct 26)
  29. SAM allows 3,000 requests per minute per team and each image costs 16, so the whole team gets about 187 images per minute. A 150 image eval sent at once uses 2,400 of them in a minute and starves the hosted demo. Pace eval runs to about 100 images per minute. (Orlando, Oct 26)
  30. Tesseract found 0 of 12 sensitive strings in phone photos (handwriting, whiteboards, an ID badge, a screen). It is built for scans. Don't fall back to it for photos. (Orlando, Oct 26)
  31. RapidOCR's misses on handwriting are detection misses, not reading misses: it reads a line well or never boxes it. Loose detection thresholds find those lines, often with garbled text but a correct box. For masking the box matters more than the text, so score OCR by box coverage, not text match. (Orlando, Oct 26)
  32. OCR can't read digits stacked vertically (a house number on a pillar); the SAM "house number" phrase has to cover it. Handwritten secrets OCR misses fall back on the sticky note or whiteboard mask plus the judge's extra_findings. (Orlando, Oct 26)
  33. OCR is local and free per image, so it can run on the full resolution photo (up to 4096 px) while the API gets 2048 px. Small on screen text needs it. (Orlando, Oct 26)
  34. iPhone JPEGs open in Pillow as format `MPO`, not `JPEG`: they carry extra embedded frames (depth or gain maps). A JPEG only format check rejects every iPhone photo. ingest.py accepts MPO and uses frame 0. (Orlando, Oct 26)
  35. Every iPhone photo in the staged set carried GPS in EXIF. ingest.py strips it, reports it, and rebuilds images from raw pixels; any code that opens an upload some other way must not send it anywhere. (Orlando, Oct 26)
  36. `mask_rle` holds COCO counts only, not the `{size, counts}` object. The size is always the working image's (height first in pycocotools), so a decoder needs the image width and height passed separately. Encode from a Fortran ordered uint8 array or pycocotools raises. (Orlando, Oct 26)
  37. SAM latency moves a lot through the day: per request p50 was 1.2 s in the morning smoke test and 2.8 to 3.6 s in the evening sweep check, same images. The sweep's wall time is its slowest phrase, so measure latency more than once before trusting a number. (Orlando, Oct 26)
  17. "Simple Image Analyzers" is on the guide's anti project list, and Stage One is pass/fail. The pitch, README and video must lead with context, multi clue leaks and destination, not "detects PII in images". (Orlando, Oct 26)
  18. API calls fail until a credit card is on the account, even with credits granted. Each person claims their own credits. (Orlando, Oct 26)
  19. Baseten's docs use `meta-models/muse-spark-open`; the hackathon model ID is `meta-models/muse-spark-open-1026`. (Orlando, Oct 26)
