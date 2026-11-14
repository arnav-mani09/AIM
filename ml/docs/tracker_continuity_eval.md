# ByteTrack continuity bottleneck — November 13, 2026

## Decision

**No safe production configuration fix established.** The current buffer is
shorter than three seconds, but lengthening it is not an identity fix. The actual
pinned tracker preserves one constructed long-occlusion identity better while
also retaining stale identities long enough to assign them to different people.
The four incomplete cache replays show mixed coverage/fragmentation diagnostics,
not a consistent improvement. No worker, baseline-bound source, frozen artifact,
production setting, identity alias, or assist label was changed.

The concrete shared-vision bottleneck is geometry-only association across gaps,
overlaps, and camera movement, before downstream track-wide team/holder evidence
is consumed. This experiment demonstrates mechanisms and tradeoffs, **not the
root cause of any particular real cross-player contamination**. The buffer and
threshold mismatches alone do not establish that root cause.

## Primary evidence and exact semantics

- `worker/film_worker.py:163` pins `supervision==0.26.1`; its call at line 215
  leaves the vision defaults unchanged. This is source evidence of the deployed
  dependency pin, not a fresh inspection of a remote deployment.
- `worker/vision.py:104` defaults to 10fps and `new_track_score=0.5`; line 115
  constructs `ByteTrack(track_activation_threshold=0.5, frame_rate=10,
  lost_track_buffer=30)`. Matching/consecutive-frame defaults are 0.8/1.
- Installed `ml/.venv/lib/python3.10/site-packages/supervision/tracker/byte_tracker/core.py:50`
  sets `det_thresh=activation+0.1`; line 51 sets
  `max_time_lost=int(frame_rate/30.0*lost_track_buffer)`. Thus current runtime
  retention is **10 frames, nominally one second**. Buffer 90 yields 30 frames,
  nominally three seconds, without changing activation or matching thresholds.
  Expiry uses a strict `>` comparison at line 294 **after association**; the
  nominal number is not an exact last-reappearance guarantee.
- Lines 170–174 split detections using **high >0.5** and **0.1 < low <0.5**.
  Exactly 0.1 and exactly 0.5 enter neither association set. New-track creation
  at line 288 rejects scores below 0.6. The worker comment that a new track needs
  `new_track_score` is therefore misleading at the current defaults.
- High-score association uses Kalman-predicted geometry, score-fused IoU and
  Hungarian matching (`core.py:212`, `matching.py`). Low scores can update only
  still-tracked, not already-lost, tracks (`core.py:244`). Jersey/team metadata
  is not an input to these associations; both teams have player class 1.
  `update_with_detections` additionally rematches returned tracks to input boxes
  with IoU cost threshold 0.5. The experiment uses this full public method, not
  a simplified/fake tracker or just its tensor internals.

Installed versions: supervision **0.26.1**, NumPy **2.2.6**, SciPy **1.15.3**.
Installed core SHA-256:
`865aa9233c62230ba099c062c01e5fa549b1376539d6d0880c13a7736a8032be`.
No network lookup, dependency installation, or remote execution was used.

## Bounded synthetic experiment

`ml/tools/tracker_continuity_eval.py` uses deterministic supplied boxes and known
synthetic identities, with float64 confidence values. Both configurations have
activation 0.5, matching 0.8, 10fps, and one minimum consecutive frame. **Only
`lost_track_buffer` changes, 30 → 90.** Team tags exist solely as synthetic
scenario annotations and are not passed to the tracker.

Rows below show **current / buffer-90** results. A fragment is an extra distinct
replay ID for one known person; a contaminated ID has emitted boxes belonging to
more than one known person. These are synthetic-only identity metrics.

| Scenario | Output / supplied boxes | Fragments | Contaminated IDs |
| --- | --- | --- | --- |
| Moving person, 5 missing frames | 55/55 / 55/55 | 0 / 0 | 0 / 0 |
| Moving person, 18 missing frames | 41/42 / 42/42 | 1 / 0 | 0 / 0 |
| Moving person, 35 missing frames | 24/25 / 24/25 | 1 / 1 | 0 / 0 |
| Opposing-team crossing, four-frame overlap occlusion | 96/96 / 96/96 | 0 / 0 | 0 / 0 |
| Same-team crossing, identical geometry | 96/96 / 96/96 | 0 / 0 | 0 / 0 |
| Smooth camera translation, 3px/frame | 90/90 / 90/90 | 0 / 0 | 0 / 0 |
| Abrupt camera translation, 120px | 88/90 / 88/90 | 2 / 2 | 0 / 0 |
| Different opposing-team person replaces stale box after 18 missing frames | 26/27 / 27/27 | 0 / 0 | 0 / 1 |
| Different same-team person replaces stale box, identical geometry | 26/27 / 27/27 | 0 / 0 | 0 / 1 |

The replacement counterexamples deliberately construct an ambiguous reappearance
at the stale location. They establish a possible regression, not its frequency
in basketball. Higher output coverage here accompanies **worse** identity
continuity. Successful simple crossings do not establish robust crossing
performance. Abrupt camera movement still fragments both configurations.

### Separate threshold probe — no threshold changes

Fresh-start probes use four equal-score frames. Ongoing probes use four 0.9
frames before three probe frames. Lost-track probes use a 0.9 frame, an empty
frame, then the score under test, always at the same position. Results agree
between buffer settings; association geometry is deliberately unambiguous.

| Score | Starts a fresh track | Continues ongoing track | Recovers already-lost track |
| --- | --- | --- | --- |
| 0.1 | No | No | No |
| 0.100001, 0.499999 | No | Yes | No |
| 0.5 | No | No | No |
| 0.500001, 0.599999 | No | Yes | Yes |
| 0.6, 0.600001 | Yes | Yes | Yes |

This exposes the boundary behavior without lowering activation to 0.4, changing
matching, or claiming a threshold fix. Cache scores are rounded to three decimals:
a cached 0.500 need not have been exactly 0.5 at original tracker input. The
synthetic boundary result must not be used to diagnose individual cached losses.

## Four existing cached detection windows

Each replay starts a new tracker five seconds before the named shot, runs
through three seconds after it, and processes **81 contiguous 10fps frames**.
All available player boxes in each window are supplied; no focal-ID filtering,
invented detections, team filtering, film decoding, or new inference occurs.
Cold-start history is not production history. Shot times locate requested
windows only, not verified makes or assist opportunities.

**Crucial incompleteness:** `worker/vision.py:143` serializes player boxes from
the tracker output, not all detector proposals. Suppressed/unmatched/weak boxes
that failed to emit are missing and cannot be recovered. Boxes and scores are
rounded. Replaying these outputs through another tracker cannot reproduce
production or isolate a real identity-switch count. Original cached IDs are
diagnostic keys only; they may already span different people.

Rows show **current / buffer-90**. “Extra IDs” sums extra distinct replay IDs per
cached key, not per real person. “Multi-key IDs” counts replay IDs spanning more
than one cached key; this is ambiguity, **never an accepted alias**.

| Window (seconds) | Supplied boxes | Emitted boxes | Replay IDs | Extra IDs | Multi-key IDs | Input IoU≥0.3 pair-frames |
| --- | --- | --- | --- | --- | --- | --- |
| Mitty 248.1–256.1, center 253.1 | 734 | 726 / 726 | 13 / 13 | 6 / 6 | 6 / 6 | 37 |
| Mitty 1145.7–1153.7, center 1150.7 | 692 | 657 / 653 | 29 / 28 | 13 / 23 | 8 / 14 | 18 |
| Riordan 3608.3–3616.3, center 3613.3 | 764 | 731 / 728 | 29 / 28 | 17 / 16 | 12 / 12 | 20 |
| Riordan 5491.8–5499.8, center 5496.8 | 730 | 707 / 709 | 23 / 22 | 8 / 9 | 6 / 8 | 21 |

IoU pair-frames count overlapping supplied-box pairs across frames, not distinct
people or proven matching errors. The longer buffer can reduce total replay IDs
while increasing per-key splitting and multi-key ambiguity. Neither lower ID
count nor higher coverage establishes better identity continuity.

Focal diagnostics for cached keys 964/961, 3767/3805, 11127/11120, and 17531/17522
are included in `summary.json` alongside complete replay assignments. In the
Mitty 1150.7 window, cached key 3767 has one replay ID under current settings and
two with the longer buffer; emitted box count remains 41. This is diagnostic
instability, not a real-person ID-switch measurement.

`assist_identity.py` and `assist_accuracy.md` were read. Their existing evidence
explicitly refuses global same-person aliases, including co-visible distinct
players and later cross-player contamination. This run does not reinterpret
jersey votes, proximity, or absence of separated co-visibility as identity truth.
The four frozen contact sheets were fingerprinted but **not freshly visually
inspected**; existing prose observations are not new pixel adjudications.

## Frozen evidence, preservation, and validation

Private artifacts: `ml/data/labels/tracker_continuity_20261113/` (git-ignored).

- `source_inventory_before.json` was captured before creating the new evaluator
  and tests: **286 existing tracked/untracked nonignored files plus the included
  frozen assist-identity files in total**. `source_inventory_after.json` matches
  every existing-file hash; no deletion or alteration was detected.
- `package_inventory_before.json` / `package_inventory_after.json` match **213
  installed source/metadata/native-library files**: all supervision Python
  sources, package metadata, and NumPy/SciPy native libraries. Package versions
  are recorded. These are local package hashes, not a remote deployment audit.
- `summary.json` records before/after hashes for both complete cache files,
  worker sources, identity adapter/docs, new evaluator/tests, and four existing
  contact sheets. `config.json` freezes constructor and derived runtime values.
- `synthetic_inputs.json`, synthetic assignment files, four extracted
  `*_inputs.json` files with timestamps and SHA-256s, and eight cached output
  files preserve actual supplied trajectories and public-method assignments.
  Threshold inputs are deterministically defined by `SCORES` and
  `threshold_probe()` in the hashed evaluator; results are in `summary.json`.
- Mitty cache SHA-256:
  `0994d981e6b5247ed58ca0a091ec1dafdd02d356071938e4526f3de34d19926a`.
  Riordan cache SHA-256:
  `cd2f1a8226ae71f7c72329433a1e19937717ff660b23b985a45e829e21504a7c`.
- Actual experiment: **3.288 CPU seconds / 3.440 wall seconds**, excluding
  source/package hashing. Cached windows each took **0.167–0.182 wall seconds**
  for both configurations together, far below 20 seconds each. A 120-second CPU
  timer and per-window 20-second wall deadlines bound execution.
- **8 actual-tracker tests pass**, including occlusion benefit, stale-replacement
  regressions, boundary semantics, team-tag independence, deterministic crossings
  and camera translations, co-visible ID uniqueness, and absence of real-person
  metrics on cached data. Import failure or a version other than 0.26.1 explicitly
  skips instead of substituting a fake tracker. See private `tests.txt`.

Validation command (no installation required):

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  ml/.venv/bin/python -m unittest discover -s ml/tools \
  -p test_tracker_continuity_eval.py -v
```

The completed single-run experiment was executed with the same thread limits
using `ml/.venv/bin/python ml/tools/tracker_continuity_eval.py`. It deliberately
refuses to overwrite the frozen `summary.json` or other artifact files. Its
precondition is the pre-edit source inventory already preserved in this folder;
it is an evidence-producing bounded experiment, not a generic replay framework.

**Disposition:** retain current production settings. Correct semantics are now
documented here, without editing the frozen worker/comment. No raw-proposal
production-parity evidence exists in these caches to justify either a buffer or
activation change as a safe fix. No labeling backlog, accuracy/generalization
claim, training, paid call, commit, deployment, or delegate was introduced.
