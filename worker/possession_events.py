"""Team rebounds and turnovers (plus hidden steals and assists) for the site's event step.

Runs inside shot_events.build_events, after the shots, on the same tracks and the same labeled
shots. The rules are ml/tools/possession.py version 2 (run_v2), so the site and
possession_eval.py agree on the same input.

The team of each ball holder comes from the film: one frame per hold is read and the holder's
torso pixels vote between the two jersey colors (about 2 minutes a game on CPU, reading the
film front to back). If the film can't be read, each holder's team falls back to the tracker's
team split, which is less reliable, so every event's confidence is lowered and the result says
film_read: false.

Steals and assists are drafted too but marked hidden: they aren't accurate yet, so the site
stores them for later training and never shows or counts them.
"""

import sys
import time
from pathlib import Path

_here = Path(__file__).resolve().parent
for p in (_here, _here.parent / "ml" / "tools"):
    if (p / "possession.py").exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

import possession as P  # noqa: E402

SHOWN = ("oreb", "dreb", "to")   # on the site
HIDDEN = ("stl", "ast")          # stored for training, never shown
NO_FILM_FACTOR = 0.7             # confidence multiplier when holders' teams come from the tracker alone


def site_events(events: list[dict], film_read: bool) -> list[dict]:
    """possession.py events in the site's event shape (the same shape as shots)."""
    out = []
    for e in events:
        if e["type"] not in SHOWN + HIDDEN:
            continue
        sure = P.EVENT_CONF.get((e["type"], e.get("how")), P.EVENT_CONF.get((e["type"], None), 0.5))
        if not film_read:
            sure *= NO_FILM_FACTOR
        detail = {k: e.get(k) for k in ("how", "evidence", "shot_t", "track", "live", "passer_track", "shooter_track")
                  if e.get(k) is not None}
        detail["film_read"] = film_read
        out.append({
            "type": e["type"],
            "t": round(float(e["t"]), 2),
            "team": e["team"].lower(),
            "shot_type": "none",
            "made": False,
            "confidence": round(sure, 2),
            "player_number": None,
            "rim": None,
            "hidden": e["type"] in HIDDEN,
            "parts": {"event": round(sure, 2)},
            "detail": detail,
        })
    return out


def build_possession(doc: dict, labeled: list[dict], info: dict, span: tuple, half_break, names: dict,
                     video: str | None = None, log=print) -> dict:
    """labeled and info come from shot_split.split (with Valley/Opponent from the coach's jersey
    colors), span is the game window and half_break the halftime range (or None). names maps the
    tracker's color groups 0 and 1 to "Valley"/"Opponent". Returns {"events", "info"}."""
    started = time.monotonic()
    window = [float(span[0]), float(span[1])]
    runs = P.hold_runs(doc, *window)
    film_read, film_error = False, None
    if video:
        try:
            P.read_holder_colors(doc, runs, video)
            film_read = any("pix" in r for r in runs)
            if not film_read:
                film_error = "no holder colors read"
        except Exception as exc:  # a bad film shouldn't lose the events; fall back to the tracker
            film_error = f"{exc}"[:200]
            for r in runs:
                for k in ("lab", "dark", "stripes", "pix", "floor"):
                    r.pop(k, None)
    else:
        film_error = "no film"
    read_s = round(time.monotonic() - started, 1)
    if film_error:
        log(f"[POSSESSION] Film not read ({film_error}); using the tracker's team split, lower confidence")
    split = {"shots": [dict(s) for s in labeled], "halftime": info["halftime"],
             "valley_basket_first_half": info["valley_basket_first_half"]}
    timeline, events = P.run_v2(doc, split, window, half_break, names, runs)
    return {
        "events": site_events(events, film_read),
        "info": {
            "method": "v2",
            "film_read": film_read,
            "film_error": film_error,
            "holds": len(runs),
            "possessions": len(timeline),
            "seconds": {"film_read": read_s, "total": round(time.monotonic() - started, 1)},
        },
    }
