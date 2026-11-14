"""Time-local observation evidence for the isolated assist experiment, not identity truth."""

from math import hypot


def pixel_hold_evidence(run, vote_min, vote_sure):
    """Recover this hold's pixel vote, not label_holders' final track-wide vote."""
    sample = dict(run)
    vote = sample.get("vote")
    sample["team"] = ("Valley" if vote >= vote_min else
                      "Opponent" if vote <= -vote_min else None) if vote is not None else None
    sample["sure"] = (vote is not None and sample["team"] is not None
                      and abs(vote) >= vote_sure and sample.get("px", 0) >= 0.15)
    return sample


def local_hold_evidence(run, sustained, track_team):
    """Require the quick hold's entire interval to have its own pixel evidence.

    A track's other holds cannot certify this interval: IDs can switch people.
    Partial overlaps and contradictory samples remain uncertain. No alias is inferred.
    """
    overlaps = [sample for sample in sustained if sample["tid"] == run["tid"]
                and sample["t0"] <= run["t1"] and run["t0"] <= sample["t1"]]
    covering = [sample for sample in overlaps
                if sample["t0"] <= run["t0"] and run["t1"] <= sample["t1"]]
    teams = {sample.get("team") for sample in overlaps}
    referee = any(sample.get("ref") for sample in overlaps)
    certain = (bool(covering) and len(teams) == 1 and None not in teams and not referee
               and all(sample.get("sure") is True for sample in overlaps))
    team = next(iter(teams)) if len(teams) == 1 else None
    if not overlaps:
        team = track_team(run["tid"])
    return {"team": None if referee else team, "sure": certain, "ref": referee,
            "team_evidence": "local_pixel_hold" if certain else "unverified_interval",
            "evidence_intervals": [[sample["t0"], sample["t1"]] for sample in overlaps]}


def shooter_hold_observation(shooter_id, hold, observations, shot_time):
    """Report geometry/timing, never promote proximity or co-visibility to player truth."""
    samples = []
    for observation in observations:
        if not hold["t0"] <= observation["t"] <= shot_time:
            continue
        shooter = [player["box"] for player in observation.get("players", []) if player["tid"] == shooter_id]
        holder = [player["box"] for player in observation.get("players", []) if player["tid"] == hold["tid"]]
        if len(shooter) != 1 or len(holder) != 1:
            continue
        first, second = shooter[0], holder[0]
        distance = hypot((first[0] + first[2] - second[0] - second[2]) / 2,
                         (first[1] + first[3] - second[1] - second[3]) / 2)
        scale = max(1, first[3] - first[1], second[3] - second[1])
        if distance > scale:
            samples.append(observation["t"])
    return {"hold_track": hold["tid"], "hold_interval": [hold["t0"], hold["t1"]],
            "release_to_shot": shot_time - hold["t1"],
            "track_relation": "same_track_unverified" if shooter_id == hold["tid"] else
                              "separated_covisible_tracks" if samples else "unresolved_tracks",
            "separated_sample_times": samples,
            "identity_verified": False, "team_evidence": hold.get("team_evidence", "unspecified"),
            "hold_team": hold.get("team"), "hold_sure": hold.get("sure") is True,
            "hold_referee": bool(hold.get("ref")), "contested_share": hold.get("contested", 0),
            "image_travel_body_heights": hold.get("travel")}
