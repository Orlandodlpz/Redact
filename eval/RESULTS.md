# Evaluation results (draft for the README)

Owner: Carlos. Written Nov 4. The README is Orlando's file, so this is a section for him to paste once the team agrees on the open points at the bottom. Every number comes from `eval/results/2026-11-04_879bdcf/` (commit `879bdcf`, clean tree, floor rules on, models `muse-spark-1.2` at `minimal` and `sam-3.1`, prompt `judge_v1`). Reproduce with `uv run python eval/run_eval.py --config redact --split dev`.

## What was measured

20 staged images (7 photographs of real scenes, 13 AI generated), all from the dev split, labeled by hand. 10 of them are labeled for all three destinations, so the 20 images give 40 scored runs and 65 labeled items per config. One run per config. Costs are list price estimates.

An item counts as caught when the final mask covers at least 90% of its labeled box. We report that two ways, and the difference matters:

- **By pixel:** the exact pixels a user downloads. This was fixed before any run, so it is the primary number.
- **By box union:** the same rule on the boxes of the masked findings. A SAM mask fills only about 80% of its own box (rounded card corners, tilted objects), and our labels are rectangles, so a fully covered card can fail the pixel rule. The box number matches our earlier judge only bake off (about 60%).

## Results

| Config | Caught, by pixel | Caught, by box union | Destination accuracy | Keep cells / mask cells | p50 latency | Cost per image run |
|---|---|---|---|---|---|---|
| **Redact** | 24 of 65 | 38 of 65 | 0.53 | 1.00 / 0.35 | 8.0 s | about $0.055 |
| B1: SAM faces and plates only | 1 of 65 | 4 of 65 | 0.27 | 1.00 / 0.00 | 1.7 s | about $0.005 |
| B2: Presidio on our OCR text | 8 of 65 | 8 of 65 | 0.32 | 1.00 / 0.06 | 0.5 s | $0 |
| B3: Muse Spark alone | 8 of 65 | 7 of 65 | 0.36 | 0.94 / 0.15 | 2.1 s | about $0.006 |

Destination accuracy asks, for each labeled item on the 10 images labeled for all three destinations, whether the system masked or kept it the way the label says for that destination. The three baselines ignore the destination on purpose, so they keep everything a label says to keep and mask almost nothing that a label says to mask. Redact is the only config that gets both kinds of cell right, and its mask cells are low mostly because of the pixel rule above.

Redact by image type (never pooled, because the AI generated images are easier):

| | By pixel | By box union |
|---|---|---|
| Photographs (19 runs, 26 items) | 8 | 11 |
| AI generated (21 runs, 39 items) | 16 | 27 |

Redact by category, by box union: credential 11 of 11, home location 10 of 11, face 3 of 5, government ID 4 of 7, personal account 4 of 6, license plate 2 of 3, payment 1 of 2, contact info 1 of 4, other sensitive 2 of 8, internal data 0 of 8.

Redact's p90 latency was 16.7 s end to end. Mean over redaction (share of the image masked outside every labeled item) was 0.020 for Redact.

## Why items were missed

Of 41 missed rows for Redact (by pixel): 14 failed only the pixel rule, 11 were never proposed by SAM or OCR so no judge could have caught them (a background face, a pedestrian's face, a hand held ID, a truck plate, a dashboard on a cartoon image), 1 was partly covered, and 15 were the judge calling the region benign: internal data such as a whiteboard of meeting notes, inbox rows, a phone number on a mug. A second judge call on those images flagged a few of them, so single runs are noisy. `eval/error_analysis.py` lists each one.

## Limits, stated plainly

- 20 images, one run each, all dev split. No test split is labeled, so none of these numbers is a held out estimate, and we make no claim about unseen images.
- 7 of the 20 are photographs, and Redact does clearly worse on those.
- No hard negative images were run, so there is no false positive rate. Over redaction is a pixel share, not a count of wrongly masked objects.
- Presidio (B2) and Muse Spark alone (B3) were run once with settings fixed beforehand (score threshold 0.4, one fixed prompt), not tuned. B3 draws its own boxes with no SAM or OCR.
- The labels were written by one team member, and an item such as a business phone number on a mug is a judgment call.
- Not built: tiles for small objects, a padded face box, pre-masking, and the 150 image set. Faces fail the pixel rule partly because SAM masks the skin, not the hairline to chin box we label.
- WebPII was not used, so there is no attribution to add for it.

## Open points before the README uses these numbers

1. Which recall is primary, pixel or box union. We recommend showing both, as above.
2. The destination accuracy and over redaction definitions, the 90% rule and B2 and B3 settings are our proposals; the team has not confirmed them.
