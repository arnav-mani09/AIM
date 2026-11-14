# Blind targeted film evidence review — 2026-11-12

## Status and scope

**Reviewer type: model. Development-agent-reviewed provisional observations, not independent human adjudication or final ground truth. Second independent human adjudication is required before any release/evaluation ground-truth claim.**

Reviewed only the six supplied development windows, totaling 111 source seconds. Selection was targeted, not random or held out; this review estimates **no general accuracy**, model precision/recall, or season/game totals. No predictions, prior assist/rebound decisions, scoreboard event JSON, or prior agent verdicts were read, either before freezing or afterward. Only original film and manually inspected original visible scoreboard pixels informed observations. No inference pipeline, external uploads, packages, training, source edits, or subagents were used.

**Output: 28 observable-fact records and 11 unknown-question records across six windows.** Records can bundle related observations/questions; these are not independent events or a statistical denominator. Unknowns remain null, never negative labels. Seven local shooting motions are described; repeated facts about a shot are not additional shots.

## Frozen private artifacts

All evidence is under the existing gitignored directory `ml/data/labels/blind_film_review_20261112/`. Do not force-add the JSON, images, or film to git.

- `observations.frozen.json`: observations, unknowns, per-fact confidence/limitations, local participant descriptions, source-time uncertainty ranges, exact evidence paths, blindness declaration, and per-window/per-stat reviewability.
- `provenance.json`: original paths, full SHA-256 hashes, byte sizes, modification timestamps, ffprobe stream/format metadata, requested windows, and overview extraction details.
- `freeze_manifest.json`: SHA-256 manifest covering 666 private artifacts at freeze, including observations, provenance, extraction scripts, 597 chronological frame JPEGs, 49 contact sheets, and original-scoreboard crops/mosaic.
- `extract_evidence.py`, `refine_evidence.py`, `check_evidence.py`: one-off evidence extraction records, not a new model/framework. `freeze_observations.py` records the authored review and refuses to overwrite frozen labels.

Frozen at **2026-11-13 04:46:38 UTC**, which is **2026-11-12 20:46:38 America/Los_Angeles**. Observations SHA-256: `104745f1dd070bf705e63a628555f2353eed95f0d62a2b014d152fa9b90420cd`.

| Original film under `backend/sample_data/` | Bytes | Duration | SHA-256 |
| --- | ---: | ---: | --- |
| `Valley Christian vs Archbishop Mitty CCS - Tactical.mp4` | 3,998,370,571 | 6304.016009 s | `752d9f3d391acca7ccaffd624c2ed5fb8802c8cde1e1fcd994e80ac4d9ff1061` |
| `Valley Christian vs Archbishop Riordan - Tactical.mp4` | 3,777,488,836 | 5956.015102 s | `6cb6e0d81257fcdae38ef06d30802f163732b49c9571c309d8c50d967456700c` |

Both originals have 1920×1080 H.264 video at 30 fps and AAC audio. Audio was not reviewed. Hashes were computed before visual labeling; metadata and evidence remained local.

## Evidence findings

Times below are **source-file seconds**, not game clock. Participants are local descriptions, not global identities, tracker IDs, detection aliases, or roster numbers. School identity is assigned only where readable scoreboard change supports the visible scoring side.

### Mitty 240–260 s — physical basket versus counted play

- White far/right-wing player passes to tall white lane cutter: pass release **251.2–251.7**, controlled catch **251.6–252.1**. White cutter shoots **252.6–253.0**. Confidence: medium for chain, high for shooting jersey/release motion.
- Consecutive source-rate frames show ball rattling on the rim and exiting through the net **254.4–254.7**. This is a physical net-through, not a missed-shot rebound. Confidence: high; counted/live-ball status remains unknown.
- Original visible inset is **0–0 at both 240 and 255.5**. Officials gesture before the shot and action stops afterward. Do **not** infer counted points, a miss, or an official assist from this alone. Whether the attempt was live/countable genuinely needs officiating/scoring context.
- Evidence: `mitty_240_260/sheet_02.jpg`, `detail_mitty_250_255/sheet_01.jpg`, `detail_mitty_250_255/sheet_02.jpg`, `burst_mitty_254.1_254.7/sheet_01.jpg`, `score_mitty_240.png`, `score_mitty_255.5.png`. All paths relative to the private directory. Facts `M240-F1`–`F4`; unknowns `M240-U1`–`U2`.

### Mitty 995–1018 s — entry pass, extended post creation, net-through

- Blue near/right-sideline player enters ball to tall blue post receiver in neon-green shoes: pass **1009.3–1009.8**, catch/control **1009.8–1010.4**. Receiver pivots/fakes and dribbles over several seconds, then shoots **1015.2–1015.6**. Confidence: high; no official assist decision.
- Source-rate rim sequence shows ball exiting the net **1016.5–1016.7**, followed by white catching overhead **1016.6–1016.9**. This particular white collection is **post-net collection, not evidence of a missed-shot rebound**. Confidence: high.
- Inset remains **11–6 at 1017.5**, very near the interval end. Physical make is visible; score entry is not verified. Score delay is not a miss label. Extended receiver-created action makes official assist credit a scorer-convention question, not simply a pass-within-time-window fact.
- Evidence: `detail_mitty_1009_1017/sheet_01.jpg`–`sheet_03.jpg`, `burst_mitty_1016.1_1016.9/sheet_01.jpg`, `burst_mitty_1016.1_1016.9/sheet_02.jpg`, `score_mitty_1017.5.png`. Facts `M995-F1`–`F4`; unknowns `M995-U1`–`U2`.

### Mitty 1138–1158 s — blue wing three, not lane-player shot/rebound

- Shooter is the **blue far/left-wing player beside the bench**, not a blue player under the basket. Control is visible before the release; release **1149.3–1149.6**. Confidence: high for release/jersey; medium for exact pre-shot ball control.
- Ball descends at/through basket **1151.0–1151.5**, official raises both arms, and original inset changes **Mitty 14 / Valley Christian 6 → 14 / 9** between 1138 and 1155. This supports a **Valley Christian three-point make**. Confidence: high, with scoreboard corroboration.
- White retrieves behind the right baseline and starts left afterward; this is not evidence of a missed-shot rebound. Exact final pass/catch preceding the shot is not frozen tightly enough to assign a passer or official assist.
- Evidence: `burst_mitty_1147.5_1149.7/sheet_02.jpg`–`sheet_04.jpg`, `detail_mitty_1149_1153/sheet_01.jpg`, `detail_mitty_1149_1153/sheet_02.jpg`, `score_mitty_1138.png`, `score_mitty_1155.png`. Facts `M1138-F1`–`F4`; unknowns `M1138-U1`–`U2`.

### Riordan 850–870 s — contested recovery, then white rim finish

- Blue far-baseline player shoots toward right basket **859.4–860.1**; consecutive frames show rim rejection into reaching players **860.6–861.2**. Confidence: medium for release timing, high for miss trajectory.
- Blue short-haired player in neon-green shoes pulls ball inward **861.1–861.6**, but white reaches into the same space. **Exclusive blue control is unresolved**, not automatically a tip and not automatically a credited offensive rebound. White later emerges and dribbles, with white control established **862.0–862.9**. Confidence: medium for contested gather, high for later white control.
- White red-shoed runner receives advancing ball **865.1–865.8**, attacks the left rim, and finishes **866.2–866.7**. Source-rate frames show ball put into and exiting below the net. Blue then collects after the physical make; **not a missed-white-shot rebound**. Confidence: high for physical finish, medium for first blue collection grip.
- Visible inset still reads **2–4 at 868**; score entry and fastbreak passer/official assist are not certified. No miss is inferred from unchanged score. Passer linkage needs bounded visual follow-up; rebound-versus-steal attribution at the earlier contested gather may need genuine human expertise or another angle.
- Evidence: `detail_riordan_857_863/sheet_01.jpg`, `detail_riordan_857_863/sheet_02.jpg`, `burst_riordan_860.6_861.6/sheet_01.jpg`, `burst_riordan_860.6_861.6/sheet_02.jpg`, `detail_riordan_865_868/sheet_01.jpg`, `burst_riordan_866.2_866.9/sheet_01.jpg`, `burst_riordan_866.2_866.9/sheet_02.jpg`, `score_riordan_868.png`. Facts `R850-F1`–`F7`; unknowns `R850-U1`–`U2`.

### Riordan 3605–3620 s — short interior pass/catch/finish

- White driving guard transfers to a different white red-shoed cutter under right basket: pass **3612.4–3613.0**, catch **3612.7–3613.2**, shot release **3613.0–3613.5**. Confidence: medium for overlapping pass/catch, high for visible white finishing side. Overlapping uncertainty ranges do not assert an impossible chronological order.
- Original inset changes **Crusaders 27 / Warriors 27 → 29 / 27** between 3605 and 3617 after the finish, supporting a **Crusaders two-point basket** and locally identifying scoring white side. Confidence: high.
- Blue holds behind right baseline for restart, not a missed-shot rebound. Temporal pass/catch/finish chain is observable; official assist remains a separate human convention decision.
- Evidence: `detail_riordan_3612_3616/sheet_01.jpg`, `detail_riordan_3612_3616/sheet_02.jpg`, `score_riordan_3605.png`, `score_riordan_3617.png`. Facts `R3605-F1`–`F4`; unknown `R3605-U1`.

### Riordan 4415–4428 s — catch/shot/miss, contested touches, later blue control

- White far/left-wing player passes **4420.4–4420.9** to white near/right-wing receiver, who controls **4420.9–4421.3** and shoots **4421.5–4421.9**. Confidence: high; exact two/three-point foot/line relationship remains unknown.
- Source-rate frames show ball rebounding right from rim **4422.7–4423.4**, then contested touches/displacement **4423.3–4424.4**. An airborne touch does not by itself establish secure control. Confidence: high for miss, medium for touching participants/control onset.
- Blue player emerging at right baseline establishes retained control **4424.4–4425.4**, then blue outlets. This establishes later **blue team control**, not a certified first individual rebounder. Earlier grip/touch attribution remains unknown; no global identity inferred.
- Evidence: `detail_riordan_4420_4426/sheet_01.jpg`, `detail_riordan_4420_4426/sheet_02.jpg`, `burst_riordan_4422.7_4423.9/sheet_01.jpg`, `burst_riordan_4422.7_4423.9/sheet_02.jpg`, `riordan_4415_4428/sheet_03.jpg`. Facts `R4415-F1`–`F5`; unknowns `R4415-U1`–`U2`.

## Reviewability and uncertainty

**For every window, full-stat-interval certification is false for shots, assists, and rebounds.** All requested time was sampled chronologically at 2 Hz, but the entire interval was not watched as full-motion video. Relevant details were inspected at 5 Hz and selected short bursts at source rate through the image tool. A contact sheet establishes sampled temporal evidence, not exhaustive absence of intervening events.

Each window starts during an existing possession and ends before a following possession/restart is complete. Thus **no boundary-truncated possession is certified complete**. Local releases, catches, physical outcomes, later control, and two scoreboard increments can be reviewable even when whole-possession totals or official credit are not. Per-window, per-stat limitations are explicit in JSON; no unknown is substituted with zero/false.

Nominal sample uncertainty is up to ±0.5 s for overview frames, ±0.2 s for detail samples, and conservatively ±0.1 s for source-rate bursts including extraction alignment. Reported timing ranges are conservative visual brackets, not calibrated probability intervals. Spatial overlap, compression, camera pans and crop edges limit exact hand-ball moments. No audible whistles or alternate cameras were used.

## What actually needs human expertise

- **Live/countable-play interpretation:** Mitty 246–260, particularly the physical net-through around 254.5 with 0–0 still displayed. This is not safely solved by a score-change heuristic.
- **Control/credit interpretation:** Riordan 861.0–862.9 (blue gather versus white recovery; rebound-then-steal versus contested rebound), and 4423.3–4425.4 (first individual credited recovery after touches). Some individual attribution may remain unobservable even to a human without another angle.
- **Official assist convention, only if official credits are needed:** the four observed local pass/shot sequences, especially the extended Mitty post possession; the Riordan fastbreak also needs passer evidence first. Raw temporal facts can be retained without forcing those credits.
- **Not specialized coaching work:** bounded later-score confirmation for Mitty 1016 and Riordan 866; clarifying the Mitty wing's preceding catch and Riordan fastbreak passer; a native-resolution foot/line crop for the Riordan wing attempt. These are evidence-visibility tasks, not reasons to ask a coach to label 73 cases.

This pass requests **no new coach labeling campaign**. If these particular provisional labels are promoted for release, all retained claims still need the required second human adjudication; prioritize the short ambiguities above rather than treating model review as final truth. No model-comparison verdict or general accuracy claim is made.

## Validation

Parsed frozen JSON, checked all cited evidence paths, and verified all 666 manifest hashes after extraction completed. Existing `ml/data/` ignore coverage protects raw images and private labels. Only this new report and the new private artifact directory were authored; unrelated shared-checkout changes were left alone.
