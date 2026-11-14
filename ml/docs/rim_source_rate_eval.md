# Bounded Riordan source-rate rim experiment

Executed November 12, 2026, America/Los_Angeles (artifact UTC dates may be
November 13). Development diagnostic, **not human adjudication**. R4415-F3's
rejection interpretation remains provisional. No labeling queue was created.

## Result: an observed sample changes the unchanged decision

The new experiment retains exactly **53 full-resolution frames**: 37 from
4422.7–4423.9 and 16 from the positive control 866.4–866.9. Inference completed
in **48.08 seconds wall time**, including child startup/loading/provenance
checks, under a hard 180-second subprocess timeout. The recorded inference
loop plus final verification took 41.11 seconds. No other film inference ran.

On the disputed trajectory, the unchanged `shots.decide()` returns **no make**
with all retained source-rate observations. Fresh approximately 10 Hz phase 1
(every third decoded frame, offset one) instead returns **make**, with exit
4423.133322222222. Inserting just **one genuinely observed ball/rim pair** into
that accepting phase changes it to **no make**, solely because the first
under-net sample fails the unchanged horizontal exit gate:

- PTS **398075999**, time base **1/90000**, actual time
  **4423.066655555555**, MP4 video sample index **132692**.
- Ball center **1348.691528, 235.111954** pixels, ball score **.838924405**.
- Rim box **1295.181274,187.927353,1356.367798,214.030807**, score **.782177191**.
- Rim units **x=.374543133, y=1.807599859**: already below `UNDER_NET=1.6`,
  but outside `NET_EXIT_X=.35`.
- All other primary predicates pass in this single-observation insertion.
  The gap fallback fails its minimum gap. The loop does not retry the later,
  centered 4423.133322 sample. The disappearance fallback does not accept it.

This is a direct observed analogue of the prior audit's synthetic sampling
probe, **not the same synthetic point or a historical-cache insertion**.
The prior interpolation at nominal 4423.033333 was not an observation; the
new point above is independently detected on a PTS-certified source frame.
No interpolation is included in any fresh path.

## Actual trajectory evidence

`x` is ball-center offset from rim-box center in rim widths; `y` is distance
below rim-box top in rim-box heights. These are image projections, not depth,
net-aperture coordinates, physical contact measurements, or ground truth.

| Decoder PTS / 90000 | Actual seconds | Ball center px | x | y |
|---|---:|---|---:|---:|
| 398066999 | 4422.966655556 | 1362.058,180.125 | .618401 | -.195778 |
| 398070000 | 4423.000000000 | 1355.703,199.069 | .717218 | .483388 |
| 398072999 | 4423.033322222 | 1352.575,217.460 | .443733 | 1.118118 |
| 398075999 | 4423.066655556 | 1348.692,235.112 | .374543 | 1.807600 |
| 398079000 | 4423.100000000 | 1344.024,257.546 | .308098 | 2.498158 |
| 398081999 | 4423.133322222 | 1336.536,278.599 | .192095 | 3.077043 |
| 398088000 | 4423.200000000 | 1328.224,320.669 | .112750 | 4.825202 |

| Fresh path selection | Disputed outcome | First under-net time | Reason |
|---|---|---:|---|
| All source frames | no make | 4423.066655556 | centering and intermediate-inside fail |
| Every third source frame, phase 0 | no make | 4423.100000000 | intermediate-inside fails |
| Every third source frame, phase 1 | make | 4423.133322222 | all primary gates pass |
| Every third source frame, phase 2 | no make | 4423.066655556 | centering fails |
| Phase 1 + one observed frame | no make | 4423.066655556 | only centering fails |

The dense path has an additional localization-sensitive failure: at exact
4423.0, the retained rim box is narrower (49.43 px, score .503188) than adjacent
rim boxes (~59–64 px). The ball's normalized x becomes .717218, outside
`SIDE_X=.6`. This explains phase 0's rejection; it is **not** needed for the
single-observed-frame flip. It would be incorrect to attribute every rejection
in the table solely to the first-under-net centering gate.

There are 26 selected observed ball/rim pairs in the disputed path and 13 in
the control. The disputed ball is not retained at 4422.7, 4423.3–4423.566655556,
or 4423.9; the rim remains retained in all 37 frames. Missing detector outputs
are not proof that the ball was absent or occluded. The decisive descent
4422.733322222–4423.266655556 is continuously observed at source rate.

## Native-image inspection: provisional geometry only

Inspected native-resolution, unresized crops in disputed `sheet_008.png`,
`sheet_016.png`, `sheet_024.png`, and both positive-control sheets. Individual
420×520 crops preserve original pixel scale, with a separate 48-pixel banner
showing exact integer PTS, time base and source sample index. Green boxes pass
class cutoffs; orange boxes are retained postprocess rows below those cutoffs.
Unannotated full 1920×1080 PNGs are preserved separately for inference/audit.

- **Disputed:** the ball approaches the projected right edge of the rim,
  then descends beside the right-hand net silhouette before moving inward in
  projection. This is consistent with the provisional net-side/rejection
  interpretation, but aperture traversal/front-back depth and exact rim
  contact remain **unresolved**, not independently adjudicated. The crops show
  players/hands around the later ball region; the exact first player touch
  during the detector gap is **unknown**. The reappearing ball rises after
  4423.6; that is outside the first-exit .4-second pop guard, not an observed
  immediate return above the rim.
- **Positive control:** the ball/net appearance at 866.6–866.9 is consistent
  with net-through, rather than the disputed right-side passage. This is a
  provisional visual reading only. Dense `decide()` accepts at 866.7,
  x=.273001, y=1.608078, and phase 0 also accepts. Phases 1 and 2 reject because
  the bounded decimated paths omit the sole retained `y<.3` observation at
  866.4; this is a missing-initial-context failure, not demonstrated misses.
  Phase 2's first under-net point additionally lies at x=.374387. The control
  ends only .2 seconds after its dense exit, so the .3/.4-second drift/pop
  guards do **not** have their complete prospective observation windows.

The negative experiment has enough retained-frame duration after its first
exit to cover both guards, but missing ball outputs still mean those guards
cannot certify physical absence of an intervening pop or touch. Neither case
establishes physical outcome accuracy from 2-D boxes alone.

## Provenance, actual PTS, and non-equivalence

Source film was discovered from frozen blind-review `provenance.json`:
`backend/sample_data/Valley Christian vs Archbishop Riordan - Tactical.mp4`.
Its 3,777,488,836 bytes match SHA-256
`6cb6e0d81257fcdae38ef06d30802f163732b49c9571c309d8c50d967456700c`.
Before extraction/inference, all 21 audit input hashes and all records in the
local detector baseline manifest were verified, including checkpoint and
baseline-bound source/dependency/data records.

The historical cache identifies `aim-yolox-m-v4`, 10 Hz and 1920×1080, but
does **not** pin checkpoint bytes, actual generation configuration, source
frame indices, or decoder PTS. Thus this is explicitly a **fresh experiment
non-equivalent to historical inference**. No claim of identical historical
weights, pixel-aligned cached detections, or a measured historical-versus-fresh
localization difference is made. **Zero historical frames are asserted to be
truly aligned**, and no detection comparison on merely equal nominal times
was performed. The old cache's made call is a separate previously established
reference, not an aligned paired experiment.

The allowed fallback uses the frozen local baseline's pinned checkpoint:
`ml/runs/v4/aim_yolox_m.pth`, SHA-256
`d009e6911b10ba08a027d870f7fee01d1deddbd4d8290b01a7f0ab85ce795660`.
Settings are YOLOX-M, four classes, 960 input, CPU float32, four Torch threads,
one interop/OpenCV thread, seed zero, `ValTransform(legacy=False)` on BGR uint8,
top-left 114 padding, native boxes restored by inverse resize ratio, no
clipping. Loading is strictly `torch.load(map_location='cpu', weights_only=True)`
with no unsafe fallback. Score is objectness times class confidence;
postprocess floor .1; class-aware NMS .45; cutoffs ball .20, player .10,
referee .35, rim .50, unchanged. Existing Torch/torchvision/numpy/yolox/OpenCV
versions match the frozen baseline. No download/install/network/paid call ran.

Frozen experiment manifest SHA-256:
`1122e214cecc36ece5d9d492ba10c79cf640dde2d73d0beb5292890973e51ee4`.
It was created read-only **before any model inference**, pinning source,
checkpoint, tool/source/dependency records, sample PNG hashes and settings.
`protocol` copies the baseline protocol verbatim: its historical population,
image order, 44-image limit and 540-second budget are **reference fields, not
this run's execution bounds**. Actual run bounds are the manifest's top-level
`budget_seconds=180`, `frame_cap=70`, exact 53-element `samples`, hashed tool,
and `budget.json`. No annotation matching/evaluation was run on these frames.
Provenance and manifest bytes were reverified after inference.

Alignment does not assume ideal 30 fps. FFprobe demuxed video packet metadata
without full-film decoding or inference (178,680 packets, equal to declared
frame count, monotonic PTS=DTS and no B frames). Bounded decoder records were
matched by actual packet position and PTS; FFmpeg `showinfo` emitted identical
PTS for each retained PNG. MP4 video sample indices are zero-based packet
ordinals, **not fabricated global decoder frame indices**. Local probe and
selected decoder indices are also retained; a global decoder ordinal is not
asserted. The final selector uses **integer PTS**, not floating time endpoints.

- Disputed retained PTS 398043000–398151000, source sample indices
  132681–132717, 37 frames inclusive.
- Control retained PTS 77976000–78021000, source sample indices
  25992–26007, 16 frames inclusive.
- Real intermediate times include 4423.0333222222225, **not** nominal
  4423.033333333333. Every record retains integer PTS and rational time base.
- Two pre-manifest extraction preparations failed closed (copyts/output
  duration semantics and floating endpoint selection). No inference ran on
  those attempts. Uncertified temporary PNGs were discarded; the first decode
  log and failure explanation are retained in `failed_preparation/decode.log`.
  The timed-out command could decode unretained post-window frames before
  timeout; no outside-window image was selected for extraction or inference.
  The corrected final command bounds input duration and exact output count.
  The final set is 53 unique retained frames; no outside-window images remain.

## Raw output scope and bounded decision scope

`detections.jsonl` retains **96 ball/rim postprocess rows** (63 disputed, 33
control), including objectness, class confidence, product score, unrounded
native xyxy boxes, and an explicit `passes_class_cutoff`. Three control rows
are below class cutoffs: ball .145928 at 866.466655556, ball .107534 at
866.533322222, and rim .106877 at 866.7. These rows remain in the raw artifact
but are excluded from path building. There are no below-cutoff disputed rows.
These are all **retained after floor .1 and NMS**, not logits, pre-NMS output,
or all below-floor detections. Other classes were inferred normally, not
retained as part of the ball/rim diagnostic.

Path building uses unchanged `best_ball()` and its confidence/recent-neighbor
logic, pairs observed rims in an explicitly bounded audit-derived ROI, and
applies the existing near-rim path retention geometry. Phase comparisons
decimate those same selected observations by **decoder frame index**, not by
position in the possibly missing-detection path. There is no held/interpolated
rim or interpolated ball. Each path is passed to unchanged `decide()` with the
actual last decoded PTS as `observed_until`.

This does **not** reconstruct initial open-shot, rescue/still-ball state,
whole-game ceiling/game-rim selection, attempt timing, dead-ball veto, assist
dependencies, or full `find_shots()` results. The control was already underway
at the start of its allowed window. The fresh dense rejection cannot be
promoted into a production correction of the historical event or downstream
assist. The defensible finding is narrower: **observed source-rate geometry
demonstrates a sample-phase-dependent unchanged outcome rule**, and late
projected centering remains non-identifying. No thresholds, timestamps,
production behavior, labels, training or deployment were changed.

## Artifacts and checks

All experimental outputs are private under
`ml/data/labels/rim_source_rate_20261112/`:

- `manifest.json`, `budget.json`, `inference.json`, `inference.log`.
- Full-frame PNGs, exact decoder logs, native overlays and contact sheets in
  `disputed/` and `positive/`.
- `detections.jsonl`: every retained raw ball/rim row and filter flag.
- `analysis.json`: selected observed paths, rim units, unchanged predicates,
  dense decisions and all three fresh decimation phases.
- `observed_insertion.json`: before/after paths, exact inserted observation,
  and manifest/analysis/detection/production-source hashes.

Tool commands (the experiment intentionally refuses an existing frozen run):

```sh
ml/.venv/bin/python ml/tools/rim_source_rate_eval.py run
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_rim_source_rate_eval.py -v
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_rim_outcome_audit.py -v
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_makes.py -v
```

Focused tests cover packet/decoder alignment, non-nominal timestamps, exact
endpoints, duplicate/mismatched PTS rejection, unchanged config/cutoffs/NMS,
no interpolation, observed centering-only decision flip, provenance tampering,
and refusal to overwrite/escape/symlink private artifacts. Existing edits and
all frozen/baseline-bound files remain untouched. No commit was created.
Validation: **11 focused tests, 8 existing audit tests and 26 make tests pass**.
