# Predetermined rim-rescan safety batch — November 13, 2026

Offline development research only. This batch owns only the new safety runner,
its focused tests, this report, and private
`ml/data/labels/rim_rescan_safety_20261113/`. No production correction,
suppression, tuning, source/checkpoint edit, training, network, installation,
paid API, full-film inference, commit, deployment, or mandatory coach task.
No human-adjudication, independent-truth, official-credit, or statistics-gain
claim is made. No applicable ancestor/root or nested `ml/` AGENTS.md exists.

## Predetermined selection

Selection was frozen read-only before decoding. SHA-256:
`8ee2e25a9a21cb0b6921ebf8bece1881907bd21007ff2f0af498e17852f64dfc`.

The rule selects two eligible final accepted triggered events per game,
preferring one FG and one FT where available. Each category sorts by earliest
attempt time then event ID. An unavailable category is recorded and falls
back to the earliest remaining eligible trigger in that same game. Each
game's control is the eligible accepted untriggered FG nearest its first
selected FG (otherwise first selected attempt), with ties by event ID.
No image, fresh outcome, scoreboard report, truth file, or prior acceptance
accuracy was used to choose or substitute cases.

Exclusion checks use both prior event IDs and **entire requested context
envelope overlap**, not merely attempt timestamps. All prior source-rate,
context, and pilot manifest intervals, pilot selection IDs, decoded extents,
and blind-film review intervals are included. Prior raw detections are hashed
for preservation but never treated as aligned comparison truth. Blind-review
content is used only for interval boundaries, never outcome labels.

| Game | Role | Attempt time (s) | Category |
|---|---|---:|---|
| Mitty | First trigger | 1396.50 | FG |
| Mitty | FT-stratum deterministic fallback | 1498.90 | FG |
| Mitty | Untriggered control | 1287.10 | FG |
| Riordan | FG trigger | 2598.60 | FG |
| Riordan | FT trigger | 2419.60 | FT |
| Riordan | Untriggered control | 2510.60 | FG |

Mitty's only eligible triggered FT was already in the pilot. The strict FT
stratum is exhausted, not evidence that new FTs are safe. Riordan retains
genuine FG/FT diversity; no cross-game substitution occurs. Both FG controls
exist. The exact event IDs, candidate/exclusion audit and fallback status
are retained in `selection.json`.

## Protocol and append-only preparation repair

Unchanged census context envelopes request 0.5 seconds before the earliest
attempt/path start through 0.5 seconds after the latest attempt+MAKE_WINDOW,
path end, observed-until, or first-under-net+0.4 seconds, clipped to source and
cache extent. All six windows are disjoint: 15.6 seconds total, 480 estimated
native frames. The fixed hard caps are six windows, 500 actual native frames,
and 600 seconds for the single inference child including startup, strict model
load, and provenance checks. There are no retries or inference budget resets.

The first preparation reused the old source-rate pure alignment helper, whose
**experiment-specific 70-frame cap** rejected each approximately 79-frame
window before ffmpeg extraction. That failed `manifest.json` and empty sheet
inventory remain untouched. Zero PNGs and zero inferences resulted. The exact
original owned runner/test bytes are preserved read-only in `frozen_sources/`.
Before the same predetermined windows were decoded, `decode_revision.json`
bound the original selection, failed manifest, byte-identical source
snapshots, and revised owned runner/test hashes. Revised verification allows
only those two source revisions and still verifies every other frozen input.
The dedicated exact integer-PTS alignment now enforces this batch's 500-frame
cap instead of importing the prior experiment's 70-frame cap. No foreign
runner artifact checks or output globals are patched. Canonical decoded
evidence is append-only `manifest_revised.json`; original evidence is retained.

Pure context/association/decision/provenance helpers are reused without
forking detector decision rules or importing `makes_eval` or scoreboard-truth
modules. The new runner provides dedicated artifact and bounded-inference
orchestration; the pinned YOLOX forward pass uses the existing protocol.

Checkpoint SHA-256:
`d009e6911b10ba08a027d870f7fee01d1deddbd4d8290b01a7f0ab85ce795660`.
CPU float32 YOLOX-M, 960, four classes, four Torch threads, one interop thread,
one OpenCV thread, seed zero. Strict `weights_only=True` loading, strict model
state, unchanged BGR `ValTransform(legacy=False)`, top-left 114 padding,
inverse-ratio native coordinates, objectness times class confidence, floor
0.1, class-aware NMS 0.45, ball cutoff 0.20 and rim cutoff 0.50. All
post-NMS floor-retained ball/rim rows survive, including below-class-cutoff
rows, empty frames, and partial/failing outputs; these are not raw logits.

Integer decoder PTS, rational time base, ffprobe packet position and exact
ffmpeg showinfo ordering bind each native PNG. Probe-local indices are not
global source-frame ordinals. No historical-frame/checkpoint equivalence is
asserted. All inference is new, with zero prior-frame reuse.

Dense paths are compared only to three freshly decimated modulo-three
schedules, sharing all observations through the first genuinely observed
in-zone above-rim entry and rerunning ball association. Three independent
phases are separate, with absent initial context explicitly unknown. Full
unchanged prospective guards are evaluated; decoded duration, missing
ball/rim detections, and missing selected pairs are separate. This is
conditional local-ROI `decide()`, not full `find_shots`, rescue, dead-ball,
team credit or game-wide attempt replay. A fixed cache-derived rim anchor and
association errors remain limitations.

## Native-image inspection before fresh decisions

Fourteen unannotated native-pixel rim/net contact sheets, 168 distinct
chronological frames, were inspected before any fresh decisions were read.
This is selected transition evidence, not exhaustive inspection of all 474
frames or possessions. The single inference child ran concurrently without
its outputs being read. The read-only `visual_observations.json` binds all
inspected sheet hashes, exact PTS-derived identities, reasoning, and provisional
calls. Its SHA-256 is
`7619fec79903a58a0857d686c3fe129dfe89e436e2521dbf1d4e42441205fbe3`.

| Case | Provisional physical call | Observed native-image evidence | Official credit |
|---|---|---|---|
| Mitty 1396.50 | Make | Descending entry, sideways stretched net, below-net exit about 1397.1 | Unknown |
| Mitty 1498.90 | Make | Rim entry about 1499.1, ball within net, below-net exit about 1499.53 | Unknown |
| Mitty 1287.10 control | Make | Rim entry about 1287.4, slow net transit, below-net exit about 1288.0 | Unknown |
| Riordan 2598.60 | Make | Close two-hand finish, visible net passage and below-net ball by 2599.2 | Unknown |
| Riordan 2419.60 FT | Make | Descending entry, stretched net, ball exits below around 2419.9 | Unknown |
| Riordan 2510.60 control | Make | Near-edge rim entry, net transit, below-net exit around 2511.3 | Unknown |

All six provisional calls are physical makes; zero provisional misses and zero
unresolved physical calls in the inspected portions. **All six official credits
remain unknown.** These are agent observations, not human adjudication or
independent outcome labels. Prior accepted calls were already known. Single
view, compression, hand/net overlap at the close finish, moving cameras, and
right-edge clipping on the Riordan control limit localization. Slow net transit
must not be equated to a physical miss simply because an exit is off-center.

Two Mitty control sheets remove only the top native strip to avoid incidental
overlay content; the exact crop recipe is retained. Other gym display pixels
may be incidental to native rim images. No display/score values or changes
were interpreted, recorded, matched, or used for selection, inference,
provisional physical calls, or safety decisions. No scoreboard report or truth
file/module is read/imported by this runner or its delivery verifier.

## New safety evidence

Every selected window decoded completely and received 79 new inferences:
**six windows, 474 native frames, zero reused inferences**. “Accept/reject” here
means the unchanged conditional local-ROI decision, not physical or official
truth. Unknown is never converted to a miss. Phases are fresh decimations of
these same newly inferred records, not historical boxes.

| New predetermined case | Dense | Shared phase 0 | Shared phase 1 | Shared phase 2 | Safety interpretation |
|---|---|---|---|---|---|
| Mitty FG 1396.50 trigger | Accept | Accept | Reject | Accept | Dense retains provisional make; phase-1 collateral rejection risk |
| Mitty FG 1498.90 fallback trigger | Accept | Accept | Accept | Accept | Unchanged positive decision |
| Mitty FG 1287.10 control | Accept | Accept | Accept | Reject | Dense retains provisional make; phase-2 association/path loss rejection risk |
| Riordan FG 2598.60 trigger | Accept | Accept | Accept | Accept | Unchanged positive decision |
| Riordan FT 2419.60 trigger | Unknown | Unknown | Unknown | Unknown | No observed qualifying initial context; never called a miss |
| Riordan FG 2510.60 control | Accept | Accept | Accept | Accept | Unchanged outcome, but branch differs across schedules |

All three **independent** phases have the same accept/reject/unknown pattern
as the shared-context columns on these six cases. That is a measured result,
not an assumption that independent phases generally observe the dense prefix.
The FT has no dense qualifying prefix, so shared schedules are not constructible
(`missing_records` in the raw shared fields); its 79 dense records and all
three independent schedules are `missing_initial_context`.

Explicit evidence accounting:

- **Potential false-make-to-rejection corrections: 0 new witnesses.** There is
  no dense rejection in this new batch and no provisional physical miss.
  This is absence of a witness in six selected cases, not zero population risk.
- **Potential collateral dense rejections: 0 observed among five evaluable
  cases; one dense outcome unknown.** The FT is not a successful safety pass.
  No actual correction or suppression was applied anywhere.
- **Potential make recoveries relative to fresh sparse schedules: 2 cases,**
  one triggered FG and one untriggered FG control. Both provisionally go
  through the net; their raw sparse rejection is evidence of possible
  collateral error **if that sparse decision were used**. Neither is a measured
  production correction, official score recovery, or historical paired gain.
- **Unchanged dense-versus-all-shared-phase outcomes: 3 cases.** Two cases are
  phase-sensitive, one is unknown. All three unchanged outcomes accept, but
  outcome stability does not establish correct guards or official credit.
- **Unknown: 1 physical-decision replay case (the new FT); 6/6 official
  credits.** Provisional image assessment alone does not resolve credit.

### What actually changes

Mitty 1396.50 has common initial context at **1396.466655556**. Dense accepts
`primary_under_net` at 1397.1, exit x = **−0.335609 rim widths**. Shared phase 1
first exits at 1397.133322222, x = **−0.352877**, failing `centered_exit`;
the gap fallback fails `previous_horizontal`. Phases 0 and 2 accept. Both
the native net passage and this near-boundary flip were retained without
threshold changes. Full decoded prospective horizons exist for every phase;
that does not repair missing selected detections.

Mitty 1287.10 control has common initial context at **1287.066655556**. Dense
accepts at 1288.033322222. Phase 2 retains only four selected path observations,
through 1287.366655556, all above the under-net threshold; later decoded
records remain present through 1289.166655556. It returns `no_make` with **no
selected under-net crossing**, despite observed initial context. This is
association/path-coverage loss, not proof of a physical miss and not a failure
to decode the prospective interval. The inherited helper's `failed_primary`
and `failed_gap` fields say `missing_above_rim_context` when no crossing exists;
those fallback strings must not be mistaken for absent initial context here
(the trace records four above-rim observations). No helper was changed to
conceal that diagnostic limitation.

Riordan 2510.60 is outcome-stable but not mechanism-stable: dense and phase 2
accept `net_disappearance`, phase 0 accepts `gap_under_net`, and phase 1 accepts
`primary_under_net`. Dense first-under-net x = **−0.369151** fails centering;
the eventual acceptance is not evidence that centering passed. The visible
net transit and missing detections remain separate evidence.

For Riordan FT 2419.60, unchanged association produces **36 selected pairs
but zero qualifying in-zone above-rim observations**. The first selected pair
is at 2419.966655556, already below the rim, after the visually observed net
passage. Complete decoding therefore cannot establish an opened attempt.
`context_diagnostic.json` retains every selected pair's actual PTS, rim units,
in-zone and above-rim predicates. No changed anchor, relaxed threshold,
invented prefix, interpolation, or outcome substitution rescues the unknown.

### Prospective guards and missing evidence

All five evaluable dense paths have complete decoded **exit+0.4-second**
horizons. Of their 15 shared phases, 14 have an observed crossing and complete
decoded guard horizons; the control's phase-2 path has no crossing from which
to anchor a guard. No FT guard is asserted without initial/crossing context.

| Dense case | Guard frames | Missing ball | Missing local rim | Not in selected paired path |
|---|---:|---:|---:|---:|
| Mitty 1396.50 | 12 | 6 | 0 | 6 |
| Mitty 1498.90 | 12 | 0 | 0 | 0 |
| Mitty 1287.10 control | 12 | 0 | 0 | 0 |
| Riordan 2598.60 | 12 | 1 | 0 | 1 |
| Riordan 2419.60 FT | Not assessable | — | — | — |
| Riordan 2510.60 control | 12 | 2 | 0 | 2 |

Only **two of five evaluable dense paths** have selected pairs at every guard
frame. All missing PTS are retained, not discarded. Across entire 79-frame
windows, absent above-cutoff ball/local-rim counts respectively are 42/20,
27/8, 8/0, 21/0, 24/1, and 43/2 in selection order. These include pre/post-shot
time and are not guard counts. Missing observations cannot certify no pop or
drift. All 474 raw floor-retained ball/rim outputs, including empty and
below-class-cutoff rows, remain in `detections.jsonl`.

## Actual measured cost

- Single inference child wall: **380.126781 seconds (6.3354 minutes)**,
  including startup, strict model loading and before/after provenance checks;
  hard timeout 600 seconds. Status complete, no retry/reset.
- Forward-loop host wall: **355.821373 seconds**, approximately **0.75068
  seconds/frame**. This is wall time, not isolated kernel latency or CPU-seconds.
- Revised bounded decoding/probing per-window wall sums to **290.209643
  seconds**. The original zero-frame failed preparation is separately recorded
  in the untouched failed manifest. Sheet creation, visual inspection, analysis,
  tests and end-to-end researcher wall were not timed and are not invented.

| Case (79 frames each) | Sum of per-frame loop wall (s) |
|---|---:|
| Mitty 1396.50 | 55.734000 |
| Mitty 1498.90 | 55.743513 |
| Mitty 1287.10 control | 55.277581 |
| Riordan 2598.60 | 69.319621 |
| Riordan 2419.60 FT | 62.264885 |
| Riordan 2510.60 control | 57.407102 |

Per-frame sums omit shared startup/provenance and small bookkeeping costs;
they are not independent per-case process benchmarks.

## Fail/continue recommendation

**FAIL the standalone automatic correction/suppression safety gate. Stop
repeating this same-view rescan sampler as a way to resolve the remaining
ambiguities.** No new false-make correction witness appears, the only new FT
cannot be evaluated despite visibly useful native images, positive decisions
remain phase/association-sensitive, and most evaluable dense guards have
missing selected evidence. This batch cannot settle prior disputed physical
outcomes or official credit. No new sample is proposed or initiated.

Dense recovery of two fresh sparse positive rejections is useful mechanism
evidence, so this is not proof that source-rate observations are useless.
Retain the diagnostic evidence, not an autonomous outcome override. Reopening
an automatic improvement claim would require qualitatively independent,
adequate outcome evidence and a validated end-to-end decision path, rather
than another similar convenience sample. That condition creates no mandatory
coach review or human-adjudication claim. All existing production decisions
and prior scoreboard evaluations remain untouched and unconsulted.

## Integrity and validation

Seven new focused tests pass without skips, plus seven existing context tests
and eleven existing source-rate helper tests: **25 total**. Tests cover
deterministic strata/ties, whole-envelope exclusions and exhausted-category
fallback, strict FG controls, 500-frame/six-window bounds, exact integer PTS,
no-clobber/tamper checks, absence of truth-module imports, actual frozen cohort,
shared context and decoded guard horizons. No unrelated test fixes were made.

The private read-only delivery verifier checks the selection and revision
bindings, all original frozen source snapshots, all other frozen inputs,
checkpoint/source identity, every PNG hash and rational PTS, exact ffmpeg
ordering, actual budgets, and **recomputes all dense/shared/independent traces**
from raw fresh outputs. It compares their JSON-normalized structures (tuples
serialize as arrays), not an approximate match. Its initial direct Python
tuple/list comparison failed before output; only that private verifier's
serialization comparison was fixed. Detector results and analysis were never
overwritten. Final verification passes in `delivery_validation.json`.

Canonical decoded manifest SHA-256:
`9a669bdd170345bfe7676feb6c1ca3c3b1667db941f6fe86ba86f932cbeb5b0a`.
`integrity.json`, `delivery_validation.json`, test log, revision record,
original failed preparation, visual records and final hash inventory preserve
the complete audit trail. Prior source-rate/context/pilot artifacts and their
frozen sources are unchanged. The shared worktree was never reset or committed.

Reproduction/check commands (the completed evidence directory is **not** a
rerun target; all writing stages refuse existing outputs):

```sh
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_rim_rescan_safety.py -v
ml/.venv/bin/python ml/tools/rim_rescan_safety.py verify
```

The one actual run used `freeze`, the retained failed zero-frame preparation,
the predecode owned-source revision, `decode`, `sheets`, one bounded `infer`,
and append-only `analyze`. No unbounded inference stage was used.
