# Detector data audit — 2026-11-12

## Decision

Do not add another detection rule or launch training from the current reports.
The defensible next action is to freeze a provenance-bound baseline and review
small-ball coverage and referee/player confusion before a controlled data refresh.
No new detector precision, recall, AP, or full-game detection recall is established
by this audit. All four classes' detector metrics remain **unknown** under the
requested strict model/annotation/image/split provenance standard.

This is an offline inspection of existing local artifacts only. No installation,
inference, training, paid service, secret access, footage upload, film decoding,
commit, deployment, or automatic creation of training labels was performed.
Coach labeling and class expansion are not part of this work.

## Reproduction and private evidence

Run from the repository root:

```sh
python3 -m unittest discover -s ml/tools -p test_detector_data_audit.py -v
python3 ml/tools/detector_data_audit.py --output ml/data/labels/detector_audit_20261112 --failure-report ml/data/labels/points_accuracy_2026_11_12/before-report.json --candidate-limit 12 --review-image-id 819 --review-image-id 845 --review-image-id 858 --review-image-id 859 --review-image-id 806 --review-image-id 850
git diff --check -- ml/tools/detector_data_audit.py ml/tools/test_detector_data_audit.py ml/docs/detector_data_audit.md
```

The standard-library tool deliberately does not reimplement `detector_report.py`.
It inventories COCO coverage, reads JPEG size headers, hashes every dataset image,
checks annotation and prediction structure, checks current game/ID/filename/exact-byte
overlap, and inventories unfiltered prediction IDs. It never equates an absent
prediction with an unscored frame or an absent annotation with a true negative.
It exports at most eight explicitly requested existing validation stills without
decoding footage and mines at most 24 cached scoring windows. No annotation files
are written. Output is restricted to the private audit directory.

Private `ml/data/labels/detector_audit_20261112/audit.json` contains exact input
SHA-256 values, per-image hashes and actual sizes, Python version, checkout HEAD,
six unreviewed scoring windows, and six copied validation-frame records. `tests.txt`
captures the focused test results. This directory is ignored by the repository's
existing `ml/data/` rule; do not force-add the images or annotations.

Nine focused unit tests pass, including provenance refusal despite matching IDs,
foreign-ID retention, invalid predictions, missing-label semantics, size reading,
duplicate/dangling annotations, exact-byte leakage, bounded review export, and
candidate balancing. These are tool tests, not detector validation.

## What the artifacts can and cannot support

| Prediction directory | Boxes | IDs with boxes | IDs overlapping current validation |
| --- | ---: | ---: | ---: |
| v1 | 2,106 | 157 | 0 |
| v2 | 1,091 | 82 | 0 |
| v2-retest | 1,718 | 130 | 0 |
| v3 | 1,670 | 130 | 0 |
| v3-menlo | 705 | 44 | 44 |
| v4 | 615 | 44 | 44 |

These are artifact counts, not detector performance measurements. All six bare
prediction files lack filenames, image sizes/hashes, annotation snapshot hashes,
checkpoint hashes, and historical train/validation manifests. The current exporter
uses Label Studio task IDs and rewrites the dataset in place. Matching IDs and a
matching report label count are necessary clues, not sufficient proof that the
labels, images, checkpoint and split were those actually evaluated.

The v1/v2/v2-retest/v3 files cannot score the current Menlo validation set at all.
v3-menlo and v4 are plausible baseline candidates, but their exact evaluation
provenance remains unbound. `v3-menlo/aim_yolox_m.pth` is byte-identical to the v3
checkpoint; the directory name alone does not establish a separate training run.

Existing `report.json` values are archival claims, not independently certified
metrics. Existing `summary.json` is an aggregate best AP, not per-class evidence.
Training logs are useful for configuration history, not a replacement for binding
predictions to the actual labeled images. No metrics were filled in from source
comments, logs, or aggregate counts.

`detector_report.py` reads today's validation JSON, silently filters foreign
prediction IDs, and selects each class's best-F1 cutoff on that same set. It does
not prove provenance or evaluate the worker's fixed operating point. Its rim
subgroups use a geometry heuristic, not adjudicated main/ceiling labels. For a
future trusted baseline, retain its matching logic if appropriate, but first bind
the artifacts, freeze cutoffs on a separate calibration set, and separately measure
the worker operating point and cross-class confusions. Do not present same-set
cutoff optimization as untouched-test performance.

## Current labeled coverage, not recall

All 811 COCO image records have matching on-disk JPEG dimensions; the structural
audit found no errors. Every image is 1920 by 1080. Current COCO totals:

| Split | Images | Ball boxes | Player boxes | Referee boxes | Rim boxes |
| --- | ---: | ---: | ---: | ---: | ---: |
| train2017 | 767 | 572 | 5,790 | 902 | 1,308 |
| val2017 | 44 | 27 | 408 | 108 | 42 |

At the configured 960 square letterbox input, these 1080p images have a 0.5
linear scale. Ball short sides below 16 input pixels occur in 286/572 training
labels and 23/27 validation labels; below eight occur in 5 and 1 respectively.
Ball original-image area below 32 squared pixels occurs in 252 training and 23
validation labels. These are geometry/coverage counts, not COCO AP-small or small
object recall. Width/height at deployment depend on the actual source dimensions.
Training also uses random multiscale resizing (`multiscale_range=5` in the v4 log)
and mosaic/mixup, so these unaugmented 960-input counts do not describe every
training tensor. They identify a data-resolution risk, not a proven cause of misses.

Training images without a ball label: 199; validation images without one: 17.
These may be occluded/off-screen balls, intentional negatives, or missing labels;
the files do not tell us which. They must not be called 216 missed balls. Referee
labels are absent in 117 training images and one validation image; rim labels in
55 and two respectively. Review visible-object completeness before interpreting
unmatched predictions as false positives. Training tasks 36, 53, 131 and 694 have
two ball labels each; inspect whether both are genuine visible balls rather than
automatically deleting the extra label.

### Game leakage and coverage

Current training: Ontario Christian (367 frames), NoLimit vs DRIVE (400 frames).
Current validation: Menlo-Atherton (44 frames). There are no shared current game
names, image IDs, filenames, or exact image bytes across these two splits. This
does not rule out alternate encodes, reused footage, or historical run leakage.
No semantic near-duplicate search was performed.

`ml/games.yaml` records that through v3, NoLimit trained on its first half and
tested on its second half. That is same-game leakage for a claimed unseen-game
generalization result, even if frames differ. It records v4 switching all NoLimit
to training and Menlo to evaluation. Historical annotation manifests are absent,
so the exact old split cannot be independently reconstructed from those comments.
Mitty and Riordan are designated evaluation games but have **zero detector COCO
frames** in this snapshot. Their scoring/track artifacts do not supply detector
ground truth. Repeated use of Menlo for checkpoint/cutoff selection also makes it
a development/validation set, not a pristine final test.

## Model and operating-point provenance

Source inspected: `worker/vision.py`, `worker/film_worker.py`, `ml/train_modal.py`,
`ml/tools/export_dataset.py`, and `ml/tools/detector_report.py`; exact byte hashes
are in the private audit. Worker source selects `MODEL_RUN = "v4"`, naming
`aim-yolox-m-v4` and `/models/aim_yolox_m_v4.pth`. No deployed model was fetched or
hashed; local v4 identity must not be assumed to prove deployed weight identity.

Training source pins YOLOX `6ddff4824372906469a7fae2dc3206c7aa4bbaee`, YOLOX-M,
four classes in order ball/player/referee/rim, 960 input, Torch 2.4.1,
Torchvision 0.19.1 and OpenCV 4.10.0.84; NumPy is only constrained to `<2`.
The v4 log records 100 epochs, batch eight, FP16, seed None, mosaic scale
0.5–1.5 and mixup probability 0.5. This does not establish bitwise repeatability.

Training's final cached prediction pass uses score floor 0.05 and NMS 0.45,
rescales to original-image coordinates, and writes only bare boxes. Its periodic
YOLOX evaluation uses log settings `test_conf=0.01`, `nmsthre=0.65`; aggregate AP
and cached-box operating-point metrics therefore need not be identical protocols.
Worker defaults are ball 0.20, player 0.10, referee 0.35, rim 0.50, NMS 0.45,
10 fps, and player new-track activation 0.50. Lower-confidence players feed
ByteTrack, not a raw player-box export. Worker resizes footage to at most 1080 high
before model preprocessing and uses GPU interpolation/FP16, whereas cached
validation uses `ValTransform` on stills. Thus even a trusted cached-box baseline
would not measure all deployment/tracking behavior. No cutoff changes are made.

Selected exact hashes, with the full source inventory in `audit.json`:

```text
checkout HEAD b9881de203069bf23051dd467a84f626f3233535
train COCO 9b9e6a4cf4f14b5ddc0ae6ee816987aaf32c5083d867bcefc6628d6208780605
val COCO   9ec13b43e6e473d60b9387b0600df3be87b53c3d3fdf62da69aa916a4619a974
local v4   d009e6911b10ba08a027d870f7fee01d1deddbd4d8290b01a7f0ab85ce795660
vision.py  00de07eff92a97408fcbbffedf05a600038d854077c652291459a1c4a219ba63
train.py   4108dfb06d44661a4f8803201e646eb20128ec7210739a8b92b0fb1b92c1e7b5
```

## Bounded review queue and concrete hypotheses

The assistant inspected existing `v4/mistakes_1.jpg`, `v4/mistakes_2.jpg` and the
full-resolution current task-845 still. This was qualitative triage, not human
adjudication or compatible-model evaluation. All following candidates remain
unreviewed for training and their archival model provenance remains unbound.

Six copied current validation stills:

| Task | Menlo film second | Review purpose |
| --- | ---: | --- |
| 819 | 1902.0 | Crowded player/referee separation and apparent foreground false player in archival sheet; audit annotation completeness. |
| 845 | 4216.0 | Striped foreground official is visibly a referee; current annotation 406 is referee, while the archive has a player box at score 0.940 in essentially the same location. A concrete cross-class confusion candidate, not an error-rate estimate. |
| 858 | 5373.0 | End-game crowd/occlusion; several apparent overlapping player errors in archival sheet; ball unlabeled, visibility unknown. |
| 859 | 5462.0 | End-game crowd/occlusion; ball unlabeled, visibility unknown. |
| 806 | 745.0 | Archive has an extra ball-shaped box near the hoop at score 0.0694 in addition to a ball near score 0.891. Review fixture/background confusion and possible label omission. |
| 850 | 4661.0 | Archive has an extra ball-shaped box near the hoop at score 0.1120 in addition to a ball near score 0.567. Same review purpose. |

The extra ball boxes in 806/850 are both below the worker ball cutoff 0.20, so
they are not evidence of false balls surviving that runtime cutoff. Conversely,
the 845 player score is well above both player ingestion and track activation
thresholds; threshold tuning alone is unlikely to remove that confusion safely.
No claim is made about other surviving false balls; their rate remains unknown.
This comparison reads stored scores, not a new precision/recall computation.
The rim archive is insufficient to establish saturation: only 42 rim labels are
present on this one validation camera, and main/ceiling identity is not annotated.
There is no defensible evidence here to prioritize a new rim rule or claim that
rim recall transfers to Mitty/Riordan.

Cached scoring failures from `points_accuracy_2026_11_12/before-report.json`:

| Game | Local film window, seconds | Cached trigger |
| --- | --- | --- |
| Mitty | 668.27–683.07 | Valley score becomes 6 |
| Riordan | 2487.73–2502.80 | Valley score becomes 19 |
| Mitty | 1853.33–1868.13 | Valley score becomes 18 |
| Riordan | 4396.00–4412.13 | Valley score becomes 30 |
| Mitty | 3389.87–3404.93 | Opponent score becomes 49 |
| Riordan | 5100.00–5115.07 | Opponent score becomes 53 |

Only six `not found` events exist in that chosen cached report; a requested cap of
12 does not justify inventing six more. The windows are heuristic: 12 seconds
before the last old score and two seconds after the first new score. Scoreboard
lag can place the shot outside the window. These could be occlusion, camera cuts,
missed detections, localization, tracking, scoreboard delay or downstream scoring
logic. They are **not** six detector false negatives. No video frames were decoded
for these windows; the queue exports timestamps and evidence pointers only.

## Next defensible training action

1. **Recover or remake the baseline, with approval for later inference.** Recover
   historical immutable annotations/images and checkpoint bindings if available;
   otherwise run the local v4 checkpoint once on a frozen dataset and write a
   manifest binding checkpoint SHA, source/YOLOX revision, annotation hashes,
   per-image hashes/IDs/sizes, categories, train/calibration/eval membership,
   preprocessing, score floor/NMS and all evaluated IDs including zero-box frames.
   Never fabricate a retroactive provenance manifest from today's files. Score
   fixed worker cutoffs, class confusion, ball size/visibility strata and
   game-separated uncertainty; use separate calibration for any cutoff sweep.
2. **Review data before training.** Adjudicate the six existing stills, four
   multiple-ball training tasks and six scoring windows. On fully labeled frames,
   annotate every in-scope visible ball/player/referee/rim and explicitly record
   true absent, occluded/unresolvable and not-reviewed states. Inspect false-ball
   fixture/background examples as negatives only after confirming no omitted ball.
   Do not turn model outputs into labels. Keep the existing four-class scope.
3. **Collect a small, diverse donor set.** As a proposed initial budget, not an
   empirically established requirement: 200–400 fully reviewed frames from at
   least two additional authorized training games/cameras, stratified across
   small airborne/held balls, motion blur, occlusion, striped officials near
   players, crowd/bench negatives and fixtures. Avoid adjacent-frame duplication;
   review all classes in each selected frame. Keep Menlo and the designated
   Mitty/Riordan evaluation footage out of training. If any evaluation game is
   explicitly reclassified as development/training, first obtain a new untouched
   whole-game test set and retire the old unseen-game claim. Obtain 100–200
   separately reviewed, game-held-out evaluation frames spanning positive and
   genuine negative/visibility strata; no full-film recall claim follows from them.
4. **Train only after evidence supports the data change.** Start with a
   controlled data-only YOLOX-M/960 fine-tuning experiment using the existing
   pinned stack, COCO start weights, augmentation and batch-eight configuration.
   Preserve the frozen old-data baseline. Run an input-resolution/augmentation
   ablation only if adjudicated small-ball misses remain; a higher input size has
   greater memory/compute cost and is not automatically better. Do not mix a rules
   change, label refresh and model/config change in one claimed improvement.
5. **Compute/data needed later, not used here.** Authorized local footage and
   a human box/visibility reviewer; disk for frozen JPEG/COCO/manifests and model
   checkpoints; one compatible CUDA GPU with capacity for YOLOX-M 960, FP16,
   batch eight (reduce batch if required), plus the existing pinned environment.
   The historical v4 log spans approximately 47 minutes for 100 epochs on its
   original small dataset; GPU identity is not recorded in the inspected log, so
   this is not a runtime/cost promise for new hardware or more data. Plan one
   baseline inference pass and one controlled training run plus evaluation, then
   consider repeated seeds only after an improvement survives held-out inspection.

Full-game unknown detection recall remains unknown until an appropriate
independently labeled sampling protocol exists. Scoring outcomes, cached track
coverage, detector comments and confident predictions cannot substitute for it.
