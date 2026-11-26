# Rebound and turnover availability

`shot_events.play_coverage(upload, events)` returns two independent category states:

```json
{"rebounds": "partial", "turnovers": "unavailable"}
```

- `unavailable`: no extraction or observations for this category. Its counts are `null`.
- `partial`: rows establish observed coverage, not complete full-game coverage. Counts include
  only undeleted rows; a deleted category remains observed and can have a known zero.
- `complete`: a successful possession extraction covered this category, including a successful
  empty extraction. Zero is a valid count. This describes pipeline coverage, not accuracy.

Rebounds covers offensive, defensive, and total rebounds for both teams. Turnovers is independent.
Assists and steals never establish either category's coverage and remain hidden.

## Persistence and reruns

The worker returns `play_coverage` next to `possession`. Successful extraction sets both to
`complete`, even if the result is empty. Skipping possession or failing extraction leaves both
`unavailable`. Falling back from film jersey reads to tracker colors is still an extraction;
`film_error` is not an extraction failure.

The backend persists coverage in the existing `GameUpload.events_info["play_coverage"]` JSON.
Without explicit coverage, legacy nonempty possession metadata without an extraction `error`
means complete coverage. Without either, visible play rows, including deleted rows, establish
partial coverage only for their own category. Manual edits need no new columns: their rows and
deletion tombstones retain the evidence. A rerun snapshots inferred coverage into `events_info`.

Existing group retention rules remain unchanged. When any visible play is reviewed, fixed, or
deleted, reruns retain the entire play group **and its existing coverage**, regardless of the
new worker result. In particular a successful rerun cannot promote retained partial manual
data to complete coverage, and a failed rerun cannot downgrade retained complete data.
Unreviewed draft replacement takes the new result's coverage. Team swaps preserve coverage.
No timestamp matching, reconciliation, migration, or backfill is performed.

## Route integration contract

`ShotEventsRead` adds `play_coverage: PlayCoverage`, with the two fields above and default
`unavailable` states for backward compatibility. `has_plays` remains the legacy any-category
availability flag; it must not be used to decide whether an individual category is zero.

The film route constructor passes:

```python
coverage = shot_events.play_coverage(upload, events)
ShotEventsRead(
    play_coverage=coverage,
    has_plays=shot_events.has_plays(upload, events),
    box_score=shot_events.box_score(events, coverage),
)
```

Keep the constructor's other existing fields unchanged.

Season aggregation uses category coverage and sums each category over its own available films.
Each game exposes `play_coverage`; the season response also exposes complete/partial/unavailable
game counts per category. An unavailable category stays null even when another category is
available. The season UI labels limited cohorts and partial observed counts, and computes
recorded counts per covered game using each category's own denominator.

`box_score(events, plays_known)` accepts either the legacy boolean or the new coverage dict.
For partial categories it returns observed counts, including zero after deletion; UI labels
must distinguish these from complete totals. Chat box-score and comparison tools include
`play_coverage` and use category-aware counts.

Insights aggregates each category only over films where that category is available, keeps
`null` when none are available, and describes complete/partial/unavailable game counts in its
scouting lines. `play_games` remains the number of films with any available category, not a
complete-coverage count. Rebound rates require complete coverage across the rebound cohort.
Turnover rates additionally require exactly matching complete rebound and turnover cohorts,
using only those films' shots for the possession estimate. Partial data or mismatched cohorts
produce `null` rates instead of combining incompatible counts and denominators. Shooting
statistics continue to include all ready films.

The review screen computes saved counts independently per category, retains partial coverage
after deletion, and labels observations separately from completed extraction. On older servers
without explicit coverage, visible play rows establish partial coverage for their category;
the legacy `has_plays` flag alone cannot certify both categories. Insights exposes
`rebound_games` and `turnover_games` separately so its stat tiles do not reuse the union count.
