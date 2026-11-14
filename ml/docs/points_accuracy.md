# Scoring-event accuracy audit — November 11, 2026

## Scope and evidence

This pass changes only `shots.py`, `makes_eval.py`, and `test_makes.py`, preserving
the pre-existing uncommitted implementation. Scoreboard changes are evaluation
labels only; production shot rules do not read the scoreboard. No paid APIs,
package installation, full-film inference, commits, or deployments were used.

Both Mitty and Riordan previously influenced development. **Neither is a globally
untouched holdout.** Improvements here are development-fixture gains, not evidence
of generalization. Cached scoreboard changes validate against Hudl FGM, FTM, 3PM,
and points for both teams. This checks completeness/totals, not every timestamp.

The initial engine and every prediction were frozen under
`/tmp/aim-points-accuracy/` before editing. After implementation, the old engine was
loaded from `before-shots.py` and replayed through the same pipeline as the new
engine. Its predictions exactly equal the initial frozen predictions on both
games. Truth and track SHA-256 identities also match before/after. These are local
artifacts, not committed fixtures; `/tmp` is not durable storage. The parent
copied the audit, frozen engine, predictions, and review sheets to the local,
gitignored `ml/data/labels/points_accuracy_2026_11_11/` directory and added an
independently replayed `parent-verified-report.json` there. These private film
artifacts must not be added to git.

| Input | SHA-256 |
| --- | --- |
| Score changes | `ac141839f09d5bf87e5c0ac4912ac3857866ff6f023d945e433f74f1a2899920` |
| Mitty v4 tracks | `0994d981e6b5247ed58ca0a091ec1dafdd02d356071938e4526f3de34d19926a` |
| Riordan v4 tracks | `cd2f1a8226ae71f7c72329433a1e19937717ff660b23b985a45e829e21504a7c` |
| Frozen original shots.py | `3f05493cf1082da442f08f4a8097134deec2d77b9a4484b8720311e41c079ec1` |
| Updated shots.py | `609fb49ff2923cbd599fb690255b2b8db79cc1605c1fe6bcd21faa40756ef0d9` |

## Frozen comparison

Both runs skip film-based 2/3-point classification. No total-points or three-point
accuracy claim follows from this comparison. Matching rules are unchanged.

| Fixture / engine | Matched scores | Unmatched makes | Event precision | Event recall |
| --- | ---: | ---: | ---: | ---: |
| Mitty before | 43/53 | 7 | 86.00% | 81.13% |
| Mitty after | 43/53 | 7 | 86.00% | 81.13% |
| Riordan before | 51/61 | 7 | 87.93% | 83.61% |
| Riordan after | 52/61 | 7 | 88.14% | 85.25% |

**One real cached-film scoring event is recovered**, not merely a synthetic test:
Riordan Opponent +2, scoreboard first seen at 4892.8 s. Before, the audit attached
the miss at 4888.6 s. Film crops show that miss followed by a distinct putback.
After, a new attempt starts at 4890.0 s and is made at 4891.0 s. No previously
matched score becomes unmatched, and the identities of all 14 unmatched makes
remain unchanged across the two fixtures.

Live attempts increase from 120 to 121 on Mitty and 141 to 142 on Riordan. The
Mitty additional attempt at 3785.8 s is also a film-visible putback, but its make
remains rejected: its first detected below-net exit is approximately 0.39 rim
widths from center, beyond the existing 0.35 cutoff. This is **not** a Mitty
scoring-accuracy gain. Warmup attempt segmentation also changes (total detected
attempts 159→161 and 164→167); those attempts remain excluded from live stats.

## Error breakdown and priorities

Before: Mitty has 7 nearby-called-miss scores and 3 not-found scores; Riordan also
has 7 nearby-called-miss scores and 3 not-found scores. There are no unmatched
truth events categorized wrong-team or dropped. Each game has 7 unmatched makes.

After: Mitty is unchanged at 7 nearby-called-miss and 3 not-found; Riordan has 6
nearby-called-miss and 3 not-found. Matched Mitty events comprise 26 FG / 17 FT;
matched Riordan events comprise 28 FG / 24 FT. Riordan still has a matched FT
classified FG (score change at 2512.8 s).

The largest measured buckets are nearby-called-miss events (14 before) and
unmatched makes (14). Those are diagnostic buckets, **not independently verified
physical causes**: a nearby miss may be an earlier attempt, and an unmatched make
may physically go in but be disallowed. Broad timing windows and hidden-overlay
intervals can also create accidental matches.

High-confidence actionable mechanisms identified:

1. **Merged quick putbacks (2 inspected examples).** The 1.5-second active attempt
   plus 2-second zone refractory interval merges a miss and a subsequent upward
   flight. This is the bounded fix in this pass. It recovers one score; the other
   remains a make-classification failure, as described above.
2. **False dead-ball vetoes (2 Riordan scores).** Makes at 886.8 and 1208.6 s have
   positive trajectory evidence but are changed to misses by slow-player / no-pan
   logic. Film shows real plays. A counterfactual restoring every veto changes
   Mitty matched/unmatched from 43/7 to 43/10 and Riordan from 51/7 to 53/13.
   Blanket removal is therefore rejected, not shipped. Stationary camera and
   player motion alone cannot distinguish waived baskets from live and-ones.
3. **Missing attempts / detector coverage (6 baseline not-found scores).** These
   require better ball continuity, refractory handling beyond an active attempt,
   or usable rim visibility. The current implementation does not recover them.
4. **Rim/net geometry and disallowed physical makes.** Remaining trajectory
   failures include off-center exits and occlusions. Crops of unmatched makes
   include referee signals, a red backboard at Mitty 3887 s, and ambiguous rim
   contacts. Those suggest dead-ball/violation and rim-out categories, but the
   crop inspection is not sufficient to assign authoritative cause counts.

### Every baseline missed score

Times are seconds from the original film; score time is `seen_new`, not the true
instant of the basket. The listed nearby attempt is an evaluator association.

| Game | Score time | Team / increment | Baseline bucket / associated attempt | Status |
| --- | ---: | --- | --- | --- |
| Mitty | 681.07 | Valley +2 | not found | unresolved |
| Mitty | 1866.13 | Valley +2 | not found | unresolved |
| Mitty | 2941.33 | Opponent +2 | called miss / 2931.7 | unresolved association/trajectory |
| Mitty | 2966.40 | Opponent +3 | called miss / 2964.0 | unresolved trajectory |
| Mitty | 3096.27 | Valley +2 | called miss / 3089.7 | unresolved association/trajectory |
| Mitty | 3402.93 | Opponent +2 | not found | unresolved |
| Mitty | 3452.00 | Opponent +1 | called miss / 3448.7 | unresolved trajectory |
| Mitty | 3789.07 | Valley +2 | called miss / 3784.9 | separate putback at 3785.8 now found, still called miss |
| Mitty | 4311.73 | Opponent +2 | called miss / 4307.0 | unresolved association/trajectory |
| Mitty | 4743.47 | Opponent +3 | called miss / 4740.0 | unresolved trajectory |
| Riordan | 749.07 | Valley +2 | called miss / 744.1 | unresolved association/trajectory |
| Riordan | 893.33 | Valley +2 | called miss / 886.8 | dead-ball veto |
| Riordan | 1048.27 | Opponent +2 | called miss / 1045.2 | unresolved trajectory |
| Riordan | 1215.20 | Valley +2 | called miss / 1208.6 | dead-ball veto |
| Riordan | 1807.20 | Valley +1 | called miss / 1803.5 | unresolved trajectory |
| Riordan | 2500.80 | Valley +1 | not found | unresolved rim/ball coverage |
| Riordan | 3915.20 | Opponent +2 | called miss / 3911.7 | unresolved trajectory |
| Riordan | 4410.13 | Valley +1 | not found | unresolved |
| Riordan | 4892.80 | Opponent +2 | called miss / 4888.6 | recovered putback at 4890.0 |
| Riordan | 5113.07 | Opponent +2 | not found | unresolved |

### Every unmatched make (unchanged)

| Game | Kind | Attempt times (seconds) |
| --- | --- | --- |
| Mitty | FG | 442.6, 1250.8, 1733.2, 1802.7, 3887.0, 4181.1 |
| Mitty | FT | 4899.3 |
| Riordan | FG | 860.1, 866.35, 2367.2, 4422.8 |
| Riordan | FT | 1788.6, 2726.3, 4334.1 |

## Implementation and tests

The split requires an observed rise from below the rim to above it, earlier
below-net evidence, recent observations, the same tracked basket, and a prior
trajectory classified as a miss. It does not change shot geometry thresholds,
infer correctness from aggregate totals, or split an already-made basket. It
currently applies to the main-ball pass while the old attempt is still active;
rescue-only putbacks, track switches, and later rebounds remain limitations.

Three new synthetic regression tests cover separate miss/putback attempts,
same-basket/recency/flight guards, and not splitting a made basket followed by an
upward ball. A fourth tests the serializable event audit; the existing CLI test
now checks JSON export. Synthetic coverage is distinct from the single real
scoring-event gain reported above.

Exact focused and broader test commands:

```sh
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_makes.py -v
ml/.venv/bin/python -m unittest discover -s ml/tools -p 'test_*.py' -v
```

Results: **26/26 scoring tests pass; 89/89 currently present ML tests pass**.
The larger count includes concurrent assist/rebound agents' tests; those files
were not changed by this pass. `git diff --check -- ml/tools/shots.py` also passes.

Exact lightweight evaluation command:

```sh
ml/.venv/bin/python ml/tools/makes_eval.py --games mitty,riordan --no-film --list --report-json /tmp/aim-points-accuracy/after-report.json
```

The new `--report-json` exports all predictions, per-score matching buckets,
unmatched makes, metrics, and source/input fingerprints. Normal evaluation still
defaults to Mitty. The baseline replay used this same `run_pipeline` with a frozen
engine substituted in `sys.modules['shots']`; frozen comparisons and original
raw-path snapshots are in `before-frozen-report.json`, `after-frozen-report.json`,
`mitty-before.json`, and `riordan-before.json` under the temporary directory.

Film inspection used existing `makes_eval.zoom` only: for each game, the 10
baseline unmatched truth events were centered on the associated attempt (or
`seen_new - 2.2` when absent), plus the 7 unmatched makes. Each event uses rim
crops from -0.6 to +2.6 seconds at 0.2-second intervals. No new detector inference
was performed. Crops remain local temporary artifacts.

## Not measured

No independently labeled complete miss set, total-point accuracy, shooter
identity accuracy, or untouched-game performance is measured here. One-to-one
score matching does not prove every found prediction is the actual basket.
Resolving the 14 unmatched makes requires whistle/violation context or careful
event-level adjudication, not adjusting make thresholds to hit Hudl totals.

## November 12 follow-up: dead-ball veto discrimination

**Decision: no production change.** `shots.py`, `makes_eval.py`, and
`test_makes.py` retain their exact starting bytes, including the prior putback
fix. No confidence changes, score-dependent runtime logic, required coach review,
or additional review queue were introduced. The two legitimate Riordan baskets
remain known failures, not corrected or hidden predictions.

### Frozen protocol and private evidence

The new starting point includes the November 11 putback fix: Mitty **43/53**
matched scores with **7** unmatched makes; Riordan **52/61** with **7** unmatched.
Snapshots, complete before/after reports, test output, review script, source/input
identities, and film sheets are under the local, gitignored directory
`ml/data/labels/points_accuracy_2026_11_12/`. The earlier durable audit remains
untouched. This directory contains private film derivatives and must not be
committed.

Inspection covered **13 candidates**: both legitimate Riordan makes, nine other
vetoed attempts already classified FG, and two vetoed attempts currently
classified `fouled` that become FG when the veto is removed upstream. Every
candidate has a full-court context sheet (`<game>-<t>-context.jpg`, 16 samples
from attempt time -5 to +10 seconds, at one-second intervals) and a rim sheet
(`<game>-<t>-rim.jpg`, 17 samples from -0.6 to +2.6 seconds, at 0.2-second
intervals). `veto-context.json` records motion in six pre/post windows, camera
departure within 15 seconds, nearby attempts within 45 seconds, and nearby
evaluation-only score changes within 30 seconds. No detector/model inference
was run. These sampled frames establish visible context, not audible whistle
timing or a definitive violation taxonomy.

### Film/context findings

Times identify attempt starts, not necessarily releases or scoreboard changes.
"Unmatched" below is the same-fixture evaluation outcome, not a claim that the
ball physically missed. Referee gesture interpretations remain provisional.

| Game / attempt | Bounded film and sequence evidence | Veto-removal outcome |
| --- | --- | --- |
| Riordan 886.8 | Active blue drive and contested release, ball through net; officials/players then stop rather than transition. A detected isolated FT follows at 912.3. | Recovers Valley +2 at 893.33. |
| Riordan 1208.6 | Active contested blue attack, rim/net descent and post-shot stoppage; near official raises arms as play ends. Detected isolated FT at 1237.5. | Recovers Valley +2 at 1215.20. |
| Mitty 369.4 | Initial white shot, contested recovery, then a separate later attempt at 372.9 that already matches the score. Rim-plane ambiguity in the earlier descent cannot justify a second score. | Additional unmatched make. |
| Mitty 698.0 | Near official's arm is raised before the later corner release; players stop, and a later arms-out gesture is visible. Ball nevertheless passes through the net. | Additional unmatched make. |
| Mitty 3331.6 | Drive/contact with a fallen player, followed by a short blue rim attempt while play stops and officials intervene. | Additional unmatched make. |
| Riordan 806.0 | Players/official already stopping before white's late shot; ball still goes through. | Additional unmatched make. |
| Riordan 1980.2 | Blue jump shot, white recovery and transition; sampled rim projection resembles a downward exit despite the ensuing rebound. | Additional unmatched make; trajectory ambiguity, not a clean dead-ball example. |
| Riordan 2003.4 | White drive and rim/net descent with a referee arm signal around the attempt, followed by stationary players/official involvement. | Additional unmatched make; generic foul/stoppage evidence resembles the positives. |
| Riordan 4048.3 | Contested blue finish, prolonged rim contact and descent, then referee/players stopped under the basket. | Additional unmatched make; same broad post-shot stoppage pattern. |
| Riordan 4459.5 | White follow-up after the 4456.7 attempt, contested recovery and subsequent blue transition rather than an uncontested inbound. | Additional unmatched make; trajectory/rebound ambiguity. |
| Riordan 5512.3 | Near official raises an arm around 5510.3, before the later white release; play stops with a blue player down, but the later ball enters the net. | Additional unmatched make. |
| Mitty 4476.4 | Contested white attempt/recovery and referee stoppage; two subsequent detected FTs at 4498.8 and 4518.8. | `fouled` becomes FG and adds an unmatched make. |
| Riordan 2398.1 | Official is already signaling during the drive before the rim flight; two subsequent detected FTs at 2419.6 and 2437.7. | `fouled` becomes FG and adds an unmatched make. |

The general distinction suggested by the film is **event ordering and award
semantics**: an allowed continuous shooting action followed by a stoppage versus
an already-dead-ball release, a waived basket, or a rebound mistaken for a net
exit. Neither a net descent nor "a foul happened" answers whether points count.
The current cached tracks provide referee boxes, not referee gesture/award
labels or whistle-to-release timing. The 886.8 candidate's `shooter_track` is
3758 versus 3820 for its following FT; at 1208.6 these IDs are 4808 versus 4975.
Thus the cached IDs alone do not establish shooter continuity across the pause.

Available numeric features do not supply a defensible substitute. The positives'
existing pre-shot motion values are **0.226873** and **0.390710** body heights/s;
other retained/promoted negatives span **0.258299–0.451419**. Their one-second
pre-shot motion values (**0.301115**, **0.514847**) also lie within the negative
range (**0.182784–0.606040**). Trajectory evidence counts **4** and **3** overlap
negative counts **2–4**. Both positives and several negatives have no camera
departure within 15 seconds. Moving any of these cutoffs would fit these two
development events, not establish the causal distinction.

The following isolated FT is a useful **research hypothesis**, not a shipped
exception: both positives have `ft_pair=False`. That flag means no partner was
detected, not that a complete one-shot award was observed. A missed/occluded
second FT, a different shooter, a separate foul, or a technical award could
produce the same record. Two counterexamples also show that merely requiring
nearby FTs would admit existing fouled misses. No threshold was selected against
final scores, and no isolated-FT exception was implemented.

### Exact replay and rejected ablation

All rows below use both complete cached v4 fixtures with film-based 2/3-point
classification disabled and the same truth/matching rules. "Remove veto" is a
private, in-memory ablation of `shots.dead_ball_make` **before** `shot_split`,
never a production edit.

| Fixture / engine | Matched scores | Unmatched makes | Event precision | Event recall |
| --- | ---: | ---: | ---: | ---: |
| Mitty frozen before / unchanged after | 43/53 | 7 | 86.0000% | 81.1321% |
| Riordan frozen before / unchanged after | 52/61 | 7 | 88.1356% | 85.2459% |
| Mitty remove veto, rejected | 43/53 | 11 | 79.6296% | 81.1321% |
| Riordan remove veto, rejected | 54/61 | 14 | 79.4118% | 88.5246% |

The ablation gains exactly the two Riordan scoring-event matches and adds
**eleven unmatched makes** across the games. All eleven newly unmatched
predictions were inspected in the sheets above. It changes 11 Mitty and 11
Riordan raw prediction records; seven Mitty and two Riordan changes remain
excluded dead-ball/warmup records. This is not the older audit's 43/10 and 53/13
counterfactual, which used the pre-putback baseline. For comparison, restoring
the current vetoed makes only after classification gives 43/10 and 54/13;
that is not equivalent to removing the rule upstream. The present fully rerun
pipeline exposes an additional `fouled` → FG false prediction in each game.

Before/after production reports have identical predictions, event associations,
false-make lists, metrics, input fingerprints, and source fingerprints. There
are **zero changed false/missed predictions**, zero scoring-event gain, and no
new synthetic tests because there is no rule change. Existing focused tests
pass **26/26**, including putback separation and made-basket non-splitting.
No focused test or evaluation command failed; the blanket-removal experiment
fails the accuracy objective and is rejected.

Reproduction commands, run from the repository root:

```sh
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_makes.py -v
ml/.venv/bin/python ml/tools/makes_eval.py --games mitty,riordan --no-film --list --report-json ml/data/labels/points_accuracy_2026_11_12/after-report.json
ml/.venv/bin/python ml/data/labels/points_accuracy_2026_11_12/inspect_vetoes.py
```

This result does **not** measure total-point, 3PT, shooter/player, or complete
FG/FT classification accuracy. The existing Riordan +1 at 2512.8 remains matched
to an FG prediction. Both games are development fixtures, not true holdouts;
there is no demonstrated real-game generalization or reduction in coach work
from this unchanged engine.

### Concrete next data/model need

Build an offline, expert-labeled bounded event-sequence set, starting with these
13 clips plus previously unmatched makes, then expand to additional games
before training or choosing thresholds. Label physical make/miss separately
from allowed/waived scoring, release/contact/stoppage timing, visible referee
award/cancel gestures, and complete one-/two-/three-FT sequences with shooter
continuity. Use existing referee crops plus the court context; extract aligned
local audio only if whistle timing is actually recoverable and independently
checked. Explicitly label visibility/occlusion rather than treating a missing
gesture or second FT as negative evidence. Scoreboard labels may adjudicate
evaluation outcomes but must be excluded from all runtime features/crops used
to train the event classifier.

A temporal referee/action/award classifier with reliable ball/shooter
continuity is the needed missing capability, not another slow-player/no-pan
cutoff. Validate on an untouched, independently labeled game and measure both
recovered allowed baskets and newly admitted waived/missed baskets, followed by
FG/FT/3PT/player/point accuracy and actual coach-workload measurement. This is
offline development labeling, **not mandatory coach review of uploaded games**.
