# Controlled 1280-input detector experiment — November 12, 2026

## Decision

Do **not** change production resolution based on this experiment. At the same
fixed cutoffs, the 1280-input variant finds four previously missed ball labels
but loses three previously matched ones: net **21 → 22 of 27**, with unmatched
ball predictions increasing **0 → 4**. Frame-processing CPU latency is **2.537×**
the 960 baseline. This is mixed development agreement, not a demonstrated
real-world accuracy improvement. Obtain labels from new games, adjudicate
omissions/localization disagreements, and measure deployment-specific latency
before considering another resolution decision. No production change is shipped.

## Frozen protocol and actual run

Exactly one local inference run completed **44/44** frozen CURRENT44 Menlo stills
in **75.465 seconds total**, within the approximately 180-second budget. Inference
and setup finished at 75.141 seconds; post-run provenance verification and export
are included in total time. No images remained unprocessed. No threshold search,
selected-case-only run, training, installs, network, paid/cloud calls, full-film
processing, MPS or GPU inference occurred.

`ml/tools/detector_resolution_eval.py` imports the baseline's unmodified pure
file hashing, manifest verification, COCO/prediction validation and evaluation
helpers. Matching remains `detector_report.match`, confidence-first greedy
per-image/per-class, IoU >= 0.5. The only changes to the baseline protocol fields
are `input_size: 960 → 1280` and `budget_seconds: 540 → 180`.

- CPU float32, four Torch threads, one interop thread, one OpenCV thread, seed 0.
- Ball 0.20, player 0.10, referee 0.35, rim 0.50; score is objectness × confidence.
- Postprocess score floor 0.10, NMS 0.45, class-aware NMS; no confidence tuning.
- Same YOLOX-M, strict four-class state loading, `weights_only=True`, no fallback.
- Same `ValTransform(legacy=False)`, BGR uint8, bilinear resize, top-left padding
  114, CHW float32, inverse resize ratio to xywh, no clipping.
- Same ordered 44 images, image bytes, annotation snapshot and checkpoint.
- Local dependencies: Torch 2.14.1, torchvision 0.29.1, NumPy 2.2.6,
  YOLOX 0.3.0, OpenCV 5.0.0; Python 3.10.13 on macOS arm64.

The checkpoint metadata is deliberately checked against **training input 960**,
not incorrectly required to claim 1280 training. The runner explicitly records
an intentional dynamic fully convolutional YOLOX inference experiment at 1280,
sets the experiment test size and passes `(1280, 1280)` to the unchanged transform.
The input guard requires an integer multiple of 32 within 320..1280 and then
restricts this particular one-variant runner to exactly 1280. There is no hidden
monkeypatch, altered baseline, model retraining or silent metadata mismatch.

## Complete-set as-labeled agreement

Each cell lists **matched / missed annotations / unmatched predictions**.

| Class | Labels | Baseline 960 | Variant 1280 | New matches | Lost matches | Unmatched delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ball | 27 | 21 / 6 / 0 | 22 / 5 / 4 | 4 | 3 | +4 |
| player | 408 | 382 / 26 / 32 | 388 / 20 / 46 | 8 | 2 | +14 |
| referee | 108 | 100 / 8 / 7 | 100 / 8 / 10 | 4 | 4 | +3 |
| rim | 42 | 42 / 0 / 0 | 42 / 0 / 0 | 0 | 0 | 0 |

Ball annotation-agreement recall is 77.78% → 81.48%, while annotation-agreement
precision is 100% → 84.62%. Unmatched predictions are not adjudicated false
objects: existing annotations can omit objects or disagree on localization.
No annotation was changed to improve these numbers.

### Exact changed annotation IDs

These are annotation identities, not approximate associations between predicted
boxes. A label is matched if it is absent from the unchanged matcher's missed
annotation list; this avoids a second custom matcher or tie-breaking rule.

| Class | Newly matched annotation IDs | Lost matched annotation IDs |
| --- | --- | --- |
| ball | 129, 312, 402, 461 | 38, 142, 360 |
| player | 8, 238, 373, 403, 447, 514, 583, 584 | 173, 415 |
| referee | 368, 406, 475, 571 | 36, 257, 269, 488 |
| rim | none | none |

The three lost ball matches are annotations 38/image 804, 142/image 814 and
360/image 840. Thus recovery of four old misses must not be presented as a
four-label net gain. Full exact baseline and variant unmatched prediction
records, including every image ID, bbox and score, are retained per class in
private `comparison.json`. Boxes move between resolutions, so no invented
cross-resolution prediction identity is used to call individual unmatched boxes
"new" or "lost". The exact counts and complete records are reported instead.

### Outcomes for all six baseline ball misses

The context descriptions below are inherited model-assisted observations from
the parent's private six-ball review, not new human adjudication or labels.

| Image ID | Annotation ID | Prior review context | 1280 outcome |
| ---: | ---: | --- | --- |
| 813 | 129 | player-held/dribbled context | matched |
| 818 | 185 | player-held/dribbled context | still missed |
| 831 | 258 | partial frame-top object | still missed |
| 835 | 312 | player-held/dribbled context | matched |
| 844 | 402 | official-held context | matched |
| 849 | 461 | official-held, relatively large foreground ball | matched |

Image 818 still has an unmatched ball prediction above the fixed cutoff
(score 0.591923), so "missed" specifically means it did not match the existing
box under this fixed IoU/matching protocol, not necessarily absence of a nearby
detection. The four unmatched ball records are in images 818, 846, 849 and 856,
with respective scores 0.591923, 0.538500, 0.663754 and 0.833177. Existing boxes,
not subjective visual recovery, determine every outcome. The reviewed misses
include held and partial balls, and must not all be characterized as tiny.

## Measured CPU cost

| Timing quantity | Baseline 960 | Variant 1280 |
| --- | ---: | ---: |
| Sum of 44 per-image processing times | 28.215 s | 71.572 s |
| Mean per-image processing time | 0.641 s | 1.627 s |
| Frame-processing throughput | 1.559 frames/s | 0.615 frames/s |
| Whole-run time including setup/export | 32.201 s | 75.465 s |

Frame latency ratio is **2.536622×**. Per-image timing includes image decode,
transform, model inference, postprocessing, box restoration and validation; it
is not isolated model-kernel latency. The historical baseline and this variant
are single runs, not repeated/interleaved benchmarks or a claim of identical
background system load. Do not extrapolate these CPU still-image numbers to
production GPU throughput, tracking, interpolation or full-game behavior.

## Private artifacts and provenance

Private, git-ignored output:
`ml/data/labels/detector_resolution_20261112/`.

- `manifest.json`: frozen read-only **before inference**, binding 152 unique
  file records: all 119 baseline provenance records plus baseline result,
  predictions and manifest, variant snapshot, new runner/tests, dependency
  entry points and local compiled extension files.
- `annotations.json`: read-only byte-identical snapshot of the baseline labels.
- `predictions.json`: all fixed-cutoff variant boxes, not only selected cases.
- `processed_images.json`: exact processed/unprocessed/zero-detection coverage.
- `result.json`: metrics, timings, command, completion and provenance status.
- `comparison.json`: same-subset metrics, exact newly/lost matched annotation
  IDs, all unmatched records for both runs, and six old-ball-miss outcomes.
- `error_review.json`: up to 12 frames from the unchanged baseline evaluator;
  this bounded review is not the complete evidence for the reported comparison.

SHA-256 identities:

```text
baseline manifest  4b8991eb63c17edba2a2647bdf62399b65873e843703ba116c0d7398723355c2
variant manifest   0bef289f509a3bf37beb07a7f9f53f257bf1f2de72b2b5b6142ffbb46a6253b9
checkpoint         d009e6911b10ba08a027d870f7fee01d1deddbd4d8290b01a7f0ab85ce795660
annotation bytes   9ec13b43e6e473d60b9387b0600df3be87b53c3d3fdf62da69aa916a4619a974
variant predictions 06a28853dbd9adde141f11cbf381e7af3ed347df4c5259e2cda0da0462c75eb6
comparison         f6549a98256e2fbaf072db1085ef4484d03f47cf63115270a1fdb8a9a6ad28b1
```

The checkpoint remains `ml/runs/v4/aim_yolox_m.pth`. Both manifests and every
bound file were verified after inference; a separate reload/recompute also
reproduced metrics, coverage, error review and the full comparison exactly.
The saved baseline metrics/coverage were independently recomputed from its
predictions before inference too. Existing baseline, report, vision, training,
prelabel, dataset, image and model files were not modified. The images and
checkpoint are hash-referenced rather than copied: retain their original bytes.
Read-only manifests and exclusive output creation are safeguards, not an
external tamper-proof archive. This document is a post-run description, not
part of the pre-inference source manifest.

## Actual commands and validation

From `/Users/arnavmani/AIM`:

```sh
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 ml/.venv/bin/python ml/tools/detector_resolution_eval.py
python3 -m unittest discover -s ml/tools -p test_detector_resolution_eval.py -v
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_detector_resolution_eval.py -v
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_local_detector_baseline.py -v
git diff --check -- ml/tools/detector_resolution_eval.py ml/tools/test_detector_resolution_eval.py ml/docs/detector_resolution_eval.md
```

The six new stdlib tests pass under both system Python and the local ML venv;
all 12 existing baseline tests also pass. New tests cover size/stride/bounds,
protocol drift, checkpoint/image/category/dependency/annotation comparability,
same-size file mutation, manifest mutation and overwrite refusal before any
inference dependencies load. No mocks or hidden dependency monkeypatches are
used. A separate `PYTHONPATH=ml/tools ml/.venv/bin/python` reload check invoked
`verify_frozen` on both manifests, `validate_comparability`, `evaluate` and
`comparison`, asserting exact equality with saved artifacts; all passed.

The run command now intentionally refuses to overwrite the existing output
directory. Do not delete the frozen artifacts to repeat it. A future authorized
run would need a new output path. On interruption the runner records only
completed image IDs and compares only that identical subset of the baseline
predictions; it suppresses agreement if no image completed or provenance fails.
The 180-second signal deadline covers setup and inference; final provenance
verification and artifact export occur after disabling that timer. This actual
whole run completed well below 180 seconds, without relying on a timeout claim.

## Limits

These are **as-labeled development agreement** measurements, not ground-truth
accuracy, untouched holdout performance, statistical confidence, new-game
generalization or production GPU equivalence. Menlo CURRENT44 is known
development/checkpoint-selection data; historical training membership is
unknown. Local checkpoint identity does not establish live deployment weights.
No confidence optimization, production edits, commit, push or deployment is
authorized or performed. The useful next evidence is adjudicated **new-game
labels plus latency evaluation**, not promotion of this one mixed result.
