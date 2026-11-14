# Rebound evidence review (development only)

## Scope and evidence

Both Mitty and Riordan are development data. No held-out claim, Hudl-total accuracy
claim, or individual-player accuracy claim is made. Existing cached tracks, labeled
shots, holder pixels, and the possession timeline were frozen before this change.
No detector inference or full-film color read was run. Ten targeted sequences were
inspected from actual local film, with ball-centered crops at miss time and +1, +2,
+3, +4, +6, +8 seconds, plus a full frame. These are diagnostic examples, not a
random precision/recall sample. Sparse frames do not establish every touch.
Five labeled sequences also received dense rim/recovery review from -0.2 through
+1.2 seconds at 0.2-second intervals; `dense_evidence` paths accompany their labels.

The local audit artifacts are in `/tmp/aim-rebounds/`: `mitty.before.json` and
`riordan.before.json` freeze labeled runs, shot inputs, timeline and original events;
`*.labels.json` reference inspected film images; `*.after.json` contain all decisions,
counts, unknowns, input hashes and a bounded next-review queue. The baseline was the
pre-edit shared working tree, not Git HEAD (which lacked existing integration work).
Artifacts are local, not checked in, and must be retained externally if needed later.

Parent follow-up (November 12, 2026): the audit artifacts have been copied to
the local, gitignored `ml/data/labels/rebounds_accuracy_2026_11_12/` directory.
Frozen labels still reference the original evidence paths; retain the copied
images if rebuilding those paths after temporary-file cleanup.

## Root causes found

- First *clearly colored* contact can occur seconds after the actual rebound. The
  real rebounder's ambiguous/absent color was skipped, allowing a later dribbler,
  defender or shooter to receive the rebound.
- A hold is geometric ball-in-box proximity. Three-frame and crowded overlaps do
  not prove controlled possession: tips, loose balls and bodies on the floor fit it.
- Whole-track voting can override the current jersey sample, including switched
  tracks. Conversely, moderate current pixel votes can also be wrong (Mitty 1005.9).
- A baseline official behind the rebound action overlaps the ball in image space.
  The old two-frame referee proximity heuristic falsely marked inspected live
  rebounds at Mitty 519.4 and 856.9 as dead ball when tried for rebound suppression.
- Searching a fixed eight seconds without the next shot as a barrier can borrow
  another shot's holder. Repeat-shot inference previously ran before referee checks.

## Changes and confidence

`run_v2` still returns `(timeline, events)` and the event type/team/time fields remain
compatible. Rebounds now have an auditable per-miss decision function, also used by
the evaluator. Searches end at the next labeled shot, halftime start, game end, or
eight seconds. A geometric control proxy requires at least 0.5 seconds and a
contested share below 0.5. These thresholds are rules, not calibrated accuracy.

Current pixel votes stronger than `VOTE_SURE` can override track identity. Weak local
votes conflicting with the track are unknown; missing/near-neutral pixel evidence
does not become certain just because an aggregate track vote was certain. Earlier
unknown control is not skipped to credit a later clearly colored player.

Raw referee suppression requires at least 0.5 seconds of exclusive torso contact,
with no overlapping player box. A referee-labeled holder first also blocks a rebound.
This is evidence for dead ball, not proof of out-of-bounds specifically. A referee
after ambiguous contact does not erase the possibility of an actual earlier board.

New `how` values distinguish `control` (0.75), `inferred_control` (0.45), `touch` (0.30),
`unresolved` (0.25), and `repeat_shot` (0.50). These are heuristic confidence tiers,
not measured probabilities. Only clean control without earlier contacts gets a
player track. Missing control still produces a low-confidence defensive inference;
it is **not** an observed rebound or individual credit. `evidence` explains the
uncertainty in raw outputs. Existing `EVENT_CONF` lookup makes the site's adapter
preserve these tiers, with its existing further reduction when film colors are absent.
The adapter retains `how`, but does not currently copy the new `evidence` string.

## Actual frozen comparison

| Development game | Before Valley O/D | After Valley O/D | Before Opponent O/D | After Opponent O/D |
| --- | --- | --- | --- | --- |
| Mitty | 11 / 24 | 5 / 24 | 5 / 21 | 5 / 27 |
| Riordan | 10 / 30 | 6 / 28 | 9 / 28 | 8 / 31 |

These are output changes, not accuracy metrics. There are 138 live-miss decisions;
25 change team/type or event presence. Four Riordan decisions are suppressed for
pre-control dead-ball evidence. Forty-two events use the observed-control proxy;
the remaining 92 emitted events explicitly carry weaker/inferred evidence.
The four suppressed decisions have not all been film-validated.

| Inspected miss (seconds) | Film-supported team outcome | Before | After |
| --- | --- | --- | --- |
| Mitty 495.7 | Opponent DREB (white advances) | wrong OREB | correct, unknown-team inference |
| Mitty 519.4 | Opponent DREB | correct | correct, unknown-team inference |
| Mitty 856.9 | Valley DREB | correct | correct, control proxy |
| Mitty 1005.9 | Valley OREB (blue gathers/dribbles) | correct | **wrong**, unknown-team inference |
| Mitty 1992.7 | Opponent DREB | correct | correct, unknown-team inference |
| Riordan 5011.2 | Opponent DREB (white advances) | wrong OREB | correct, possible touch/inference |
| Riordan 5287.3 | Valley DREB | correct default guess | correct, control proxy |

On these **seven targeted team-outcome labels only**, before is 5/7 and after 6/7
(Mitty 4/5 both; Riordan 1/2 to 2/2). Correct defensive defaults are still guesses,
not validated control detections. The Mitty 1005.9 regression remains: weak current
color conflicts with track identity, becomes unknown, and the retained defense
fallback is wrong. This is not a general accuracy improvement estimate.

Three inspected sequences remain unknown: Riordan 5029.9 (crowded loose ball/fall and
stoppage), 2047.2 (upstream shot/shooting-team ambiguity), and 715.8 (restart shown,
but make/miss and prior control not established). Another 128 misses are unreviewed.
No rebounder numbers, identities, exact acquisition times, team rebounds, or full-game
rebound precision/recall were labeled. The control proxy can still be a later dribbler;
upstream shot/make errors, undetected out-of-bounds and quarter boundaries remain.

## Reproduce

From the repository root:

```sh
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_rebounds.py -v
ml/.venv/bin/python -m unittest discover -s worker -p test_possession_events.py -v
ml/.venv/bin/python ml/tools/rebound_eval.py --snapshot /tmp/aim-rebounds/mitty.before.json --labels /tmp/aim-rebounds/mitty.labels.json --output /tmp/aim-rebounds/mitty.after.json
ml/.venv/bin/python ml/tools/rebound_eval.py --snapshot /tmp/aim-rebounds/riordan.before.json --labels /tmp/aim-rebounds/riordan.labels.json --output /tmp/aim-rebounds/riordan.after.json
```

For future changes, `--freeze mitty --snapshot <new-path>` records the current
implementation from existing caches and refuses to overwrite a baseline. Run this
**before** changing logic. Comparison freezes the holder/timeline inputs instead of
rerunning evolving shot or assist code. `--video <local-film> --limit 6` generates a
bounded next-review set (hard maximum 20). Add labels only after inspecting those
images; unknowns never enter the labeled score. An evidence path is required for
every non-unknown label. Preserve artifacts and record any relabeling explicitly.

Validation: 21 rebound regressions and 6 existing worker possession tests pass.
Cached-input `run_v2` integration matches the evaluator exactly in both games
(61 Mitty rebounds / 102 timeline segments; 73 Riordan / 125 segments).
This is accuracy groundwork with a known regression, not production validation.

## Parent follow-up: conflicting-color regression

The initial implementation above is preserved in `*.after.json`. The parent
replay in `*.parent.json` fixes the Mitty 1005.9 regression without using that
timestamp in production logic. When the first sustained control has a track
team but conflicting weak current color, a subsequent strong, uncontested local
color sample can corroborate that existing team. Any intervening opposing contact
or referee evidence blocks corroboration. Unknown track identity cannot be filled
from a later holder, and an aggregate track vote alone is not corroboration.

The result remains `inferred_control`, with no credited player and confidence
below 0.5; it does not become a verified rebound. The site's worker adapter now
retains the `evidence` reason as well as `how`.

On the same seven targeted film-supported labels, the parent replay gets all
seven team outcomes correct. That sample was used for development and does not
measure full-game accuracy, individual attribution, or coach review time.
Fourteen decisions use the new corroboration rule; those other changed cases
still require independent review. Additional synthetic regressions check that
opposing contact, referee contact, crowding, or track-only support cannot make
the uncertain control appear observed.
