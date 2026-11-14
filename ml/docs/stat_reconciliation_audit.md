# Automatic stat reconciliation audit

## Scope

Backend ingestion and aggregation audit against the current shared-checkout worker
contract. Existing uncommitted service changes were inspected and preserved. No
additional production defect was demonstrated in the exercised paths, so this
change adds regressions without changing service behavior, schemas, migrations,
or the frontend contract.

## Traced behavior

- `backend/app/services/shot_events.py:85`: worker results replace draft-only shot
  and possession groups independently. A group containing a reviewed, corrected,
  manually added, or deleted visible event is retained under the existing policy.
- `backend/app/services/shot_events.py:33`: totals are computed from persisted live
  events, not the worker's cached `box_score`. Field goals include 2s and 3s;
  points are `2 * FGM + 3PM + FTM`.
- `backend/app/services/shot_events.py:56`: possession metadata distinguishes
  successful extraction from missing/failed extraction; manually retained plays
  also establish availability. The current worker represents a skipped extraction
  as `possession: null`, not a separate skipped-state object.
- Film, season, insights, and the chat box-score helper read the persisted events.
  Insights use shots from possession-covered films for possession-rate denominators.

## Added regression coverage

`backend/tests/test_shot_events.py` now exercises:

1. Automatic FG2-to-FG3, missed-to-made FT, and team corrections after plays exist,
   including a manually corrected play. Three reloads keep shooting totals current
   across film, season, insights, and chat without losing the play correction.
   A deliberately stale worker `box_score` cannot override persisted-event totals.
2. Replacing shots and plays repeatedly removes previous drafts rather than
   accumulating events. Hidden assists/steals remain stored but not counted; a
   lower-confidence rebound remains a draft, without a new confidence cutoff or
   fabricated player identity.
3. Successful nonempty possession extraction followed by failed or skipped
   extraction removes obsolete automatic play totals and returns unknown/null.
   A subsequent successful empty extraction returns known zero.
4. Editing a shot's make, value, and team does not infer or rewrite the independently
   observed rebound from its `detail.shot_t` provenance.
5. A shot and two plays at the same timestamp retain independent identities.
   Cross-upload and nonexistent event IDs return 404 without changing the film.

Existing tests additionally cover manual deletions/restores, reviewed-shot
survival, swapping both teams, swapping before plays or shots exist, unknown
versus zero across views, hidden-event rejection, and weighted season counts.

## Limits and follow-up boundaries

- These are in-memory SQLite ingestion/API/aggregation tests. They do not run
  video inference, assess whether a rebound really occurred, validate detector
  accuracy, or certify an uncertain draft as verified.
- Reviewed groups are deliberately frozen as a whole. One manual correction can
  therefore retain other drafts in that group on rerun. This pre-existing policy
  was not redesigned under the instruction to preserve manual-edit handling.
- The current worker emits event type/time/team and optional `detail.shot_t`, not
  a durable source-event ID or authoritative shot foreign key. Timestamp
  coincidence is not identity; `shot_t` is provenance, not a database event ID.
  This audit does not claim source-ID deduplication or reference integrity that
  the current contract does not provide. A durable per-event reconciliation
  contract needs separate worker/backend coordination; none was invented here.
- Repeated identical reruns are covered, but duplicate observations already
  present inside a single worker payload cannot safely be identified merely by
  matching timestamps. No blanket deduplication was added.
- No network, package installation, migration, live database, commit, push, or
  deployment is needed for the tests.

## Validation

Baseline: `cd backend && .venv/bin/python -m unittest tests.test_shot_events tests.test_insights tests.test_season -q`
passed 32 tests before this audit's additions. The same command passes 37 tests
with the five added regression methods.

Expanded focused run: `cd backend && .venv/bin/python -m unittest tests.test_shot_events tests.test_insights tests.test_season tests.test_chat -q`
passes 47 tests, including the existing chat suite.
