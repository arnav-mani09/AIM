# Exact association-stage witnesses — November 13, 2026

## Result and scope

The disputed Riordan loss is **predicted-geometry/high-stage rejection followed
by new-track confirmation delay**. The Mitty region migration is **high-stage
competition between two eligible boxes**, followed by an unconfirmed track taking
the other region. Neither disputed event originates in the public output rematch.
No generic coding defect is established by these cases; no production fix,
threshold/buffer sweep, ID alias, or appearance gate is proposed.

This experiment uses only the NEW raw capture, not historical tracked caches:
244 frames, 2,960 player/referee proposals, 2,430 actual player inputs. Both a
fresh **uninstrumented** replay and an **instrumented** replay independently match
all 244 original fresh outputs and the previously saved replay, including array
values, shapes, dtypes, classes, scores, IDs, and output order. There are 2,212
emissions. These counts describe supplied proposals and replay outputs, never
real-person accuracy, IDF1/HOTA, adjudicated switches, or safe downstream aliases.

Private evidence: `ml/data/labels/tracking_association_trace_20261113/`.
The prior raw capture and continuity experiments are read-only inputs. All four
existing native-pixel review sheets were inspected; their pN annotations are
frame-local proposal-list positions, not persistent identities. Visual descriptions
below concern jersey/body regions, not proof that an ID belongs to a person.

## Installed primary source and instrumentation

The authority is the installed **supervision 0.26.1** source, not an upstream
description of another ByteTrack implementation. `installed_primary_source.json`
preserves the relevant function text, installed path, start line, and file hash:

- `supervision/tracker/byte_tracker/core.py`: public update line 65, tensor update
  line 151, duplicate removal line 362; SHA-256
  `865aa9233c62230ba099c062c01e5fa549b1376539d6d0880c13a7736a8032be`.
- `matching.py`: assignment line 26, score fusion line 61; SHA-256
  `7e81a4eba09c870f6a653de50e618266bcf12cecc5f812ba77b9d707c260e973`.
- `single_object_track.py`: activate line 76, update line 105; SHA-256
  `6f327af8753790d3ead115f69b2a5e1eb9e96589c5146437ef0b6ae98eb91d03`.

Only in-process wrappers are installed, with `ExitStack` restoration on success
or exception; installed files and production code are never edited. The wrappers
call the original prediction, IoU, fusion, and assignment functions exactly once.
Stage identity uses the actual caller code object plus the validated three-stage
order, not a threshold heuristic: low association and public rematch both use .5.
Duplicate-removal IoU is recorded separately, not mislabeled as another Hungarian
stage. Original `staticmethod` prediction descriptors are restored too.

For every frame, `traces.json` preserves:

- Before/after track state and predicted before/after boxes, internal/external
  IDs, score, activation, frame/start indices and tracklet length.
- High, low and unconfirmed row/column identities and boxes; exact float32
  round-trip source-proposal references, including all equal candidates rather
  than silently choosing one. These are input provenance links, not people.
- Original IoU costs, score-fused costs, assignment input **copied before the
  original mutates it**, post-call clamped matrix, shape/dtype, threshold, winners,
  unmatched rows and unmatched columns.
- Public rematch input detections versus eligible post-update tracks, costs and
  winners/losers, plus duplicate-removal inputs/costs and final state.

The actual assignment replaces entries above its threshold by `threshold+0.0001`,
then calls SciPy Hungarian assignment and rejects selected above-threshold edges.
Thus recording the matrix after calling it would destroy precisely the rejected
cost witnesses below. For high and unconfirmed stages, cost is
`1 - IoU(predicted_track_box, proposal_box) * proposal_score`. Low stage uses
`1 - IoU`. The public stage matches original detections to updated/smoothed boxes
using `1 - IoU`, threshold .5. Current constructor remains activation .5, 10 fps,
buffer 30, matching .8, minimum-consecutive 1; derived birth score is .6 and
`max_time_lost` is 10. New tracks born after frame 1 are initially unactivated,
even though an external ID is already allocated with minimum-consecutive 1.

## Riordan samples 151 / 152 / 153

PTS are respectively 325188000 / 325197000 / 325206000, seconds
3613.2 / 3613.3 / 3613.4. The reviewed white-jersey #4 region has frame-local p2
in each of these frames. All three proposals are present and are supplied to
the tracker; this is not detector absence or a proposal/class cutoff rejection.

| Sample | Stage and edge | IoU | Unmodified input cost | Gate | Result |
| --- | --- | --- | --- | --- | --- |
| 151 | high: ID 5 → p2 | .2505988390644258 | .7615430015783252 | .8 | accepted |
| 152 | high: ID 5 → p2 | .1970798780153954 | .8118542438594284 | .8 | rejected |
| 153 | high: Lost ID 5 → p2 | 0 | 1 | .8 | rejected |
| 153 | unconfirmed: ID 32 → p2 | .4836236238479614 | .5449025960442171 | .7 | accepted |

At 152, p2's score is **.9546675086021423**, and its unchanged native box is
`[1392.0126953125, 360.01068115234375, 1512.282470703125, 562.1759643554688]`.
ID 5's actual Kalman prediction is
`[1475.8466225049167, 369.32156625945754, 1569.2464175584896, 565.9717621457544]`.
The narrow, right-lagging predicted box yields only .1970798780 IoU. Even
unfused geometric cost is **.8029201219846046 > .8**; fusion increases it to
.8118542438594284. At this score the required IoU is .20949702194520795.
This distinguishes a geometry failure from a high-confidence detector failure;
confidence alone cannot rescue insufficient overlap.

Every high-stage edge into p2 is above .8. ID 5 has no other overlapping high
proposal. There is **no feasible competing winner stealing p2**. The original
assignment clamps ID 5's cost to .8001; the trace retains the pre-clamp number.
The low stage is shape `[4,0]`, so it cannot rescue ID 5: this high-score proposal
is not reconsidered as a low-score detection. ID 5 becomes Lost immediately.
The only unconfirmed row (ID 31) has cost 1 to p2 and instead matches p7 at
.4190421784128091. Unmatched p2 exceeds the .6 birth threshold and creates
**ID 32, Tracked but unactivated**.

ID 32 is therefore absent from sample 152's public rematch columns. ID 5 is also
absent because it is Lost. P2's best cost to any eligible public column is
.9095218704644485, above .5. This rematch faithfully cannot emit p2; it did not
cause ID 5's loss. At 153, ID 32 matches p2 in the unconfirmed stage, becomes
activated, and public p2 → ID 32 cost is .13206823632606268. For comparison,
151's public p2 → ID 5 cost was .3229646056306049.

The saved Lab medians `[168,124,140]`, `[167,124,141]`, `[170,124,143]` are
consistent local appearance evidence, not sufficient proof of person continuity
or permission for an ID-5/32 alias. The loss happens before any lost-buffer
expiration: increasing the buffer does not change this frame's rejected edge.

## Mitty samples 90 / 91 / 92

PTS 103554000 / 103563000 / 103572000, seconds 1150.6 / 1150.7 / 1150.8.

At 90, white-region p2, score .9289151430130005, has no high/unconfirmed winner
and births unactivated ID 38. At 91 the unconfirmed stage selects white-region
p7 for ID 38: IoU .46150726079940796, fused cost .6360092855535271 ≤ .7.
Overlapping blue-region p8, score .7400349378585815, has ID-38 IoU
.1170755997300148 and cost .9133599658290423, so is ineligible. P8 births
**unactivated ID 40**. The public p7 → ID 38 cost is .1505969039415026;
p8's best eligible public cost is .7472467936976634 and it does not emit.

At 92, ID 38's prediction is
`[1353.808284519461, 286.29876708984375, 1444.8319986836639, 457.591943359375]`,
exactly its previous filtered box. Its two eligible competing high-stage edges:

| Proposal region | Score | ID-38 IoU | Fused cost | Result |
| --- | --- | --- | --- | --- |
| p4, white | .9001291990280151 | .2749021930337173 | .7525525091735152 | loses |
| p7, different blue region | .8308497667312622 | .29838423119191015 | .7520875311179145 | wins |

Both costs pass .8, but blue p7 is cheaper by **.000464978055600751**.
No other high-stage row has an eligible edge to either of these two columns.
This isolates the actual geometry × score competition, rather than calling
it random matching, missing detection, public rematch, or color-based behavior.
The blue proposal's slightly larger IoU outweighs its lower score. The Hungarian
winner for ID 38 is already p7 **before** public rematching.

The subsequent unconfirmed stage assigns ID 40 to the remaining white p4:
IoU .6072771549224854, fused cost .4533721009516114 ≤ .7. Blue p6, score
.8634997606277466, has ID-40 IoU .2641514539718628 and cost
.7719052827258253 > .7; it remains unmatched and births unactivated ID 43.
The public stage emits p4 → ID 40 at cost .10701743676348052 and p7 → ID 38
at .3208112163241994. P6's best public cost is .7347868078138698, so it does
not emit. These are region assignments, not accepted human-identity exchanges.

ID 38's emitted p7 Lab medians at 91 and 92 are `[90,128,125]` and
`[88,130,126]`: Euclidean distance **3 in OpenCV uint8 Lab coordinates**, not
calibrated perceptual delta-E. Native crops show different jersey regions despite
these near-identical aggregate values. Median-Lab-only gating would not resolve
this case reliably; overlap, shadow and mixed pixels confound it.

## Controls and all-frame output invariants

Mitty 29/30/31 has real blue/white overlap but **9 supplied player boxes and 9
emissions in each frame**. All public winning costs are below .5 (largest per
frame .3992572243425966, .4107237062290735, .38476030491091306). The control
IDs are the same set `{1,2,3,4,5,6,7,8,9}`; proposal-list positions change.
This is a local nonfailure control, not proof of person identity or universal
overlap robustness. Exact per-frame winners are in `witnesses.json`.

Riordan 212 has only referee p10 in the reviewed official-shaped region; that
class never enters tracking. At 213, referee p10 score .7215192317962646 and
player p11 score .29927223920822144 have native box IoU .9238504092475093.
Only p11 enters, in the low stage, where the sole eligible existing row is
ID 21 far away, IoU 0, cost 1 > .5. Low detections do not birth new tracks.
At 214, referee p9 score .7680095434188843 and player p10 score
.28102907538414 have IoU .9257682739821547. The low row is ID 19, cost 1 to
p10; the official-region player proposal again does not emit. Both public best
costs are 1. This is **upstream class ambiguity plus low-stage eligibility**,
not a missing player identity, referee track loss, or basis for merging IDs.

Across **976 actual assignment calls** (four per frame), assertions check exact
score-fusion algebra, original-dtype IoU reconstruction, correct input versus
post-clamp cost matrices, finite JSON values, accepted-edge thresholds,
one-to-one winners, unmatched-set complements, and exact public-output parity.
Matched public costs range from -4.386423979596543e-08 to .48731382259778555;
tiny negative costs are retained floating-point IoU artifacts, not clipped by
the experiment. Reconstructing float32 birth boxes as float64 incorrectly
changes these costs, so each snapshot explicitly preserves box dtype.

There are **2,174 internally matched proposal occurrences also publicly emitted**;
all retain their internal winner ID in public output. This does **not** mean
public rematching is always harmless: seven other internal winners are suppressed
by its .5 gate at samples 13, 138, 139, 140, 141, 222, 223. Their best costs are
.5718826774601121, .5916554817751591, .5030175922714155,
.5567782563753911, .5134554388024632, .5192480837788451,
.5331643245178443 respectively. These are outside the disputed triplets.
One further internally matched occurrence (216, p4 → ID 19) is removed before
public output by duplicate pruning: its updated box has IoU cost
.1399117975141827 < .15 to Lost ID 9; ID 19's age is 15 frames versus ID 9's
32, and the shorter track is dropped. No invented appearance identity follows.
The remaining 38 emissions were not stage matches, consistent with activated
births on each window's first frame. Full matrices preserve all these distinctions.

## Disposition and evidence needed

The disputed behavior follows the actual configured algorithm. There is no
established generic coding bug warranting a production patch; the owned
experiment intentionally contains **no replacement matcher or proposed fix**.
The seven separate public-gate suppressions and duration-based duplicate pruning
are explicit pipeline tradeoffs here, not evidence that a nearest-ID alias is safe.

Before testing any identity-sensitive association change, obtain:

- For Riordan: independently adjudicated consecutive native-frame person links,
  visible jersey-number/body-part evidence on both sides of the gap, and
  multi-frame motion/camera-motion evidence explaining the lagging narrow
  prediction. A temporally anchored, uncertainty-aware continuation must be
  distinguished from a different person reappearing near a stale track.
- For Mitty: separated pre/post-occlusion reference crops for each overlapping
  person; visibility/occluder masks or body-part-local descriptors that exclude
  foreground contamination; and multi-frame trajectory/jersey evidence through
  the crossing. The two medians cannot supply this missing discriminative signal.
- For referee ambiguity: independently reviewed person class/visible uniform
  evidence over adjacent frames, rather than treating low-score player duplicates
  on an official as missing player detections or injecting referees into tracking.
- Validate any later design on the overlap controls and independently labeled
  longer clips, including stale replacements and co-visible distinct players.
  This experiment supplies causal repros, not a real-accuracy metric or approval.

## Preservation, budget and reproduction

Frozen input SHA-256s remain:

```text
manifest c2ec015bb7a4b0d2f35d74e4220a3e2ceb18da1664c75d81bd4c691fc8a44b02
inputs   ea068f63c4e459c8b0595ef594cc6dc6a9c5d5e636c13f15886f8ca835898cac
outputs  7ef55ab0496e29b5fcf5970f06b3a0f872dc6fbcae76c0ce499368244cf5be32
replay   810a78b1ca4d8cf33e47a9172ef5322f45ebd35933be2ac845f57055c8932800
```

The completed bounded run takes **17.786283 CPU seconds / 19.558722 wall
seconds**, including source/package hashing, full capture-manifest verification,
both replays, invariant checks and artifact writes. The runner has a 120-second
CPU timer, with one-thread numerical libraries. Before the completed run, a trace
development assertion caught float32-versus-float64 reconstruction; it was fixed
in the new tracer only. A subsequent startup stopped on concurrent shared-file
changes. Neither attempt performed inference or changed any frozen input.

The initial inventory has 558 shared/frozen files; five shared files changed and
one new document appeared before the completed run while other work continued.
`concurrent_changes_before_replay.json` records those exact paths/hashes; nothing
was overwritten or reverted by this experiment. The completed replay's before/
after inventories match for **559 files**, and **213 installed package/source/
metadata/native-library hashes** match. Manifest verification also succeeds before
and after replay. Package versions and exact dependency hashes are preserved.

`traces.json` covers all 244 frames; `focal_traces.json` contains the twelve
requested frames. `witnesses.json` gives the disputed numerical edges, controls,
and internal/public cross-check. `output_cost_invariants.json` distinguishes the
seven public-gate suppressions from duplicate pruning. `replayed_outputs.json`,
`summary.json`, installed primary source, inventories and `tests_final.txt`
complete the private evidence. Seven focused tests pass; the final recorded
suite takes 1.627 seconds (2.73 user+system CPU seconds including startup).

Focused tests (no inference, network, installs, training, production edits,
commits, deployment, sweeps, or subdelegation):

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  ml/.venv/bin/python -m unittest discover -s ml/tools \
  -p test_tracking_association_trace.py -v
```

The evidence-producing CLI `ml/tools/tracking_association_trace.py` refuses to
overwrite a completed trace. Do not rerun the capture/inference command.
