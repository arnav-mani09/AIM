# Stratified automatic rim-rescan pilot — November 13, 2026

Offline development research only. This is new local detector inference, not
another cache census, human adjudication, official scoring, or a production
change. No independent truth labels are available; no automatic statistics
improvement can be claimed. No coach backlog is created.

## Frozen selection and protocol

Before any source decoding or image inspection, `selection.json` was written
exclusively and made read-only. SHA-256:
`72a8efa9e5c666740ab9cc2a085adf35e0a564a5dc7efd98ce7e97f4ad76a101`.
It binds the exact six event records and historical traces, both source-film
byte hashes, current census/cache inputs, runner/tests/helpers, installed
YOLOX source, dependency versions, checkpoint, configuration and windows.
There were no applicable ancestor/root or nested `ml/` AGENTS.md files.

Required trigger strata: Mitty FG 967.10, Mitty FT 1782.20, Riordan FG 860.10,
and Riordan gap-branch FT 1788.60. Controls are eligible **accepted** untriggered
events, matched to FG if any remain, closest in absolute time to the selected
FG in their game; ties sort by ascending event ID. All events in previously
reviewed blind-film intervals or prior source-rescan intervals are excluded
from the control pool. Strict failure is retained rather than substituted.
This deterministically selects Mitty FG 1024.80 and Riordan FG 940.50; neither
control stratum fails. Selection did not use image appearance or new outcomes.
The required Riordan 860.10 trigger falls in a previously reviewed broad
850–870 interval, but had not undergone the previous automatic rim rescan;
it is not represented as a wholly unseen development example.

Existing census window policy is reused unchanged for every selected case,
including controls: start 0.5 s before the earliest attempt/path start; end
0.5 s after the latest attempt+MAKE_WINDOW, path end, observed-until, or
first-under-net+0.4 s, clipped to cache/source extent. Merge touching or
overlapping requests within each game only; preserve all event IDs. The six
nonoverlapping windows total 15.6 s and estimate 480 source frames. Hard limits
are six windows, 500 total frames and a **600-second total inference child**
timeout, including startup/model loading/provenance checks. No budget resets,
threshold tuning or film-wide inference are allowed.

Pinned checkpoint SHA-256:
`d009e6911b10ba08a027d870f7fee01d1deddbd4d8290b01a7f0ab85ce795660`.
CPU float32 YOLOX-M, 960, four classes, four Torch threads, one interop and
one OpenCV thread, seed zero, strict `weights_only=True` loading without
unsafe fallback. Unchanged BGR `ValTransform(legacy=False)`, top-left 114 pad,
native inverse-ratio coordinates, score product, floor .1, class-aware NMS
.45, ball cutoff .20 and rim cutoff .50. Retained post-NMS ball/rim rows
include below-class-cutoff observations, not arbitrary below-floor detections.

## Comparison and provenance limits

Each native PNG is associated with integer decoder PTS, rational time base,
ffprobe packet position and exact ffmpeg showinfo PTS ordering. Probe-local
decoder indices are not global source-frame ordinals. No timestamp is hidden
or reconstructed from nominal fps. Every frame is newly inferred: the six
windows do not overlap the prior source-rescan windows, so zero prior frame
inferences are reused. Historical caches do not establish checkpoint/config
or source-frame/decoder identity: historical decisions are background only,
**never aligned paired comparisons**.

Fresh dense observations are compared with all three modulo-three schedules,
sharing all decoded records through the dense first genuinely observed
in-zone above-rim point. Ball selection runs again on each schedule. All three
independent schedules are also evaluated without that prefix; absent initial
context is explicitly unknown, not a miss. Decoded duration/completeness,
prospective .4 s guard horizon, missing ball/rim detections, and selected-path
coverage remain separate fields. The windows request context but cannot
guarantee that the detector observes it.

These are conditional local-ROI `decide()` paths, not full `find_shots`, rescue,
dead-ball or game-wide attempt-count replays. The fixed cache-derived rim
anchor and original association helper can fail on moving cameras or wrong
ball/rim associations. A rejection can be collateral damage, not a correction.

## Native-image provisional inspection

Before reading the fresh detector decisions, this development agent inspected
20 unannotated native-pixel rim/net contact sheets (160 chronological frames)
around the six transitions. These are selected portions, not a claim that all
474 frames or full possessions received exhaustive review. The inspected image
hashes, exact PTS-derived timestamps and reasoning are retained in
`visual_observations.json`. Historical calls were already known, so this is
not an independent blinded truth study.

| Selected case | Provisional physical outcome | Native-image evidence |
|---|---|---|
| Mitty FG 967.10 trigger | Make | Net-through/deformation at 967.266655556–967.30; below-net exit at 967.333322222–967.366655556. |
| Mitty FT 1782.20 trigger | Make | Net stretch at 1782.466655556–1782.533322222; below-net exit at 1782.566655556–1782.60. |
| Riordan FG 860.10 trigger | Miss | Rim rebound above through 860.666655556, right-lip contact at 860.866655556–860.90, then descent beside/right of net at 860.933322222–861.033322222 into contested hands. |
| Riordan FT 1788.60 trigger | Miss | Multiple rim bounces, then outside-right fall at 1789.633322222–1789.733322222 continuing to 1789.90. Single-view depth limits certainty. |
| Mitty FG 1024.80 control | Make | Rim entry about 1025.033322222, net stretch and below-net exit at 1025.10–1025.166655556. |
| Riordan FG 940.50 control | Make | Entry at 940.733322222–940.80, prolonged net deformation, exit beneath at 941.30–941.333322222. |

No official live/counting status, scoreboard credit, possession or assist
attribution is inferred from these local observations. “Miss” is provisional,
not a human-adjudicated label; “unknown” remains appropriate for automated
paths lacking actual initial or crossing evidence.

## Executed results and costs

**474 new full-frame inferences; zero reuse; all six samples retained.** Each
window decoded 79 frames, with exact packet/decoder/showinfo agreement,
monotonic rational PTS, no cadence gaps larger than one native frame and
endpoints within one source frame of the requested envelope. All six have
observed initial above-rim context and full prospective .4 s decoded guard
horizons in dense, shared-prefix phases and independent phases. All 42 path
evaluations are retained; no initial-context failures arose in this cohort.

| Case | Fresh dense | Shared phases 0 / 1 / 2 | Independent phases 0 / 1 / 2 | Paired case result |
|---|---|---|---|---|
| Mitty FG 967.10 trigger | Accept | Accept / Accept / Accept | Accept / Accept / Accept | Unchanged |
| Mitty FT 1782.20 trigger | Accept | Accept / Accept / Accept | Accept / Accept / Accept | Unchanged |
| Riordan FG 860.10 trigger | Reject | Reject / Accept / Accept | Reject / Accept / Accept | Changed |
| Riordan FT 1788.60 trigger | Reject | Reject / Accept / Reject | Reject / Accept / Reject | Changed |
| Mitty FG 1024.80 control | Accept | Accept / Accept / Accept | Accept / Accept / Accept | Unchanged |
| Riordan FG 940.50 control | Accept | Accept / Accept / Accept | Accept / Accept / Accept | Unchanged |

Thus **two changed, four unchanged, zero unknown paired case results**, and
three changed comparisons among 18 shared-context phase comparisons. These
counts describe this frozen purposive pilot only, not population accuracy.
The independent schedules happen to reproduce the same pattern; they are
separately reconstructed observations, not assumed equivalent to shared
prefixes. All historical cache calls accepted, but differences from those
calls are **not** included in the paired-comparison counts.

- **Riordan FG 860.10 potential correction:** dense first under-net observation
  is 861.0, x=0.527650065 rim units: centering and prospective drift fail.
  Shared phase 0 also rejects. Phase 1 first sees exit at 861.033322222,
  x=0.323910396, and phase 2 at 861.066655556, x=0.120922991; both accept the
  primary branch. This matches the provisional outside-right miss but is
  not independent confirmation or a production correction.
- **Riordan FT 1788.60 potential correction:** dense exit at 1789.7 has
  x=0.394085285, fails primary centering and gap length. Phase 1 exits at
  1789.733322222, x=0.372583955 and accepts the gap branch, while phases 0
  and 2 reject. New intervening observations prevent the dense gap acceptance;
  neither thresholds nor timestamps were changed. The visual interpretation
  is a provisional outside-right miss, not adjudicated scoring truth.
- **Possible collateral rejection:** none appears among this pilot's four
  provisional makes: both positive trigger cases and both untriggered controls
  accept densely and in every phase. Four positives cannot establish safety;
  shared development bias, single-view ambiguity, association errors and the
  prior positive phase-2 rejection remain live objections to auto-suppression.

Decoded completeness is **not** complete detector evidence:

| Case | Dense guard frames | Missing ball | Missing local rim | Not in selected ball/rim path |
|---|---:|---:|---:|---:|
| Mitty FG 967.10 | 12 | 4 | 2 | 4 |
| Mitty FT 1782.20 | 12 | 0 | 0 | 0 |
| Mitty FG 1024.80 | 12 | 0 | 0 | 0 |
| Riordan FG 860.10 | 12 | 5 | 0 | 5 |
| Riordan FT 1788.60 | 12 | 6 | 0 | 6 |
| Riordan FG 940.50 | 12 | 6 | 0 | 6 |

Only two of six dense paths have selected ball/rim pairs at every guard frame.
Missing detections do not mean physical absence; passing unchanged guard
predicates on incomplete observations is not proof of no drift/pop. All
missing PTS, raw retained detections, paths, exact crossing coordinates,
predicate booleans and branch decisions remain in `analysis.json` and
`detections.jsonl`; nothing is filtered from the delivered evidence.

Measured **inference child wall 379.759610 s (6.3293 min)**, including startup,
strict model loading and before/after input verification, below the hard
600-second timeout. Measured **loop wall 359.477531 s (5.9913 min)** for 474
frames, approximately .7584 s/frame; loop timing is host wall, not CPU-seconds
or isolated neural-network kernel latency. Per-frame timings are retained.
Extraction, visual review and analysis are outside the inference budget;
end-to-end researcher wall and per-window extraction costs were not timed and
are not invented. `budget.json` and `inference.json` are the measured records.

| Case (79 frames each) | Sum of measured per-frame loop wall seconds |
|---|---:|
| Mitty FG 967.10 | 64.771006 |
| Mitty FT 1782.20 | 62.425401 |
| Mitty FG 1024.80 control | 56.918037 |
| Riordan FG 860.10 | 60.306521 |
| Riordan FT 1788.60 | 55.565015 |
| Riordan FG 940.50 control | 59.411947 |

These sums exclude tiny loop bookkeeping and shared startup/provenance costs;
they are not per-case standalone process-wall benchmarks.

**Decision: the source-rate second pass merits further tightly bounded
offline validation, but is insufficient as a standalone automatic correction
and must not be rolled out.** Two genuinely new, phase-sensitive candidate
corrections span FG and gap FT, so abandoning all source-rate research is not
supported by this pilot. Conversely, detector gaps, the small selected sample,
prior collateral evidence and lack of independent outcome truth preclude a
net-gain or safe-suppression claim. No additional inference, new coach tasks,
rules, thresholds or production policy changes are initiated by this finding.
Independent outcome truth would be required before any automatic improvement
claim; that requirement is not converted into a mandatory coach backlog.

## Reproduction and artifact safety

New owned files: `ml/tools/rim_rescan_pilot.py`,
`ml/tools/test_rim_rescan_pilot.py`, this document, and private
`ml/data/labels/rim_rescan_pilot_20261113/`. Existing shared edits, prior/frozen
artifacts, films, caches, checkpoints, production, UI and assists are untouched.
There is no network, install, paid API, training, commit or deploy.

The completed directory is evidence, not a rerun target: `freeze`/`run` refuse
an existing directory, and JSON/log/detection outputs use exclusive creation.
No global output directories are monkeypatched and no foreign helper runner
artifact checks are bypassed; only pure selection/decision/provenance helpers
are reused. PNGs remain full native 1920×1080, with unannotated native-pixel
rim/net crop contact sheets for provisional inspection.

Focused tests:

```sh
ml/.venv/bin/python -m unittest discover -s ml/tools -p test_rim_rescan_pilot.py -v
```

Six new focused tests pass without skips after freezing; eleven existing
source-rate helper tests and seven existing context tests also pass (24 total).
They cover deterministic frozen selection, FG preference/tie/exclusion rules,
strict control failure, caps, missing-context unknowns, tamper rejection,
exclusive writes and foreign-output refusal. Private `validate_delivery.py`
additionally verifies actual cohort identity, all PNG hashes, exact PTS and
cadence, complete manifest/detection binding, actual budget, shared above-rim
context and .4 s decoded guard horizons separately from detector coverage.
Its persisted result and a final hash inventory bind the delivered evidence.

The actual run used separate `freeze` and `decode` stages, then one subprocess
`infer` with `timeout=600`, followed by `analyze`. It did not rerun `run` against
the frozen directory. `selection.json` binds predecode intent;
`manifest.json` SHA-256 is
`dc4c81a5bba505d68a4709195f9b0b6fd76db349de0b25e33df257c171154353`;
`detections.jsonl` SHA-256 is
`81623024e98288199f774641cf0c1cf3ca345b247084c7316ab2b6ad727e7dc4`.
