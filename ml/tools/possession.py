"""Team possession, rebounds, turnovers, steals and assists from a tracks file and its shots.

Usage:
    ml/.venv/bin/python ml/tools/possession.py ml/data/tracks/valley-vs-archbishop-mitty.v4.json \
        --game valley-vs-archbishop-mitty --video "backend/sample_data/<game>.mp4" [--sheets] [--method v1]

Reads <tracks>.json, <tracks>.split.json (shot_split.py) and <tracks>.window.json
(game_window.py), writes <tracks>.possession.json, and prints the totals next to the Hudl box
score when the game has one. --video reads each ball holder's jersey color from the film (about
90 s a game, cached in <tracks>.holders.json); without it the tracker's team split is used.
--sheets writes zoomed check sheets of each event type and of 30 random moments.

Version 2 (default), rules, not a model:
- Who holds the ball. In each frame the player whose box holds the ball (sideways, from the
  chest down to a dribble at the feet) has it; a hold counts when the same player keeps it for
  HOLD_RUN_MIN frames. Player boxes that are really a referee are skipped.
- Their team. The holder's torso color is read from the film. The two jersey colors are learned
  from this game's holders, and each track votes over all its holds (plus the tracker's team
  split), because one hold's crop can catch the floor or the defender. Striped shirts are
  referees.
- Team with the ball over time: each frame of a hold is evidence for the holder's team, the
  basket on screen is weak evidence, and a change costs SWITCH_COST (Viterbi, per half). Touches
  under BLIP seconds with no shot are merged away. Changes land when the other team first has
  the ball, not when the camera crosses half court.
- Rebound: the first clearly-colored holder after a live miss. The same team shooting again at
  the same basket is an offensive rebound; a referee first is a team rebound (not counted);
  nobody seen means the defense.
- Turnover: a change of possession not explained by a make, a defensive rebound, free throws, a
  period break, a timeout or a ball that went to the rim. Steal: one with no referee handling the
  ball just before (after violations and out-of-bounds the official hands it to the inbounder).
- Assist: the hold just before the shooter's catch belongs to a teammate at least a body height
  away, within PASS_AIR_MAX of the catch and ASSIST_WINDOW of the shot. Uses 2-frame holds too.

Version 1 (--method v1) took the team with the ball from which basket the camera shows. It lags
real changes by 4 to 8 s.

Status (Nov 11): tuned on Mitty, checked untouched on Riordan. Possession at random live
moments, clear cases: v2 right 31 of 40 (v1 25 of 40). Rebounds are close on Riordan; turnovers
are still the weakest (fake possession changes when a defender is boxed with the ball or a
missed shot isn't found).
"""

import argparse
import json
import random
import statistics as st
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot_split import frame_at, jersey_groups, motion, players  # noqa: E402
from shots import best_ball, ceiling_line, game_rims  # noqa: E402

ML = Path(__file__).resolve().parents[1]
SWITCH_HOLD = 2.0     # seconds the play must stay at the other basket before it's a new possession
DREB_DELAY = 15.0     # a miss followed by a change of basket within this many seconds is a defensive rebound.
                      # Mitty: clean rebounds take 4 to 8 s to cross; 10 to 14 s ones were slow walk-ups
LONG_STOP = 40.0      # a change after this long with play stopped is a period change, not a turnover
DEAD_MOTION = 0.12    # players' movement below this means play stopped (live play is 0.3 to 0.7)
STEAL_LOOK = (4.0, 1.0)  # window for the movement number kept on each turnover (not used to decide)
REF_LOOK = 12.0       # look this far back from a change for an official handling the ball
HOLD_MIN = 2          # frames (0.2 s) a player must hold the ball to count as a holder
ASSIST_WINDOW = 4.0   # the pass must end within this many seconds before the ball reaches the rim
SHOOTER_HOLD_MAX = 3.0  # a shooter who held the ball longer than this made his own shot
MIN_PLAYERS = 5       # fewer players than this on screen means a timeout or a break, not play

# Version 2: who actually holds the ball.
HOLD_RUN_MIN = 3      # frames (0.3 s) the same player must hold the ball to count as a sustained hold
HOLD_WEIGHT = 1.0     # evidence per frame of a sustained hold for the holder's team
HOLD_WEAK = 0.4       # the same, when the holder's jersey color is close to both teams
CAMERA_WEIGHT = 0.15  # evidence per frame from which basket is on screen (it lags real changes)
SWITCH_COST = 8.0     # evidence needed to start a new possession (Mitty: 4 gave 158 possessions, 8 gave 114; about 130 is right)
PASS_AIR_MAX = 3.0    # longest gap between the passer's hold and the catch (the holds miss some frames)
BLIP = 4.0            # a possession shorter than this, with no shot, between two of the other team's is a touch
REB_LOOK = 8.0        # after a miss, look this long for the first player to get the ball
REF_STRIPES = 3.4     # dark/light changes across a torso row at or above this, with dark pixels, is a referee shirt
REF_DARK = 0.08


def side_per_frame(doc):
    """'L', 'R' or None per frame: which basket is on screen."""
    W, H = doc["frame_size"]
    line = ceiling_line(doc)
    out = []
    for t, boxes in doc["frames"]:
        rims = game_rims(boxes, H, line)
        sides = {"L" if (r[1] + r[3]) / 2 < W / 2 else "R" for r in rims}
        out.append((t, sides.pop() if len(sides) == 1 else None))
    return out


def segments(sides, start, end, hold=SWITCH_HOLD, fps=10):
    """Runs of play at one basket: [t0, t1, side]. A new side must be seen for `hold` seconds
    (counting only frames that show a rim, within twice that time) before it starts a run."""
    runs, cur, cur_t0 = [], None, start
    pending, pending_t0, seen = None, None, 0
    for t, s in sides:
        if t < start or t > end or s is None:
            continue
        if cur is None:
            cur, cur_t0 = s, t
            continue
        if s == cur:
            pending, seen = None, 0
            continue
        if pending != s or t - pending_t0 > 2 * hold:
            pending, pending_t0, seen = s, t, 0
        seen += 1
        if seen >= hold * fps * 0.6:
            runs.append([cur_t0, pending_t0, cur])
            cur, cur_t0, pending, seen = s, pending_t0, None, 0
    if cur is not None:
        runs.append([cur_t0, end, cur])
    return runs


def rim_visits(doc):
    """Times any ball is seen at a game rim: inside the rim's width (with some slack) from four
    rim widths above it to just below it. Looser than the shot finder on purpose: it's used to
    tell a missed shot the finder didn't catch (the ball went to the rim) from a turnover (it
    never did)."""
    H = doc["frame_size"][1]
    line = ceiling_line(doc)
    out = []
    for t, boxes in doc["frames"]:
        rims = game_rims(boxes, H, line)
        if not rims:
            continue
        for b in boxes:
            if b[0] != 0 or b[5] < 0.15:
                continue
            bx, by = (b[1] + b[3]) / 2, (b[2] + b[4]) / 2
            for r in rims:
                w, h = r[3] - r[1], r[4] - r[2]
                if r[1] - 0.6 * w <= bx <= r[3] + 0.6 * w and r[2] - 4 * w <= by <= r[4] + 1.5 * h:
                    out.append(t)
                    break
            else:
                continue
            break
    return out


def team_at(side, t, info):
    """Team attacking the basket on this side of the frame at time t."""
    first = "L" if info["valley_basket_first_half"] == "left" else "R"
    valley_side = first if t < info["halftime"] else ("R" if first == "L" else "L")
    return "Valley" if side == valley_side else "Opponent"


def other(team):
    return "Opponent" if team == "Valley" else "Valley"


def stopped_before(doc, t, span):
    """Seconds of stopped play (players barely moving, or few on screen) just before t."""
    stop, k = 0.0, 1.0
    while stop < span:
        m = motion(doc, t - k - 1.0, t - k, step=0.5)
        if m is not None and m >= DEAD_MOTION and len(players(frame_at(doc, t - k))) >= 5:
            break
        stop, k = stop + 1.0, k + 1.0
    return stop


def pan_speed(doc, t0, t1):
    """Fastest camera pan between t0 and t1, in frame widths per second: the median sideways
    shift of tracked players from one frame to the next (everyone shifts together on a pan)."""
    fps, W = doc["fps"], doc["frame_size"][0]
    best, prev = 0.0, None
    for k in range(int(t0 * fps), int(t1 * fps) + 1):
        if not 0 <= k < len(doc["frames"]):
            continue
        cur = {b[6]: (b[1] + b[3]) / 2 for b in players(doc["frames"][k][1])}
        if prev:
            common = [i for i in cur if i in prev]
            if len(common) >= 3:
                best = max(best, abs(st.median(cur[i] - prev[i] for i in common)) * fps / W)
        prev = cur
    return best


def players_around(doc, t0, t1):
    """Median number of players on screen between t0 and t1."""
    fps = doc["fps"]
    counts = [len(players(doc["frames"][k][1])) for k in range(int(t0 * fps), int(t1 * fps) + 1, 5)
              if 0 <= k < len(doc["frames"])]
    return st.median(counts) if counts else 0


def ref_handled(doc, t0, t1):
    """True when a referee holds the ball for a moment between t0 and t1. On every throw-in after
    a violation or an out-of-bounds ball the official hands the ball to the inbounder, so this
    marks a dead-ball turnover. After a steal play never stops and no official touches the ball."""
    fps, run = doc["fps"], 0
    for k in range(int(t0 * fps), int(t1 * fps) + 1):
        if not 0 <= k < len(doc["frames"]):
            continue
        boxes = doc["frames"][k][1]
        balls = [b for b in boxes if b[0] == 0 and b[5] >= 0.3]
        refs = [b for b in boxes if b[0] == 2 and b[5] >= 0.4]
        held = any(r[1] - 0.15 * (r[3] - r[1]) <= (b[1] + b[3]) / 2 <= r[3] + 0.15 * (r[3] - r[1])
                   and r[2] <= (b[2] + b[4]) / 2 <= r[2] + 0.7 * (r[4] - r[2])
                   for b in balls for r in refs)
        run = run + 1 if held else 0
        if run >= 2:
            return True
    return False


def live_shots(shots):
    """Shots that count, with 'live' marking misses the ball stays in play after (a missed field
    goal, or the last free throw of a trip)."""
    keep = [s for s in shots if s["kind"] in ("FG", "FT", "fouled")]
    for i, s in enumerate(keep):
        nxt = keep[i + 1] if i + 1 < len(keep) else None
        more_fts = (s["kind"] == "FT" and nxt is not None and nxt["kind"] == "FT"
                    and nxt["basket"] == s["basket"] and nxt["t"] - s["t"] <= 30)
        s["live_miss"] = not s["made"] and s["kind"] != "fouled" and not more_fts
    return keep


def possession_events(doc, split, window, half_break):
    start, end = window
    sides = side_per_frame(doc)
    info = {"halftime": split["halftime"], "valley_basket_first_half": split["valley_basket_first_half"]}
    runs = []
    halves = [(start, half_break[0]), (half_break[1], end)] if half_break else [(start, end)]
    for h0, h1 in halves:
        runs += segments(sides, h0, h1)
    for r in runs:
        r.append(team_at(r[2], (r[0] + r[1]) / 2, info))
    shots = live_shots(split["shots"])
    visits = rim_visits(doc)
    events = []
    for i, (t0, t1, side, team) in enumerate(runs):
        mine = [s for s in shots if t0 - 1 <= s["t"] < t1 + 1 and s["team"] == team]
        # Rebounds after misses inside this run that the same team shot again after.
        for a, b in zip(mine, mine[1:]):
            if a["live_miss"]:
                events.append({"type": "oreb", "team": team, "t": a["t"], "shot_t": a["t"]})
            elif a["made"] and not (a["kind"] == "FT" and b["kind"] == "FT" and b["t"] - a["t"] <= 30):
                # Scored, then shot again at the same basket without the play ever leaving it:
                # the other team lost the ball before getting it past half court (a press).
                events.append({"type": "to", "team": other(team), "t": (a["t"] + b["t"]) / 2,
                               "backcourt": True})
        last_run = i + 1 == len(runs) or runs[i + 1][0] - t1 > 5  # end of a half
        if last_run:
            continue
        change_t = t1
        stop = stopped_before(doc, change_t, LONG_STOP + 1)
        last = mine[-1] if mine else None
        if last and last["made"]:
            continue  # scored (field goal or free throw)
        if last and last["live_miss"]:
            if change_t - last["t"] <= DREB_DELAY:
                events.append({"type": "dreb", "team": other(team), "t": last["t"], "shot_t": last["t"]})
                continue
            events.append({"type": "oreb", "team": team, "t": last["t"], "shot_t": last["t"]})
        if last and not last["live_miss"] and not last["made"] and change_t - last["t"] <= DREB_DELAY:
            continue  # missed free throw with more to come, or a fouled shot: ball changes by rule
        if stop >= LONG_STOP:
            continue  # quarter break or jump ball: the ball changes hands by rule
        if players_around(doc, change_t - 8, change_t + 2) < MIN_PLAYERS:
            continue  # timeout or quarter break: the camera wanders over an empty floor
        since = last["t"] + 2 if last else t0
        if any(since <= v <= change_t for v in visits):
            # The ball went to the rim but the shot finder has no attempt there: maybe a missed
            # shot it didn't catch, maybe a pass near the rim. Not a turnover, and no rebound
            # either, since there may have been no shot (Mitty: counting a rebound here added 11
            # rebounds the box score doesn't have).
            continue
        m = motion(doc, change_t - STEAL_LOOK[0], change_t + STEAL_LOOK[1], step=0.5)
        dead = ref_handled(doc, max(since, change_t - REF_LOOK), change_t + 1.0)
        events.append({"type": "to", "team": team, "t": change_t, "stop_before": stop,
                       "motion": None if m is None else round(m, 3), "live": not dead,
                       "pan": round(pan_speed(doc, change_t - 4, change_t + 1), 3)})
        if not dead:
            events.append({"type": "stl", "team": other(team), "t": change_t})
    return runs, events


def holders(doc, start, end):
    """Hold runs [track_id, t0, t1, box_at_end, box_at_start]: who has the ball, frame by frame."""
    fps, prev, runs = doc["fps"], None, []
    cur, cur_t0, cur_first, cur_last, cur_t1, n = None, None, None, None, None, 0
    for t, boxes in doc["frames"]:
        if t < start or t > end:
            continue
        recent = prev[:2] if prev and t - prev[2] <= 0.5 else None
        ball = best_ball(boxes, recent)
        who = None
        if ball is not None:
            bx, by = (ball[1] + ball[3]) / 2, (ball[2] + ball[4]) / 2
            prev = (bx, by, t)
            best = None
            for p in players(boxes):
                x0, y0, x1, y1 = p[1:5]
                h = y1 - y0
                if x0 - 0.15 * (x1 - x0) <= bx <= x1 + 0.15 * (x1 - x0) and y0 - 0.25 * h <= by <= y0 + 0.66 * h:
                    d = abs(bx - (x0 + x1) / 2)
                    if best is None or d < best[0]:
                        best = (d, p)
            if best:
                who = best[1]
        if who is not None and who[6] == cur:
            cur_last, cur_t1, n = who[1:5], t, n + 1
            continue
        if who is not None:
            if cur is not None and n >= HOLD_MIN:
                runs.append([cur, cur_t0, cur_t1, cur_last, cur_first])
            cur, cur_t0, cur_t1, cur_first, cur_last, n = who[6], t, t, who[1:5], who[1:5], 1
        elif cur is not None and t - cur_t1 > 1.0:
            if n >= HOLD_MIN:
                runs.append([cur, cur_t0, cur_t1, cur_last, cur_first])
            cur, n = None, 0
    if cur is not None and n >= HOLD_MIN:
        runs.append([cur, cur_t0, cur_t1, cur_last, cur_first])
    return runs


def assists(doc, split, holds, groups):
    """For each made field goal, the pass (if any) that led to it."""
    team_of = lambda tid: groups.get(doc["tracks"].get(str(tid), {}).get("group"))
    out = []
    for s in split["shots"]:
        if s["kind"] != "FG" or not s["made"]:
            continue
        # The shooter's last hold before the ball reached the rim.
        before = [h for h in holds if h[2] <= s["t"] and h[2] >= s["t"] - 3.0]
        if s.get("shooter_track") is not None:
            mine = [h for h in before if h[0] == s["shooter_track"]]
            before_sh = mine[-1] if mine else (before[-1] if before else None)
        else:
            before_sh = before[-1] if before else None
        if before_sh is None:
            continue
        sh_tid, sh_t0, sh_t1, _, sh_box0 = before_sh
        if sh_t1 - sh_t0 > SHOOTER_HOLD_MAX:
            continue
        earlier = [h for h in holds if h[2] <= sh_t0 + 0.05 and h[0] != sh_tid and h[2] >= sh_t0 - 1.5]
        if not earlier:
            continue
        p_tid, p_t0, p_t1, p_box1, _ = earlier[-1]
        if s["t"] - p_t1 > ASSIST_WINDOW:
            continue
        p_team, sh_team = team_of(p_tid), team_of(sh_tid)
        # Jersey groups are noisy (a defender's box often covers the ball too), so a passer from
        # the other jersey group only rules the pass out when the shooter's own group is right.
        if p_team is not None and p_team != s["team"] and sh_team == s["team"]:
            continue  # came from the other team: a rebound or a steal, not a pass
        h = max(p_box1[3] - p_box1[1], sh_box0[3] - sh_box0[1])
        dist = abs((p_box1[0] + p_box1[2]) / 2 - (sh_box0[0] + sh_box0[2]) / 2) + abs(p_box1[3] - sh_box0[3])
        if dist < h:
            continue  # same spot: probably one player's track broke, not a pass
        out.append({"type": "ast", "team": s["team"], "t": p_t1, "shot_t": s["t"],
                    "passer_track": p_tid, "shooter_track": sh_tid})
    return out


# ---------------------------------------------------------------------------------------------
# Version 2: possession from who actually holds the ball.
#
# Version 1 above times possession by which basket the camera shows, so a change lands when the
# camera crosses half court, 4 to 8 s late. Version 2 finds the player holding the ball in each
# frame, reads that player's jersey color from the film, and gives the ball to that team. The
# camera side only fills in when no one is seen holding the ball.


def _iou(a, b):
    x0, y0, x1, y1 = max(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3]), min(a[4], b[4])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    return inter / ((a[3] - a[1]) * (a[4] - a[2]) + (b[3] - b[1]) * (b[4] - b[2]) - inter)


def hold_runs(doc, start, end, min_frames=HOLD_RUN_MIN):
    """Sustained holds: the same player has the ball for HOLD_RUN_MIN frames or more.
    A player holds the ball when it sits inside their box sideways (a little slack) anywhere from
    the chest down to the feet (a dribble). The box nearest the ball's center wins. Player boxes
    that are really a referee (the detector boxed one person twice) are skipped."""
    seq, prev = [], None
    for k, (t, boxes) in enumerate(doc["frames"]):
        if t < start or t > end:
            continue
        recent = prev[:2] if prev and t - prev[2] <= 0.5 else None
        ball = best_ball(boxes, recent)
        who = None
        if ball is not None:
            bx, by = (ball[1] + ball[3]) / 2, (ball[2] + ball[4]) / 2
            prev = (bx, by, t)
            refs = [b for b in boxes if b[0] == 2 and b[5] >= 0.3]
            best = None
            for p in players(boxes):
                x0, y0, x1, y1 = p[1:5]
                w, h = x1 - x0, y1 - y0
                if not (x0 - 0.1 * w <= bx <= x1 + 0.1 * w and y0 + 0.1 * h <= by <= y1):
                    continue
                if any(_iou(p, r) > 0.5 for r in refs):
                    continue
                d = abs(bx - (x0 + x1) / 2) / w
                if best is None or d < best[0]:
                    best = (d, p)
            if best:
                who = best[1]
        seq.append((k, t, who))
    runs, i = [], 0
    while i < len(seq):
        j = i
        while (j + 1 < len(seq) and seq[i][2] is not None and seq[j + 1][2] is not None
               and seq[j + 1][2][6] == seq[i][2][6]):
            j += 1
        if seq[i][2] is not None and j - i + 1 >= min_frames:
            k, _, who = seq[(i + j) // 2]
            runs.append({"k": k, "t0": seq[i][1], "t1": seq[j][1], "tid": who[6],
                         "box": [round(v) for v in who[1:5]], "first": [round(v) for v in seq[i][2][1:5]],
                         "last": [round(v) for v in seq[j][2][1:5]], "n": j - i + 1})
        i = j + 1
    return runs


def read_holder_colors(doc, runs, video):
    """Reads the middle frame of each hold from the film and stores the holder's torso color
    (median of the brighter half of the torso pixels, so black sleeves and shadows don't pull
    it) and a stripe count for spotting referees. Reads the film once, front to back, keeping
    only the frames needed (about 90 s per game)."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video))
    vfps = cap.get(cv2.CAP_PROP_FPS)
    by_k = {r["k"]: r for r in runs}
    want = sorted((round(doc["frames"][k][0] * vfps), k) for k in by_k)
    if not want:
        return
    vi = max(0, want[0][0] - 1)
    cap.set(cv2.CAP_PROP_POS_FRAMES, vi)
    wi = 0
    while wi < len(want):
        target, k = want[wi]
        if target - vi > 300:  # a long jump: seek instead of reading every frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            vi = target
        while vi < target:
            cap.grab()
            vi += 1
        ok, img = cap.read()
        vi += 1
        while wi < len(want) and want[wi][0] < vi:
            r = by_k[want[wi][1]]
            wi += 1
            if not ok:
                continue
            x0, y0, x1, y1 = r["box"]
            w, h = x1 - x0, y1 - y0
            crop = img[int(y0 + 0.2 * h):int(y0 + 0.5 * h), int(x0 + 0.25 * w):int(x1 - 0.25 * w)]
            if crop.size == 0:
                continue
            lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(float)
            bright = lab[:, 0] >= np.percentile(lab[:, 0], 50)
            r["lab"] = np.median(lab[bright], axis=0).round(1).tolist()
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(float)
            ww = gray.shape[1]
            mid = gray[:, ww // 4: ww - ww // 4] if ww >= 8 else gray
            r["dark"] = round(float((mid < 70).mean()), 3)
            light = (mid > 110).astype(np.int8)
            r["stripes"] = round(float(np.abs(np.diff(light, axis=1)).sum(axis=1).mean()), 2) if mid.shape[1] > 1 else 0.0


def label_holders(doc, runs, groups):
    """Team for each hold. The two jersey colors are learned from this game's holders (two
    color groups over all holds), and each group is named by the tracker's team split of the
    players in it, which is right most of the time. A hold's own color beats its track's team:
    tracks sometimes switch players. Striped shirts are referees (no team). Holds without a
    color (no film) fall back to the track's team."""
    import cv2
    import numpy as np

    colored = [r for r in runs if "lab" in r]
    team_of_track = lambda tid: groups.get(doc["tracks"].get(str(tid), {}).get("group"))
    if len(colored) >= 20:
        X = np.array([[0.3 * r["lab"][0], r["lab"][1], r["lab"][2]] for r in colored], dtype=np.float32)
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
        cv2.setRNGSeed(0)
        _, lab, cent = cv2.kmeans(X, 2, None, crit, 10, cv2.KMEANS_PP_CENTERS)
        lab = lab.ravel()
        votes = np.zeros((2, 2))
        for r, c in zip(colored, lab):
            t = team_of_track(r["tid"])
            if t:
                votes[c][0 if t == "Valley" else 1] += 1
        # Name the groups so the two together agree best with the tracker.
        same = votes[0][0] + votes[1][1] >= votes[0][1] + votes[1][0]
        names = {0: "Valley", 1: "Opponent"} if same else {0: "Opponent", 1: "Valley"}
        d = np.linalg.norm(X[:, None, :] - cent[None], axis=2)
        for r, c, dd in zip(colored, lab, d):
            r["team"] = names[int(c)]
            r["sure"] = bool(abs(dd[0] - dd[1]) >= 6)
    for r in runs:
        if r.get("stripes", 0) >= REF_STRIPES and r.get("dark", 0) >= REF_DARK:
            r["team"], r["ref"] = None, True
    # One player's color can read differently from hold to hold: the torso crop catches the floor
    # or the defender pressed against him. So each track votes once over all its holds, with the
    # tracker's own team for the whole track as one more vote, and every hold takes the result.
    votes = {}
    for r in runs:
        if r.get("ref") or r.get("team") is None:
            continue
        v = votes.setdefault(r["tid"], {"Valley": 0.0, "Opponent": 0.0})
        v[r["team"]] += 1.0 if r.get("sure") else 0.5
    for r in runs:
        if r.get("ref"):
            continue
        v = dict(votes.get(r["tid"], {"Valley": 0.0, "Opponent": 0.0}))
        t = team_of_track(r["tid"])
        if t:
            v[t] += 1.0
        total = v["Valley"] + v["Opponent"]
        if total == 0:
            r["team"], r["sure"] = None, False
            continue
        r["team"] = "Valley" if v["Valley"] > v["Opponent"] else "Opponent" if v["Opponent"] > v["Valley"] else (t or None)
        r["sure"] = r["team"] is not None and max(v.values()) / total >= 0.7 and total >= 1.5

    def track_team(tid):
        """The voted team for any track, including ones never seen in a sustained hold."""
        v = dict(votes.get(tid, {"Valley": 0.0, "Opponent": 0.0}))
        t = team_of_track(tid)
        if t:
            v[t] += 1.0
        if v["Valley"] == v["Opponent"]:
            return t
        return "Valley" if v["Valley"] > v["Opponent"] else "Opponent"
    return track_team


def possession_timeline(doc, runs, sides, info, window, half_break, fps=10):
    """Team with the ball, second by second, as runs [t0, t1, team]. Each frame of a hold is
    evidence for the holder's team, and which basket is on screen is weak evidence for the team
    attacking it. A new possession costs SWITCH_COST, so a one-off wrong color or a defender's
    brief touch doesn't flip it. Solved per half for the best overall sequence (Viterbi)."""
    import numpy as np

    start, end = window
    halves = [(start, half_break[0]), (half_break[1], end)] if half_break else [(start, end)]
    side_at = {round(t, 1): s for t, s in sides}
    out = []
    for h0, h1 in halves:
        n = int(round((h1 - h0) * fps)) + 1
        ev = np.zeros((n, 2))  # evidence for [Valley, Opponent]
        for r in runs:
            if r.get("team") is None or r["t1"] < h0 or r["t0"] > h1:
                continue
            col = 0 if r["team"] == "Valley" else 1
            a, b = max(0, int(round((r["t0"] - h0) * fps))), min(n - 1, int(round((r["t1"] - h0) * fps)))
            ev[a:b + 1, col] += HOLD_WEIGHT if r.get("sure") else HOLD_WEAK
        for i in range(n):
            s = side_at.get(round(h0 + i / fps, 1))
            if s:
                ev[i, 0 if team_at(s, h0 + i / fps, info) == "Valley" else 1] += CAMERA_WEIGHT
        score = ev[0].copy()
        back = np.zeros((n, 2), dtype=np.int8)
        for i in range(1, n):
            new = np.empty(2)
            for st_ in (0, 1):
                stay, switch = score[st_], score[1 - st_] - SWITCH_COST
                back[i, st_] = st_ if stay >= switch else 1 - st_
                new[st_] = max(stay, switch) + ev[i, st_]
            score = new
        path = np.empty(n, dtype=np.int8)
        path[-1] = int(np.argmax(score))
        for i in range(n - 1, 0, -1):
            path[i - 1] = back[i, path[i]]
        i0 = 0
        for i in range(1, n + 1):
            if i == n or path[i] != path[i0]:
                out.append([round(h0 + i0 / fps, 1), round(h0 + (i - 1) / fps, 1),
                            "Valley" if path[i0] == 0 else "Opponent"])
                i0 = i
    return out


def merge_blips(timeline, shots):
    """Removes touches: a possession under BLIP seconds with no shot by that team, sitting between
    two possessions of the other team, is a deflection or a defender's hand on the ball (or a
    wrong color), not a change of possession. The three runs become one."""
    out = [list(r) for r in timeline]
    changed = True
    while changed:
        changed = False
        for i in range(1, len(out) - 1):
            a, b, c = out[i - 1], out[i], out[i + 1]
            if (a[2] == c[2] != b[2] and b[1] - b[0] < BLIP and b[0] - a[1] <= 1.0 and c[0] - b[1] <= 1.0
                    and not any(s["team"] == b[2] and b[0] - 0.5 <= s["t"] <= b[1] + 1.0 for s in shots)):
                out[i - 1:i + 2] = [[a[0], c[1], a[2]]]
                changed = True
                break
    return out


def team_at_time(timeline, t):
    for t0, t1, team in timeline:
        if t0 <= t <= t1 + 0.05:
            return team
    return None


def possession_events_v2(doc, split, window, half_break, runs, timeline):
    """Rebounds from the first player to get the ball after each live miss; turnovers and
    steals from possession changes nothing else explains; all timed at the real moment."""
    shots = live_shots(split["shots"])
    visits = rim_visits(doc)
    holds = sorted((r for r in runs if r.get("team") or r.get("ref")), key=lambda r: r["t0"])
    events = []
    # Rebounds.
    for i, s in enumerate(shots):
        if not s["live_miss"]:
            continue
        nxt = shots[i + 1] if i + 1 < len(shots) else None
        # Only holds whose team is clear count here: one wrong color decides a rebound alone.
        first = next((r for r in holds if s["t"] + 0.3 <= r["t0"] <= s["t"] + REB_LOOK
                      and (r.get("ref") or r.get("sure"))), None)
        again = (nxt is not None and nxt["team"] == s["team"] and nxt["basket"] == s["basket"]
                 and nxt["t"] - s["t"] <= REB_LOOK)
        if again and not any(r.get("sure") and r.get("team") == other(s["team"]) and s["t"] + 0.3 <= r["t0"] < nxt["t"]
                             for r in holds):
            # The same team shot again at the same basket and the other team never clearly had
            # the ball: an offensive rebound (putbacks are often too quick to count as a hold).
            events.append({"type": "oreb", "team": s["team"], "t": s["t"], "shot_t": s["t"]})
            continue
        if first is not None and first.get("ref"):
            continue  # an official has it first: the ball went out of bounds (a team rebound)
        if first is not None:
            team = first["team"]
            t = first["t0"]
        else:
            team, t = other(s["team"]), s["t"]  # nobody seen: the defense usually ends up with it
        events.append({"type": "oreb" if team == s["team"] else "dreb", "team": team, "t": t, "shot_t": s["t"]})
    rebs = {round(e["shot_t"], 1): e for e in events}
    # Turnovers: a change of possession with no make, defensive rebound or dead-ball reason.
    for prev_run, run in zip(timeline, timeline[1:]):
        if run[0] - prev_run[1] > 1.0:
            continue  # halftime gap
        a, change = prev_run[2], run[0]
        mine = [s for s in shots if prev_run[0] - 1 <= s["t"] <= change + 0.5 and s["team"] == a]
        last = mine[-1] if mine else None
        if last and last["made"] and change - last["t"] <= 12:
            continue  # scored, then the other team inbounds
        if last and last["live_miss"]:
            e = rebs.get(round(last["t"], 1))
            if e and e["type"] == "dreb" and abs(e["t"] - change) <= REB_LOOK:
                continue  # defensive rebound
        if last and not last["live_miss"] and not last["made"] and change - last["t"] <= DREB_DELAY:
            continue  # free throws or a fouled shot: the ball changes by rule
        if any(s["kind"] == "FT" and change - 5 <= s["t"] <= change + 30 for s in shots):
            continue  # a foul and free throws: the ball changes by rule, not a turnover
        if stopped_before(doc, change, LONG_STOP + 1) >= LONG_STOP:
            continue  # quarter break or jump ball
        if players_around(doc, change - 8, change + 2) < MIN_PLAYERS:
            continue  # timeout: the camera wanders over an empty floor
        since = last["t"] + 2 if last else prev_run[0]
        if any(since <= v <= change for v in visits):
            continue  # the ball went to the rim: likely a shot the finder missed, not a turnover
        ref_before = any(r.get("ref") and change - 6 <= r["t0"] <= change + 0.5 for r in holds)
        dead = ref_before or ref_handled(doc, change - 6, change + 1.0)
        events.append({"type": "to", "team": a, "t": change, "live": not dead})
        if not dead:
            events.append({"type": "stl", "team": other(a), "t": change})
    return events


def assists_v2(split, runs):
    """A made field goal is assisted when the hold just before the shooter's catch belongs to a
    teammate (a different player, at least a body height away), the ball went straight from one
    to the other (no other hold in between, at most PASS_AIR_MAX apart), the pass ended within ASSIST_WINDOW of the shot, and the
    shooter didn't hold the ball long (a long dribble-drive is his own basket)."""
    holds = sorted((r for r in runs if r.get("team")), key=lambda r: r["t0"])
    out = []
    for s in split["shots"]:
        if s["kind"] != "FG" or not s["made"]:
            continue
        before = [r for r in holds if r["t1"] <= s["t"] and r["t1"] >= s["t"] - 3.0]
        if not before:
            continue
        sh = None
        if s.get("shooter_track") is not None:
            mine = [r for r in before if r["tid"] == s["shooter_track"]]
            sh = mine[-1] if mine else None
        if sh is None:
            mine = [r for r in before if r["team"] == s["team"]]
            sh = mine[-1] if mine else None
        if sh is None or sh["t1"] - sh["t0"] > SHOOTER_HOLD_MAX:
            continue
        earlier = [r for r in holds if r["t1"] < sh["t0"] and r is not sh]
        if not earlier:
            continue
        p = earlier[-1]
        if p["team"] != s["team"]:
            continue  # the ball came from the other team: a rebound or a steal, not a pass
        if sh["t0"] - p["t1"] > PASS_AIR_MAX or s["t"] - p["t1"] > ASSIST_WINDOW:
            continue
        # The same track id on both holds is allowed: the tracker sometimes hands one player's id
        # to the teammate who catches the pass. The distance check below still rules out a
        # player simply holding on.
        pb, sb = p["last"], sh["first"]
        h = max(pb[3] - pb[1], sb[3] - sb[1])
        if abs((pb[0] + pb[2]) / 2 - (sb[0] + sb[2]) / 2) + abs(pb[3] - sb[3]) < h:
            continue  # same spot: probably one player's track broke, not a pass
        out.append({"type": "ast", "team": s["team"], "t": p["t1"], "shot_t": s["t"],
                    "passer_track": p["tid"], "shooter_track": sh["tid"]})
    return out


HUDL_KEYS = {"oreb": "oreb", "dreb": "dreb", "to": "to", "stl": "stl", "ast": "ast"}


def hudl(game_id):
    data = yaml.safe_load((ML / "data/stats/2026-27-hudl-box-scores.yaml").read_text())
    for g in data["games"]:
        if g["id"] == game_id:
            return {"Valley": g["team_totals"]["valley"], "Opponent": g["team_totals"]["opponent"]}
    return None


def sheet(video, events, out, title):
    """Three frames per event (1.5 s before, at, 1.5 s after), one row per event."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video))
    rows = []
    for e in events[:10]:
        tiles = []
        for dt in (-1.5, 0.0, 1.5):
            cap.set(cv2.CAP_PROP_POS_MSEC, (e["t"] + dt) * 1000)
            ok, img = cap.read()
            img = cv2.resize(img, (480, 270)) if ok else np.zeros((270, 480, 3), np.uint8)
            tiles.append(img)
        row = np.hstack(tiles)
        m, s = divmod(int(e["t"]), 60)
        cv2.putText(row, f"{m}:{s:02d} {e['type']} {e['team']}", (8, 26), 0, 0.8, (0, 255, 255), 2)
        rows.append(row)
    if rows:
        img = np.vstack(rows)
        cv2.putText(img, title, (8, img.shape[0] - 10), 0, 0.7, (255, 255, 255), 2)
        cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 75])


def ball_point(doc, t):
    """The ball's center near time t (or None)."""
    for dk in (0, 1, -1, 2, -2, 3, -3):
        boxes = frame_at(doc, t + dk / doc["fps"])
        balls = [b for b in boxes if b[0] == 0 and b[5] >= 0.2]
        if balls:
            b = max(balls, key=lambda b: b[5])
            return (b[1] + b[3]) / 2, (b[2] + b[4]) / 2
    return None


def zoom_sheet(video, doc, items, out, title, offsets=(-1.0, 0.0, 1.0), half=200):
    """One row per item: zoomed crops around the ball at each offset from the item's time, with
    the item's label. Full frames were too small to tell who touched the ball."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video))
    W, H = doc["frame_size"]
    rows = []
    for it in items:
        tiles = []
        for dt in offsets:
            t = it["t"] + dt
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, img = cap.read()
            pt = ball_point(doc, t) or (W / 2, H / 2)
            if not ok:
                img = np.zeros((H, W, 3), np.uint8)
            x, y = int(min(max(pt[0], half), W - half)), int(min(max(pt[1], half), H - half))
            crop = cv2.resize(img[y - half:y + half, x - half:x + half], (360, 360))
            cv2.circle(crop, (int((pt[0] - x + half) * 360 / (2 * half)), int((pt[1] - y + half) * 360 / (2 * half))),
                       14, (0, 255, 255), 2)
            tiles.append(crop)
        row = np.hstack(tiles)
        m, s_ = divmod(int(it["t"]), 60)
        cv2.putText(row, f"{it.get('n', '')} {m}:{s_:02d} {it['label']}", (8, 28), 0, 0.8, (0, 255, 255), 2)
        rows.append(row)
    if rows:
        img = np.vstack(rows)
        cv2.putText(img, title, (8, img.shape[0] - 10), 0, 0.7, (255, 255, 255), 2)
        cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 75])


def count(events):
    counts = {team: {k: 0 for k in HUDL_KEYS} for team in ("Valley", "Opponent")}
    for e in events:
        counts[e["team"]][e["type"]] += 1
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--game", required=True)
    parser.add_argument("--video", type=Path, help="reads holders' jersey colors (cached) and, with --sheets, makes check sheets")
    parser.add_argument("--method", choices=("v1", "v2"), default="v2")
    parser.add_argument("--sheets", action="store_true", help="write zoomed check sheets (needs --video)")
    args = parser.parse_args()
    doc = json.loads(args.tracks.read_text())
    split = json.loads(args.tracks.with_suffix(".split.json").read_text())
    wpath = args.tracks.with_suffix(".window.json")
    wdoc = json.loads(wpath.read_text()) if wpath.exists() else {}
    window = split["window"]
    half_break = wdoc.get("halftime")
    games = yaml.safe_load((ML / "games.yaml").read_text())["games"]
    game = next(g for g in games if g["id"] == args.game)
    groups = jersey_groups(doc, game)
    info = {"halftime": split["halftime"], "valley_basket_first_half": split["valley_basket_first_half"]}

    if args.method == "v1":
        runs_v1, events = possession_events(doc, split, window, half_break)
        events += assists(doc, split, holders(doc, *window), groups)
        timeline = [[r[0], r[1], r[3]] for r in runs_v1]
        hruns = []
    else:
        cache = args.tracks.with_suffix(".holders.json")
        hruns = None
        if cache.exists():
            cached = json.loads(cache.read_text())
            if cached.get("window") == window:
                hruns = cached["runs"]
        if hruns is None:
            hruns = hold_runs(doc, *window)
            if args.video:
                read_holder_colors(doc, hruns, args.video)
                cache.write_text(json.dumps({"window": window, "runs": hruns}))
        track_team = label_holders(doc, hruns, groups)
        timeline = possession_timeline(doc, hruns, side_per_frame(doc), info, window, half_break)
        timeline = merge_blips(timeline, live_shots(split["shots"]))
        events = possession_events_v2(doc, split, window, half_break, hruns, timeline)
        # Assists use shorter holds too (a catch-and-shoot lasts a few frames), each with its
        # track's voted team.
        quick = hold_runs(doc, *window, min_frames=2)
        for r in quick:
            r["team"] = track_team(r["tid"])
        events += assists_v2(split, quick)
    events.sort(key=lambda e: e["t"])

    counts = count(events)
    print(f"{len(timeline)} possessions ({sum(r[2] == 'Valley' for r in timeline)} Valley), method {args.method}")
    truth = hudl(args.game)
    print(f"{'':10}" + "".join(f"{k:>12}" for k in HUDL_KEYS))
    for team in ("Valley", "Opponent"):
        row = f"{team:10}"
        for k, hk in HUDL_KEYS.items():
            row += f"{counts[team][k]:>7}" + (f" ({truth[team][hk]:>2})" if truth else "")
        print(row)
    out = args.tracks.with_suffix(".possession.json")
    out.write_text(json.dumps({"method": args.method, "timeline": timeline, "events": events, "counts": counts}, indent=1))
    print("wrote", out)
    if args.sheets and args.video:
        random.seed(0)
        for kind in HUDL_KEYS:
            group = [e for e in events if e["type"] == kind]
            pick = sorted(random.sample(group, min(10, len(group))), key=lambda e: e["t"])
            items = [{"t": e["t"], "n": i + 1, "label": f"{kind} {e['team']}" + (f" (shot {e['shot_t']:.0f}s)" if "shot_t" in e else "")}
                     for i, e in enumerate(pick)]
            path = args.tracks.with_name(args.tracks.stem + f".{args.method}.{kind}.jpg")
            zoom_sheet(args.video, doc, items, path, f"10 random {kind}, {args.method} (crops 1 s before, at, 1 s after)")
            print("wrote", path)
        live = [r for r in timeline if r[1] - r[0] >= 2]
        random.seed(1)
        moments = []
        while len(moments) < 30 and live:
            r = random.choice(live)
            t = round(random.uniform(r[0], r[1]), 1)
            if players_around(doc, t - 1, t + 1) >= MIN_PLAYERS:
                moments.append(t)
        moments.sort()
        for part in range(3):
            chunk = moments[part * 10:(part + 1) * 10]
            items = [{"t": t, "n": part * 10 + i + 1, "label": f"has ball: {team_at_time(timeline, t)}"} for i, t in enumerate(chunk)]
            path = args.tracks.with_name(args.tracks.stem + f".{args.method}.poss{part + 1}.jpg")
            zoom_sheet(args.video, doc, items, path, "who has the ball (crops 0.5 s before, at, 0.5 s after)",
                       offsets=(-0.5, 0.0, 0.5))
            print("wrote", path)
        (args.tracks.with_suffix(f".{args.method}.moments.json")).write_text(json.dumps(moments))


if __name__ == "__main__":
    main()
