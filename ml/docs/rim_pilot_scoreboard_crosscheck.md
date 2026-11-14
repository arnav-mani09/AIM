# Rescan pilot: evaluation-only scoreboard cross-check

November 13, 2026. This is an offline counterfactual, **not shipped accuracy,
physical-outcome adjudication, or an end-to-end second-pass implementation**.

## Method

After the six pilot windows and their outcomes were frozen, apply every pilot
dense `made` decision to the corresponding uniquely identified prediction in
`ml/data/labels/points_accuracy_2026_11_12/after-report.json`, in memory only.
Do not select corrections using scoreboard truth. Match the complete resulting
prediction lists to the existing scoreboard events using unchanged
`makes_eval.event_report`. No original predictions, truth, pilot evidence or
runtime source is overwritten. No new source-film processing is involved.

The scoreboard file hash and every source hash bound by the frozen scoring
report were checked against current bytes. Replaying each original prediction
list reproduces its original complete event report exactly. Each of the six
pilot cases maps to exactly one original prediction by game and attempt time.

## Result

- Mitty: all three pilot decisions retain made status. The counterfactual keeps
  43 of 53 scoring events matched and seven unmatched makes.
- Riordan: the pilot rejects attempts 860.10 and 1788.60; its 940.50 control
  remains made. Both rejected predictions are in the frozen scoreboard audit's
  unmatched-make list. Applying all three decisions retains the same 52 of 61
  scoring-event matches, reducing unmatched predictions from seven to five.
- The exact list of previously matched scoreboard events is preserved for each
  game, not merely its size. No additional scoring event is recovered.

For Riordan this hypothetical scoring-event precision is 52/57 (91.23%), versus
the frozen report's 52/59 (88.14%); recall remains 52/61 (85.25%). These are
**counterfactual development-fixture matching metrics only**. They must not be
reported as current platform accuracy or a measured generalization gain.

## Why this is not yet an automatic correction

The local detector is pinned, but historical detector checkpoint/config/frame
equivalence is unproven. Pilot decisions use bounded local `decide` paths, not
full `find_shots` state or downstream recomputation. Team, shot value and player
credit are not validated. A scoreboard-unmatched call is not independently
certified as a physical miss: attribution and event-matching errors can also
cause nonmatches. Six development cases cannot establish correction safety,
trigger enrichment, missing-shot recovery, or reduced coach time.

This cross-check adds corroboration for the two provisional corrections while
preserving the distinction between an experimental outcome and a deployed
improvement. Scoreboard information remains evaluation-only and must not enter
selection, detector inference, or runtime correction logic.

## Frozen pilot identities

- `selection.json`:
  `72a8efa9e5c666740ab9cc2a085adf35e0a564a5dc7efd98ce7e97f4ad76a101`
- `summary.json`:
  `3bbdf43dfe6b6067700a986d417612b17d47652aebbe5e531b6ca98ad204c8ba`
- `analysis.json`:
  `f47ee2eab5ff90c2712f9450f3403e9d4b559b21753a87240ac56d1c27b7ae7c`

All three live under `ml/data/labels/rim_rescan_pilot_20261113/`. See
`rim_rescan_pilot.md` for selection, native-image inspection, actual inference
cost, complete decoded horizons and incomplete detector coverage.
