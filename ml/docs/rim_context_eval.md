# Full-context Riordan rim diagnostic

Executed November 12, 2026, America/Los_Angeles. Private development evidence,
**not human adjudication, outcome ground truth, or a production correction**.
No coach review queue or mandatory review backlog was created.

## Actual experiment and conclusion

Retained **113 unique full-resolution source frames**, only from the two
authorized windows: 43 at 866.0–867.4 and 70 at 4422.2–4424.5. Of these,
**53 exactly matching previous frame inferences were reused and 60 extensions
were newly inferred**. The inference child, including startup, model loading,
and provenance verification, completed in **75.7803 seconds**, under a hard
240-second subprocess timeout. CPU float32, four Torch threads, one interop
thread and one OpenCV thread; no other film inference ran.

**The disputed sample-phase result persists with shared observed initial
context and complete decoded prospective guard horizons.** Dense rejects;
phase 1 accepts; phases 0 and 2 reject. The positive control is more nuanced:
dense and phases 0 and 1 accept, but phase 2 rejects because its first
under-net observation is off-center, **not because initial context is missing**.
Consequently this experiment does not justify blanket denser resampling or
claim safety for every phase or outcome. In particular, the positive control
does not independently validate phase-2 accuracy.

Canonical evidence is `ml/data/labels/rim_context_20261112/analysis_context.json`.
All primary/gap predicate booleans, accepted branches, rejected causes, native
coordinates, scores, PTS, selected paths and per-path coverage are retained.

## What “context” means here

Frame identity is integer decoder PTS with rational time base 1/90000,
matched to ffprobe packet position and the zero-based MP4 video sample ordinal;
ffmpeg showinfo PTS must match the extracted PNG ordering exactly. Retained
endpoints are PTS 77940000–78066000 and 397998000–398205000. Frame selection is
not `time * fps` or float-time matching. No ball/rim interpolation or held rim
is used.

Each trajectory starts at its **first genuinely observed `shots.in_zone()`
above-rim entry**, not the beginning of the video window. Earlier decoded
frames remain available for detector/ball-selection context. Feeding the
whole window into `decide()` without opening an attempt would mistake the
control's rising, initially below-net ball at 866.033322 for an exit. Main-pass
attempt opening already requires zone entry; this is diagnostic path scoping,
not a new runtime rule, threshold adjustment, or timestamp exception.

For common-context phases, all decoded frames through the first dense
qualifying above-rim point are shared: **866.4** for the control and
**4422.766655555555** for the disputed case. Subsequent decoded indices are
retained modulo three, for phases 0, 1, 2. Ball selection is rerun independently
on each selected record sequence, using unchanged `best_ball()`; phases do not
merely inherit the dense track. The control has one qualifying initial
above-rim point in each common-context path, the disputed paths have three.
This shared prefix deliberately isolates descent sampling; it is **not** a
claim that an ordinary independently decimated stream observes that prefix.

Independent pure phases are also recorded. The disputed three pure phases
reproduce the same reject/accept/reject pattern with observed initial context.
Control pure phase 0 accepts; pure phases 1 and 2 have **no observed in-zone
initial context** and are marked `missing_initial_context`, with **no outcome
decision asserted**. Earlier projected above-rim points outside the attempt
zone do not establish an opened attempt.

This remains conditional `decide()` evidence using the previous audit's local
rim anchors and unchanged near-rim geometry. It does not recreate whole-game
ceiling/game-rim choice, rescue/still-ball history, attempt counts, dead-ball
veto, assist attribution, or full `find_shots()` parity.

## Decisions with common initial context

Times below are actual PTS-derived seconds. “Pass” means the unchanged primary
predicates pass on retained observations, not that physical outcome is known.

| Case/path | Made | First under-net | Exit x / y (rim units) | Primary result |
|---|---|---:|---:|---|
| Control dense | yes | 866.700000000 | .273001 / 1.608078 | all pass |
| Control phase 0 | yes | 866.700000000 | .273001 / 1.608078 | all pass |
| Control phase 1 | yes | 866.733322222 | .329974 / 1.822258 | all pass |
| Control phase 2 | no | 866.766655556 | .374387 / 2.149402 | centered exit fails |
| Disputed dense | no | 4423.066655556 | .374543 / 1.807600 | intermediate-inside and centered exit fail |
| Disputed phase 0 | no | 4423.100000000 | .308098 / 2.498158 | intermediate-inside fails |
| Disputed phase 1 | yes | 4423.133322222 | .192095 / 3.077043 | all pass |
| Disputed phase 2 | no | 4423.066655556 | .374543 / 1.807600 | centered exit fails |

All accepting rows use `primary_under_net`, not disappearance/gap fallback.
All eight rows fail the gap fallback's minimum gap-length predicate. Additional
gap failures are: previous-vertical for control dense and phase 2;
previous-horizontal for disputed phases 0 and 2. Neither fallback rescues any
rejected row. All other primary predicates, including observed no-pop/no-drift,
pass; these negative guards have incomplete detection coverage as detailed
below.

The earlier observed discriminating frame is still present unchanged: PTS
398075999, sample 132692, ball center (1348.691528, 235.111954), score .838924;
rim (1295.181274, 187.927353, 1356.367798, 214.030807), score .782177.
Its x=.374543 exceeds `NET_EXIT_X=.35`. Phase 1 misses it and first tests a
later, centered point. The separate localization-sensitive failure at exact
4423.0 remains: the rim width is 49.429932 pixels, score .503188, and x=.717218
fails `SIDE_X=.6`. Thus not every rejection has the same cause.

## Decoded horizon is not detection coverage

Every dense/common-context path's actual last decoded frame is later than
its first exit + .4 seconds, covering both .3-second drift and .4-second pop
horizons in time. Control phase endpoints are 867.4, 867.333322, 867.366656;
disputed endpoints are 4424.5, 4424.433322, 4424.466656. Dense endpoints are
867.4 and 4424.5.

The table counts selected-rate decoded frames strictly after exit through
exit+.4, not all dense frames for the decimated paths.

| Case/path | Required guard end | Guard frames | Missing ball / local rim | Missing selected pair |
|---|---:|---:|---:|---:|
| Control dense | 867.100000000 | 12 | 2 / 0 | 2 |
| Control phase 0 | 867.100000000 | 4 | 1 / 0 | 1 |
| Control phase 1 | 867.133322222 | 4 | 2 / 0 | 2 |
| Control phase 2 | 867.166655556 | 4 | 1 / 0 | 1 |
| Disputed dense | 4423.466655556 | 12 | 6 / 0 | 6 |
| Disputed phase 0 | 4423.500000000 | 4 | 3 / 0 | 3 |
| Disputed phase 1 | 4423.533322222 | 4 | 3 / 0 | 3 |
| Disputed phase 2 | 4423.466655556 | 4 | 2 / 0 | 2 |

None has complete detected-pair coverage of every guard frame. Exact missing
PTS are retained separately in `coverage`. Missing detections do not prove
absence, occlusion, lack of contact, or an unobserved pop. The source-rate
disputed descent itself remains continuously observed around the decisive
exit; its later guard gap must not be hidden behind “full context.”

## Native overlay inspection

Inspected native-scale 420×520 crops with separate PTS/sample banners in
control sheets 008, 016, 024, 032 and disputed sheets 016, 024, 032, 040, 048.
Native full 1920×1080 unannotated PNGs and every individual overlay are retained.
Green boxes pass original class cutoffs; orange boxes are retained postprocess
rows below those cutoffs. Sheets concatenate crops without resizing pixels.

- Control: the approach rises to the rim, the ball/net sequence is consistent
  with the previous provisional net-through interpretation, then the ball
  descends toward a blue player's hands. At about 866.9–867.1, hand/ball
  overlap and several weak/missing detector outputs make contact and guard
  continuity uncertain. The off-center phase-2 detection cannot be promoted
  to a physically adjudicated miss.
- Disputed: the descent runs along the projected right rim/net side. Around
  4423.3–4423.5667, visible ball/player-hand overlap coincides with missing
  retained ball detections; at 4423.6 onward the retained ball rises near
  players. That later rise is outside the first-exit .4-second guard. The
  view remains consistent with provisional rejection/net-side passage, but
  physical aperture traversal, depth, precise contact, and first player touch
  are unresolved. No human adjudication is claimed.

## Narrow automatic second-pass candidate, not a rollout recommendation

The pre-inference manifest preregistered a generic evidence trigger using only
runtime trajectory geometry and existing constants: **an accepted first
under-net exit whose immediately preceding observed point is outside
`NET_EXIT_X`**. It identifies an off-center-to-centered sampled transition
that can hide an earlier off-center under-net crossing. No time, game ID,
new tuned margin, physical-truth inference, or outcome override is involved.

It fires on the disputed accepting phase 1, not on any common-context control
phase, and not on the rejecting dense disputed path. An automatic bounded
second pass could seek actual intermediate source observations plus common
initial/guard context, then rerun unchanged decision logic. Missing evidence
must remain missing; it must not manufacture a correction or send a mandatory
review task to a coach. This candidate does not cover rejected coarse paths
such as the control's phase-2 centering failure.

Measured coverage on **all six already-frozen curated audit trajectories**
whose underlying current cache hashes were verified (not all game attempts):

| Existing cached trajectory | Cached made | Trigger |
|---|---|---|
| Riordan R4415-F3, provisional rejection | yes | yes |
| Riordan R850-F6, provisional make control | yes | no |
| Riordan R3605-F2, provisional make | yes | yes |
| Mitty M240-F3, provisional make | yes | no |
| Mitty M995-F3, provisional make | no | no |
| Mitty M1138-F3, provisional make | yes | no |

That is **2/6 audit trajectories**, or **2/5 cached accepting trajectories**;
it includes the disputed example and **one of five provisional positive
examples**. The additional positive trigger is workload/possible collateral
evidence demand, not a measured classification error. No fresh inference was
run on it. This selected six-case coverage is not a whole-game trigger rate,
recall/precision estimate, measured whole-game gain, or proof of safe second
pass behavior on that additional case. No runtime implementation was changed.

## Frozen provenance, reuse, and append-only analysis correction

The pre-inference manifest SHA-256 is
`e6f1e82486bea0982f3606f2142ad33d6fd355227ffcd4e9c5b63280a09ecd60`.
It was read-only before any extension inference and binds source/checkpoint,
full protocol, dependency versions, helper/runtime sources, audit cache hashes,
all PNG hashes, exact PTS/sample identities, extraction commands, and each
reuse row. Prior complete inference's manifest identity and raw detections
file hash were verified and frozen before reuse. All 53 overlapping PNG byte
hashes and lengths, source identity, PTS/sample/packet identity, checkpoint,
full protocol and versions match; no overlap was needlessly reinferred.

Pinned checkpoint SHA-256:
`d009e6911b10ba08a027d870f7fee01d1deddbd4d8290b01a7f0ab85ce795660`.
Settings remain YOLOX-M, four classes, 960, strict safe CPU checkpoint load,
seed zero, `ValTransform(legacy=False)` BGR uint8/top-left 114 pad,
inverse-ratio native coordinates, score product, floor .1, class-aware NMS
.45, cutoffs ball .20/rim .50. Torch/torchvision/numpy/yolox/OpenCV versions
are 2.14.1/0.29.1/2.2.6/0.3.0/5.0.0. Output retains ball/rim rows after
postprocessing, including below-class-cutoff rows, not logits/pre-NMS or
arbitrary below-floor observations. Other classes were inferred normally.

**Historical cache equivalence remains unprovable.** It does not bind original
checkpoint/configuration, source-frame identity or decoder PTS. Exact reuse
here is solely with the previous pinned fresh experiment, not the historical
10 Hz cache. Zero historical frames are claimed exactly aligned.

The first post-inference diagnostic, preserved as `analysis.json`, incorrectly
treated pre-attempt control ascent as an exit. **Do not use it as attempt
evidence.** No inference or frozen prior artifact was overwritten to correct
that analysis. Exact pre-inference versions of the two new source files were
preserved read-only in `frozen_inference_sources/`, with byte-identical hashes
checked against the original manifest. `source_snapshots.json` binds their
original paths/hashes to those preserved bytes. The corrected source and test
hashes were frozen in a separate `analysis_revision_manifest.json` **before**
the corrected analysis ran. Verification permits only these two owned source
revisions, requires exact original-manifest/snapshot hash equality, verifies
the revision's current source hashes, and still strictly checks all other
frozen inputs. No output-global monkeypatch or foreign artifact-directory
bypass is used. Existing overlays and original report/integrity records remain
unchanged; canonical results are append-only `analysis_context.json` and
`integrity_context.json`.

## Regression checks and reproduction

Seven focused tests pass, including actual artifact hashes/context/horizons,
missing-detection versus decoded-horizon distinction, common above-rim entry,
pre-attempt below-net exclusion, strict multi-field reuse, no-clobber/tamper
rejection, and the evidence-only trigger:

```sh
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_rim_context_eval.py -v
```

The completed private directory deliberately refuses repeat execution or
overwriting. `rim_context_eval.py run` is for a new, absent dedicated directory,
not an instruction to delete evidence and rerun this experiment. The separate
`analyze-revision` stage was executed once and also refuses existing outputs.
No network, install, paid call, full-film inference, training, commit,
deployment, production edit, new mandatory review workflow, or blanket
resampling recommendation occurred.
