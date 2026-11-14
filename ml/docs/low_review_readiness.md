# Low-review box scores: readiness and acceptance

Updated November 13, 2026. The product objective is to remove coaches' stat-entry
work, not turn them into required annotators or full-game reviewers. Development
labeling and diagnostic review belong to the development team. Optional coach
correction is a recovery feature, not evidence of automated accuracy.

## What is demonstrated

- Points: the current cache-only development replay matches 43 of 53 scored
  events at Mitty and 52 of 61 at Riordan, with seven unmatched predicted makes
  in each game. This is scoring-event matching, not total-points, three-point,
  player-credit or generalization accuracy. The quick-putback fix recovers one
  film-supported Riordan score without losing previous matches.
  Follow-up inspection did not justify a safe dead-ball rule change. Motion,
  camera behavior and net trajectories overlap between awarded and disallowed
  baskets; changing the veto alone recovers some scores but admits additional
  unmatched makes. Temporal release/official-signal/award evidence is needed.
- Rebounds: seven targeted team-outcome examples have film-supported labels.
  The parent follow-up matches all seven after fixing conflicting-color handling.
  The sample influenced development; full-game event accuracy is unknown.
  Most events still use inferred or otherwise weak evidence. Correct guesses
  are not observed player control.
- Assists: there are no independently adjudicated assist/no-assist labels.
  The isolated detector largely abstains because shooter/holder identity or
  pass-flight evidence is insufficient. Assists remain hidden and the experiment
  is not wired into production.
  The identity investigation found cross-player track contamination in inspected
  sequences. Time-local evidence now replaces track-wide certainty in the
  experimental adapter; no player aliases were defensibly established. These
  fixes do not create assist ground truth or demonstrate an accuracy gain.
  Current assist replays also use shot caches of unverified source provenance,
  predating the current shot code, rather than an end-to-end refreshed pipeline.
  A subsequent blind model review found visible rim rejection at Riordan
  4422.7–4423.4 seconds, contradicting the made-shot input at 4422.8 seconds
  underlying the experiment's sole Riordan assist candidate. The current-source
  scoring audit also predicts this make, so stale assist inputs alone do not
  explain the discrepancy. This provisional finding is not human-adjudicated
  truth; see `blind_review_crosscheck.md`. The candidate is not evidence of
  successful assist detection, and the first credited rebounder remains unknown.
- Current confidence scores are heuristic tiers, not calibrated probabilities.
  A high score cannot justify automatic certification without validation.
- A controlled 1280-input detector experiment on the same 44 development stills
  produced mixed annotation agreement, losing some previously matched balls and
  adding unmatched detections. It does not justify a production resolution
  increase or establish improved points/rebounds/assists. Parent verification
  reproduced its complete-set metrics and comparison and verified both frozen
  manifests; the six variant and twelve baseline regression tests pass.
  See `detector_resolution_eval.md` for the full tradeoff and latency protocol.

Both Mitty and Riordan influenced development. No untouched-game claim can be
made for either, and there is no measured coach-time reduction yet. Passing
regression tests does not establish basketball accuracy.

## Engineering priorities

### Rescan decision: stop standalone correction experiments

The predetermined safety batch (`rim_rescan_safety.md`) fails the release case
for source-rate-only automatic correction or suppression. No additional
false-make correction witness was found; sparse phases can reject provisional
makes, and a free throw remains unknown despite complete decoded footage.
Repeated same-view sampling does not resolve missing identity, control, depth,
or official-credit evidence. Do not continue this sampler as a substitute for
better temporal evidence or independently adjudicated validation, and do not
promote the earlier pilot counterfactual to current product accuracy. Production
remains unchanged. Development-owned work should now address tracker continuity
and temporal event evidence rather than add a coach review queue.

### Tracker decision: no buffer-only identity fix

`tracker_continuity_eval.md` verifies the pinned tracker's buffer scaling and
activation semantics. Its actual-tracker synthetic experiments also show that
longer retention can assign a stale identity to a different person. The four
cached-window replays are incomplete because the cache contains post-tracker
boxes rather than every detector proposal. Neither the parameter mismatch nor
more emitted boxes establishes better real identity continuity. Do not change
production retention/activation settings on this evidence. Further association
work needs provenance-bound pre-tracker proposals and time-local appearance,
with independent identity/control labels before player-credit accuracy claims.

The fresh raw capture now permits exact input/output replay. The subsequent
`tracking_association_trace.md` isolates one continuation failure to the
predicted-geometry gate plus new-track confirmation delay, and one
appearance-inconsistent region migration to near-tied high-stage geometry costs.
Neither originates in the final public rematch. All captured outputs reproduce;
this establishes causal mechanisms, not independently adjudicated player links
or a safe identity fix. Simple torso-color medians do not resolve the inspected
overlap. More buffer/threshold sweeps are not the next accuracy step; distinct
body-part/appearance and multi-frame evidence must be validated against actual
person identities and stale-replacement counterexamples.

1. Preserve event-level baselines and fix the observed scoring errors, including
   false dead-ball vetoes, missed attempts, and FG/FT classification. Evaluate
   made-shot value and team attribution jointly with event detection.
2. Improve ball continuity, camera-motion handling, player-track continuity and
   shooter-to-holder identity. These shared inputs constrain rebounds and assists.
3. Build independently reviewed positive, negative and uncertain sequences from
   complete possessions, including events the detector never proposed. Predicted
   made-shot opportunities alone cannot measure whole-game assist recall.
4. Validate on additional games and camera conditions with a frozen version.
   Establish previous use before calling any game held out. Do not tune on the
   test game or use matching box-score totals as event truth.
5. Use automatic cross-checks and a targeted second pass on uncertain sequences.
   Neither smoothing totals nor withholding difficult events establishes complete
   stats. Missing footage/control should remain explicit, not silently fabricated.

## Measure actual remaining work

Before claiming near-zero coach review, measure on complete independently labeled
games, with team and player results separated:

- Missed real events and false events per game for each stat, plus precision and
  recall. Report unobservable and unreviewed intervals separately.
- Wrong team, wrong player, wrong shot value, and incorrect scoring credit.
- Unflagged errors among automatically accepted events, not just errors in the
  review queue. Confidence calibration needs both clean and difficult examples.
- Required correction count, mandatory review clips, total clip duration,
  actual active coach time, and turnaround; compare with the existing workflow.
- Automatic output coverage. Hiding all uncertain events can reduce apparent
  errors while making a box score incomplete.

Agree on a coach-time budget and tolerated per-game errors before a release
claim. A mandatory full-game review fails the product objective even if it yields
an accurate corrected box score. A zero-review promise is not supported by current
evidence; an elapsed-time delivery estimate would be speculative until complete
game validation identifies the remaining error burden.
