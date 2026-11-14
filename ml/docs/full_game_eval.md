# Independent source-timeline evaluation

`ml/tools/full_game_eval.py` is an offline, standard-library evaluation and template
export tool. It runs no inference, decodes no footage, generates no truth labels,
and adds no coach workflow. Existing seven rebound development examples and
predicted-made-opportunity assist templates cannot measure whole-game precision,
recall, or events the model never proposed. This harness provides the measurement
contract, not evidence of real accuracy or reduced coach time.

## Export and run

```sh
python3 ml/tools/full_game_eval.py export \
  ml/data/tracks/valley-vs-archbishop-mitty.v4.window.json \
  valley-vs-archbishop-mitty \
  ml/data/labels/full_game_eval_20261112/mitty.unreviewed.json
python3 ml/tools/full_game_eval.py export \
  ml/data/tracks/valley-vs-archbishop-riordan.v4.window.json \
  valley-vs-archbishop-riordan \
  ml/data/labels/full_game_eval_20261112/riordan.unreviewed.json
python3 -m unittest discover -s ml/tools -p test_full_game_eval.py
python3 ml/tools/full_game_eval.py evaluate INPUT.json NEW_REPORT.json --tolerance 1
```

Every output uses exclusive creation: existing files are never overwritten. Work
on a separately named copy for independent annotation. No annotation is required
from coaches; future evaluation needs independent source review evidence, whoever
does that work. Cached windows are estimates, not independently confirmed game
boundaries. Both named games are development data, not held-out validation.

Export exhaustively tiles the entire cached `[start,end)` timeline in deterministic
120-second windows (`--width` changes this). It does not read predictions or use
model confidence. Halftime, quiet stretches, and stretches with no predictions
remain represented. The cached source-window file path and SHA-256 are recorded;
this is a hash of the window metadata, **not the footage**. Source annotations
should reference immutable footage/version evidence separately. Evaluated reports
also hash the exact input and evaluator implementation. Existing artifacts remain
private/local; nothing is uploaded.

## Input contract (schema version 1)

An exported document contains the game identifier, two team names, `source` with
`path`, lowercase SHA-256 and `split_role` (`development` or `held_out`),
`timeline`, `timeline_independently_confirmed`, `intervals`, `truth_events`,
`predicted_events`, and `review_log`. All these fields are required. A true
timeline confirmation also requires nonblank `timeline_evidence` from independent
boundary review. Assertions are an auditable input contract, not automatically
verified evidence of independent review. Keep source split assignments honest.

Intervals have unique `id`, finite `start`/`end`, and one explicit `status`:

- `reviewed_complete`: independently reviewed for **all three event types** across
  the entire interval, including any negative time. Requires
  `independent_of_predictions: true` and nonblank `evidence`.
  Set `reviewer_type` to `human`, `model`, or `unknown` (the default). Human
  adjudication also requires a nonblank `reviewer` identifier. Provisional model
  labels may support explicitly qualified interval diagnostics, but do not
  establish independently verified full-game accuracy.
- `partially_reviewed`: some source review, with the same independence/evidence
  requirements, but **no precision/recall scoring**. Split out genuinely complete
  subintervals to score them. Known true events here are explicitly unscored.
- `unreviewed`: unknown truth, including empty exported event arrays.
- `unobservable`: source cannot establish truth; explicitly excluded.

Intervals must be ordered, nonoverlapping and inside the timeline. Gaps are
reported as unlisted/unreviewed seconds and prevent full-game claims. Blank,
missing, or unknown statuses fail validation. No events and no annotations never
mean a verified negative interval. Only affirmative `reviewed_complete` permits
an empty truth list to establish negative evidence.

Events use `id`, finite source-video `time` in seconds, `type` (`point`, `rebound`,
or `assist`), `team`, and `player` (stable string ID or explicit null). Point events
represent one actual scoring action, including free throws, and require integer
`points` of 1, 2, or 3. Truth teams must be known; predicted team may be null,
which cannot earn a team-constrained match. Truth events additionally require
nonblank `evidence` referencing independent source review. Truth outside complete
or partially reviewed intervals fails. For example:

```json
{"id":"truth-001","time":253.2,"type":"point","team":"Valley",
 "player":"roster-player-12","points":2,"evidence":"source review record 001"}
```

Truth must be collected from source intervals, not seeded from predicted shots,
made-shot opportunities, or blank labels. There is intentionally no dependency
on a detector shot list: an independently observed scoring action without any
predicted shot is a missed real event. Team rebounds may have a null player.
Source basketball/statistical annotation conventions must remain consistent.

## Matching and metrics

Matching is one-to-one within event type, the **same reviewed-complete interval**,
inclusive timestamp tolerance (default one second), and equal team. Time intervals
are half-open: an event at an interval end belongs to the next interval; an event
at timeline end is invalid. Tolerance cannot bridge review boundaries. For
contiguous complete tiles this is deliberately conservative: combine tiles into
a single complete interval when independently justified, rather than changing
timestamps to rescue a match.

Multiple eligible truths for a prediction fail as ambiguous rather than using a
greedy optimistic assignment. Duplicate truth type/time/team entries fail.
Multiple predictions for one truth select the closest; identical duplicate
predictions break ties by ID and the rest remain false events. Equidistant
conflicting predictions fail. This policy deliberately rejects some dense event
sets; resolve independent timing or narrow tolerance instead of cherry-picking.

`interval_metrics` reports per-type precision/recall, counts, false prediction IDs,
and missed truth IDs. Predicted events in partial, unreviewed, unobservable, or
unlisted time are unscored, not false positives. Known truths in partial time are
also unscored. Zero denominators return null, never perfect accuracy.

- Team accuracy uses a separate one-to-one type/time-only diagnostic pairing with
  the same ambiguity checks. Wrong teams still produce both a false event and a
  missed real event in the primary team-constrained metric.
- Player accuracy is conditional on primary matched events with known true player;
  missing predicted player is incorrect, unknown true player is excluded and counted.
- Points-value accuracy is separate and conditional on primary matched point
  events. A correct-time/team event with a wrong value still matches as an event,
  but fails value accuracy. This is not total-score accuracy or end-to-end player
  accuracy; missed events and false events remain essential alongside attribution.

`full_game_metrics` is null and `partial` is true unless independently confirmed
timeline boundaries are completely covered by independent complete intervals.
Those intervals must also have explicit named human adjudication; otherwise
`reference_status` is `provisional_or_unspecified`, and full-game metrics remain
null even when `complete_timeline_coverage` is true. The human review can be
performed by the development team; this is not a coach labeling requirement.
Even complete development-game coverage is not held-out generalization evidence.
The tool rejects nonfinite times, overlapping intervals, invalid identities,
invalid point values, duplicate IDs, and oversized input (10 MB or 10,000 entries
per list). Tolerance is bounded to 0–30 seconds. Validation failures produce no
report. The tool does not silently fix ambiguous annotations.

## Explicit review burden only

`review_log` defaults to an empty list, yielding null `review_burden`. Each real
entry must include a unique `id`, `evidence` referencing an actual review/correction/timer log,
`reviewer_role`, nonnegative finite `active_seconds`, and nonnegative integer
`reviewed_events` and `corrections`. Sessions must be disjoint and nonduplicated;
do not invent timings or infer them from confidence, test counts, template size,
or event volume. The tool sums explicit logs and reports time by role; analyst
time is not coach time. `coach_time_gain` remains null because no independent
baseline/comparative time study exists here. No real accuracy or coach-time gain
has yet been established by these synthetic regressions or unreviewed exports.
