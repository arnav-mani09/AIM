# Isolated assist sequence experiment

This is **not wired into possession.py, worker output, or the site**. Assists must
remain hidden. Mitty and Riordan are both development games. There is no untouched
test claim and no measured accuracy improvement. No Hudl totals supply labels.

## Files and integration

- `ml/tools/assist_sequences.py`: standard-library-only reusable detector.
- `ml/tools/assist_identity.py`: time-local pixel/hold adapter and non-certifying
  shooter/holder observation diagnostics. It does not infer player aliases.
- `ml/tools/assist_eval.py`: cache adapter, baseline comparison, blank film-review
  templates and event-level evaluation. Importing the detector does not import
  possession; only the optional cache adapter lazily imports it.
- `ml/tools/test_assists.py`: synthetic positive/negative sequence and scorer
  regressions. Synthetic cases are not film truth.
- Local, gitignored `ml/data/labels/assist_{mitty,riordan}_candidates.json` and
  `assist_{mitty,riordan}_annotations.json`: predictions and independent unreviewed
  labels for every **predicted** made field goal, including non-candidates.
- `ml/data/labels/assist_review_notes.json` and three `assist_*_review.jpg` sheets:
  limited, uncertain-only inspection notes. These are not scored ground truth.

The parent can import `AssistConfig, detect_assists` from `assist_sequences` using
the existing tools import path. Call:

```python
result = detect_assists(split, quick_runs, observations, config=AssistConfig(), identity_map={})
candidate_events = result["events"]
decisions = result["decisions"]
```

Preserve **all** two-frame runs, including unknown-team and referee holds. Each
needs `tid, t0, t1, first, last, team, sure` and optional `ref, contested, n`.
Team `sure=True` is model evidence, not verified team identity. A missing certainty
flag causes abstention. Observations have `t`, `ball: [x,y] | None`, and `players:
[{tid, box: [x0,y0,x1,y1]}]` in the same pixel space. The cache adapter supplies
these using existing ball/player selection. Optional identity_map maps track IDs
to independently established canonical identities; aliased passer/shooter tracks
are rejected. It does not authorize inferred jersey numbers.

Output retains `type='ast', team, t, shot_t, passer_track, shooter_track, track`.
Extra fields explicitly mark `review_status='unreviewed'`,
`identity_status='track_only_unverified'`, `player=None`, `player_conf=0`.
No calibrated event confidence is asserted. Do not let downstream attribution
turn these candidates into certified player statistics. Parent review, labeled
validation and an explicit integration decision are required before any wiring.

## Sequence rules

Require an actual matching shooter hold before a predicted made FG; no fallback
to a nearby teammate. Merge adjacent same-ID holds to avoid resetting a drive's
clock/travel at every tracking dropout. Require the immediately preceding holder
to be a certain teammate, with a distinct non-aliased ID. Unknown, opposing and
referee holds cannot be filtered out to invent a direct pass.

Bound pass flight (0.15–1.5s), catch-to-rim time (2.5s), release-to-rim time
(1.8s), shooter hold (1.5s) and endpoint/fragment travel (0.8 body heights).
Reject any intervening shot, including missed shots preceding a rebound/putback.
Require at least two intermediate ball observations outside both co-visible
players' boxes, at least one body-height separation, monotone progress from the
passer's side to the receiver's side, and no observation gap over 0.35s. Progress
uses simultaneous player coordinates, reducing simple shared camera-pan effects.
Short transfers and nearby handoffs are deliberately excluded, even though some
real scoring conventions might credit an assist. Thresholds are conservative,
untuned heuristics rather than a general basketball assist definition.

## Observations, not accuracy

Initial cache replay, before the time-local identity adapter, produced:

- Mitty: 35 predicted made-FG opportunities; current recomputed baseline 7
  candidates (Valley 2, Opponent 5), bounded detector 0.
- Riordan: 38 predicted made-FG opportunities; baseline 12 (Valley 4, Opponent 8),
  bounded detector 1 (Opponent, pass 4420.3s, catch 4421.1s, shot 4422.8s).

The older serialized Mitty `.possession.json` contains 8 assists (2/6), not the 7
from replaying current code and caches. Treat it as stale, not equivalent evidence.
The command outputs are authoritative for each replay; another agent owns the
shared possession code and may change it. Both teams and identities remain model
predictions. Candidate reduction is **not** evidence of improved precision.

There are **0 independently adjudicated assist/no-assist film labels**. All 73
annotation-template rows are unreviewed; limited contact-sheet inspections of
Mitty 248–255s, Riordan 854–862s and 4417–4425s remain uncertain. Precision, recall
and labeled accuracy are therefore undefined (`null`), not zero or 100%.
The sheets use 3fps, six columns, chronological row-major order; the final Mitty
row has blank cells because that extract is only seven seconds.

## Reproduction

Focused regressions:

```sh
ml/.venv/bin/python -m unittest discover -s ml/tools -p 'test_assists.py' -v
```

Latest result: **49 tests passed** using `-p 'test_assist*.py'` to include the
new identity adapter regressions. This validates synthetic failure cases
and evaluation bookkeeping, not film-level accuracy.

Initial cache-only export commands (existing output files are never overwritten):

```sh
ml/.venv/bin/python ml/tools/assist_eval.py --tracks ml/data/tracks/valley-vs-archbishop-mitty.v4.json --game valley-vs-archbishop-mitty --out ml/data/labels/assist_mitty_candidates.json --template ml/data/labels/assist_mitty_annotations.json
ml/.venv/bin/python ml/tools/assist_eval.py --tracks ml/data/tracks/valley-vs-archbishop-riordan.v4.json --game valley-vs-archbishop-riordan --out ml/data/labels/assist_riordan_candidates.json --template ml/data/labels/assist_riordan_annotations.json
```

Re-run current code against caches without modifying earlier export files:

```sh
ml/.venv/bin/python ml/tools/assist_eval.py --tracks ml/data/tracks/valley-vs-archbishop-mitty.v4.json --game valley-vs-archbishop-mitty
ml/.venv/bin/python ml/tools/assist_eval.py --tracks ml/data/tracks/valley-vs-archbishop-riordan.v4.json --game valley-vs-archbishop-riordan
```

Evaluate saved predictions only against independently completed templates:

```sh
ml/.venv/bin/python ml/tools/assist_eval.py --predictions ml/data/labels/assist_mitty_candidates.json --annotations ml/data/labels/assist_mitty_annotations.json
ml/.venv/bin/python ml/tools/assist_eval.py --predictions ml/data/labels/assist_riordan_candidates.json --annotations ml/data/labels/assist_riordan_annotations.json
```

Labels: `assist`, `no_assist`, `uncertain`, `unreviewed`. Scored labels need a known
team, reviewer, film evidence path/time span and notes. Confirm the made FG and
team first; otherwise use `uncertain`. Optional track attribution must be reviewed
independently and is scored separately from binary assist detection. Duplicate or
ambiguous shot matches fail rather than silently inflate metrics. Predictions
outside reviewed opportunities are reported as unscored, never automatic false
positives. Recall is conditional on labeled predicted made-FG opportunities, not
game-level assist recall; missing made shots are outside this evaluation.

Bounded sheet extraction used existing ffmpeg, e.g.:

```sh
ffmpeg -hide_banner -loglevel error -ss 4417 -i 'backend/sample_data/Valley Christian vs Archbishop Riordan - Tactical.mp4' -t 8 -vf 'fps=3,scale=480:-1,tile=6x4' -frames:v 1 -update 1 ml/data/labels/assist_riordan_4423_review.jpg
```

## Open questions and limitations

Moving-film review clips are available locally under
`ml/data/labels/assist_review_clips/`: `mitty_247_257.mp4`,
`riordan_853_864.mp4`, and `riordan_4416_4427.mp4`. Their filenames give
original-film start/end times in seconds; clip time zero is the start time.
These silent, 960-pixel-wide excerpts are review aids, not adjudicated labels.
Use the original film when the reduced resolution obscures control or identity.

Human moving-film review must establish positive and negative examples, including
non-candidates, with agreed assist-credit rules for short drives and handoffs.
Explicit shooter IDs are frequently missing/mismatched; this conservative detector
abstains instead of guessing. Track-ID alias maps and jersey/team identity still
need independent evidence. Pixel votes can remain confidently wrong. Rebounds
whose preceding shot was missed by the shot detector can still masquerade as
passes. Ball detections can follow unrelated objects. Shooter travel is based on
hold endpoints/fragments, can miss an out-and-back within one hold, and is not
camera-compensated; camera motion can cause extra abstentions. Sparse or occluded
flight creates false negatives by design. Candidate confidence is not calibrated.
These issues, plus zero reliable labels, preclude deployment or gain claims.

## November 12, 2026: identity/observation investigation

This remains an isolated, hidden experiment. Development review belongs to the
implementation team; the 73 blank opportunities are **not a coach labeling task**.
There are still zero independently adjudicated assist/no-assist examples. Four
additional local image sequences were inspected by the implementation agent for
identity failure modes only, not scored assist truth. Existing templates and
review artifacts were not overwritten. The new templates also remain unreviewed.

### Root causes and bounded change

The original adapter let any sustained, certain hold certify **every** two-frame
hold with that track ID, regardless of time. `label_holders` also replaces local
pixel team/certainty with track-wide voting. This is unsafe when an ID switches
from one person to another. The adapter now recovers each sustained hold's own
pixel vote using the existing possession thresholds (vote 0.2, sure 0.5, pixel
share 0.15), and requires a same-track sustained interval covering the entire
quick hold. Conflicting overlapping evidence, partial overlap, missing pixels,
and local referee evidence cannot certify a hold. A track-only team fallback is
retained for diagnostics but is always uncertain. All unknown/intervening quick
holds remain in the sequence. This is a correctness fix to evidence scope, not
a calibrated improvement in team or assist accuracy.

The detector adds `shooter_hold_observation`: actual hold ID/interval, timing to
shot, local team/certainty/referee/contestation, image-space travel, and whether
the two IDs appear separated by more than one body height in simultaneous
observations. These are explicitly **not identity truth**. No newer/nearer
teammate replaces `split.shooter_track`, and no pass, travel or flight threshold
is loosened. Existing `identity_map` remains an externally supplied **exclusion**
guard against crediting a same-player pass. It does not promote a mismatched
shooter or establish an alias. No new real-film aliases were accepted: none of
the four reviewed sequences supports a safe, whole-track canonical identity.
If future review establishes fragments, aliases must be game/time scoped, reject
overlapping contradictory people, and preserve the source track/visual evidence;
a global union of these observed IDs would be wrong.

`split.shooter_track` and hold runs do not observe the same event. `shot_split`
walks backward from rim-zone time through upper-body ball contacts, including a
single frame; possession holds require at least two frames with lower/chest-to-
feet ball contact. Thus missing shooter holds can reflect a release/dribble
observation gap or a defender winning the box test, not a real pass or a known
same-player track fragment. A shot's `t` is not the release or `make_t`.

### Actual local identity review

Frozen sheets are in `ml/data/labels/assist_identity_20261112/`. Each contains six
original-film frames in chronological row-major order, two columns, cropped from
1920x1080 coordinates `[300:1700,160:760]`, resized to 840x360 per tile. Red is the
split shooter ID, green the last quick-holder ID, yellow detected ball boxes
(not verified ball truth). Identity means visual continuity only; no jersey
number, roster person, assist credit, or made-shot truth was adjudicated.

- **Mitty 253.1s**, IDs **964/961**, last hold **252.0–252.3s**, inspected
  **251.2,252.0,252.2,252.4,252.7,253.1s** (`mitty_251.2_identity.jpg`):
  ID 964 initially boxes a blue defender, then boxes a white player after the
  overlap. ID 961 had boxed a white player. A local same-player fragment is
  possible after the overlap, but whole-track equivalence is contradicted by
  the earlier distinct people. **No alias accepted; assist unreviewed.**
- **Mitty 1150.7s**, IDs **3767/3805**, last hold **1148.7–1148.9s** (same-ID
  fragments begin 1147.6s), inspected **1147.0,1148.0,1148.8,1149.4,1149.9,1150.5s**
  (`mitty_1147.0_identity.jpg`): both IDs initially box separate blue players;
  later red boxes a white defender, and green also boxes a white player.
  This is cross-player identity contamination, not defensible global aliasing.
  **No alias accepted; assist unreviewed.**
- **Riordan 3613.3s**, IDs **11127/11120**, last hold **3611.9–3612.3s**, inspected
  **3611.9,3612.3,3612.6,3612.9,3613.2,3613.4s** (`riordan_3611.9_identity.jpg`):
  green follows a white ball carrier into traffic, then boxes a blue defender;
  red appears on a white player near the basket. A fragmented carrier track is
  plausible but the overlap obscures continuity. Lack of separated co-visibility
  before shot time is **not evidence of sameness**. **No alias accepted; assist
  unreviewed.**
- **Riordan 5496.8s**, IDs **17531/17522**, last hold **5495.8–5496.1s**, inspected
  **5494.8,5495.2,5495.6,5496.0,5496.4,5496.8s** (`riordan_5494.8_identity.jpg`):
  red starts on a blue ball carrier, green on a white defender; later red boxes
  a white player while green boxes blue. This contradicts a stable whole-track
  identity for either. **No alias accepted; assist unreviewed.**

Reviewed outcome: **0 confirmed safe same-player aliases**, four sequences with
contradictory cross-player tracking, and possible but unresolved temporal
fragmentation in two. These findings cannot identify the actual assist passer
or establish player-level precision. Frame inspection is narrower than a full
moving-film adjudication and does not turn uncertain identity into a label.

Motion is also camera-sensitive. During Mitty 1147.6–1148.9s the cached rim center
moves **95.0 pixels left**, while track 3805's box center moves **79.0 pixels left**.
Subtracting that one rim's motion would reverse the horizontal displacement to
16.0 pixels right. This demonstrates image-space travel is not court travel;
it does not justify automatic camera compensation (depth, zoom, track switches
and occlusion remain). Travel gating is unchanged. Simultaneous flight geometry
and the new separated-track diagnostic are invariant to shared image translation,
but neither repairs identity switches.

### Frozen replay results, not accuracy

Every reason is an ordered first-abstention gate; changing local team evidence can
change run merging and which gate fires without changing a candidate or its truth.

| Reason | Mitty before | Mitty after | Riordan before | Riordan after |
| --- | ---: | ---: | ---: | ---: |
| shooter_hold_mismatch | 13 | 13 | 17 | 17 |
| uncertain_shooter_hold | 12 | 14 | 11 | 14 |
| unknown_shooter_or_team | 3 | 3 | 1 | 1 |
| no_shooter_hold | 2 | 2 | 1 | 1 |
| no_preceding_hold | 2 | 1 | 0 | 0 |
| same_player_or_track_switch | 1 | 2 | 1 | 0 |
| intervening_or_uncertain_holder | 1 | 0 | 1 | 2 |
| drive_or_stale_catch | 1 | 0 | 4 | 1 |
| handoff_overlap_or_long_gap | 0 | 0 | 1 | 1 |
| bounded_pass_catch_make (candidate) | 0 | 0 | 1 | 1 |
| Total predicted made-FG opportunities | 35 | 35 | 38 | 38 |

Baseline events are byte-for-byte equal as parsed JSON before/after: **7 Mitty,
12 Riordan**. They use the old track-wide adapter inputs intentionally, not the
new bounded inputs. Bounded candidates remain **0/1**, including the same
unverified Riordan 4422.8s opportunity. No accuracy gain is claimed. Among all
quick holds, **999/1986 Mitty** and **1108/2399 Riordan** change at least one
team/certainty/referee field; old global certainty is removed from **727/799**
respectively. This measures evidence handling, not correct team assignments.
Mismatch diagnostics: Mitty **6 separated-co-visible / 7 unresolved**, Riordan
**5 / 12**. These are geometric buckets, not verified distinct/same people.

All changed first-gate outcomes are saved in `summary.json`: Mitty shot times
3887.0,4052.61,4244.3; Riordan 866.35,2266.0,2510.6,4809.4,5082.5,5544.4.
Evaluation still has **0 reviewed opportunities**, **0 attribution checks**, and
precision/recall/accuracy **null**, with **35/38 unreviewed** template rows.

### Versions and reproduction

Frozen `*_before.json`, `*_manifest.json` contain original results/runs/splits,
source hashes and UTC mtimes. `*_frozen_replay.json` contains complete adapted
runs, split and observations limited to each made-FG's four-second decision
window. Replaying these compact observations was asserted identical to the
full cached observations. Original adapter/detector/dependency source snapshots
and `after_*.py` are preserved beside them. `*_after.json` are CLI exports,
`*_annotations.json` remain blank. Do not overwrite any of these artifacts.

Both track files identify model **aim-yolox-m-v4**, tracking schema **1**, **10fps**,
**1920x1080**. Track SHA-256: Mitty
`0994d981e6b5247ed58ca0a091ec1dafdd02d356071938e4526f3de34d19926a`,
Riordan `cd2f1a8226ae71f7c72329433a1e19937717ff660b23b985a45e829e21504a7c`.
Split SHA-256: Mitty
`08d3679a50b225ec9cfcdc7ca0bf26403fcb4cc43ef28323db6540019a6dd328`,
Riordan `5a06091fc45ee09dc836939f1b44bec51c794f7dc4bf3022744b705ef8c22684`.
The split mtimes are **November 11, 2026, 08:33:06 / 08:33:37 UTC**, older than
the current `shots.py` at **November 12, 2026, 07:40:22 UTC**, SHA-256
`609fb49ff2923cbd599fb690255b2b8db79cc1605c1fe6bcd21faa40756ef0d9`.
Current shots source contains the quick-putback reopening fix; these cached
splits cannot be asserted to include it. No shot refresh or inference was run.
Treat the 35/38 opportunities as conditional on potentially stale shot inputs,
not the latest detector's opportunity set. Mtime ordering is a warning, not proof
of which source generated a cache. New CLI exports fingerprint all sources and
inputs before/after adaptation and fail if they change mid-replay.

Exact validation/export commands run (existing exports are immutable):

```sh
ml/.venv/bin/python -m unittest discover -s ml/tools -p 'test_assist*.py' -v
ml/.venv/bin/python ml/tools/assist_eval.py --tracks ml/data/tracks/valley-vs-archbishop-mitty.v4.json --game valley-vs-archbishop-mitty --out ml/data/labels/assist_identity_20261112/mitty_after.json --template ml/data/labels/assist_identity_20261112/mitty_annotations.json
ml/.venv/bin/python ml/tools/assist_eval.py --tracks ml/data/tracks/valley-vs-archbishop-riordan.v4.json --game valley-vs-archbishop-riordan --out ml/data/labels/assist_identity_20261112/riordan_after.json --template ml/data/labels/assist_identity_20261112/riordan_annotations.json
ml/.venv/bin/python ml/tools/assist_eval.py --tracks ml/data/tracks/valley-vs-archbishop-mitty.v4.json --game valley-vs-archbishop-mitty --out ml/data/labels/assist_identity_20261112/mitty_final.json
ml/.venv/bin/python ml/tools/assist_eval.py --tracks ml/data/tracks/valley-vs-archbishop-riordan.v4.json --game valley-vs-archbishop-riordan --out ml/data/labels/assist_identity_20261112/riordan_final.json
ml/.venv/bin/python ml/tools/assist_eval.py --predictions ml/data/labels/assist_identity_20261112/mitty_after.json --annotations ml/data/labels/assist_identity_20261112/mitty_annotations.json
ml/.venv/bin/python ml/tools/assist_eval.py --predictions ml/data/labels/assist_identity_20261112/riordan_after.json --annotations ml/data/labels/assist_identity_20261112/riordan_annotations.json
```

The diagnostic additions are frozen in `*_frozen_replay.json`; final CLI exports
include the expanded source/config provenance (`games.yaml`, `track_teams.py`),
and match those frozen decisions. Final source snapshots and tests use `final_*`
filenames. Earlier exports intentionally remain untouched. To verify frozen outputs
without invoking possession, model inference, or rewriting artifacts:

```sh
PYTHONPATH=ml/tools ml/.venv/bin/python - <<'PY'
import json
from pathlib import Path
from assist_sequences import detect_assists
for game in ('mitty', 'riordan'):
    path = Path('ml/data/labels/assist_identity_20261112') / f'{game}_frozen_replay.json'
    frozen = json.loads(path.read_text())
    replay = detect_assists(frozen['split'], frozen['runs'], frozen['observations'])
    assert json.loads(json.dumps(replay)) == frozen['result']
    print(game, 'frozen replay matches')
PY
```

Remaining work is a temporally trained release/control/identity model with
camera/occlusion-aware features and development-owned training examples for
track switches, true fragments, passes, dribbles, rebounds and putbacks. Build
small independently adjudicated assist/no-assist and time-scoped identity sets,
then validate on untouched games. These four sampled sequences do not suffice
to train or calibrate that model. Do not wire this experiment into
`possession.assists_v2`, production player attribution, worker output or the UI
without actual assist labels, validated identity continuity and an explicit
integration decision. Coach review is not a prerequisite for developing these
labels; do not transfer the current 73-example backlog to coaches.

## Blind-review dependency warning — November 12, 2026

After blind observations were frozen, parent cross-checking identified a likely
false upstream make underlying the sole strict Riordan candidate at shot time
4422.8 seconds. Observation `R4415-F3` shows rim rejection at 4422.7–4423.4;
`R4415-F4/F5` distinguish contested touches from later blue control. These are
model-reviewed provisional observations, not human-adjudicated assist labels.
The current-source scoring report also calls the shot made, so this is not
explained solely by stale assist caches. Do not count this candidate as a true
assist, infer an official rebounder, or modify frozen predictions to conceal the
discrepancy. See `blind_review_crosscheck.md` for provenance and limitations.
