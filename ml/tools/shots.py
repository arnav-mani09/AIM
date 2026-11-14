"""Find shot attempts and makes from a tracks file (ball and rim boxes only).

Usage:
    ml/.venv/bin/python ml/tools/shots.py ml/data/ontario.tracks-v2.json --video "backend/sample_data/<game>.mp4"

How it decides, per frame, in image coordinates (the camera pans, but ball and rim are in
the same frame, so that doesn't matter):
- Only "game" rims count: not ceiling hoops, and at least 60% as wide as the widest rim
  in the frame (far-court hoops from other games are small).
- Attempt: the ball enters the zone above a game rim (up to 3 rim-widths above it,
  half a rim-width to either side) after being out of it for SHOT_GAP seconds. A second
  pass (Rescue) follows every moving ball and fills short gaps in its path, for shots the
  main pass misses because the detector lost the ball near the backboard.
- Make: the ball drops from above the rim to under the net near its center (see decide()).
  Otherwise a miss.
Writes <tracks>.shots.json and, with --video, a sheet of make frames and one of misses.
These are rules, not a model; the stats sheet is the check.

Status (Nov 10): make rule rewritten after hand-checking every Mitty attempt on 30 fps rim
crops. On Mitty (used for tuning) it catches 46 of 52 real makes and calls 3 of 66 real
misses makes (the old rule: 25 of 52, and 10 false). Totals: Mitty 52 makes found vs 53
official, Riordan 57 vs 61. Still open: dead-ball shots after a whistle look like real makes.

Nov 11: the rescue pass added shots the main pass missed (free throws at Mitty 62:04 and
74:59, Riordan 44:14, and several field goals); hand-labeled Mitty makes now 47 of 52 caught,
still 3 false. Halftime warmups and fouled misses are handled in shot_split.py. Shots taken
while the camera doesn't show the rim can't be found (Riordan 41:37, a free throw).
"""

import argparse
import json
import random
from pathlib import Path

# A rim whose box ends this far (share of frame height) above the game's typical rim is a raised
# ceiling hoop. Relative, not fixed: a high camera puts every game rim near the top of the frame
# (Menlo-Atherton's rims sit at 20% of the height, game 1's at 31%).
CEILING_GAP = 0.09
SHOT_GAP = 2.0
MAKE_WINDOW = 1.5
MIN_BALL, MIN_RIM = 0.2, 0.5


def ceiling_line(doc: dict) -> float:
    """Share of frame height above which a rim counts as a ceiling hoop, from this game's rims."""
    frame_h = doc["frame_size"][1]
    ys = sorted(b[4] / frame_h for _, boxes in doc["frames"] for b in boxes if b[0] == 3 and b[5] >= MIN_RIM)
    return ys[len(ys) // 2] - CEILING_GAP if ys else 0.0


def game_rims(boxes, frame_h, line):
    rims = [b for b in boxes if b[0] == 3 and b[5] >= MIN_RIM and b[4] / frame_h >= line]
    if not rims:
        return []
    widest = max(b[3] - b[1] for b in rims)
    return [b for b in rims if b[3] - b[1] >= 0.6 * widest]


JUMP_PX = 400   # the game ball doesn't move this far (pixels, either way) between two frames 0.1 s apart


def best_ball(boxes, prev=None):
    """The game ball: nearest the last seen ball when that was recent, else the surest one.
    A stray low-score "ball" elsewhere in the frame otherwise breaks the ball's path."""
    balls = [b for b in boxes if b[0] == 0 and b[5] >= MIN_BALL]
    if not balls:
        return None
    if prev is not None:
        px, py = prev
        dist = lambda b: abs((b[1] + b[3]) / 2 - px) + abs((b[2] + b[4]) / 2 - py)  # noqa: E731
        candidates = [ball for ball in balls if dist(ball) <= JUMP_PX]
        return min(candidates, key=lambda ball: dist(ball) - 100 * ball[5]) if candidates else None
    return max(balls, key=lambda b: b[5])


# Settings for the rescue pass (see Rescue).
# A ball detection within STILL_PX of a spot where balls were seen at least twice between
# STILL_LOOK[0] and STILL_LOOK[1] seconds earlier is a ball that isn't flying: on the floor, held,
# or something round in the stands that the detector keeps calling a ball. On Mitty a fake
# "ball" in the crowd took over the main pass during a free throw (Nov 11).
STILL_PX, STILL_LOOK = 8.0, (3.0, 0.5)
# The detector often loses the ball for a few frames in front of the backboard or above the top
# of the picture. If a ball's last spot and its next spot are at most GAP_FILL seconds apart, its
# path in between (fill_gap) is checked for the zone above the rim too.
GAP_FILL = 1.0
# A rim the detector misses for a frame or two is taken from the last frame that had one.
RIM_HOLD = 0.3


def predict(trail, t):
    """Where the game ball should be at time t, from its last two spots (straight line), and how
    long ago it was last seen. None if it wasn't seen within GAP_FILL."""
    if not trail or t - trail[-1][2] > GAP_FILL:
        return None
    x1, y1, t1 = trail[-1]
    if len(trail) >= 2 and 0 < t1 - trail[-2][2] <= 0.5:
        x0, y0, t0 = trail[-2]
        vx, vy = (x1 - x0) / (t1 - t0), (y1 - y0) / (t1 - t0)
        return x1 + vx * (t - t1), y1 + vy * (t - t1), t - t1
    return x1, y1, t - t1


def fill_gap(trail, n):
    """Points on the ball's path between its last two spots in `trail`. Height follows a curve
    through an earlier spot too when there is one (a thrown ball arcs above the straight line),
    sideways position a straight line."""
    (xa, ya, ta), (xb, yb, tb) = trail[-2], trail[-1]
    earlier = [p for p in trail[:-2] if 0.15 <= ta - p[2] <= 1.2]
    pts = []
    for k in range(1, n):
        f = k / n
        tt = ta + f * (tb - ta)
        x = xa + f * (xb - xa)
        if earlier:
            (x0, y0, t0) = earlier[-1]
            # Height through three points (t0, ta, tb): a parabola, like a ball in flight.
            y = (y0 * (tt - ta) * (tt - tb) / ((t0 - ta) * (t0 - tb))
                 + ya * (tt - t0) * (tt - tb) / ((ta - t0) * (ta - tb))
                 + yb * (tt - t0) * (tt - ta) / ((tb - t0) * (tb - ta)))
        else:
            y = ya + f * (yb - ya)
        pts.append((tt, x, y))
    return pts


def still_balls(history, boxes, t, anchor=None):
    """Ids of ball boxes in this frame that aren't moving (see STILL_PX). `history` is a list of
    (t, [(x, y), ...], anchor) for recent frames, oldest first. Checked twice: in the picture,
    and relative to a rim (`anchor`, the widest game rim's center), which catches things fixed
    in the gym, like a round shape on a banner, while the camera pans."""
    earlier = [h for h in history if t - STILL_LOOK[0] <= h[0] <= t - STILL_LOOK[1]]
    out = set()
    for b in boxes:
        if b[0] != 0:
            continue
        x, y = (b[1] + b[3]) / 2, (b[2] + b[4]) / 2
        hits = sum(1 for _, pts, _a in earlier if any(abs(px - x) <= STILL_PX and abs(py - y) <= STILL_PX for px, py in pts))
        if anchor is not None:
            ax, ay = anchor
            fixed = sum(1 for _, pts, a in earlier if a is not None and any(
                abs((px - a[0]) - (x - ax)) <= STILL_PX and abs((py - a[1]) - (y - ay)) <= STILL_PX for px, py in pts))
            hits = max(hits, fixed)
        if hits >= 2:
            out.add(id(b))
    return out


def rim_anchor(rims):
    """Center of the widest game rim, or None."""
    if not rims:
        return None
    r = max(rims, key=lambda r: r[3] - r[1])
    return (r[1] + r[3]) / 2, (r[2] + r[4]) / 2


def in_zone(bx, by, r):
    """The zone above a rim where a shot passes: up to 3 rim widths above it, half a rim width
    out to each side."""
    x0, y0, x1, y1 = r[1:5]
    w = x1 - x0
    return x0 - 0.5 * w <= bx <= x1 + 0.5 * w and y0 - 3 * w <= by <= y0 + 0.2 * (y1 - y0)


def rim_x(shot):
    """Where the shot's rim is now in the picture (x of its center). The camera often pans hard
    while the ball goes through the net (60 px a frame on Mitty), so it's followed frame to frame
    instead of kept where it was when the shot started."""
    return shot.get("_rim_x", (shot["rim"][0] + shot["rim"][2]) / 2)


def follow_rim(shot, rims):
    cx0 = rim_x(shot)
    near = [r for r in rims if abs((r[1] + r[3]) / 2 - cx0) < 2 * (r[3] - r[1])]
    if near:
        r = min(near, key=lambda r: abs((r[1] + r[3]) / 2 - cx0))
        shot["_rim_x"] = (r[1] + r[3]) / 2


def find_shots(doc: dict) -> list[dict]:
    """Main pass: follow one game ball (best_ball) and open an attempt when it enters the zone
    above a game rim. Rescue pass (Rescue below): follow every moving ball separately, so an
    attempt is still found when the main pass lost the ball or followed a fake one."""
    frame_h, line = doc["frame_size"][1], ceiling_line(doc)
    shots, open_shot, last_in_zone, last_ball = [], None, -999.0, None
    rescue, last_rims = Rescue(), (-99.0, [])
    for t, boxes in doc["frames"]:
        recent = last_ball[:2] if last_ball and t - last_ball[2] <= 0.5 else None
        ball, rims = best_ball(boxes, recent), game_rims(boxes, frame_h, line)
        if rims:
            last_rims = (t, rims)
        rescue_rims = rims or (last_rims[1] if t - last_rims[0] <= RIM_HOLD else [])
        found = rescue.step(t, boxes, rescue_rims)
        if ball is not None:
            bx, by = (ball[1] + ball[3]) / 2, (ball[2] + ball[4]) / 2
            last_ball = (bx, by, t)
            for r in rims:
                x0, y0, x1, y1 = r[1:5]
                w = x1 - x0
                if in_zone(bx, by, r):
                    if open_shot and returning_above_rim(open_shot, (t, bx, by, x0, y0, x1, y1)):
                        previous = decide(dict(open_shot), observed_until=t)
                        if not previous["made"]:
                            shots.append(previous)
                            open_shot, last_in_zone = None, -999.0
                    if open_shot is None and t - last_in_zone >= SHOT_GAP:
                        open_shot = {"t": t, "rim": [round(v) for v in r[1:5]], "ball_score": ball[5],
                                     "rim_score": r[5], "path": []}
                    last_in_zone = t
                near_rim = abs(bx - (x0 + x1) / 2) < 3 * w and by < y1 + 6 * (y1 - y0)
                if (open_shot and not open_shot.get("rescued") and near_rim
                        and abs((x0 + x1) / 2 - rim_x(open_shot)) < 2 * w):
                    open_shot["path"].append((t, bx, by, x0, y0, x1, y1))
                    break
        if open_shot:
            follow_rim(open_shot, rescue_rims)
        if found and open_shot is None and t - last_in_zone >= SHOT_GAP:
            start, r, (ct, cx, cy), score = found
            open_shot = {"t": round(start, 2), "rim": [round(v) for v in r[1:5]], "ball_score": score,
                         "rim_score": r[5], "rescued": True, "path": [(ct, cx, cy, *r[1:5])]}
            last_in_zone = t
        if open_shot and open_shot.get("rescued"):
            p = rescue.near(open_shot, rescue_rims, t)
            if p:
                open_shot["path"].append(p)
        if open_shot and t - open_shot["t"] > MAKE_WINDOW:
            shots.append(decide(open_shot, observed_until=t))
            open_shot = None
    if open_shot:
        shots.append(decide(open_shot, observed_until=doc["frames"][-1][0]))
    for s in shots:
        if s["made"] and dead_ball_make(doc, s):
            s["made"], s["dead_ball_make"] = False, True
    return shots


# Dead-ball makes. After a real make in live play the other team inbounds and the game moves to
# the other end, so the camera pans away from the basket within a few seconds (2 to 6 s on almost
# every scored field goal at Mitty and Riordan). Shots after a whistle (a foul, a violation, the
# shot clock) also go in, but then nobody runs: the camera stays on the basket and the players were
# already moving slowly before the shot. Free throws are left alone (players stand still before
# them, and the camera stays for the second one).
LEAVE_WITHIN = 7.0        # seconds after the make for the camera to leave the basket
DEAD_SLOW = (0.15, 0.5)   # players' movement before the shot (shot_split.motion) that reads as a dead ball


def camera_leaves(doc, shot, t0, horizon):
    """Seconds after t0 until the shot's rim leaves the picture at a side of the frame for a
    full second (the camera following play to the other end), or None within `horizon`."""
    fps, frame_w = doc["fps"], doc["frame_size"][0]
    x0, _, x1, _ = shot["rim"]
    cx, w, gone = (x0 + x1) / 2, x1 - x0, None
    start = int(round(t0 * fps))
    for t, boxes in doc["frames"][start:start + int(horizon * fps) + int(fps) + 1]:
        rims = [b for b in boxes if b[0] == 3 and b[5] >= 0.4 and abs((b[1] + b[3]) / 2 - cx) < 2.5 * w]
        if rims:
            r = min(rims, key=lambda b: abs((b[1] + b[3]) / 2 - cx))
            cx, w, gone = (r[1] + r[3]) / 2, r[3] - r[1], None
            continue
        gone = t if gone is None else gone
        if t - gone >= 1.0 and not 0.25 * frame_w <= cx <= 0.75 * frame_w:
            return gone - t0 if gone - t0 <= horizon else None
    return None


def dead_ball_make(doc, shot) -> bool:
    """Heuristic dead-ball candidate, only with a complete post-make observation window.
    Slow players and a camera that stays put are not conclusive: timeouts and and-ones can
    have the same pattern. Missing observations must not be treated as a stationary camera.
    """
    from shot_split import motion   # shared with the free throw rule

    make_t = shot.get("make_t", shot["t"])
    frames, fps = doc["frames"], doc["fps"]
    start = int(round(make_t * fps))
    stop = start + int((LEAVE_WITHIN + 1.0) * fps) + 1
    observed = frames[max(0, start):stop]
    if (not observed or observed[0][0] > make_t + 1.0 / fps
            or observed[-1][0] < make_t + LEAVE_WITHIN + 1.0
            or any(after[0] - before[0] > 1.5 / fps for before, after in zip(observed, observed[1:]))):
        return False
    rim_center = (shot["rim"][0] + shot["rim"][2]) / 2
    rim_width = shot["rim"][2] - shot["rim"][0]
    if not any(box[0] == 3 and box[5] >= MIN_RIM
               and abs((box[1] + box[3]) / 2 - rim_center) < 2 * rim_width
               for _, boxes in observed for box in boxes):
        return False
    m = motion(doc, shot["t"] - 4.0, shot["t"] - 0.5)
    if m is None or not DEAD_SLOW[0] <= m < DEAD_SLOW[1]:
        return False
    return camera_leaves(doc, shot, make_t, LEAVE_WITHIN) is None


class Rescue:
    """Follows every moving ball detection as its own short track (still ones are skipped, see
    still_balls), so a shot is found even when the main pass's single ball was lost in front of
    the backboard or switched to a fake ball in the crowd. On Mitty and Riordan (Nov 11) this
    found free throws the main pass never saw. A track enters the zone either with a detection
    in it or across a gap (fill_gap)."""

    def __init__(self):
        self.tracks, self.history, self.balls, self.last_zone = [], [], [], -999.0

    def step(self, t, boxes, rims):
        self.history = [h for h in self.history if t - h[0] <= STILL_LOOK[0]]
        anchor = rim_anchor(rims)
        still = still_balls(self.history, boxes, t, anchor)
        self.history.append((t, [((b[1] + b[3]) / 2, (b[2] + b[4]) / 2) for b in boxes if b[0] == 0 and b[5] >= MIN_BALL],
                             anchor))
        self.tracks = [k for k in self.tracks if t - k[-1][2] <= GAP_FILL]
        self.balls = [b for b in boxes if b[0] == 0 and b[5] >= MIN_BALL and id(b) not in still]
        pairs = []
        for i, b in enumerate(self.balls):
            bx, by = (b[1] + b[3]) / 2, (b[2] + b[4]) / 2
            for j, k in enumerate(self.tracks):
                g = predict(k, t)
                if g is None:
                    continue
                d = abs(bx - g[0]) + abs(by - g[1])
                if d <= max(150.0, 1500.0 * g[2]):
                    pairs.append((d, i, j))
        used_b, used_k, updated = set(), set(), []
        for d, i, j in sorted(pairs):
            if i in used_b or j in used_k:
                continue
            used_b.add(i), used_k.add(j)
            b = self.balls[i]
            self.tracks[j].append(((b[1] + b[3]) / 2, (b[2] + b[4]) / 2, t))
            updated.append((self.tracks[j], b))
        for i, b in enumerate(self.balls):
            if i not in used_b:
                self.tracks.append([((b[1] + b[3]) / 2, (b[2] + b[4]) / 2, t)])
        found = None
        for k, b in updated:
            bx, by, _ = k[-1]
            gap = t - k[-2][2]
            for r in rims:
                w = r[3] - r[1]
                if in_zone(bx, by, r):
                    hit = (t, r, (t, bx, by), b[5])
                elif 0.15 <= gap <= GAP_FILL and abs(k[-2][0] - bx) + abs(k[-2][1] - by) < 12 * w:
                    inside = [p for p in fill_gap(k, 20) if in_zone(p[1], p[2], r)]
                    # Start at the first point in the zone; the path gets the last one still
                    # above the rim, so the make rule sees the ball over the rim.
                    hit = (inside[0][0], r, inside[-1], b[5]) if inside else None
                else:
                    hit = None
                if hit:
                    if t - self.last_zone >= SHOT_GAP and found is None:
                        found = hit
                    self.last_zone = t
        return found

    def near(self, shot, rims, t):
        """This frame's moving ball nearest the shot's rim (for the make rule), as a path point."""
        cx0 = rim_x(shot)
        best = None
        for r in rims:
            x0, y0, x1, y1 = r[1:5]
            w = x1 - x0
            if abs((x0 + x1) / 2 - cx0) >= 2 * w:
                continue
            for b in self.balls:
                bx, by = (b[1] + b[3]) / 2, (b[2] + b[4]) / 2
                if abs(bx - (x0 + x1) / 2) < 3 * w and by < y1 + 6 * (y1 - y0):
                    last = shot["path"][-1] if shot["path"] else None
                    d = abs(bx - last[1]) + abs(by - last[2]) if last else abs(bx - (x0 + x1) / 2)
                    if best is None or d < best[0]:
                        best = (d, (t, bx, by, x0, y0, x1, y1))
        return best[1] if best else None


# Make rule, in rim units: x is the ball's sideways offset from the rim's center in rim widths,
# y is its height below the rim's top edge in rim-box heights (0 = rim top, 1 = rim front edge).
# The net hangs to about y = 1.5, so y >= UNDER_NET means the ball has come out of the bottom.
UNDER_NET = 1.6
NET_EXIT_X = 0.35   # a make leaves the net near its center; a ball rolling off the side is wider
OVER_RIM_X = 1.0    # the last point above the rim must be roughly over it
SIDE_X = 0.6        # on the way down it must stay inside the rim's width
EXIT_DRIFT = 0.6   # sideways move (rim widths) in the 0.3 s after leaving the net that rules out a make
LOST_GAP, LOST_X = 0.3, 0.6   # see "Lost in the net" in decide()
DROP_TIME = 1.5     # a ball can roll around the rim for over a second before dropping in


def rim_units(p):
    t, bx, by, x0, y0, x1, y1 = p
    return t, (bx - (x0 + x1) / 2) / (x1 - x0), (by - y0) / max(1.0, y1 - y0)


def returning_above_rim(shot, point):
    """A new upward flight after a below-net miss can be a quick putback, not the old shot."""
    path = shot["path"]
    if not path:
        return False
    if abs((point[3] + point[5]) / 2 - rim_x(shot)) >= 2 * (point[5] - point[3]):
        return False
    time, horizontal, vertical = rim_units(point)
    previous_time, _, previous_vertical = rim_units(path[-1])
    return (0 < time - previous_time <= 0.3 and abs(horizontal) <= SIDE_X
            and vertical < 0.3 <= previous_vertical
            and any(rim_units(sample)[2] >= UNDER_NET for sample in path))


def decide(shot: dict, observed_until=None) -> dict:
    """Make = the ball comes out under the net near its center, having dropped there from
    above the rim without leaving the rim's width, and doesn't pop back up right after.
    Checked by hand on the Mitty game (Nov 10): a rim-out or a ball rolling off the front
    rim leaves to the side (x past about 0.4 by the time it's under the net) or bounces up.

    Second, weaker case: the ball is last seen inside the net near its center, then lost
    for half a second (the net and players hide it).

    The old rule (Nov 3) wanted the ball under the rim within 0.5 s and no change of
    sideways direction. Balls that roll on the rim take longer, and a ball swinging in the
    net changes direction, so it called about half the real makes misses."""
    path = shot.pop("path")
    shot.pop("_rim_x", None)
    pts = [rim_units(p) for p in path]
    if observed_until is None:
        observed_until = pts[-1][0] if pts else shot["t"]
    made, evidence, make_t = False, 0, None
    for k, (t, x, y) in enumerate(pts):
        if y < UNDER_NET:
            continue
        # First point under the net. Look back to the last point above the rim.
        above = [j for j in range(k) if pts[j][2] < 0.3]
        if above:
            a = above[-1]
            ta, xa = pts[a][0], pts[a][1]
            stays_inside = all(abs(pts[j][1]) <= SIDE_X for j in range(a + 1, k))
            pops_up = any(q[2] < 0.3 for q in pts[k + 1:] if q[0] - t <= 0.4)
            # Out of the net a make falls nearly straight; a ball rolling off the rim keeps
            # moving sideways (Mitty 6:09, Riordan 61:00).
            drifts = any(abs(q[1] - x) > EXIT_DRIFT for q in pts[k + 1:] if q[0] - t <= 0.3)
            if (abs(xa) <= OVER_RIM_X and t - ta <= DROP_TIME and y <= 5.5 and stays_inside
                    and abs(x) <= NET_EXIT_X and not pops_up and not drifts):
                made, make_t = True, t
                evidence = 1 + sum(1 for q in pts[k + 1:] if q[0] - t <= 0.4 and abs(q[1]) <= SIDE_X)
            # Lost in the net: last seen over the rim near its center, hidden for a while (the
            # net, often during a camera pan), then seen under the net a little to one side.
            j = k - 1
            if (not made and LOST_X and k > 0 and t - pts[j][0] >= LOST_GAP and t - pts[j][0] <= 1.0
                    and -1.5 <= pts[j][2] <= 1.2 and abs(pts[j][1]) <= 0.5 and abs(x) <= LOST_X
                    and y <= 5.5 and not pops_up and not drifts):
                made, make_t, evidence = True, t, 1
        break
    if not made:
        for k, (t, x, y) in enumerate(pts):
            if not (0.6 <= y < UNDER_NET and abs(x) <= 0.25):
                continue
            above = [j for j in range(k) if pts[j][2] < 0.3]
            if not above or abs(pts[above[-1]][1]) > OVER_RIM_X or t - pts[above[-1]][0] > 1.0:
                continue
            if not all(abs(point[1]) <= SIDE_X for point in pts[above[-1] + 1:k]):
                continue
            if any(point[2] < 0.3 for point in pts[k + 1:]):
                continue
            nxt = pts[k + 1][0] if k + 1 < len(pts) else None
            if (nxt if nxt is not None else observed_until) - t >= 0.5:
                made, make_t, evidence = True, t, 0
                break
    shot["made"] = made
    shot["evidence"] = evidence
    if make_t is not None:
        shot["make_t"] = make_t
    # Rough confidence until it's calibrated against stats sheets.
    shot["confidence"] = round(min(1.0, 0.5 * shot["ball_score"] + 0.3 * shot["rim_score"] + 0.2 * min(1, evidence)), 2)
    return shot


def sheet(video: Path, shots: list[dict], out: Path, title: str) -> None:
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video))
    tiles = []
    for s in shots[:12]:
        t = s.get("make_t", s["t"])
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, img = cap.read()
        if not ok:
            continue
        x0, y0, x1, y1 = s["rim"]
        w = x1 - x0
        cx, cy = (x0 + x1) // 2, y0
        crop = img[max(0, cy - 4 * w):cy + 3 * w, max(0, cx - 4 * w):cx + 4 * w].copy()
        crop = cv2.resize(crop, (320, 280))
        m, s_ = divmod(int(t), 60)
        cv2.putText(crop, f"{m}:{s_:02d}", (8, 28), 0, 0.9, (0, 255, 255), 2)
        tiles.append(crop)
    if not tiles:
        return
    tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % 4)
    rows = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
    img = np.vstack(rows)
    cv2.putText(img, title, (8, img.shape[0] - 10), 0, 0.8, (255, 255, 255), 2)
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 80])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--window", type=float, nargs=2, metavar=("START", "END"),
                        help="only count shots between these seconds (tip-off and final buzzer)")
    args = parser.parse_args()
    doc = json.loads(args.tracks.read_text())
    shots = find_shots(doc)
    start, end = args.window or (0.0, doc["frames"][-1][0])
    shots = [s for s in shots if start <= s["t"] <= end]
    made = [s for s in shots if s["made"]]
    minutes = (end - start) / 60
    print(f"{len(shots)} attempts, {len(made)} makes over {minutes:.0f} min "
          f"({len(shots) / minutes:.1f} attempts/min, {len(made) / max(1, len(shots)):.0%} made)")
    out = args.tracks.with_suffix(".shots.json")
    out.write_text(json.dumps(shots, indent=1))
    print("wrote", out)
    if args.video:
        random.seed(0)
        for name, group in (("makes", made), ("misses", [s for s in shots if not s["made"]])):
            pick = sorted(random.sample(group, min(12, len(group))), key=lambda s: s["t"])
            path = args.tracks.with_name(args.tracks.stem + f".{name}.jpg")
            sheet(args.video, pick, path, f"12 random {name}")
            print("wrote", path)


if __name__ == "__main__":
    main()
