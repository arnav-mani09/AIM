"""Find when the game starts and ends in a film, from its tracks file alone.

Usage:
    ml/.venv/bin/python ml/tools/game_window.py ml/data/tracks/<game>.v4.json [--true START END]

Full-game films run long: warmups, introductions and halftime are on the tape, and some
films keep recording after the buzzer (a JV game, kids shooting around). Stats should only
count game time, so this finds tip-off, the final buzzer, halftime and likely quarter breaks.

How it decides, from what the detector already sees each second:
- Referees are the best sign of game time. In warmups they're mostly off the court; during
  play, timeouts and quarter breaks at least one is on screen nearly all the time; after
  the buzzer they walk off within seconds.
- Warmups have many balls in the air at once (2 to 5 per frame). Game time has one.
- A "live" second has refs on screen most of the time and few balls around it. Live
  stretches with gaps under 3 minutes (timeouts, refs blocked) are joined. Stretches of
  8+ minutes are halves; halftime is the 5 to 25 minute gap between two of them.
- Tip-off: refs arrive 20 to 70 s before the jump ball, while players stand in lines or
  around the circle. When play starts the players spread out along the court, so their
  feet suddenly cover much more of the frame's height. Tip-off is the first moment after
  the refs arrive and the warmup balls are gone when that spread jumps above normal.
- Final buzzer: the last moment refs are on screen before they leave for good.
- Quarter breaks (lower confidence): in each half, the stretch with players off the floor
  (benches) closest to the half's middle. A full timeout looks the same, so treat these as
  a guess for the coach to confirm.

These are rules, not a model. Checked against scoreboard times in ml/games.yaml.
"""

import argparse
import json
import statistics as st
from pathlib import Path

REF_MIN, BALL_MIN, PLAYER_MIN = 0.5, 0.3, 0.5
MERGE_GAP = 180  # seconds: shorter gaps in live time are timeouts or missed refs
MIN_HALF = 480  # seconds: a stretch this long is a half, not a stray
HALFTIME = (300, 1500)  # seconds: how long halftime can be


def per_second(doc: dict) -> dict:
    """Per whole second: share of frames with a ref, balls per frame, players per frame,
    and how spread out players' feet are up and down the frame (share of frame height)."""
    frame_h, out = doc["frame_size"][1], {}
    for t, boxes in doc["frames"]:
        s = out.setdefault(int(t), {"n": 0, "ref": 0, "balls": 0, "players": 0, "spread": []})
        players = [b for b in boxes if b[0] == 1 and b[5] >= PLAYER_MIN]
        s["n"] += 1
        s["ref"] += any(b[0] == 2 and b[5] >= REF_MIN for b in boxes)
        s["balls"] += sum(1 for b in boxes if b[0] == 0 and b[5] >= BALL_MIN)
        s["players"] += len(players)
        if len(players) >= 4:
            s["spread"].append(st.pstdev([b[4] for b in players]) / frame_h)
    end = max(out) + 1 if out else 0
    series = {k: [] for k in ("ref", "balls", "players", "spread")}
    for sec in range(end):
        s = out.get(sec)
        n = s["n"] if s else 0
        series["ref"].append(s["ref"] / n if n else 0.0)
        series["balls"].append(s["balls"] / n if n else 0.0)
        series["players"].append(s["players"] / n if n else 0.0)
        series["spread"].append(st.mean(s["spread"]) if s and s["spread"] else None)
    return series


def mean(xs: list, a: int, b: int) -> float:
    """Mean of xs[a:b], skipping missing values; 0 if there are none."""
    vals = [x for x in xs[max(0, a):max(0, b)] if x is not None]
    return sum(vals) / len(vals) if vals else 0.0


def live_stretches(series: dict) -> list[list[int]]:
    """[start, end] seconds of stretches with refs on screen and no warmup balls."""
    n = len(series["ref"])
    live = [mean(series["ref"], t - 15, t + 15) >= 0.75 and mean(series["balls"], t - 15, t + 15) <= 1.3
            and mean(series["players"], t - 15, t + 15) >= 4 for t in range(n)]
    runs, start = [], None
    for t, on in enumerate(live + [False]):
        if on and start is None:
            start = t
        if not on and start is not None:
            runs.append([start, t])
            start = None
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < MERGE_GAP:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] >= MIN_HALF]


def pick_halves(stretches: list) -> list:
    """The two stretches with a halftime-sized gap between them that cover the most time.
    One long stretch alone is used if no pair fits (a film with no halftime break)."""
    best, best_len = stretches[:1], -1
    for a, b in zip(stretches, stretches[1:]):
        gap = b[0] - a[1]
        if HALFTIME[0] <= gap <= HALFTIME[1] and (a[1] - a[0]) + (b[1] - b[0]) > best_len:
            best, best_len = [a, b], (a[1] - a[0]) + (b[1] - b[0])
    if best_len < 0 and stretches:
        best = [max(stretches, key=lambda r: r[1] - r[0])]
    return best


def find_tipoff(series: dict, rough: int, typical_spread: float) -> int:
    """First second near the rough start with refs on, warmups over, and players spreading out."""
    for t in range(max(0, rough - 150), rough + 240):
        refs_on = mean(series["ref"], t - 10, t + 20) >= 0.8
        warmups_over = mean(series["balls"], t, t + 20) <= 1.2
        spread = mean(series["spread"], t - 5, t + 5)
        if refs_on and warmups_over and spread >= 1.1 * typical_spread:
            return t
    return rough


def find_buzzer(series: dict, rough: int) -> int:
    """Last second near the rough end that still has refs on screen before they leave."""
    for t in range(rough + 60, rough - 240, -1):
        if mean(series["ref"], t - 10, t) >= 0.7 and mean(series["ref"], t, t + 30) < 0.5:
            return t
    return rough


def quarter_break(series: dict, half: list) -> list | None:
    """Stretch of 40+ s with players off the floor, closest to the half's middle."""
    a, b = half
    mid, runs, start = (a + b) / 2, [], None
    for t in range(a + 120, b - 120):
        low = mean(series["players"], t - 5, t + 5) < 4
        if low and start is None:
            start = t
        if not low and start is not None:
            if t - start >= 40:
                runs.append([start, t])
            start = None
    return min(runs, key=lambda r: abs((r[0] + r[1]) / 2 - mid)) if runs else None


def find_window(doc: dict) -> dict:
    series = per_second(doc)
    halves = pick_halves(live_stretches(series))
    if not halves:
        return {"found": False}
    inside = [x for x in series["spread"][halves[0][0]:halves[-1][1]] if x is not None]
    typical = st.median(inside) if inside else 0.0
    start = find_tipoff(series, halves[0][0], typical)
    end = find_buzzer(series, halves[-1][1])
    halves[0][0], halves[-1][1] = start, end
    out = {"found": True, "start": start, "end": end, "halves": halves}
    if len(halves) == 2:
        out["halftime"] = [halves[0][1], halves[1][0]]
    out["quarter_breaks"] = [q for q in (quarter_break(series, h) for h in halves) if q]
    return out


def clock(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--true", type=float, nargs=2, metavar=("START", "END"),
                        help="hand-set window to compare against (seconds into the file)")
    args = parser.parse_args()
    w = find_window(json.loads(args.tracks.read_text()))
    if not w["found"]:
        print("no game found (no long stretch with refs on court)")
        return
    print(f"tip-off {w['start']} s ({clock(w['start'])}), final buzzer {w['end']} s ({clock(w['end'])})")
    if "halftime" in w:
        print(f"halftime {clock(w['halftime'][0])} to {clock(w['halftime'][1])}")
    for q in w["quarter_breaks"]:
        print(f"likely quarter break {clock(q[0])} to {clock(q[1])}")
    if args.true:
        print(f"vs true {args.true[0]:.0f} to {args.true[1]:.0f}: "
              f"start off by {w['start'] - args.true[0]:+.0f} s, end off by {w['end'] - args.true[1]:+.0f} s")
    out = args.tracks.with_suffix(".window.json")
    out.write_text(json.dumps(w, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
