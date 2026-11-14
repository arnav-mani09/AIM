# Coach workflow audit

Date: November 13, 2026. Scope: the review page, PlaysPanel, GameInsights,
InsightsPanel and review API adapter in the shared checkout. Existing uncommitted
work was inspected and preserved. No backend, worker or ML implementation was
edited. `reviewMock.ts` was inspected and left unchanged.

## Real automatic flow

1. `backend/app/services/film_processing.py` starts event extraction after tracking
   finishes. `refresh_events` stores the job output and marks `events_status=done`.
   This is a processing state, not an accuracy certification.
2. `backend/app/services/shot_events.py:review_status` maps that state to `ready`.
   The film events response returns shots, visible team plays, availability and a
   box score. It does not require coach confirmation.
3. The review page loads those events and polls every ten seconds while pending.
   Its box score includes non-deleted **draft** events; unreviewed events already
   contribute. Insights mount automatically, without a save or confirmation step.
4. `backend/app/api/v1/routes/insights.py` includes films whose event processing is
   ready. It aggregates draft shots and visible plays, excluding deleted shots;
   there is no full-game review or `requires_review` gate in this path.
5. Corrections are optional. Shot/play patches and additions return persisted
   events; swap returns the updated event collection. The screen then recalculates
   counts and its existing debounced insight refresh runs. Processing status and
   all saved event fields participate in the refresh version.

No heuristic-confidence-to-"verified" rule was found in the inspected read-only
insight components. The audit therefore adds no replacement approval mechanism.
Model scores are not calibrated accuracy probabilities or player identification.

## Demonstrated gaps fixed

- **Uncovered writes:** the existing play-save guard did not cover shot patches,
  shot additions, repeated swaps or rerun starts. These actions now share that
  synchronous guard. Existing play serialization and the insight refresh were
  extended, not replaced with a second queue or a review requirement.
- **Unsaved certification/counts:** shot and play patches used optimistic event
  updates, including `fixed`/`confirmed`. Totals and checked counts now change only
  after the API succeeds. Failed confirmation leaves the shot selected and draft;
  failed edits preserve the last saved values. Navigation to the next shot occurs
  only after successful confirmation.
- **Stale reads:** a pending events read could overwrite a later correction.
  Mutation starts invalidate older reads. A refresh error no longer replaces the
  entire persisted screen with an error-only view. Existing events also remain
  visible, read-only, during a rerun or a failed rerun.
- **Stale insights:** old results remain explicitly labeled while refreshing and
  after errors; a local retry is available. Responses are scoped to the current
  token/team/film and event version; canceled requests cannot replace newer data.
  A skipped/pending film response is not installed as a new all-zero game. Ready
  status itself changes the version, even if event contents did not change.
- **Unknown rendered as zero:** nullable points-per-game, rebound and turnover
  insight values now render a dash, while genuine numeric zero remains zero.
  Existing box-score missing-play behavior remains unchanged: unavailable plays
  yield null/dashes; an available event set with no counted plays yields zero.
- **Development data replacement:** a live write failure or subsequent read
  outage could activate sample mode and replace persisted data. Automatic sample
  fallback is now limited to the initial development read before any successful
  real read. Mutations never silently enter sample mode. Explicit development
  sample mode remains available, and sample events do not request live insights.
- **Mandatory-work/accuracy language:** introductory text and progress labels now
  describe optional checks, automatic estimates, persisted corrections and
  missing data. A draft's confidence is labeled a model score, not “% sure”; fixed
  events do not retain a misleading original model-confidence badge. Missing
  plays do not imply shooting stats require rerunning or manual review.

Assists and steals remain excluded from visible stats and editable event types.
No player attribution or unsupported player-level accuracy claim was added.

## Validation performed

All checks ran locally, without network, installation, browser automation or new
test dependencies/frameworks.

- `cd aim-app && ./node_modules/.bin/tsc --noEmit --incremental false`: passed.
- Targeted ESLint over all six owned frontend files: no errors; one existing
  `react-hooks/set-state-in-effect` warning at review page line 81, the unchanged
  development sign-in effect's `setToken("mock")`.
- `git diff --check`: passed.
- In-memory Node assertions against TypeScript-transpiled actual modules, using
  installed TypeScript/React and mocked I/O: draft/deleted totals; missing plays
  versus available-empty zeros; nullable and actual-zero insight tiles; live
  read/write outage and 404 protection; initial development sample fallback.
- In-memory review-page hook harness: persisted-only shot/play counts; failed
  confirmation; cross-action shot/play/add/swap/rerun exclusion; late load
  rejection; saved play refresh version; duplicate swap prevention; retained
  pending/failed events.
- In-memory GameInsights hook harness: loading/refresh labels; failure retention;
  retry; skipped-film zero protection; canceled late responses; cross-film
  isolation. These are focused component/adapter assertions, not an end-to-end
  browser test or a basketball accuracy benchmark. No existing frontend test
  files/framework were found. An initial harness-only tree walker recursion error
  was corrected before the passing review-page run.

Required local Next.js documentation was read before frontend changes:
`aim-app/AGENTS.md` and the installed Next.js `use-client.md` directive guide.

## Backend coordination and exact limits

- No new API fields or endpoint changes are required by this patch. The backend
  must continue returning canonical persisted events, `ready` only when event
  processing finishes, and `skipped` for films whose insights are not ready.
- The existing `has_plays` contract is coarse: it says a possession pass succeeded
  or a visible play exists (including one added manually). It does not certify
  complete rebound/turnover coverage, distinguish per-stat failure, or measure
  missed events. The frontend cannot infer per-stat unknowns from this flag. If
  backend work introduces partial availability, expose nullable fields/coverage
  explicitly and coordinate the local box-score calculation; do not silently
  reinterpret unknown as zero. Counts here are estimates of detected events,
  never a claim of complete game coverage.
- These guards serialize only this mounted screen. They do not provide
  cross-tab/user locking, backend idempotency, job serialization or rollback. A
  timeout after server commit can still leave the client uncertain; rereading
  persisted state is needed before retrying a potentially duplicated addition.
- Ready processing and high confidence do not prove accurate makes, attempts,
  zones, team identity, rebounds, turnovers or complete film coverage. Reruns can
  retain previously corrected event groups under the existing backend contract;
  they do not promise newly accurate output. No full-game correction task is
  imposed as a prerequisite or proposed as the accuracy solution.
- This pass does not modify or independently validate workers, extraction models,
  processing jobs, multi-user races, the outside-scope season implementation or
  chat grounding. The existing backend processing/aggregation flow was traced in
  source, not executed against a live backend.
