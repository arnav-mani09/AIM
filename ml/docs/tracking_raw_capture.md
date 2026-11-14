# Fresh raw association capture — November 13, 2026

## Outcome and scope

Completed **244 fresh native frames, 61 in each requested six-second window**,
using one CPU inference child with a **400-second hard wall timeout**, including
startup, imports, provenance verification, safe checkpoint loading, inference,
and final verification. Actual child wall time: **276.460 seconds**. One attempt;
no inference retries, timer resets, parameter sweeps, training, network access,
installation, paid calls, commits, deployment, or production edits.

The private usable dataset is
`ml/data/labels/tracking_raw_capture_20261113/` (approximately 593 MiB).
It contains **2,430 player proposals and 530 referee proposals**, retained after
the existing 0.1 postprocess floor and class-aware 0.45 NMS, **before per-class
cutoffs or tracking**. Forty referee proposals fail the 0.35 referee cutoff but
are preserved. All 2,430 player proposals pass the unchanged 0.1 player cutoff
and form actual `sv.Detections` inputs. The current tracker emits 2,212 boxes;
**218 supplied player proposal occurrences do not emit**. These are observations
of this fresh run, not historical missing-box counts or real-person metrics.

All **244 independently replayed output frames match the fresh capture exactly**:
array values, dtypes, shapes, classes, confidence values, and tracker IDs. This
does not claim equivalence to historical `.v4` outputs or production GPU results.
Existing caches retain only post-tracker player outputs and cannot recover the
omitted detector proposals or their original scores.

Production remains unchanged. A longer buffer is **not established as safe**.
Nothing here approves an ID alias, relabels an assist, transfers labels to a
coach, or establishes adjudicated identity-switch/IDF1/HOTA metrics.

## Exact source-frame identity

Windows are inclusive and use actual integer source PTS, not invented `time*fps`
frame identities:

| Window | Source seconds | First / last PTS | Frames |
| --- | --- | --- | --- |
| Mitty 253.1 | 250.1–256.1 | 22509000 / 23049000 | 61 |
| Mitty 1150.7 | 1147.7–1153.7 | 103293000 / 103833000 | 61 |
| Riordan 3613.3 | 3610.3–3616.3 | 324927000 / 325467000 | 61 |
| Riordan 5496.8 | 5493.8–5499.8 | 494442000 / 494982000 | 61 |

Both source streams use time base `1/90000`; all retained images are 1920×1080
lossless PNGs. For each window, targets are `start + k/10` seconds, `k=0..60`.
Each target chooses the nearest available in-window decoded integer PTS; ties
choose the earlier PTS; duplicate selections are removed. In this run there are
61 distinct selections per window, with exact 0.1-second spacing.

Full-video **packet metadata indexing** is used, not full-film image decoding.
The streams have no B frames, PTS=DTS, and packet count equals stream frame count.
Bounded ffprobe frame decoding joins `pkt_pos` to the original video packet,
requires packet PTS = decoder PTS = best-effort timestamp, and records the
zero-based source video packet/sample ordinal. This is not an assumed global
decoder-frame counter. Each selected PNG also matches ffmpeg `showinfo` integer
PTS and emitted frame ordinal exactly. Original probe and decode commands and
stderr logs are retained. Seeking can decode required keyframe preroll; the
bounded probes allow 0.05 seconds of endpoint lookahead, and ffmpeg uses a 6.05
second input limit plus the exact PTS select list and 61-output-frame cap. Only
in-window selected frames are saved/inferred; there is no film-wide decode.

## Frozen inference and tracker protocol

- Architecture: local YOLOX-M, four classes, input 960, CPU float32, seed 0.
- Four PyTorch intraop threads; one interop thread; one OpenCV thread. BLAS and
  platform thread environment limits are also set to four in the child.
- `torch.load(map_location="cpu", weights_only=True)` only; no unsafe fallback;
  checkpoint metadata checked and state dict loaded strictly.
- Checkpoint: `ml/runs/v4/aim_yolox_m.pth`, 101,520,126 bytes, SHA-256
  `d009e6911b10ba08a027d870f7fee01d1deddbd4d8290b01a7f0ab85ce795660`.
- Existing baseline cutoffs: ball .20, player .10, referee .35, rim .50;
  postprocess floor .10, NMS .45, class-aware. This dataset exports every retained
  player/referee row, not pre-NMS logits, below-floor detections, ball/rim rows,
  or every person actually present in the image.
- Original seven-column postprocess float32 rows, objectness, class confidence,
  float32-product score, native xyxy (without rounding or clipping), postprocess
  row index, and per-class cutoff flag are retained. JSON numbers round-trip the
  saved values; they are not three-decimal cache confidences.
- Only cutoff-passing **player class 1** enters ByteTrack. Referees deliberately
  do not enter; absence of a referee in tracker output is not a lost association.
- Current actual `supervision==0.26.1` public `update_with_detections`:
  activation .5, frame rate 10, lost buffer 30, matching .8, consecutive frames 1.
  Derived `max_time_lost=10`, new-track `det_thresh=.6`. No changes to any setting.
- Each window starts an independent fresh tracker; all selected frames are
  sequentially updated, including empties if present. IDs are **window-local
  replay keys**, not production IDs. No cross-window history is manufactured.
- Inputs are serialized and flushed **before** the mutable tracker call;
  input xyxy/confidence are float64, class ID is native integer, matching the
  current worker's `sv.Detections` construction. Null mask/tracker ID and empty
  data/metadata are explicit. Full output array schemas are preserved, including
  the different empty-output dtypes/shapes returned by supervision.

Installed versions: torch 2.14.1, torchvision 0.29.1, NumPy 2.2.6, SciPy 1.15.3,
supervision 0.26.1, YOLOX 0.3.0, opencv-python 5.0.0.93. Manifest includes Python,
executable, ffmpeg version, source/checkpoint/baseline hashes, all baseline-bound
files, runner/tests/helper sources, all installed supervision and YOLOX Python
sources, packet metadata files, and every selected image. Verification completed
before and after inference, and again before independent replay.

**Worker preprocessing is not identical.** This capture deliberately uses the
frozen CPU baseline `ValTransform(legacy=False)`: OpenCV bilinear resize into
uint8 BGR, top-left uint8 padding 114, then CHW float32. The worker first creates
a float tensor and uses PyTorch `F.interpolate(..., bilinear,
align_corners=False)`, float padding, and CUDA half precision when on GPU. Its
decoder uses an fps filter rather than explicit original PTS selections, and it
batches frames. Both CPU and GPU worker preprocessing can therefore differ from
this frozen baseline. No exact historical frame, live checkpoint, or GPU-parity
claim is made.

## Concrete native-pixel review

Reviewed all four fresh native event-center images plus the twelve adjacent
native 1:1 crops in `review_*.png`. Green boxes are emitted player proposals,
red boxes are nonemitted player proposals, cyan boxes are referee proposals.
`pN` denotes zero-based position in that frame's saved `proposals` list, not a
person label. Crop bounds and sample indices are in `inspection_recipe.json`.
Unmodified native PNGs remain the primary visual evidence.

1. **Riordan 3613.2–3613.4: preserved proposal, failed continuation.** Samples
   151/152/153, PTS 325188000/325197000/325206000. The visually continuous
   white-jersey #4 region emits replay ID 5 at 3613.2; the 3613.3 proposal p2,
   score **0.9546675086021423**, native box
   `[1392.0126953125,360.01068115234375,1512.282470703125,562.1759643554688]`,
   is supplied but does not emit; the nearby visually corresponding box emits
   ID 32 at 3613.4. State replay confirms ID 5 becomes Lost at sample 152 while
   ID 32 is newly present but unactivated, then activated at sample 153.
   Local Lab for the three proposals is `[168,124,140]`, `[167,124,141]`,
   `[170,124,143]`: useful local appearance continuity to test in a future
   association design. This is concrete fresh-run nonemission/fragmentation
   evidence, not an approved ID-5↔ID-32 alias or dataset-wide identity metric.

2. **Mitty 1150.6–1150.8: opposing-appearance overlap ambiguity.** Samples
   90/91/92, PTS 103554000/103563000/103572000. The native crops show a white
   jersey #34 behind a blue-jersey defender. At sample 91, white-region p7 emits
   replay ID 38 while overlapping blue-region p8, score **0.7400349378585815**,
   is supplied but unconfirmed/nonemitted. At sample 92, ID 38 emits on the
   different, foreground blue region p7; white-region p4 emits ID 40 while
   blue-region p6, score **0.8634997606277466**, does not emit. Replay state records
   confirm these ID assignments and confirmation changes. This is a qualitative
   appearance-inconsistent association candidate with exact input evidence, not
   a human-adjudicated switch count or an ID alias. Simple median Lab is itself
   confounded here: ID-38's two emitted crops have `[90,128,125]` and
   `[88,130,126]` despite their visually different jersey regions. Occlusion and
   shadow can make color alone insufficient.

3. **Riordan 5496.8: class ambiguity, not a missing player identity.** At sample
   213, PTS 494712000, player p11 score **0.29927223920822144** overlaps referee
   p10 score **0.7215192317962646** on the same visibly striped official near
   native x260–320, y350–540. Both class-aware NMS proposals survive the floor;
   only the player row enters tracking and does not emit. The duplicate class
   interpretations and similar torso Lab are preserved, not converted to a
   player alias, coach label, or purported ID switch. Neighboring samples 212/214
   corroborate that this is an official-shaped region.

4. **Mitty 253.0–253.2: real overlap without universal failure.** Samples
   29/30/31 show several overlapping blue/white player regions under the hoop.
   Player proposals in these three frames all emit under current settings;
   sample 31 additionally retains a referee-class interpretation in the raised
   arms region. This prevents interpreting every overlap or class-confusable
   proposal as an association error. It does not establish longer-term identity.

Existing review evidence was also inspected: the cropped historical
`blind_film_review_20261112/detail_mitty_250_255/frame_0008.jpg` and native
1920×1080 `rim_rescan_safety_20261113/riordan_4_decoded/frame_017.png`.
The latter is a **different moment** (2419.633322… source seconds), not a paired
historical frame for this capture. It shows the same gym's blue/white players,
striped officials, benches and potential overlapping body regions. Neither
existing image is used to assert exact historical-frame correspondence.

## Torso appearance limitations

Every exported player/referee proposal gets a local torso measurement on the
**actual native image and native box**, not coordinates misapplied to a resized
preview. The middle half of box width and 20–50% of height are converted using
OpenCV uint8 BGR→Lab; channel medians are saved without color clustering.
Integer crop bounds are explicitly clipped to image width/height, with requested
bounds, effective bounds, clipping flag, pixel count, empty/invalid status and
null Lab where appropriate. No crop in this run was empty or required clipping
of the torso subregion; synthetic focused tests exercise both cases. Some full
proposal boxes nevertheless extend beyond the image and remain unclipped.

`occlusion_assessed=false` is intentional. A nonempty crop can contain another
player, official, skin, court, background, jersey lettering or shadows. Crop
containment is not a visibility guarantee. Local Lab is **time-local team/jersey
appearance evidence, never unique person identity**, a trusted team assignment,
or a license to move downstream labels between tracks/coaches.

## Files and exact replay

- `manifest.json`: immutable capture/source/config/dependency/frame identity.
- `inputs.jsonl`: one record for every completed frame, all raw person-class
  proposals, native appearance, proposal-to-input index list, original Detections.
- `outputs.jsonl`: corresponding original current-tracker outputs.
- `replayed_outputs.json`, `replay.json`: independent deserialized-input replay
  and exact parity result for every fresh output frame.
- `capture_status.json`, `inference.log`, `inference_verified.json`: hard-budget
  result, per-frame processing times, successful final provenance verification.
- `summary.json`, `association_evidence.json`: per-window proposal/output counts,
  exact box-equality input/output references, and replay states around each event.
  Equal boxes produce all candidate references, not a hidden uniqueness claim.
- `inspect_capture.py`, `inspection_recipe.json`, `review_*.png`: saved-input-only
  analysis and reproducible native crop/overlay recipe, not new inference.
- `tests.txt`, `validation.json`, `final_inventory.json`: focused tests and
  additional actual-data integrity checks; artifact inventory excludes itself.

Identity SHA-256s:

```text
manifest c2ec015bb7a4b0d2f35d74e4220a3e2ceb18da1664c75d81bd4c691fc8a44b02
inputs   ea068f63c4e459c8b0595ef594cc6dc6a9c5d5e636c13f15886f8ca835898cac
outputs  7ef55ab0496e29b5fcf5970f06b3a0f872dc6fbcae76c0ce499368244cf5be32
replay   810a78b1ca4d8cf33e47a9172ef5322f45ebd35933be2ac845f57055c8932800
```

The actual capture command, from repository root, was:

```sh
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 \
  ml/.venv/bin/python ml/tools/tracking_raw_capture.py capture
```

It intentionally refuses an existing output directory, so **do not rerun
inference**. The CLI `replay` mode also writes exclusively and is intended for
the initial replay; existing saved results are never overwritten. To verify
again **without inference or artifact writes**, use:

```sh
OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 PYTHONPATH=ml/tools ml/.venv/bin/python - <<'PY'
import json
import tracking_raw_capture as capture
manifest = json.loads((capture.OUTPUT / "manifest.json").read_text())
capture.verify(manifest)
inputs = capture.read_lines(capture.OUTPUT / "inputs.jsonl")
expected = capture.read_lines(capture.OUTPUT / "outputs.jsonl")
actual = capture.replay_records(inputs, expected)
assert len(inputs) == len(expected) == len(actual) == 244
assert actual == json.loads((capture.OUTPUT / "replayed_outputs.json").read_text())
print("244 exact fresh-capture replay frames; frozen provenance verified")
PY
```

Eight focused tests pass: serialization/schema round-trip; actual tracker replay
parity and mismatch rejection; input-versus-output distinction; empty-frame
preservation and array shapes; deterministic integer PTS selection, bounds and
packet alignment rejection; native torso bounds/clipping/empty/invalid crops;
same-size provenance mutation; and safe handling of a truncated final JSONL row.
The real windows contain no empty player-input or player-output frames; tests
cover those semantics without substituting synthetic evidence for this dataset.

```sh
OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 ml/.venv/bin/python -m unittest discover \
  -s ml/tools -p test_tracking_raw_capture.py -v
```

The runner's timeout kills and waits for its one inference child. Completed
JSONL records are retained and independently replayed even on timeout/failure;
partial results explicitly list captured/replayed counts and cannot claim full
coverage. A truncated final row is ignored, not manufactured. This run completed
all four windows with post-run provenance verification. No parameter change is
recommended: the next useful input is this preserved proposal/appearance stream
for controlled appearance-aware association research and eventual adjudication.
