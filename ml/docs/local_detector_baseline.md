# Fresh local detector baseline — November 12, 2026 (Pacific)

This is a **measured as-labeled agreement baseline**, not a model accuracy gain.
The existing local v4 checkpoint was run once on all **44 CURRENT44 Menlo
development/checkpoint-selection still images**, containing 585 existing boxes.
This is **not an untouched holdout**. Historical training membership is unknown.

## Actual run

- Completed 44/44 frames; no unprocessed frames and no zero-detection frames.
- Exported 584 predictions after the fixed class cutoffs; no old prediction cache
  was read. Explicit processed IDs are stored independently of predictions, so a
  processed frame with zero boxes is distinguishable from an unprocessed frame.
- Measured runtime: **32.201 seconds**, including imports, input verification,
  model construction/loading and inference through post-run provenance checking
  and prediction export. The image loop totaled **28.215 seconds**. Subsequent
  matching/review export is outside that runtime measurement.
- CPU only, float32, batch one, four Torch intra-op threads, one inter-op thread
  and one OpenCV thread. The enforced inference/setup wall-time budget was 540
  seconds; it was not approached. No GPU/MPS, network, cloud service, training,
  full-film decoding, or dependency installation was used.
- Local environment: Python 3.10.13, macOS 15.7.3 arm64, Torch 2.14.1,
  Torchvision 0.29.1, NumPy 2.2.6, YOLOX 0.3.0 and OpenCV 5.0.0.
- Safe `torch.load(..., map_location="cpu", weights_only=True)` **succeeded**.
  No serialization API incompatibility occurred and no unsafe-load fallback was
  used. The tool stops and records an exception if this API or dependencies fail.

## Fixed protocol and results

YOLOX-M with four classes and checkpoint-validated input size 960, using the
existing `ValTransform(legacy=False)` / `postprocess` approach from
`ml/train_modal.py` and `ml/tools/prelabel.py`. BGR images are resized with the
YOLOX OpenCV transform, padded at top-left with 114, and passed as CHW float32.
Boxes are restored using the original resize ratio without clipping. Scores are
objectness times class confidence. Class-aware NMS is fixed at 0.45 with a common
pre-filter floor of 0.10, then fixed worker cutoffs are applied. No calibration,
threshold sweep, ceiling-rim exclusion, or confidence masking was performed.

Matching reuses **`detector_report.match`**, greedy descending-score matching
within each image/class at IoU >= 0.5. Its old cache-reading/report entry point is
not called. Foreign IDs and unknown categories cause errors, not silent filtering.
Decoded image sizes must match COCO sizes exactly.

| Class | Cutoff | Existing labels | Matched | Missed annotations | Unmatched predictions | Agreement precision | Agreement recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ball | 0.20 | 27 | 21 | 6 | 0 | 100.00% | 77.78% |
| Player | 0.10 | 408 | 382 | 26 | 32 | 92.27% | 93.63% |
| Referee | 0.35 | 108 | 100 | 8 | 7 | 93.46% | 92.59% |
| Rim | 0.50 | 42 | 42 | 0 | 0 | 100.00% | 100.00% |

Here, agreement precision = matched / (matched + unmatched predictions), and
agreement recall = matched / (matched + missed annotations). An unmatched
prediction is **not a proven real-world false positive**: annotation omissions
have not been adjudicated. Similarly, these values do not establish real-world
recall, generalization, complete negative labeling, rim saturation, or full-game
detector recall. There are only 27 labeled balls and 42 labeled rims in one camera.

CPU still-image `ValTransform` is **not equivalent** to the worker's GPU tensor
interpolation, half precision, video sampling, ByteTrack, or downstream logic.
These hashes identify the evaluated **local** checkpoint only; they do not prove
which weights are live in deployment.

## Frozen provenance and private artifacts

Private, git-ignored directory:
`ml/data/labels/local_detector_baseline_20261112/`.

- `manifest.json`: written exclusively and made read-only **before loading the
  model or running inference**, at `2026-11-13T04:45:04.731359+00:00` UTC
  (November 12 Pacific). It binds image IDs/names/dimensions/byte sizes/SHA-256,
  actual COCO bytes, checkpoint bytes, category mapping, source hashes, dependency
  versions, ordered membership, preprocessing, budgets and thresholds. Source
  records include the tool, matching implementation, three reference inference
  files, and all installed YOLOX Python sources. This is a fresh manifest, not
  fabricated provenance for historical cached predictions.
- `annotations.json`: read-only exact-byte copy of the evaluated COCO snapshot.
- `predictions.json`: fresh COCO-style xywh boxes, class IDs, image IDs and scores
  at the fixed cutoffs, without rounding.
- `processed_images.json`: explicit processed, unprocessed and zero-box IDs.
- `result.json`: metrics, completeness, timings, command, failures (null here),
  manifest hash and successful post-run provenance verification.
- `error_review.json`: up to 12 actual error frames, ranked by total missed-label
  plus unmatched-prediction count, then image ID; includes original filenames,
  annotated missed-box IDs/coordinates and unmatched predicted boxes/scores.
  It is a review queue, not a human adjudication. No overlays were generated.

SHA-256 bindings:

```text
manifest:   4b8991eb63c17edba2a2647bdf62399b65873e843703ba116c0d7398723355c2
checkpoint: d009e6911b10ba08a027d870f7fee01d1deddbd4d8290b01a7f0ab85ce795660
COCO bytes: 9ec13b43e6e473d60b9387b0600df3be87b53c3d3fdf62da69aa916a4619a974
```

The checkpoint is `ml/runs/v4/aim_yolox_m.pth` (101,520,126 bytes); the COCO
source is `ml/data/dataset/annotations/instances_val2017.json` (107,199 bytes).
All 119 bound file records and the manifest's own hash were checked unchanged
after inference. Hash verification plus exclusive creation/read-only permissions
prevents unnoticed mutation/accidental overwriting; this is not an external
tamper-proof archive. The existing source images and checkpoint are referenced,
not duplicated, so retain them for reproducibility.

The bounded review queue contains image IDs
**859, 845, 858, 802, 804, 819, 852, 822, 835, 839, 841, 843**.
For example, image 835 is
`valley-christian-vs-menlo-atherton-tactical__t03326.0.jpg`; its missed ball
annotation is ID 312, xywh approximately `[1644.591, 409.411, 20.978, 22.372]`.
Image 859 includes missed player annotations 583 and 584 and five unmatched
predictions. These references come from the actual matching output, not old
scoring windows. The top-12 queue is deliberately incomplete; all predictions
and labels remain available to reconstruct all 40 misses and 39 unmatched boxes.

## Exact commands and validation

Run from `/Users/arnavmani/AIM`:

```sh
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 ml/.venv/bin/python ml/tools/local_detector_baseline.py --threads 4 --seconds 540 --max-images 44
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_local_detector_baseline.py -v
```

The default output directory must **not already exist**. Repeating the first
command now intentionally refuses to overwrite this baseline. To run a separate
authorized baseline later, choose a new `--output` directory; this task does not
authorize replacing the frozen artifacts. `--max-images` can explicitly bound a
future run; subset/timeout results list unprocessed IDs and never claim full-set
coverage. No metrics are emitted if nothing completed or provenance changed.

The focused tests use only the standard library and cover same-size provenance
mutation, missing files, explicit zero-box versus unprocessed coverage, foreign
prediction/processed/annotation IDs, unknown classes, category mapping and image
dimensions, duplicate processed IDs, exclusive artifact creation, and refusal of
an existing output directory before loading inference dependencies.

All **12 tests passed** under both `ml/.venv/bin/python` and the system
`python3`. A separate post-run check rehashed all 119 provenance records,
confirmed the read-only manifest/hash and explicit coverage, and independently
recomputed the saved metrics and 12-frame review from the exported predictions
and annotation snapshot using the same shared matcher; all matched exactly.

No production, training, detector audit or existing report file was modified.

## Parent verification and missed-ball review

The parent independently rehashed the manifest-bound files and recomputed all
metrics and the complete saved error-review export from the frozen predictions
and COCO snapshot. Both reproduced exactly, and all 12 focused tests passed.

A private contact sheet at
`ml/data/labels/ball_miss_review_20261112/six_ball_misses.jpg` shows all six missed
ball annotations at original-image scale with their existing boxes overlaid.
Images 813, 818 and 835 show player-held/dribbled-ball contexts; 831 is a partial
frame-top object; 844 and 849 show balls held by officials. The latter include
a relatively large foreground ball, so small-object resolution alone is not a
complete explanation. These are model-assisted visual observations, not human
adjudication, new training labels, or evidence that every annotation is correct.

Next controlled experiment: repeat the same frozen annotation agreement protocol
at a larger detector input, keeping class cutoffs and matching unchanged. Any
gain must be reported with additional unmatched predictions and CPU cost; it does
not authorize changing deployed resolution or replacing an untouched-game test.
