"""Conservative, offline pass -> catch -> made-FG candidates, not certified assists.

No pipeline imports or writes. Runs use possession.hold_runs' dictionaries, including
unknown/referee holds. Observations are {t, ball: [x, y] | None, players:
[{tid, box: [x0, y0, x1, y1]}]}. All coordinates must share a pixel space.
Team certainty must be supplied on runs as sure=True; identity aliases may be
provided explicitly. Track IDs never establish jersey/player identity.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from math import hypot

from assist_identity import shooter_hold_observation


@dataclass(frozen=True)
class AssistConfig:
    pass_air_min: float = 0.15
    pass_air_max: float = 1.5
    assist_window: float = 4.0
    catch_to_shot_max: float = 2.5
    release_to_shot_max: float = 1.8
    shooter_hold_max: float = 1.5
    shooter_travel_max: float = 0.8
    merge_gap: float = 0.35
    min_separation: float = 1.0
    min_flight_samples: int = 2
    min_progress: float = 0.15
    flight_start_max: float = 0.4
    flight_end_min: float = 0.6
    flight_gap_max: float = 0.35
    max_contested: float = 0.5

    def __post_init__(self):
        for name, value in vars(self).items():
            if not isinstance(value, (int, float)) or not 0 <= value < float("inf"):
                raise ValueError(f"Invalid {name}")
        if (self.pass_air_min > self.pass_air_max or self.min_flight_samples < 2
                or not isinstance(self.min_flight_samples, int)
                or not 0 < self.flight_start_max < self.flight_end_min < 1):
            raise ValueError("Invalid flight bounds")


def center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def height(box):
    return max(1.0, box[3] - box[1])


def contains(box, point):
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _merge_runs(runs, config):
    merged = []
    for original in sorted(runs, key=lambda run: (run["t0"], run["t1"])):
        run = dict(original)
        if run["t1"] < run["t0"]:
            raise ValueError("Hold ends before it starts")
        run["travel"] = hypot(*(end - start for start, end in zip(center(run["first"]), center(run["last"])))) / height(run["first"])
        if merged:
            prev = merged[-1]
            gap = run["t0"] - prev["t1"]
            if (0 <= gap <= config.merge_gap and run["tid"] == prev["tid"]
                    and run.get("team") == prev.get("team") and run.get("ref") == prev.get("ref")):
                jump = hypot(*(end - start for start, end in zip(center(prev["last"]), center(run["first"])))) / height(prev["last"])
                prev["travel"] += jump + run["travel"]
                prev.update(t1=run["t1"], last=run["last"], n=prev.get("n", 0) + run.get("n", 0),
                            sure=prev.get("sure") is True and run.get("sure") is True,
                            contested=max(prev.get("contested", 0), run.get("contested", 0)))
                if "team_evidence" in prev or "team_evidence" in run:
                    prev["team_evidence"] = "local_pixel_hold" if prev["sure"] else "unverified_interval"
                    prev["evidence_intervals"] = prev.get("evidence_intervals", []) + run.get("evidence_intervals", [])
                continue
        merged.append(run)
    return merged


def _flight(passer, shooter, observations, config):
    progress = []
    for observation in observations:
        ball = observation.get("ball")
        boxes = {player["tid"]: player["box"] for player in observation.get("players", [])}
        if ball is None or passer["tid"] not in boxes or shooter["tid"] not in boxes:
            continue
        origin_box, target_box = boxes[passer["tid"]], boxes[shooter["tid"]]
        if contains(origin_box, ball) or contains(target_box, ball):
            continue
        origin, target = center(origin_box), center(target_box)
        delta = [end - start for start, end in zip(origin, target)]
        length = hypot(*delta)
        scale = max(height(origin_box), height(target_box))
        if length < config.min_separation * scale:
            continue
        fraction = sum((value - start) * direction for value, start, direction in zip(ball, origin, delta)) / length ** 2
        lateral = abs((ball[0] - origin[0]) * delta[1] - (ball[1] - origin[1]) * delta[0]) / length
        if 0.05 <= fraction <= 0.95 and lateral <= 0.6 * scale:
            progress.append((observation["t"], fraction))
    unique = sorted(dict(progress).items())
    valid = (len(unique) >= config.min_flight_samples
             and unique[0][1] <= config.flight_start_max
             and unique[-1][1] >= config.flight_end_min
             and unique[-1][1] - unique[0][1] >= config.min_progress
             and all(after[0] - before[0] <= config.flight_gap_max for before, after in zip(unique, unique[1:]))
             and all(after[1] >= before[1] - 0.1 for before, after in zip(unique, unique[1:])))
    return unique if valid else []


def detect_assists(split, runs, observations=(), config=None, identity_map=None):
    """Return compatible ast events plus one auditable decision per predicted made FG.

    Abstains on missing shooter/team/flight evidence, intervening unknown holds,
    rebounds, short handoffs, same/aliased IDs, long catches and fragmented drives.
    Does not fall back to the latest teammate when shooter_track is unavailable.
    Thresholds are development heuristics, not calibrated probabilities.
    """
    config = config or AssistConfig()
    identity_map = identity_map or {}
    holds = _merge_runs(runs, config)
    observations = sorted(observations, key=lambda item: item["t"])
    times = [item["t"] for item in observations]
    shots = sorted(split["shots"], key=lambda shot: shot["t"])
    events, decisions, seen = [], [], set()
    for shot in shots:
        if shot.get("kind") != "FG" or shot.get("made") is not True:
            continue
        shot_time, team, shooter_id = shot["t"], shot.get("team"), shot.get("shooter_track")
        key = (shot_time, team)
        if key in seen:
            continue
        seen.add(key)
        decision = {"shot_t": shot_time, "team": team, "shooter_track": shooter_id, "status": "abstain"}
        decisions.append(decision)

        def reject(reason):
            decision["reason"] = reason

        if team is None or shooter_id is None:
            reject("unknown_shooter_or_team")
            continue
        nearby = [hold for hold in holds if shot_time - config.assist_window <= hold["t1"]
                  and hold["t0"] < shot_time]
        if not nearby:
            reject("no_shooter_hold")
            continue
        shooter = nearby[-1]
        decision["shooter_hold_observation"] = shooter_hold_observation(
            shooter_id, shooter, observations[bisect_left(times, shooter["t0"]):bisect_right(times, shot_time)], shot_time)
        if shooter["tid"] != shooter_id or shooter["t1"] > shot_time:
            reject("shooter_hold_mismatch")
            continue
        if (shooter.get("ref") or shooter.get("team") != team or shooter.get("sure") is not True
                or shooter.get("contested", 0) >= config.max_contested):
            reject("uncertain_shooter_hold")
            continue
        if (shot_time - shooter["t1"] > config.release_to_shot_max
                or shot_time - shooter["t0"] > config.catch_to_shot_max
                or shooter["t1"] - shooter["t0"] > config.shooter_hold_max
                or shooter["travel"] > config.shooter_travel_max):
            reject("drive_or_stale_catch")
            continue
        if len(nearby) < 2:
            reject("no_preceding_hold")
            continue
        passer = nearby[-2]
        decision.update(passer_track=passer["tid"], pass_t=passer["t1"], catch_t=shooter["t0"])
        if (passer["tid"] == shooter_id or identity_map.get(passer["tid"], passer["tid"])
                == identity_map.get(shooter_id, shooter_id)):
            reject("same_player_or_track_switch")
            continue
        if (passer.get("ref") or passer.get("team") != team or passer.get("sure") is not True
                or passer.get("contested", 0) >= config.max_contested):
            reject("intervening_or_uncertain_holder")
            continue
        gap = shooter["t0"] - passer["t1"]
        if not config.pass_air_min <= gap <= config.pass_air_max:
            reject("handoff_overlap_or_long_gap")
            continue
        if any(passer["t1"] <= other["t"] < shot_time for other in shots if other is not shot):
            reject("intervening_shot_or_rebound")
            continue
        segment = observations[bisect_right(times, passer["t1"]):bisect_left(times, shooter["t0"])]
        flight = _flight(passer, shooter, segment, config)
        if not flight:
            reject("no_distinct_player_ball_flight")
            continue
        decision.update(status="candidate", reason="bounded_pass_catch_make", flight=flight)
        events.append({"type": "ast", "team": team, "t": passer["t1"], "shot_t": shot_time,
                       "passer_track": passer["tid"], "shooter_track": shooter_id, "track": passer["tid"],
                       "catch_t": shooter["t0"], "player": None, "player_conf": 0.0,
                       "identity_status": "track_only_unverified", "review_status": "unreviewed",
                       "method": "bounded_pass_catch_v1"})
    return {"events": events, "decisions": decisions}
