# Blind film review: post-freeze dependency cross-check

Reviewed November 12, 2026. This cross-check occurred after the independent
model review froze its observations. It does not amend those labels, convert
them into human adjudication, or establish accuracy on complete games.

## Integrity

All 666 relative files bound by
`ml/data/labels/blind_film_review_20261112/freeze_manifest.json` were rehashed:
zero mismatches. The SHA-256 of `observations.frozen.json` is
`104745f1dd070bf705e63a628555f2353eed95f0d62a2b014d152fa9b90420cd`.
Original full-film hashes were not recomputed in this cross-check.

## Riordan: one dependency failure across stats

- Blind observation `R4415-F3` describes rim contact followed by visible
  rejection outside the net at 4422.7–4423.4 seconds. Evidence is the source-rate
  sheet `burst_riordan_4422.7_4423.9/sheet_01.jpg` under the frozen review folder.
- `R4415-F4` records contested touches, not established first control.
  `R4415-F5` establishes later blue control at 4424.4–4425.4; it does not identify
  the first official rebounder.
- `ml/data/labels/assist_identity_20261112/riordan_final.json` contains the sole
  strict assist candidate, relying on the cached made shot at 4422.8 seconds.
  A pass/catch chain alone cannot validate that candidate when the shot misses.
- `ml/data/labels/points_accuracy_2026_11_12/after-report.json` also contains
  `made: true` at 4422.8, with `make_t: 4423.1`, in its Riordan predictions and
  unmatched `false_makes`. Its bound `shots.py` hash matches current source:
  `609fb49ff2923cbd599fb690255b2b8db79cc1605c1fe6bcd21faa40756ef0d9`.
  This is a current-source cached-track scoring discrepancy, not just a stale
  assist split. It is not a newly refreshed end-to-end inference result.

Thus a likely false make can yield a spurious assist opportunity and exclude a
real missed-shot rebound opportunity. No new aggregate precision/recall is
computed: the observations remain provisional and the review was targeted.
Shot timestamps and visual release/contact timestamps have different anchors;
their difference alone is not an event-matching failure.

## Action and release limits

Investigate cached trajectory evidence and the make decision before considering
a generic fix. Do not hardcode a timestamp, remove the dead-ball veto, tune to
scoreboard totals, or treat all later collections as rebounds. Preserve frozen
predictions and observations. Keep assists hidden; require independently
adjudicated complete sequences and untouched-game validation before claiming
low-review box scores. Development review remains our responsibility, not a
new mandatory coach task.

## Source-rate follow-up

The bounded experiment in `rim_source_rate_eval.md` used actual PTS-aligned
frames and a pinned local detector. Adding one genuinely observed intermediate
ball/rim pair changes an accepting decimated path to no make under unchanged
decision predicates. This confirms sampling sensitivity on fresh observations,
not just on synthetic interpolation. Historical cache weights/alignment remain
unverified, so this is not a paired historical-cache correction or an adjudicated
physical outcome. The positive control's short window omits initial context in
two decimation phases and does not complete post-exit guards. Full-context
controls are required before promoting source-rate resampling into a runtime
correction strategy. No production or frozen prediction was changed.

The subsequent `rim_context_eval.md` experiment supplied common initial
above-rim context and complete decoded post-exit horizons. The disputed
sampling-phase sensitivity persists; the positive control also has a
centering-based rejection in one phase even with shared initial context.
Complete decoded time does not imply complete ball detections. The generic
evidence trigger selects both the disputed trajectory and a provisional
positive among the curated cases. It is a candidate for acquiring more
automatic evidence, not a rule for deleting makes, an accuracy metric, or a
validated production second pass. Broader cached trigger coverage can estimate
its processing workload but cannot establish correctness without independent
outcome labels.
