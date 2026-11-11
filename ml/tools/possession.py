"""Team possession, rebounds, turnovers, steals and assists from a tracks file and its shots.

Usage:
    ml/.venv/bin/python ml/tools/possession.py ml/data/tracks/valley-vs-archbishop-mitty.v4.json \
        --game valley-vs-archbishop-mitty [--video "backend/sample_data/<game>.mp4"]

Reads <tracks>.json, <tracks>.split.json (shot_split.py) and <tracks>.window.json
(game_window.py), writes <tracks>.possession.json, and prints the totals next to the Hudl box
score when the game has one. With --video it also writes contact sheets of each event type for
a hand check.

How it decides (rules, not a model):
- Which team has the ball. The camera follows the ball and pans to whichever basket the play
  is at, and it never shows both baskets at once (checked on Mitty: 0 frames with rims on both
  sides). So the side of the frame the game rim is on says which basket the play is at, and a
  team only attacks one basket per half. A run of frames at one basket is one team's
  possession. The side has to hold for SWITCH_HOLD seconds before it counts as a change, so a
  quick look back up the floor doesn't split a possession. Frames with no rim keep the last side.
- How a possession ends, at each change of basket:
  - the team's last shot before the change was a make (or a made last free throw): it scored.
  - it was a miss: the other team got the defensive rebound, if the change came within
    DREB_DELAY seconds of the miss. A miss followed by another shot from the same team at the
    same basket is an offensive rebound. A miss with a long wait and no other shot before the
    change counts as an offensive rebound followed by a turnover.
  - there was no shot: a turnover. Changes right after a long stop (quarter breaks, the jump
    ball, halftime) are not turnovers: the ball changes hands by rule there.
- Turnovers are also skipped when the ball went to the rim after the team's last counted shot
  (probably a shot the finder missed) and when few players are on screen (timeouts, breaks).
  A team that scores and then shoots again at the same basket means the other team lost the
  ball before crossing half court: a backcourt turnover.
- Steal: a turnover where no official handled the ball in the 12 s before the change. After a
  violation or an out-of-bounds ball the official hands the ball to the inbounder; after a
  steal play never stops. (Player movement was tried first and didn't separate the two.)
- Assist: the ball holder in each frame is the player whose box holds the ball (same test as
  shot_split.shooter), kept only when it lasts HOLD_MIN frames. A made field goal is assisted
  when the shooter got the ball from a different player of the same team (not the other
  jersey group) within ASSIST_WINDOW seconds of the shot, the pass travelled at least a body
  height (a broken track on one player isn't a pass), and the shooter didn't hold it long.

Status (Nov 11): tuned on Mitty, checked untouched on Riordan. Mitty lands within about 3 of
Hudl on most team stats; Riordan is off by 4 to 9 on offensive rebounds, Valley defensive
rebounds and Opponent turnovers. Known limits: the team-with-the-ball timeline lags real changes
by the 4 to 8 s the ball takes to cross half court, shots the finder misses turn into fake
turnovers, and assists depend on a box-overlap ball-holder test that often picks the defender.
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--game", required=True)
    parser.add_argument("--video", type=Path)
    args = parser.parse_args()
    doc = json.loads(args.tracks.read_text())
    split = json.loads(args.tracks.with_suffix(".split.json").read_text())
    wpath = args.tracks.with_suffix(".window.json")
    wdoc = json.loads(wpath.read_text()) if wpath.exists() else {}
    window = split["window"]
    half_break = wdoc.get("halftime")
    games = yaml.safe_load((ML / "games.yaml").read_text())["games"]
    game = next(g for g in games if g["id"] == args.game)

    runs, events = possession_events(doc, split, window, half_break)
    holds = holders(doc, *window)
    events += assists(doc, split, holds, jersey_groups(doc, game))
    events.sort(key=lambda e: e["t"])

    counts = {team: {k: 0 for k in HUDL_KEYS} for team in ("Valley", "Opponent")}
    for e in events:
        counts[e["team"]][e["type"]] += 1
    print(f"{len(runs)} possessions at one basket ({sum(r[3] == 'Valley' for r in runs)} Valley)")
    truth = hudl(args.game)
    print(f"{'':10}" + "".join(f"{k:>12}" for k in HUDL_KEYS))
    for team in ("Valley", "Opponent"):
        row = f"{team:10}"
        for k, hk in HUDL_KEYS.items():
            row += f"{counts[team][k]:>7}" + (f" ({truth[team][hk]:>2})" if truth else "")
        print(row)
    out = args.tracks.with_suffix(".possession.json")
    out.write_text(json.dumps({"runs": runs, "events": events, "counts": counts}, indent=1))
    print("wrote", out)
    if args.video:
        random.seed(0)
        for kind in HUDL_KEYS:
            group = [e for e in events if e["type"] == kind]
            pick = sorted(random.sample(group, min(10, len(group))), key=lambda e: e["t"])
            path = args.tracks.with_name(args.tracks.stem + f".{kind}.jpg")
            sheet(args.video, pick, path, f"10 random {kind}")
            print("wrote", path)


if __name__ == "__main__":
    main()
