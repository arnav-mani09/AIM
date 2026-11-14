# Riordan rim rejection → make → assist: bounded diagnostic

Date: November 12, 2026 (America/Los_Angeles). Development investigation only.
The frozen reviewer is a model, **not an independent human adjudicator**.
R4415-F3's rejection is a provisional interpretation, not evaluation ground truth.

## Concrete causal result

The current `ml/tools/shots.py` SHA-256 is
`609fb49ff2923cbd599fb690255b2b8db79cc1605c1fe6bcd21faa40756ef0d9`,
matching the points report and assist experiment provenance. Replaying the
unchanged Riordan v4 cache reproduces `t=4422.8, made=true, make_t=4423.1,
evidence=2, confidence=0.87`. This is the **primary under-net branch** of
`decide()`, NOT rescue interpolation, the lost-ball gap fallback, or the
net-disappearance fallback. The attempt is not rescued. `dead_ball_make()` does
not veto it; the final `find_shots()` output remains made.

The rule treats a ball center falling below a rim bounding box near its center
as a net exit. It has **no observation of aperture traversal, net interior,
front/back depth, or actual rim contact**. A ball traveling beside/outside the net
can project into this same accepted corridor. Conditional on the provisional
rejection being confirmed, this is an outcome-evidence/decision-rule false
positive: projected proximity is being promoted to physical net-through.
It is not an identified detector dropout at the decisive samples. The cache
alone cannot determine whether the provisional rejection interpretation is
correct, or establish a particular detector localization error.

### Exact accepted evidence

Coordinates below come from the actual main-pass path, not a hand-built replay.
`x` is ball-center offset in rim widths; `y` is height below rim top in rim-box
heights. These are image coordinates, not court/depth coordinates.

| Source seconds | Ball center px | Rim box px | x | y |
|---|---|---|---:|---:|
| 4422.8 | 1382, 114.55 | 1293.1,182.9,1356.9,211.1 | .8934 | -2.4238 |
| 4422.9 | 1368, 161.85 | 1294.7,184.6,1355.3,210.9 | .7096 | -.8650 |
| 4423.0 | 1353, 217.50 | 1296.2,186.6,1355.8,214.2 | .4530 | 1.1196 |
| 4423.1 | 1337, 278.50 | 1291.3,187.0,1356.7,216.8 | .1988 | 3.0705 |
| 4423.2 | 1324, 342.00 | 1289.9,190.1,1352.1,216.9 | .0482 | 5.6679 |

At the first `y >= UNDER_NET (1.6)`, 4423.1:

- Last above-rim sample is 4422.9: `abs(x)=.7096 <= OVER_RIM_X=1.0`.
- Drop time is .2 s, within `DROP_TIME=1.5`; exit `y=3.0705 <= 5.5`.
- The sole intervening point, 4423.0, has `abs(x)=.4530 <= SIDE_X=.6`.
- Exit `abs(x)=.1988 <= NET_EXIT_X=.35`.
- No retained later point within .4 s returns to `y < .3`.
- Only 4423.2 is retained within .3 s for drift; its x displacement is .1506,
  below `EXIT_DRIFT=.6`. The 4423.6 detection is too late for that guard.
- `evidence=2` is this exit plus one later horizontally nearby observation,
  **not two independently observed net/aperture crossings**. That later point's
  `y=5.6679` is not required to satisfy the exit vertical limit.

The computed confidence is the rounded detection-score/evidence heuristic
`.5*.856 + .3*.804 + .2*1 = .8692`, not calibrated outcome confidence.

### Demonstrated sampling-phase vulnerability (synthetic probe only)

At 4423.0 the ball is still classified as not under-net (`y=1.1196`) and is
sideways at `x=.4530`. One 10 Hz step later it is already much deeper below
the net (`y=3.0705`) and has moved inward to `x=.1988`. Thus the rule checks
centering late, not at the physical aperture or even the `y=1.6` crossing.

As an explicitly **synthetic, unobserved sensitivity test**, insert just one
linear interpolation of all seven raw path coordinates, one third of the way
from 4423.0 to 4423.1. That yields 4423.033333, `x=.36295, y=1.80353`.
With unchanged production constants, this earlier first-under-net point fails
`.35` centering and the entire decision becomes **no make**. The loop breaks
after the first under-net sample, so the later centered sample is not retried.
The exact-coordinate regression test checks both results. This is not a new
ball detection, evidence of actual contact/rejection, or a production fix;
it isolates a concrete sample-phase dependency that the targeted source-rate
experiment must test. Interpolating a ball at rim contact is not physical truth.

## Detector observations versus decision failure

The raw cache has exactly one ball and one rim on every decisive frame
4422.8–4423.2. Ball scores are .856, .884, .857, .784, .854;
rim scores are .804, .814, .563, .794, .812. Every box passes the relevant
confidence filters. The chosen ball centers match those raw boxes exactly.
There is no rescue-generated above-rim point and no alternative ball selected
over another detection in these frames. The rim moves only a few pixels;
its x center is 1325 at 4422.8 and 1324 at 4423.1. This is not a lost-rim hold
or a large panning-coordinate error at the crossing.

There ARE missing ball detections at 4423.3–4423.5 and again at
4423.9–4424.1, while rims remain detected. The first gap leaves only one
observed post-exit point for the short drift/pop guard. Thus negative evidence
is sparse; the implementation treats absence of a contradictory detection as
absence of a contradiction. However, the positive make predicate has already
been satisfied with consecutive real boxes. A missing observation does not
trigger the make fallback in this case. Later upward motion at 4423.6–4423.8
remains below the rim-top cutoff, and can also occur after collection/touch
following a real make; it is not automatically a rejection signature.

The frozen source-rate sheet was inspected along with individual frames 10,
13 and 16. It shows a close right-side rim/net interaction and subsequent
descent toward players, but ball centers against a broad rim box cannot
certify which side of the aperture/net the ball traversed. Do not convert
this non-blind second model inspection into human confirmation, or assume
the frozen description's “rebounds to the right” implies a measured rightward
reversal in screen x: cached x actually decreases through the accepted crossing.

## Bounded positive controls, selected without totals

Controls are the other frozen review's local make observations, selected by
physical finish evidence rather than game totals, score-matching success, or
the detector's answer. They remain provisional; physical net-through is not
necessarily a counted/live basket. Three source-rate positive sheets (Mitty
254.1–254.7 and 1016.1–1016.9, Riordan 866.2–866.9) were also inspected.
The remaining two controls rely on the frozen local visual/score sequence,
not on matching game totals.

| Frozen observation | Attempt t | Rule exit t | Current branch/result | Local contrast |
|---|---:|---:|---|---|
| M240-F3 | 253.1 | 254.5 | Primary / make | Rim rattle, central exit x=-.0826, y=2.1856; intermediate detection gaps |
| M995-F3 | 1015.6 | none | No make | Physical net-through in burst, but drift rejects first under-net point at 1016.6 |
| R850-F6 | 866.35 | 866.7 | Primary / make | Rescued start includes synthetic 866.45 point; exit x=.3289, y=1.8239 |
| R3605-F2 | 3613.3 | 3613.7 | Primary / make | .4 s gap from above to exit x=.0146, y=3.0339; no aperture sample |
| M1138-F3 | 1150.7 | 1151.3 | Primary / make | .5 s gap before exit x=-.0716, y=2.0308 |

M995-F3 is particularly important: its first under-net point at 1016.6 has
x=.2419, y=2.4709, but x reaches 1.0215 at 1016.8, a .7796-width displacement
in .2 s. `no_exit_drift` fails. The source burst shows net-through before a
player's collection. The rule does not distinguish ball motion after an exit
from collection/handling. This is a second local rule limitation, not a request
to fix another event. R850-F6's accepted exit is already close to the .35
boundary. Tightening horizontal or missing-observation gates to reject this
one negative could reject real positives; no thresholds were tuned.

## Cascading dependency and different time anchors

The points report puts the 4422.8 attempt in `false_makes`. That report bucket
means unmatched to its score-change matching procedure; it is not by itself
frame-level proof of a rim rejection. The independent provisional film
observation provides the separate disagreement being investigated.

The strict isolated assist experiment's `riordan_final.json` has exactly one
event: `t=4420.3, catch_t=4421.1, shot_t=4422.8`, tracks 13513 → 13470, reason
`bounded_pass_catch_make`. It remains unreviewed, track-only/unverified.
Its provenance explicitly says `unverified_cached_split_not_recomputed` and
that the split predates current shot source. Current replay independently
reproduces this same made call, so stale split provenance does not explain
away the scoring failure. If human review confirms a miss, this assist
candidate loses its make prerequisite; that does not disprove the visible
pass/catch or establish player identity. No assist output was changed.

All are source-file seconds, but not the same event anchor:
4420.3 is inferred pass, 4421.1 catch, frozen release range 4421.4–4422.0,
4422.8 detector above-rim zone entry (NOT release), 4423.1 inferred exit,
and frozen rejection range 4422.7–4423.4. The overlapping ranges are not a
timestamp disagreement. Source-rate burst labels are nominal start+index/30,
with the frozen review's conservative ±.1 s extraction allowance; they are not
verified decoder PTS alignment against cached inference frames.

## Minimum experiment needed, not executed

Do NOT rerun the full film, alter thresholds, or add a timestamp rule.
The cache cannot distinguish physical net-through from this projected descent.

1. Extract only Riordan **4422.7–4423.9** at source rate (about 36–37 frames),
   preserving actual source PTS/frame indices. Retain full frame for inference;
   inspect a native-resolution rim/net/ball crop, not a rescaled detector input.
2. Run the **same existing cached-v4 detector configuration and identified
   checkpoint** on these frames, recording all ball/rim boxes and raw scores,
   including below-filter detections. Verify actual cache generation settings
   first: the cache's `model=aim-yolox-m-v4, fps=10` does not itself pin checkpoint
   bytes or inference resolution. Do not assume current local v4 weights equal
   historical cached weights. No checkpoint download/training is warranted.
3. Overlay at the exact original frame PTS, compare the 10 Hz cache on matching
   decoded frames, and have an independent human mark aperture entry, net-side
   passage, rejection/contact if visible, and the first player touch. This
   separates sampling/localization errors from correctly detected but
   non-discriminating 2-D geometry. Explicitly record occluded/unknown frames.
4. Use one tiny positive control, Riordan **866.4–866.9** (about 15–16 frames),
   with unchanged settings and the same aperture/net annotation protocol.
   Denser same-angle boxes may still be non-identifying: then abstain and
   request human/alternate-angle evidence, not more full-film inference.

## Reproduction and artifacts

`ml/tools/rim_outcome_audit.py` reads existing caches, temporarily wraps
`shots.decide` in-process to retain selected actual paths, and restores the
function afterward. It replays full cached context (not full-film inference)
so rescue state, global rim filtering, and dead-ball veto indexing are intact.
Only six bounded cases and their raw ball/rim frames are written to the new
private `ml/data/labels/rim_outcome_audit_20261112/audit.json`. Input hashes,
frozen observations, all rule checks, final results and assist dependency are
included. It refuses to overwrite an existing private audit directory.

```sh
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_rim_outcome_audit.py -v
ml/.venv/bin/python ml/tools/rim_outcome_audit.py
```

The diagnostic's branch explanation mirrors current predicates for inspection,
not a new inference or production policy. Its exact numerical regression test
records the current disputed acceptance, not a ground-truth label.
Validation: eight new diagnostic tests and all 26 existing `test_makes.py`
tests pass. The production `shots.py` hash remains unchanged.
No production, shared inference, datasets, checkpoints, frozen evidence or
existing edits were modified. No network, installations, paid calls, video
inference, commits or deployment were used.
