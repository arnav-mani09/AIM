"""Label each field goal attempt as a 2 or a 3, from where the shooter's feet were at takeoff.

Usage:
    ml/.venv/bin/python ml/tools/three_point.py ml/data/tracks/<game>.v4.json --video "backend/sample_data/<game>.mp4"

Needs <tracks>.split.json from shot_split.py (team and FT/FG per attempt). Writes <tracks>.threes.json and,
with --sheet, contact sheets of the release frames with the arc drawn in.

How it works:
1. Shooter and feet. Follow the ball back from the rim. In flight it is lower in the picture the earlier
   you look, until the shooter's gather, where it stops dropping. The player holding it there is the
   shooter, and the bottom of their box at that moment is where their feet were (on the floor, before
   the jump). Stopping at the first player the ball overlaps instead picks players under the basket,
   because from a high camera the ball's flight passes over them.
2. Court lines without a court model. The camera pans and zooms, but the rim is in every shot frame.
   Shift and scale each shot frame so its rim lands at the same spot with the same width. Painted
   lines then stack up across a game's shots while players blur out, so averaging the thin dark lines
   of all shot frames at one basket shows that basket's 3-point arc.
3. Trace the arc. Cast rays from a point inside the arc (the floor below the rim) and follow the
   strongest line around the basket, keeping the radius smooth from one ray to the next.
4. Per shot, compare the feet's distance from that point with the arc's distance in the same direction.
   Then look for the painted line in the shot's own frame near the expected spot, which corrects for
   the small shifts a camera pan causes, and use it when it's clear.
Rules and image geometry, not a model. Checked against Hudl 3PA counts and by eye.
"""

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np

SC = 20                  # map pixels per rim width
MAP_W, MAP_H = 1000, 600
RX, RY = 500, 120        # where the rim center lands in the map
FLOOR_BELOW = 4.0        # rim widths from rim center down to a point inside the arc (floor under the rim)
FLOOR_TOP = 1.75         # the floor (and the far side of the arc) starts this many rim widths below the rim
GATHER_LOOKBACK = 3.0    # seconds to follow the ball back from the rim
SEARCH = 1.2             # rim widths either side of the average arc to look for the line in a shot's own frame
ARC_FT = 19.75           # high school 3-point distance from the center of the basket (NFHS)
MARGIN_FT = 0.5          # feet within this many feet past the arc count as on the line: a 2
BX, BY = RX, RY + int(FLOOR_BELOW * SC)
_T = np.linspace(0, 2 * np.pi, 160, endpoint=False)
COS_T, SIN_T = np.cos(_T), np.sin(_T)   # 160 points around each ellipse


def frame_at(doc, t):
    i = int(round(t * doc["fps"]))
    return doc["frames"][i][1] if 0 <= i < len(doc["frames"]) else []


def players(boxes):
    return [b for b in boxes if b[0] == 1 and b[5] >= 0.4]


def game_rim(boxes, ref_x):
    rims = [b for b in boxes if b[0] == 3 and b[5] >= 0.5]
    if not rims:
        return None
    widest = max(b[3] - b[1] for b in rims)
    rims = [b for b in rims if b[3] - b[1] >= 0.6 * widest]
    return min(rims, key=lambda b: abs((b[1] + b[3]) / 2 - ref_x))


def ball_path(doc, t):
    """Ball positions walking back from time t, one per frame: (t, x, y). Stops at a long gap or a jump."""
    fps, path, prev, gap = doc["fps"], [], None, 0
    for k in range(int(GATHER_LOOKBACK * fps) + 1):
        tt = t - k / fps
        balls = [b for b in frame_at(doc, tt) if b[0] == 0 and b[5] >= 0.2]
        if not balls:
            gap += 1
            if gap > 3 and path:
                break
            continue
        if prev:
            b = min(balls, key=lambda b: abs((b[1] + b[3]) / 2 - prev[0]) + abs((b[2] + b[4]) / 2 - prev[1]))
        else:
            b = max(balls, key=lambda b: b[5])
        x, y = (b[1] + b[3]) / 2, (b[2] + b[4]) / 2
        if prev and abs(x - prev[0]) + abs(y - prev[1]) > 250 * (gap + 1):
            break
        prev, gap = (x, y), 0
        path.append((tt, x, y))
    return path


def holder(boxes, x, y):
    best = None
    for p in players(boxes):
        x0, y0, x1, y1 = p[1:5]
        w, h = x1 - x0, y1 - y0
        if x0 - 0.15 * w <= x <= x1 + 0.15 * w and y0 - 0.1 * h <= y <= y1:
            d = abs(x - (x0 + x1) / 2)
            if best is None or d < best[0]:
                best = (d, p)
    return best[1] if best else None


def find_takeoff(doc, s):
    """Shooter box, rim box and time at the gather. Falls back to shot_split's shooter when the
    ball can't be followed back to a holder. None if neither works."""
    tk = gather_takeoff(doc, s)
    if tk is None and s.get("shooter_track") is not None:
        tk = feet_of(doc, s, s["shooter_track"], s["t"] - 0.3, back=1.5)
        if tk:
            tk["shooter_from"] = "first player the ball overlaps"
    return tk


def feet_of(doc, s, tid, t, back):
    """The player's lowest box bottom (feet on the floor) in the last frames before t, with the rim."""
    fps, best = doc["fps"], None
    for k in range(int(back * fps) + 1):
        t2 = t - k / fps
        boxes = frame_at(doc, t2)
        me = [b for b in boxes if b[0] == 1 and b[6] == tid]
        rim = game_rim(boxes, (s["rim"][0] + s["rim"][2]) / 2)
        if me and rim is not None:
            if best is None or me[0][4] > best[1][4]:
                best = (t2, me[0], rim)
            if k >= 4 and best:
                break
    if best is None:
        return None
    t2, me, rim = best
    return {"take": round(t2, 2), "shooter_box": [round(v) for v in me[1:5]], "shooter_track": tid,
            "rim_at_take": [round(v) for v in rim[1:5]], "feet": [round((me[1] + me[3]) / 2, 1), round(me[4], 1)]}


def gather_takeoff(doc, s):
    path = ball_path(doc, s["t"])
    if len(path) < 3:
        return None
    # The shot time is often after the top of the flight, so walking back the ball first rises to
    # its apex. From the apex back, it drops in the picture (y grows) until the gather. Stop at the
    # first point after which it rises again by more than a little.
    early = [k for k, p in enumerate(path) if path[0][0] - p[0] <= 1.5]
    k_apex = min(early, key=lambda k: path[k][2])
    lowest, k_low = path[k_apex][2], k_apex
    for k in range(k_apex, len(path)):
        y = path[k][2]
        if y > lowest:
            lowest, k_low = y, k
        elif y < lowest - 25 and k - k_low >= 2:
            break
    # The holder at the gather, or at the nearest frame around it where someone holds the ball.
    for dk in (0, 1, -1, 2, -2, 3):
        k = k_low + dk
        if not 0 <= k < len(path):
            continue
        tt, x, y = path[k]
        p = holder(frame_at(doc, tt), x, y)
        if p is not None:
            break
    else:
        return None
    # Feet: lowest box bottom of this player around the gather (on the floor before the jump).
    tk = feet_of(doc, s, p[6], tt + 2 / doc["fps"], back=0.4)
    if tk:
        tk["shooter_from"] = "ball at the gather"
    return tk


def line_map(img):
    """Thin dark lines (painted court lines on light wood) as a 0/1 image."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    k = max(9, int(round(img.shape[1] / 1920 * 18)) | 1)
    bh = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    return (bh > 18).astype(np.float32)


def to_map(rim):
    """Affine that puts this rim's center at (RX, RY) with width SC."""
    x0, y0, x1, y1 = rim
    sc = SC / (x1 - x0)
    return np.float32([[sc, 0, RX - sc * (x0 + x1) / 2], [0, sc, RY - sc * (y0 + y1) / 2]])


def thin_ridges(m):
    """Keep only thin bright curves in an averaged line map (drops blobs like logos and crowds)."""
    resp = np.zeros_like(m)
    for ang in range(0, 180, 15):
        dx, dy = 5 * np.cos(np.deg2rad(ang)), 5 * np.sin(np.deg2rad(ang))
        a = cv2.warpAffine(m, np.float32([[1, 0, dx], [0, 1, dy]]), m.shape[::-1])
        b = cv2.warpAffine(m, np.float32([[1, 0, -dx], [0, 1, -dy]]), m.shape[::-1])
        resp = np.maximum(resp, np.minimum(m - a, m - b))
    return cv2.GaussianBlur(resp, (3, 3), 0)


def ellipse_points(cx, cy, a, b, th, side, k=160):
    """Points on an ellipse (map pixels), leaving out the part behind the basket (baseline side)."""
    t = np.linspace(0, 2 * np.pi, k, endpoint=False)
    x = cx + a * np.cos(t) * np.cos(th) - b * np.sin(t) * np.sin(th)
    y = cy + a * np.cos(t) * np.sin(th) + b * np.sin(t) * np.cos(th)
    keep = x > BX - 2 * SC if side == "left" else x < BX + 2 * SC
    return x[keep], y[keep]


def fit_arc(resp, cover, side, around=None):
    """The 3-point arc as an ellipse (cx, cy, a, b, angle) in map pixels.

    A painted circle on the floor always looks like an ellipse from a fixed camera, and the straight
    corner pieces of the line differ from that circle by under a foot, so an ellipse fits the whole
    line. Search for the ellipse whose outline runs along the most thin-line response, with its center
    near the floor under the rim and its long axis roughly level. Bright blobs (lettering, logos) are
    clipped so a long faint line beats a short bright one."""
    resp = resp.copy()
    resp[:RY + int(FLOOR_TOP * SC)] = 0      # wall, stands and backboard sit above the floor
    on = resp[cover]
    c = np.clip(resp / (np.percentile(on[on > 0], 97) + 1e-6), 0, 1)

    def along_many(P, cm):
        """Mean line strength on each ellipse in P (rows of cx, cy, a, b, angle), all at once.
        NaN where under 60% of the outline is on the floor seen in enough shot frames."""
        cx, cy, a, b, th = (P[:, i:i + 1] for i in range(5))
        x = cx + a * COS_T * np.cos(th) - b * SIN_T * np.sin(th)
        y = cy + a * COS_T * np.sin(th) + b * SIN_T * np.cos(th)
        keep = x > BX - 2 * SC if side == "left" else x < BX + 2 * SC
        xi, yi = x.astype(int), y.astype(int)
        ok = keep & (xi >= 0) & (xi < MAP_W) & (yi >= 0) & (yi < MAP_H)
        xi, yi = np.clip(xi, 0, MAP_W - 1), np.clip(yi, 0, MAP_H - 1)
        ok &= cover[yi, xi]
        n_keep, n_ok = keep.sum(1), ok.sum(1)
        vals = np.where(ok, cm[yi, xi], 0).sum(1) / np.maximum(n_ok, 1)
        return np.where(n_ok >= 0.6 * np.maximum(n_keep, 1), vals, np.nan)

    def score_many(P, cm, off=10):
        """Line strength on each ellipse minus on slightly smaller and larger copies. A painted line is
        strong only right on it; floor grain, crowds and lettering are strong all around."""
        out = np.empty(len(P))
        for i in range(0, len(P), 4000):      # in chunks, to keep memory small
            Q = P[i:i + 4000]
            on = along_many(Q, cm)
            sides = []
            for d in (-off, off):
                R = Q.copy()
                R[:, 2] += d
                R[:, 3] += d
                sides.append(along_many(R, cm))
            sides = np.array(sides)
            n = (~np.isnan(sides)).sum(0)
            side_mean = np.where(n > 0, np.nansum(sides, 0) / np.maximum(n, 1), on)
            out[i:i + 4000] = np.where(np.isnan(on), -1.0, on - side_mean)
        return out

    def score(p, cm):
        return float(score_many(np.array([p], dtype=np.float64), cm)[0])

    # Lines are a few pixels wide, so a coarse grid would step right over them. Widen them with a max
    # filter (keeps a thin line as strong as a bright blob, unlike a blur), search coarsely, then
    # polish the best few candidates on sharper copies and keep the one that fits the sharp map best.
    levels = [cv2.dilate(c, np.ones((k, k), np.uint8)) for k in (9, 5)] + [c]
    if around is None:
        grid = (np.arange(BX - 3 * SC, BX + 3.01 * SC, SC / 2), np.arange(BY - 2 * SC, BY + 2.01 * SC, SC / 2),
                np.arange(5 * SC, 12.01 * SC, SC / 2), np.arange(1.5 * SC, 6.01 * SC, SC / 4),
                np.deg2rad(np.arange(-15, 16, 3)))   # the arc sits nearly level from a side camera
    else:   # a small search around a starting guess (the other basket's arc, mirrored)
        cx0, cy0, a0, b0, th0 = around
        grid = (cx0 + np.arange(-1, 1.01, 0.25) * SC, cy0 + np.arange(-0.5, 0.51, 0.25) * SC,
                a0 + np.arange(-1, 1.01, 0.25) * SC, b0 + np.arange(-0.3, 0.31, 0.15) * SC,
                th0 + np.deg2rad(np.arange(-3, 3.1, 1.5)))
    mesh = np.stack(np.meshgrid(*grid, indexing="ij"), -1).reshape(-1, 5)
    scores = score_many(mesh, levels[0])
    order = np.argsort(-scores, kind="stable")
    coarse = [(scores[i], tuple(float(v) for v in mesh[i])) for i in order[:40]]
    best, best_s = None, -1.0
    for _, p in coarse:
        steps = [SC / 4, SC / 4, SC / 4, SC / 8, np.deg2rad(1)]
        for cm in levels:
            s_ = score(p, cm)
            improved = True
            while improved:
                improved = False
                for i, st in enumerate(steps):
                    for d in (-st, st):
                        q = list(p); q[i] += d
                        if abs(q[4]) > np.deg2rad(15):
                            continue
                        sq = score(tuple(q), cm)
                        if sq > s_:
                            p, s_, improved = tuple(q), sq, True
            steps = [v / 2 for v in steps]
        if s_ > best_s:
            best, best_s = p, s_
    return best, best_s


def arc_radius(arc, ang):
    """Distance from (BX, BY) to the arc along a ray at this angle (map pixels)."""
    (cx, cy, a, b, th), _ = arc
    d = np.array([np.cos(np.deg2rad(ang)), np.sin(np.deg2rad(ang))])
    R = np.array([[np.cos(th), np.sin(th)], [-np.sin(th), np.cos(th)]])   # map to the ellipse's own axes
    o, v = R @ np.array([BX - cx, BY - cy]), R @ d
    A = (v[0] / a) ** 2 + (v[1] / b) ** 2
    B = 2 * (o[0] * v[0] / a ** 2 + o[1] * v[1] / b ** 2)
    C = (o[0] / a) ** 2 + (o[1] / b) ** 2 - 1
    disc = B * B - 4 * A * C
    if disc < 0 or C > 0:
        return None   # the point is outside the ellipse: the fit is off
    return float((-B + np.sqrt(disc)) / (2 * A))


def refine(lines_frame, M, ang, r_avg):
    """Look for the painted line along this shot's own ray near the average arc. Returns radius or None."""
    Mi = cv2.invertAffineTransform(M)
    rs = np.arange(max(SC, r_avg - SEARCH * SC), r_avg + SEARCH * SC)
    th = np.deg2rad(ang)
    mx, my = BX + rs * np.cos(th), BY + rs * np.sin(th)
    ix = (Mi[0, 0] * mx + Mi[0, 1] * my + Mi[0, 2]).astype(int)
    iy = (Mi[1, 0] * mx + Mi[1, 1] * my + Mi[1, 2]).astype(int)
    h, w = lines_frame.shape
    ok = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
    if ok.mean() < 0.8:
        return None
    v = np.zeros(len(rs))
    v[ok] = lines_frame[iy[ok], ix[ok]]
    v = np.convolve(v, np.ones(3) / 3, "same")
    # A thin line is a short run of line pixels; a player's dark clothing is a long one.
    runs, start = [], None
    for i, on in enumerate(v > 0.5):
        if on and start is None:
            start = i
        if not on and start is not None:
            runs.append((start, i)); start = None
    if start is not None:
        runs.append((start, len(v)))
    thin = [(a, b) for a, b in runs if (b - a) <= 0.6 * SC]
    if not thin:
        return None
    a, b = min(thin, key=lambda r: abs((r[0] + r[1]) / 2 - (r_avg - rs[0])))
    return float(rs[(a + b) // 2])


def read_at(cap, video, t):
    """One frame at t seconds. Seeks, so only the frames around each shot get decoded. The film can
    be a file or a web link (a signed R2 link on Modal); a link can drop, so on a failed read it
    reopens the film once and tries again."""
    for attempt in range(2):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, img = cap.read()
        if ok:
            return img
        if attempt == 0:
            cap.open(str(video))
    return None


def classify(doc, shots, video, side_of=None, debug=None):
    """Label each field goal in shots (from shot_split) with points 2 or 3, margin and arc_source.
    Changes the shots in place and returns the arc found for each basket."""
    if side_of is None:   # which basket: the rim's side of the picture
        half_w = doc["frame_size"][0] / 2
        side_of = lambda rim: "left" if (rim[0] + rim[2]) / 2 < half_w * 960 / doc["frame_size"][0] else "right"  # noqa: E731
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise OSError(f"can't open the film: {str(video)[:80]}")
    scale = 960 / doc["frame_size"][0]   # work on half-size frames: plenty for court lines
    frames, acc = {}, {}
    for s in shots:
        if s.get("kind") != "FG":
            continue
        tk = find_takeoff(doc, s)
        if tk is None:
            s["points"] = None
            continue
        s.update(tk)
        img = read_at(cap, video, tk["take"])
        if img is None:
            s["points"] = None
            continue
        img = cv2.resize(img, (960, int(doc["frame_size"][1] * scale)))
        lines = line_map(img)
        rim = [v * scale for v in tk["rim_at_take"]]
        M = to_map(rim)
        side = side_of(rim)
        a, n = acc.setdefault(side, [np.zeros((MAP_H, MAP_W), np.float32), np.zeros((MAP_H, MAP_W), np.float32)])
        a += cv2.warpAffine(lines, M, (MAP_W, MAP_H))
        n += cv2.warpAffine(np.ones_like(lines), M, (MAP_W, MAP_H))
        frames[id(s)] = (lines, M, side)
    arcs, maps = {}, {}
    for side, (a, n) in acc.items():
        m = np.where(n >= 4, a / np.maximum(n, 1), 0).astype(np.float32)
        maps[side] = (thin_ridges(m), n >= 4)
        arcs[side] = fit_arc(*maps[side], side)
    # The camera sits near mid-court, so the two baskets' arcs are close to mirror images. When one
    # fit is much weaker (a noisy floor, or few shots at that end), search near the mirrored other one.
    if len(arcs) == 2:
        strong, weak = sorted(arcs, key=lambda k: -arcs[k][1])
        if arcs[weak][1] < 0.7 * arcs[strong][1]:
            cx, cy, a_, b_, th = arcs[strong][0]
            arcs[weak] = fit_arc(*maps[weak], weak, around=(2 * BX - cx, cy, a_, b_, -th))
            print(f"{weak} basket arc was weak; refit near the mirrored {strong} arc")
    for side in arcs:
        resp = maps[side][0]
        print(f"{side} basket arc: line contrast along it {arcs[side][1]:.2f}")
        if debug:
            vis = cv2.cvtColor((255 * (resp / (np.percentile(resp, 99.7) + 1e-6)).clip(0, 1)).astype(np.uint8), cv2.COLOR_GRAY2BGR)
            x, y = ellipse_points(*arcs[side][0], side, k=400)
            for px, py in zip(x.astype(int), y.astype(int)):
                cv2.circle(vis, (px, py), 1, (255, 0, 255), -1)
            cv2.circle(vis, (BX, BY), 3, (255, 0, 0), -1)
            cv2.imwrite(str(debug / f"arc_{side}.png"), cv2.resize(vis[60:380, 160:840], None, fx=1.5, fy=1.5))
    for s in shots:
        if id(s) not in frames:
            continue
        lines, M, side = frames[id(s)]
        fx, fy = s["feet"][0] * scale, s["feet"][1] * scale
        mx, my = M[0, 0] * fx + M[0, 2], M[1, 1] * fy + M[1, 2]
        r_feet = float(np.hypot(mx - BX, my - BY))
        ang = float(np.degrees(np.arctan2(my - BY, mx - BX)))
        r_avg = arc_radius(arcs[side], ang)
        if r_avg is None:
            s.update(points=2, arc_source="behind basket", margin=None)
            continue
        r_own = refine(lines, M, ang, r_avg)
        r_arc = r_own if r_own is not None else r_avg
        # Feet past the line, in rough feet: the arc is 19 ft 9 in from the basket in every direction,
        # so its radius along this ray sets the scale (the far side is squashed in the picture).
        margin = ARC_FT * (r_feet - r_arc) / r_arc
        s.update(points=3 if margin > MARGIN_FT else 2, margin=round(margin, 1),
                 arc_source="own frame" if r_own is not None else "game average")
    return arcs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--sheet", action="store_true", help="write contact sheets of 2s and 3s")
    parser.add_argument("--debug", type=Path, help="folder for pictures of the traced arcs")
    args = parser.parse_args()
    doc = json.loads(args.tracks.read_text())
    split = json.loads(args.tracks.with_suffix(".split.json").read_text())
    shots = split["shots"]
    arcs = classify(doc, shots, args.video, debug=args.debug)
    fg = [s for s in shots if s.get("kind") == "FG"]
    print(f"{len(fg)} field goal attempts, {sum(s.get('points') is None for s in fg)} without a takeoff found")
    for team in ("Valley", "Opponent"):
        mine = [s for s in fg if s.get("team") == team]
        threes = [s for s in mine if s.get("points") == 3]
        print(f"{team:9} 3PA {len(threes):3}  (made {sum(s['made'] for s in threes)}) of {len(mine)} FGA")
    out = args.tracks.with_suffix(".threes.json")
    out.write_text(json.dumps({"arcs": {k: {"ellipse_rim_widths": [round(float(v[0][0] - RX) / SC, 2), round(float(v[0][1] - RY) / SC, 2)] + [round(float(x) / SC, 2) for x in v[0][2:4]] + [round(float(np.degrees(v[0][4])), 1)],
                                         "line_strength": round(v[1], 3)} for k, v in arcs.items()},
                               "shots": shots}, indent=1))
    print("wrote", out)
    if args.sheet:
        random.seed(0)
        for pts in (2, 3):
            group = [s for s in fg if s.get("points") == pts]
            pick = sorted(random.sample(group, min(12, len(group))), key=lambda s: s["t"])
            sheet(args.video, doc, pick, arcs, args.tracks.with_name(args.tracks.stem + f".pts{pts}.jpg"), f"12 random {pts}s")


def sheet(video, doc, shots, arcs, out, title):
    """Release frames with the shooter box (green), feet (red dot) and the game-average arc (magenta)."""
    cap = cv2.VideoCapture(str(video))
    tiles = []
    for s in shots:
        cap.set(cv2.CAP_PROP_POS_MSEC, s["take"] * 1000)
        ok, img = cap.read()
        if not ok:
            continue
        rim = s["rim_at_take"]
        side = "left" if (rim[0] + rim[2]) / 2 < doc["frame_size"][0] / 2 else "right"
        Mi = cv2.invertAffineTransform(to_map(rim))
        mx, my = ellipse_points(*arcs[side][0], side, k=600)
        for px, py in zip(Mi[0, 0] * mx + Mi[0, 2], Mi[1, 1] * my + Mi[1, 2]):
            cv2.circle(img, (int(px), int(py)), 2, (255, 0, 255), -1)
        x0, y0, x1, y1 = s["shooter_box"]
        cv2.rectangle(img, (x0, y0), (x1, y1), (0, 255, 0), 2)
        cv2.circle(img, (int(s["feet"][0]), int(s["feet"][1])), 7, (0, 0, 255), -1)
        img = cv2.resize(img, (640, 360))
        m, sec = divmod(int(s["t"]), 60)
        cv2.putText(img, f"{m}:{sec:02d} {s['team'][0]} m={s['margin']} {s['arc_source'][:3]}", (8, 26), 0, 0.7, (0, 255, 255), 2)
        tiles.append(img)
    if not tiles:
        return
    tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % 3)
    img = np.vstack([np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)])
    cv2.putText(img, title, (8, img.shape[0] - 10), 0, 0.8, (255, 255, 255), 2)
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    print("wrote", out)


if __name__ == "__main__":
    main()
