"""A small jersey number model, trained on the reader's own confident reads, and player groups built
from numbers.

Usage (ml venv; Modal login from ~/.modal.toml):
    ml/.venv/bin/python ml/tools/jersey_model.py train --games mitty riordan --test-on-other [--local]
    ml/.venv/bin/python ml/tools/jersey_model.py vote ml/data/tracks/<game>.v4.json [--preds <name>]
    ml/.venv/bin/python ml/tools/jersey_model.py players ml/data/tracks/<game>.v4.json

Why: EasyOCR (jersey_numbers.py) first searches each crop for where text is, which is slow (about
$1 per game on GPUs) and misses about 2 of 3 tracks. Basketball jerseys show the number on the
front and back, so a plain image classifier on the torso crop can learn to read it directly.

Training labels come for free from jersey_numbers.py, no hand labeling:
- Only tracks whose EasyOCR vote has confidence 0.6 or more.
- Inside such a track, only the crops between the first and last crop that EasyOCR read as the
  track's number. Tracks often switch to another player partway through, so crops outside that
  stretch may show someone else. Crops read as a different number are dropped too.

The model is a ResNet18 with three small heads: how many digits (1 or 2), the first digit, and
the second digit. Reading digit by digit lets it name numbers it rarely saw in training (an 11
from 1s and 1s). A crop's reading is the most likely whole number; its probability is the
product of the head probabilities.

Steps:
- train: builds the labeled sets and trains, on this Mac's GPU with --local (about the same
  speed as a T4 for a model this small) or on a Modal T4 using the private aim-train volume.
  Then it reads every crop of the chosen games. With --test-on-other it also trains one model per
  game and reads the other game with it, which is the fair test.
- vote: per track, same rule as jersey_numbers.py (2 or more crops agree, at least half the
  readings). Writes ml/data/jerseys/<game>.v4.<preds>.jerseys.json.
- players: drops tracks outside live game time (spectators, warmups), then joins tracks into
  players. See off_court_share() and join_players().

Everything stays in ml/data (gitignored); the crops show minors.
"""

import argparse
import io
import json
import pickle
import random
from collections import Counter, defaultdict
from pathlib import Path

ML = Path(__file__).resolve().parents[1]
JER = ML / "data" / "jerseys"
TRACKS = ML / "data" / "tracks"
GAMES = {"mitty": "valley-vs-archbishop-mitty.v4", "riordan": "valley-vs-archbishop-riordan.v4"}

LABEL_CONF = 0.6     # track vote confidence needed to use its crops for training
SIZE = 128           # model input, px
MIN_PROB = 0.85      # a crop's reading counts in the vote only above this (half that with a roster)
VOL_DIR = "/jersey"


# ---------- labels ----------

def best_reading(r):
    r = [x for x in r if x[1] >= 0.3 and not (len(x[0]) == 2 and x[0][0] == "0" and x[0] != "00")]
    return max(r, key=lambda x: x[1])[0] if r else None


def training_set(game: str) -> list[tuple[bytes, str]]:
    base = JER / GAMES[game]
    crops = pickle.loads((base.parent / (base.name + ".crops.pkl")).read_bytes())
    reads = json.loads((base.parent / (base.name + ".reads.json")).read_text())
    votes = json.loads((base.parent / (base.name + ".jerseys.json")).read_text())
    by = defaultdict(list)
    for (tid, t, jpg), (_, _, r) in zip(crops, reads):
        by[tid].append((jpg, best_reading(r)))
    out = []
    for tid, v in votes.items():
        if not v.get("number") or v.get("confidence", 0) < LABEL_CONF:
            continue
        items, num = by[tid], v["number"]
        hits = [i for i, (_, rd) in enumerate(items) if rd == num]
        for jpg, rd in items[hits[0]:hits[-1] + 1]:
            if rd in (None, num):
                out.append((jpg, num))
    return out


def all_crops(game: str) -> list[bytes]:
    base = JER / GAMES[game]
    return [c[2] for c in pickle.loads((base.parent / (base.name + ".crops.pkl")).read_bytes())]


# ---------- model (runs on Modal) ----------

def encode(num: str):
    """'7' -> (0, 7, -100); '25' -> (1, 2, 5). -100 means 'no second digit' (ignored in the loss)."""
    return (0, int(num), -100) if len(num) == 1 else (1, int(num[0]), int(num[1]))


def build_model():
    import torch.nn as nn
    import torchvision

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            m = torchvision.models.resnet18(weights=torchvision.models.ResNet18_Weights.IMAGENET1K_V1)
            m.fc = nn.Identity()
            self.body = m
            self.length, self.first, self.second = nn.Linear(512, 2), nn.Linear(512, 10), nn.Linear(512, 10)

        def forward(self, x):
            f = self.body(x)
            return self.length(f), self.first(f), self.second(f)

    return Net()


def to_tensor(jpg: bytes, train: bool):
    import torchvision.transforms as T
    from PIL import Image

    img = Image.open(io.BytesIO(jpg)).convert("RGB")
    norm = [T.ToTensor(), T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])]
    if train:  # no flips: a mirrored 21 is not a 21
        tf = T.Compose([T.RandomResizedCrop(SIZE, scale=(0.75, 1.0), ratio=(0.85, 1.15)),
                        T.RandomRotation(8), T.ColorJitter(0.35, 0.35, 0.35, 0.05),
                        T.RandomGrayscale(0.15), T.RandomApply([T.GaussianBlur(5, (0.1, 1.5))], p=0.3)] + norm)
    else:
        tf = T.Compose([T.Resize((SIZE, SIZE))] + norm)
    return tf(img)


class CropSet:
    """Training crops for the DataLoader. Kept at the top of the file so loader processes on macOS
    (which start fresh and re-import this file) can find it."""

    def __init__(self, data):
        self.data = data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, i):
        import torch

        jpg, num = self.data[i]
        return to_tensor(jpg, True), torch.tensor(encode(num))


def train_model(data: list[tuple[bytes, str]], device: str = "cuda", epochs: int = 14, batch: int = 128, workers: int = 6):
    import torch
    import torch.nn.functional as F
    from torch.utils.data import DataLoader

    dl = DataLoader(CropSet(data), batch_size=batch, shuffle=True, num_workers=workers, drop_last=True,
                    persistent_workers=workers > 0)
    model = build_model().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 1e-3, total_steps=epochs * len(dl))
    for ep in range(epochs):
        model.train()
        tot = n = 0
        for x, y in dl:
            x, y = x.to(device), y.to(device)
            a, b, c = model(x)
            loss = F.cross_entropy(a, y[:, 0]) + F.cross_entropy(b, y[:, 1]) + F.cross_entropy(c, y[:, 2], ignore_index=-100)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tot += loss.item() * len(x)
            n += len(x)
        print(f"epoch {ep + 1}: loss {tot / n:.3f}", flush=True)
    return model


def predict(model, jpgs: list[bytes], device: str = "cuda", top: int = 5) -> list[list]:
    """The `top` most likely numbers per crop with their probabilities, best first:
    [[number, probability], ...]. Keeping more than the best one lets a team roster pick the
    likeliest number that's actually on the team."""
    import torch

    model.eval()
    out = []
    with torch.no_grad():
        for k in range(0, len(jpgs), 256):
            x = torch.stack([to_tensor(j, False) for j in jpgs[k:k + 256]]).to(device)
            a, b, c = (t.softmax(1).cpu() for t in model(x))
            # 10 one-digit numbers, then 90 two-digit ones (10 to 99; "05" is not a jersey number)
            one = a[:, :1] * b
            two = (a[:, 1, None, None] * b[:, :, None] * c[:, None, :]).reshape(len(x), 100)[:, 10:]
            probs = torch.cat([one, two], 1)
            p, idx = probs.topk(top, 1)
            for i in range(len(x)):
                out.append([[str(int(j)), round(float(q), 3)] for q, j in zip(p[i], idx[i])])
    return out


def cmd_predict(name: str, games: list[str]) -> None:
    """Read every crop of these games with a saved model (ml/data/jerseys/models/<name>.pth)."""
    import torch

    model = build_model()
    model.load_state_dict(torch.load(JER / "models" / f"{name}.pth", map_location="cpu"))
    model.to("mps")
    for g in games:
        path = JER / f"{GAMES[g]}.preds-{name}.json"
        path.write_text(json.dumps(predict(model, all_crops(g), device="mps")))
        print("wrote", path, flush=True)


try:
    import modal
except ImportError:
    modal = None

if modal:
    app = modal.App("aim-jersey-model")
    volume = modal.Volume.from_name("aim-train", create_if_missing=True)
    image = (
        modal.Image.debian_slim(python_version="3.10")
        .pip_install("torch==2.4.1", "torchvision==0.19.1", "pillow", "numpy<2")
        .run_commands("python -c \"import torchvision; torchvision.models.resnet18(weights='IMAGENET1K_V1')\"")
    )

    @app.function(image=image, gpu="T4", volumes={"/vol": volume}, timeout=3600, cpu=8)
    def remote_run(train_games: list[str], predict_games: list[str], name: str) -> dict:
        import torch

        data = [x for g in train_games for x in pickle.loads(Path(f"/vol{VOL_DIR}/{g}.train.pkl").read_bytes())]
        random.seed(0)
        print(f"{name}: {len(data)} training crops from {train_games}", flush=True)
        model = train_model(data)
        buf = io.BytesIO()
        torch.save(model.state_dict(), buf)
        Path(f"/vol{VOL_DIR}/{name}.pth").write_bytes(buf.getvalue())
        volume.commit()
        return {g: predict(model, pickle.loads(Path(f"/vol{VOL_DIR}/{g}.crops.pkl").read_bytes()))
                for g in predict_games}


def run_local(train_games: list[str], predict_games: list[str], name: str) -> dict:
    """Same as remote_run, on this Mac's GPU (torch "mps"). Small batches and 2 loader processes,
    so it doesn't take the CPU from film decoding running at the same time."""
    import torch

    data = [x for g in train_games for x in training_set(g)]
    random.seed(0)
    torch.manual_seed(0)
    print(f"{name}: {len(data)} training crops from {train_games}", flush=True)
    model = train_model(data, device="mps", epochs=12, batch=64, workers=2)
    (JER / "models").mkdir(exist_ok=True)
    torch.save(model.state_dict(), JER / "models" / f"{name}.pth")
    return {g: predict(model, all_crops(g), device="mps") for g in predict_games}


def cmd_train(games: list[str], other: bool, local: bool) -> None:
    import tempfile

    runs = [(games, games, "all")]
    if other:
        runs = [([g], [h for h in games if h != g], f"from-{g}") for g in games] + runs
    if local:
        for tr, pr, name in runs:
            for g, preds in run_local(tr, pr, name).items():
                path = JER / f"{GAMES[g]}.preds-{name}.json"
                path.write_text(json.dumps(preds))
                print("wrote", path, flush=True)
        return

    tmp = Path(tempfile.mkdtemp())
    with volume.batch_upload(force=True) as up:
        for g in games:
            ts = training_set(g)
            print(f"{g}: {len(ts)} training crops, numbers {Counter(n for _, n in ts).most_common(8)} ...")
            (tmp / f"{g}.train.pkl").write_bytes(pickle.dumps(ts))
            (tmp / f"{g}.crops.pkl").write_bytes(pickle.dumps(all_crops(g)))
            up.put_file(str(tmp / f"{g}.train.pkl"), f"{VOL_DIR}/{g}.train.pkl")
            up.put_file(str(tmp / f"{g}.crops.pkl"), f"{VOL_DIR}/{g}.crops.pkl")
    with app.run():
        results = list(remote_run.starmap(runs))
    for (_, _, name), res in zip(runs, results):
        for g, preds in res.items():
            path = JER / f"{GAMES[g]}.preds-{name}.json"
            path.write_text(json.dumps(preds))
            print("wrote", path)


# ---------- vote ----------

def vote_model(game_stem: str, preds_name: str, roster: dict | None = None, doc: dict | None = None) -> dict:
    """Per-track vote over the model's crop readings. With a roster ({team group: set of numbers})
    and the tracks doc, each crop's reading is its likeliest number on that team's roster."""
    crops = pickle.loads((JER / f"{game_stem}.crops.pkl").read_bytes())
    preds = json.loads((JER / f"{game_stem}.preds-{preds_name}.json").read_text())
    per = defaultdict(list)
    for (tid, t, _), top in zip(crops, preds):
        if top and not isinstance(top[0], list):  # older files kept only the best reading
            top = [top]
        allowed = None
        if roster and doc:
            allowed = roster.get(doc["tracks"][str(tid)]["group"])
        if allowed:
            top = [x for x in top if x[0] in allowed]
            need = MIN_PROB / 2  # the roster already rules out most wrong numbers
        else:
            need = MIN_PROB
        num, p = top[0] if top else (None, 0.0)
        per[tid].append((t, num if p >= need else None, p))
    result = {}
    for tid, rs in per.items():
        got = [n for _, n, _ in rs if n]
        if not got:
            result[tid] = {"number": None, "crops": len(rs), "reads": 0}
            continue
        (num, agree), = Counter(got).most_common(1)
        share = agree / len(got)
        ok = agree >= 2 and share >= 0.5
        result[tid] = {"number": num if ok else None, "crops": len(rs), "reads": len(got), "agree": agree,
                       "confidence": round(share * min(1.0, agree / 4), 2) if ok else 0.0,
                       "votes": dict(Counter(got).most_common(4))}
    return result


# ---------- off the court ----------

def off_court_share(doc: dict, window: dict | None) -> dict:
    """Per track, the share of its time outside live game time: before tip-off, after the final
    buzzer, or at halftime (from game_window.py's <tracks>.window.json).

    Spectators and kids on the floor show up at those times (warmup shirts before the game, a
    hoodie shooting around after it). Filtering by where the feet are in the frame doesn't work:
    on the hand check those people stood on the floor, while a real player in the near corner
    looked "off court". Game time separates them cleanly."""
    if not window or not window.get("found"):
        return {}
    start, end = window["start"], window["end"]
    breaks = [window["halftime"]] if window.get("halftime") else []
    out = {}
    for tid, v in doc["tracks"].items():
        a, b = v["start"], v["end"]
        span = max(0.1, b - a)
        live = max(0.0, min(b, end) - max(a, start))
        for h0, h1 in breaks:
            live -= max(0.0, min(b, h1) - max(a, h0))
        out[tid] = 1 - max(0.0, live) / span
    return out


# ---------- players ----------

def join_players(doc: dict, numbers: dict, stitch_map: dict | None, min_conf: float = 0.3) -> dict:
    """Group tracks into players: same team and same confident number, never on screen at the same
    time. Stitched groups (stitch_tracks.py) come first, then numbers join them further.
    If two tracks with the same team and number are on screen together for a good while, one is
    wrong (or the team has two players with one number), so the track from the less confident
    group is left out. Only that track, not its whole group.
    Returns {player key: {"team", "number", "tracks": [...], "seconds"}}."""
    tracks = doc["tracks"]
    group_of = {}
    if stitch_map:
        for old, new in stitch_map.items():
            group_of[str(old)] = str(new)
    groups = defaultdict(list)
    for tid in tracks:
        groups[group_of.get(tid, tid)].append(tid)

    # Number per stitched group: votes weighted by track confidence and length.
    gnum = {}
    for g, tids in groups.items():
        score = Counter()
        for t in tids:
            v = numbers.get(t)
            if v and v.get("number") and v.get("confidence", 0) >= min_conf:
                score[v["number"]] += v["confidence"] * tracks[t]["frames"]
        if score:
            (num, s), = score.most_common(1)
            if s >= 0.7 * sum(score.values()):
                gnum[g] = (num, s)

    # Jersey color is "unsure" for about 1 in 7 numbered tracks (shadows, mixed boxes). If that
    # number is clearly one team's elsewhere in the game (80% of its time), use that team.
    num_team = defaultdict(Counter)
    for g, (num, s) in gnum.items():
        for t in groups[g]:
            if tracks[t]["group"] != "unsure":
                num_team[num][tracks[t]["group"]] += tracks[t]["frames"]

    def team_of(g, num):
        teams = Counter(tracks[t]["group"] for t in groups[g] if tracks[t]["group"] != "unsure")
        if teams:
            return teams.most_common(1)[0][0]
        c = num_team[num]
        if c:
            (team, n), = c.most_common(1)
            if n >= 0.8 * sum(c.values()):
                return team
        return None

    players = defaultdict(lambda: {"tracks": [], "spans": [], "score": 0.0})
    for g, (num, s) in sorted(gnum.items(), key=lambda x: -x[1][1]):
        team = team_of(g, num)
        if team is None:
            continue
        p = players[f"{team}#{num}"]
        added = False
        for t in groups[g]:
            a, b = tracks[t]["start"], tracks[t]["end"]
            # A real clash: this track and one already given the number are on screen together
            # for a good part of the shorter one. Brief overlaps are the same person boxed twice.
            if any(min(b, d) - max(a, c) > max(0.5, 0.3 * min(b - a, d - c)) for c, d in p["spans"]):
                continue
            p["tracks"].append(t)
            p["spans"].append((a, b))
            added = True
        if added:
            p["score"] += s
            p["team"], p["number"] = team, num
    out = {}
    for k, p in players.items():
        if not p["tracks"]:
            continue
        out[k] = {"team": p["team"], "number": p["number"], "tracks": sorted(p["tracks"], key=int),
                  "seconds": round(sum(tracks[t]["frames"] for t in p["tracks"]) / 10, 1)}
    return out


def combine(easy: dict, model: dict) -> dict:
    """EasyOCR's number for a track when it gave one, else the model's. On the hand check (model
    trained on the other game) EasyOCR was the more precise of the two, and the model named about
    twice as many tracks, so the model fills the gaps instead of overruling."""
    out = dict(model)
    for t, v in easy.items():
        if v.get("number"):
            out[t] = dict(v, source="easyocr")
    return out


def parse_roster(items: list[str]) -> dict | None:
    """["1=0,1,2,15"] -> {1: {"0", "1", "2", "15"}}. Team groups as in the tracks file (0 or 1)."""
    if not items:
        return None
    out = {}
    for it in items:
        team, nums = it.split("=")
        out[int(team)] = set(nums.split(","))
    return out


def cmd_players(tracks_path: Path, preds: str, off_max: float, roster: dict | None = None) -> None:
    doc = json.loads(tracks_path.read_text())
    stem = tracks_path.stem
    easy = json.loads((JER / f"{stem}.jerseys.json").read_text())
    if preds:
        model = vote_model(stem, preds, roster, doc if roster else None)
        numbers = combine(easy, model)
    else:
        numbers = easy
    wpath = TRACKS / f"{stem}.window.json"
    off = off_court_share(doc, json.loads(wpath.read_text()) if wpath.exists() else None)
    if not off:
        print("no game window found (run game_window.py first); keeping every track")
    dropped = {t for t, s in off.items() if s > off_max}
    numbers = {t: v for t, v in numbers.items() if t not in dropped}
    smap_path = TRACKS / f"{stem}.stitch_map.json"
    smap = None
    if smap_path.exists():
        raw = json.loads(smap_path.read_text())
        smap = raw.get("map", raw) if isinstance(raw, dict) else None
        smap = {str(k): str(v if not isinstance(v, dict) else v.get("new")) for k, v in smap.items()} if smap else None
    players = join_players(doc, numbers, smap)
    tr = doc["tracks"]
    total = sum(v["frames"] for t, v in tr.items() if t not in dropped) / 10
    named_tracks = sum(tr[t]["frames"] for t, v in numbers.items() if v.get("number") and v.get("confidence", 0) >= 0.3) / 10
    named_players = sum(p["seconds"] for p in players.values())
    print(f"off court: {len(dropped)} tracks dropped ({sum(tr[t]['frames'] for t in dropped) / 600:.0f} player-min)")
    print(f"player screen time with a number: tracks alone {named_tracks / total:.0%}, "
          f"after joining {named_players / total:.0%} (of {total / 60:.0f} player-min)")
    for k, p in sorted(players.items(), key=lambda x: -x[1]["seconds"]):
        print(f"  {k}: {len(p['tracks'])} tracks, {p['seconds'] / 60:.1f} min")
    out = JER / f"{stem}.players{'-' + preds if preds else ''}.json"
    out.write_text(json.dumps(players, indent=1))
    print("wrote", out)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="step", required=True)
    t = sub.add_parser("train")
    t.add_argument("--games", nargs="+", default=list(GAMES))
    t.add_argument("--test-on-other", action="store_true")
    t.add_argument("--local", action="store_true", help="train on this Mac's GPU (mps) instead of Modal")
    pr = sub.add_parser("predict")
    pr.add_argument("--model", default="all")
    pr.add_argument("--games", nargs="+", default=list(GAMES))
    v = sub.add_parser("vote")
    v.add_argument("tracks", type=Path)
    v.add_argument("--preds", default="all")
    pl = sub.add_parser("players")
    pl.add_argument("tracks", type=Path)
    pl.add_argument("--preds", default="all", help="model predictions to use; empty for EasyOCR votes")
    pl.add_argument("--roster", nargs="*", default=[], help='team group=numbers, e.g. 1=0,1,2,3,15 (optional)')
    pl.add_argument("--off-max", type=float, default=0.5, help="drop tracks outside live game time more than this share of the time")
    a = p.parse_args()
    if a.step == "train":
        cmd_train(a.games, a.test_on_other, a.local)
    elif a.step == "predict":
        cmd_predict(a.model, a.games)
    elif a.step == "vote":
        res = vote_model(a.tracks.stem, a.preds)
        out = JER / f"{a.tracks.stem}.{a.preds}.jerseys.json"
        out.write_text(json.dumps(res, indent=1))
        n = sum(1 for v in res.values() if v["number"])
        print(f"{n} of {len(res)} tracks got a number -> {out}")
    else:
        cmd_players(a.tracks, a.preds, a.off_max, parse_roster(a.roster))


if __name__ == "__main__":
    main()
