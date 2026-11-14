# Whole-cache rim second-pass coverage and demand

Measured November 12, 2026, America/Los_Angeles, using **both complete cached
games**, not the six curated paths. Research evidence only: no score-truth
input, source-film access/decoding, inference, network, installation, paid call,
runtime edit, production suppression, coach backlog, commit, or deployment.
No applicable root/ancestor or `ml/` AGENTS.md was present.

## Actual census

“Accepted make” below means the **final post-dead-ball-veto `find_shots` result**,
not an intermediate accepting `decide` call and not a physically certified make.
“Eligible game” means exactly the FG/FT emission cohort produced by
`makes_eval.run_pipeline(game, film=False)` and the existing worker kind filter.

| Game / cohort | Attempts | Final accepted makes | Triggered makes | Trigger / accepted |
|---|---:|---:|---:|---:|
| Mitty, complete cache | 237 | 69 | 9 | 13.04% |
| Riordan, complete cache | 183 | 64 | 17 | 26.56% |
| Both, complete cache | 420 | 133 | 26 | 19.55% |
| Mitty, eligible game | 121 | 50 | 6 | 12.00% |
| Riordan, eligible game | 142 | 59 | 16 | 27.12% |
| Both, eligible game | 263 | 109 | 22 | 20.18% |

| Game / all-cache category | Attempts | Accepted | Triggered |
|---|---:|---:|---:|
| Mitty FG | 93 | 32 | 5 |
| Mitty FT | 28 | 18 | 1 |
| Mitty unknown FG/FT context | 116 | 19 | 3 |
| Riordan FG | 105 | 33 | 8 |
| Riordan FT | 37 | 26 | 8 |
| Riordan unknown FG/FT context | 41 | 5 | 1 |

Eligible totals are **198 FG attempts / 65 accepted / 13 triggered**, and
**65 FT attempts / 44 accepted / 9 triggered**. “Unknown” is not silently called
an FG: it includes out-of-window and known excluded runtime labels, whose
counterfactual FG/FT type is not evaluated. All 24 unknown-category accepted
makes and their four triggers remain in the all-cache numbers only.

### Cohort mismatch is material

The existing cache-only game-window finder returns Mitty **236–5008 s**, halftime
2094–2674; Riordan **621–5612 s**, halftime 2811–3366. This census neither corrects
nor certifies those windows. Mitty drops 76 out-of-window, 25 warmup, 5 dead-ball,
and 10 fouled attempts; Riordan drops 16 out-of-window, 19 warmup, and 6 fouled
attempts. These sum to 116 and 41, respectively. Out-of-window attempts are absent
from the returned labeled list; warmup/dead-ball/fouled labels are returned but
not worker shot events. This is why counting all `run_pipeline` rows as game
FG/FTs would also be wrong.

Mitty's three extra triggers are out-of-window; Riordan's extra trigger is a
warmup. The **22/109 eligible result must not be represented as 26/133 game
coverage**. No film-based 2/3-point classification ran. Teams and FG/FT types are
current cache-only runtime assignments, not independently validated labels.

## Complete decision paths and final links

The new tool calls unchanged `shots.find_shots`, `rim_outcome_audit.explain`, and
`rim_context_eval.trigger`. Every `decide` invocation retains the full path,
rim-unit path, crossing, primary/gap predicates, accepted branch, observed-until
horizon, pre-veto output, and trigger result. A deep copy goes to `explain` with
the original decision function; the runtime call receives the original argument.
Both temporary wrappers restore exception-safely. Each final attempt links to
the **returned Python object identity**, not approximate time or “any make at
this time.” Retained references prevent object-ID recycling. Multiple links
would select the last call; a missing final trace fails the census rather than
becoming an untriggered/safe event. A distinct uninstrumented replay confirms
exact equality of both post-veto `find_shots` and complete labeled outputs.

| Trace accounting | Mitty | Riordan |
|---|---:|---:|
| `decide` calls | 238 | 183 |
| Accepting calls before final gating | 84 | 77 |
| Raw triggering calls | 12 | 19 |
| Calls not retained as final attempts | 1 | 0 |
| Pre-veto makes vetoed | 14 | 13 |
| Final accepted makes | 69 | 64 |
| Final triggered makes | 9 | 17 |
| Missing final traces / multiple identity links | 0 / 0 | 0 / 0 |
| Exact duplicate trace groups / duplicate final times | 0 / 0 | 0 / 0 |

Mitty trace 176 at **5362.40**, observed until 5363.7, accepts and triggers during
the returning-above-rim probe but is **not appended**. Trace 177, same attempt
time, observed until 5364.0 with an extended 12-point rather than 10-point path,
rejects and is the retained final event `mitty:cache:0176:t=5362.40`. Counting the
earlier call would invent an accepted make. This is a repeated main-pass probe,
not a second rescued shot. No rescue/main duplicate final event or exact
duplicate trace occurred; the links retain `rescued` provenance regardless.

Raw triggers also occur at Mitty 6136.20 and 6265.60 and Riordan 1980.20 and
2398.10, but the final dead-ball veto rejects all four. Thus **31 raw triggering
calls become 26 final triggers**, not 31 game makes. Riordan 1980.20 remains an
eligible FG **miss**, while 2398.10 is subsequently classified fouled.

Final context accounting: Mitty has 206 paths with observed previous/above
context and 31 without an under-net observation; Riordan has 155 and 28. No
final trace is missing, and no observed crossing lacks a previous/above point.
The no-under-net cohort includes one accepted Mitty net-disappearance event,
`mitty:cache:0168:t=5152.90` (make time 5153.4), outside the runtime window.
It cannot satisfy this first-under-net trigger. Absent context is explicitly
recorded, never inferred as safety.

## Exact trigger events and merged requests

IDs are census-local stable IDs, **not production database IDs**: prefix
`mitty:cache:` or `riordan:cache:`, then the four-digit final-attempt index and
`:t=` followed by the two-decimal attempt time below. The complete literal ID,
full-precision cached path, final output, and selected trace index are in each
game JSON. `accepted_makes.json` separately lists **all 133 final accepted
events**, including untriggered events, with exact IDs and attempt/make times.
Seconds here are cache timestamps, **not newly aligned source PTS**.

| Game | ID index | Attempt s | Make s | Category/cohort | Merged request s | Frame estimate |
|---|---|---:|---:|---|---|---:|
| Mitty | 0021 | 967.10 | 967.3 | FG eligible | 966.6–969.2 | 80 |
| Mitty | 0039 | 1396.50 | 1397.1 | FG eligible | 1396.0–1398.6 | 80 |
| Mitty | 0040 | 1498.90 | 1499.6 | FG eligible | 1498.4–1501.0 | 80 |
| Mitty | 0049 | 1782.20 | 1782.6 | FT eligible | 1781.7–1784.3 | 80 |
| Mitty | 0128 | 4181.10 | 4181.9 | FG eligible | 4180.6–4183.2 | 80 |
| Mitty | 0132 | 4232.80 | 4233.2 | FG eligible | 4232.3–4234.9 | 80 |
| Mitty | 0167 | 5116.90 | 5117.8 | unknown/outside | 5116.4–5119.0 | 80 |
| Mitty | 0186 | 5727.14 | 5727.8 | unknown/outside | 5726.635–5729.2 | 78 |
| Mitty | 0200 | 5941.80 | 5942.5 | unknown/outside | 5941.3–5943.9 | 80 |
| Riordan | 0022 | 860.10 | 861.0 | FG eligible | 859.6–862.2 | 80 |
| Riordan | 0054 | 1788.60 | 1789.7 | FT eligible | 1788.1–1790.7 | 80 |
| Riordan | 0078 | 2419.60 | 2419.9 | FT eligible | 2419.1–2421.7 | 80 |
| Riordan | 0084 | 2598.60 | 2599.1 | FG eligible | 2598.1–2600.7 | 80 |
| Riordan | 0092 | 3269.80 | 3270.4 | unknown/warmup | 3269.3–3271.9 | 80 |
| Riordan | 0118 | 3613.30 | 3613.7 | FG eligible | 3612.8–3615.4 | 80 |
| Riordan | 0119 | 3639.20 | 3639.4 | FG eligible | 3638.7–3641.3 | 80 |
| Riordan | 0128 | 3939.10 | 3939.5 | FT eligible | 3938.6–3941.2 | 80 |
| Riordan | 0129 | 4005.10 | 4005.6 | FT eligible | 4004.6–4007.2 | 80 |
| Riordan | 0130 | 4020.50 | 4020.9 | FT eligible | 4020.0–4022.6 | 80 |
| Riordan | 0132 | 4163.70 | 4164.0 | FT eligible | 4163.2–4165.8 | 80 |
| Riordan | 0136 | 4232.30 | 4232.7 | FT eligible | 4231.8–4234.4 | 80 |
| Riordan | 0137 | 4254.60 | 4254.9 | FT eligible | 4254.1–4256.7 | 80 |
| Riordan | 0145 | 4422.80 | 4423.1 | FG eligible | 4422.3–4424.9 | 80 |
| Riordan | 0152 | 4679.10 | 4679.9 | FG eligible | 4678.6–4681.2 | 80 |
| Riordan | 0165 | 5082.50 | 5082.9 | FG eligible | 5082.0–5084.6 | 80 |
| Riordan | 0180 | 5544.40 | 5544.8 | FG eligible | 5543.9–5546.5 | 80 |

All triggers use `primary_under_net` except Riordan 1788.60 (`gap_under_net`).
The latter matters: the unchanged generic function is not primary-branch-only.

### Bounded workload, not an inference run

Each request begins 0.5 s before the earlier of attempt time and first path
point, and ends 0.5 s after the latest of attempt+`MAKE_WINDOW`, last path point,
observed-until, and first-under-net+0.4 s. Requests clip to cache/source extent;
overlapping or touching intervals union **within a game only**, preserving all
event IDs. None of the actual requests overlaps; the one rescued Mitty path
begins at 5727.135, accounting for its 2.565 s envelope. All others span 2.6 s.
These envelopes request trajectory/guard evidence; they do not guarantee actual
detections, common observed initial context, or reconstruction of whole-game
tracking state. The cache cannot identify an exact source-frame reuse schedule.

Actual source rates come from the existing hashed ffprobe provenance, without
opening either film: Mitty **567360001/18912000 Hz**, Riordan
**536040001/17868000 Hz** (both nominal `30/1`, not cache `10` Hz). Counts are
conservative estimates `ceil(duration * actual_average_rate) + 1` per merged
window, including endpoint/rounding allowance; **not exact PTS counts**.

| Cohort | Mitty windows / seconds / frames | Riordan windows / seconds / frames | Both |
|---|---|---|---|
| All-cache | 9 / 23.365 / 718 | 17 / 44.2 / 1360 | **26 / 67.565 / 2078** |
| Eligible FG/FT | 6 / 15.6 / 480 | 16 / 41.6 / 1280 | **22 / 57.2 / 1760** |

The eligible envelopes cover about 0.47% of the combined cached time extent;
this is source-duration demand, not a demonstrated runtime speedup.

### Explicit CPU extrapolation only

The **existing source-rate experiment** measured 53 full 1920×1080 frames at
YOLOX-M **960**, CPU float32, four Torch threads / one interop / one OpenCV:
**41.1082511 s loop plus final verification**, **48.0771862 s child wall including
startup/loading/provenance**. Those are historical measurements, not timings
from this cache-only census. The manifest hash matches its inference record.
Linear extrapolation of these same-960 measurements gives:

| Cohort | Mitty loop / wall min | Riordan loop / wall min | Both loop / wall min |
|---|---|---|---|
| All-cache, 2078 estimated frames | 9.28 / 10.86 | 17.58 / 20.56 | **26.86 / 31.42** |
| Eligible, 1760 estimated frames | 6.21 / 7.26 | 16.55 / 19.35 | **22.75 / 26.61** |

Formula is `estimated_frames * measured_seconds / 53` separately for loop and
wall. The wall figure amortizes startup per frame naively; startup does not
actually scale linearly. Decoder seeks, new extraction, scheduling, caching,
thermal/hardware changes, missing detections, and larger context needs can
change cost. **Neither column is a deployment guarantee or a fresh benchmark**;
the census replay wall times (~15.18 s Mitty, ~13.84 s Riordan, including parity
replays) are not detector latency and are not used in this projection.

## Recommendation and selection blind spots

**A further bounded offline, stratified rescan experiment is worth doing; a
production rollout or suppression rule is not justified.** The candidate is not
rare: it requests evidence on 20.18% of currently eligible accepting events,
including 9 FTs. It is nevertheless a small absolute source envelope: 57.2 s,
about 1760 conservatively estimated source frames across both games. Do not
infer that these 22 are errors, or that the 87 eligible untriggered accepts are
safe. Current evidence cannot quantify error enrichment or net accuracy gain.

A concrete next step, **not executed here**, is four previously unrescanned
eligible triggers spanning both games and both kinds: Mitty FG **967.10** and
FT **1782.20**, Riordan FG **860.10** and gap-branch FT **1788.60**. Their union
is 10.4 s / ~320 conservative frames; naive same-960 loop/wall extrapolation is
4.14/4.84 min. A 240-second hard budget is therefore not reliably enough even
for those four; use smaller capped stages or a separately approved budget.
Retain the already-studied Riordan disputed 4422.80 and positive/control paths
as controls, verify strict source/checkpoint/PTS identity before any reuse, and
preserve common observed initial and guard context. Include a capped matched
untriggered control stratum before estimating error enrichment. Independent
outcome adjudication remains necessary before any correction claim.

- **False negatives:** this acceptance-gated trigger cannot select rejected
  coarse paths, including the prior control's phase-2 centering rejection and
  Mitty's curated 1015.60 miss. It is not a false-negative recovery strategy.
- **Missed attempts:** no opened attempt, no selected ball/rim, off-camera rim,
  failed attempt opening, bad game window, or suppressed/rescue-missed attempt
  yields no final trigger candidate. Such omissions are not in the denominator.
- **Other false makes:** centered previous observations, disappearance,
  localization/depth ambiguity, wrong ball/rim association, or an unrecognized
  dead-ball make can all evade this particular geometry predicate. Unknown
  context and rejected/vetoed candidates are not certified safe.
- **Selection and generalization:** these are two development-influenced caches,
  not holdouts. The six original curated cases reproduce their old trigger
  pattern, but are not the sampling frame. Triggering a provisional positive
  is collateral evidence demand, not an error label. Historical cache
  checkpoint/configuration and exact source-frame equivalence remain unproven.

## Frozen evidence and checks

Private artifacts: `ml/data/labels/rim_rescan_coverage_20261112/`.
`inputs_before.json` and `inputs_after.json` bind **439** existing/current source
and input files and match exactly: both complete track caches, all current
`ml/tools/*.py` and `worker/*.py`, the context documentation, original audit,
context/source-rate frozen evidence, and film-rate provenance. No old source or
artifact was overwritten. Source-video hashes are quoted from frozen provenance,
**not revalidated by reading film bytes**; neither film is an execution input.
All unowned pre-existing working-tree changes were left in place.

| Principal frozen input | SHA-256 |
|---|---|
| Mitty `.v4.json` | `0994d981e6b5247ed58ca0a091ec1dafdd02d356071938e4526f3de34d19926a` |
| Riordan `.v4.json` | `cd2f1a8226ae71f7c72329433a1e19937717ff660b23b985a45e829e21504a7c` |
| `shots.py` | `609fb49ff2923cbd599fb690255b2b8db79cc1605c1fe6bcd21faa40756ef0d9` |
| `rim_outcome_audit.py` | `3bb8e20603f7dcacc3acebac6da84bbb6b2b39ad55f5ceb3594714eb593d708c` |
| `rim_context_eval.py` | `2bb8cbf2fff555782a603df2827fd008de5b0eb16e1da4ef872d343dfe5872dc` |
| `makes_eval.py` | `3a352b82ebe187976fe659235a0b2d402910b467e4576107478812e4e2472ed7` |

`mitty.json` and `riordan.json` retain every trace and final attempt;
`summary.json` retains cohorts, all merged/request windows, exact links, frame
estimates, and projection inputs. `runtime_windows.json` supplements the census
with the unchanged window-finder outputs. `integrity.json` freezes initial
outputs; `delivery_integrity.json` separately binds the later documentation,
accepted-event index, validation recipe/results, and all initial artifacts.

Six new focused tests cover deduplication, final-veto gating, last-call identity,
window merging, unknown context, and exception-safe restoration. All **32** rim
tests pass, including existing frozen-evidence/context integrity tests:

```sh
PYTHONDONTWRITEBYTECODE=1 ml/.venv/bin/python -m unittest discover -s ml/tools -p 'test_rim*py' -v
```

`rim_rescan_coverage.py` refuses an existing output directory. Do not delete the
frozen census to rerun it. The private validation recipe is likewise no-clobber.
