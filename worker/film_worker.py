"""AIM film worker on Modal: heavy video work that doesn't belong on the web server.

Deploy:  backend/.venv/bin/modal deploy worker/film_worker.py
Run one: backend/.venv/bin/modal run worker/film_worker.py --source-key teams/1/film/abc.mp4 [--detect]
         (or --events with a tracks key as --source-key)

The backend starts `make_proxy` when an upload completes and polls the call
for its result, then starts `detect_players` (GPU) the same way, then `make_events`.
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import modal

app = modal.App("aim-film")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install("boto3==1.40.76", "sentry-sdk==2.71.0")
)

PROXY_HEIGHT = 720
# Keyframe every 2 s at 30 fps so seeking in the player lands quickly.
KEYFRAME_INTERVAL = 60


def _r2():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}),
    )


def _probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_entries", "format=duration:stream=codec_type,width,height",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(result.stdout)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    return {
        "duration": float(info["format"]["duration"]),
        "width": video.get("width"),
        "height": video.get("height"),
        "has_audio": any(s.get("codec_type") == "audio" for s in info.get("streams", [])),
    }


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # ffmpeg writes the useful part of its error at the end.
        raise RuntimeError(f"{cmd[0]} failed: {result.stderr[-2000:]}")


def _init_sentry(environment: str) -> None:
    import sentry_sdk

    if os.environ.get("SENTRY_DSN"):
        sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], environment=environment, send_default_pii=False)
        sentry_sdk.set_tag("component", "film-worker")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("aim-r2"), modal.Secret.from_name("aim-sentry")],
    cpu=8.0,
    memory=8192,
    timeout=40 * 60,
)
def make_proxy(source_key: str, environment: str = "development") -> dict:
    """Make a 720p H.264 playback copy and a thumbnail next to the original in R2."""
    import sentry_sdk

    _init_sentry(environment)
    sentry_sdk.set_tag("source_key", source_key)
    try:
        return _make_proxy(source_key)
    except Exception as exc:
        # Report here as well as to the backend: the worker's traceback has the ffmpeg detail.
        sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(timeout=5)
        raise


def _make_proxy(source_key: str) -> dict:
    started = time.monotonic()
    bucket = os.environ["R2_BUCKET"]
    r2 = _r2()
    stem = source_key.rsplit(".", 1)[0]
    proxy_key, thumbnail_key = f"{stem}.proxy-720p.mp4", f"{stem}.thumb.jpg"

    with tempfile.TemporaryDirectory() as tmp:
        source, proxy, thumb = Path(tmp) / "source", Path(tmp) / "proxy.mp4", Path(tmp) / "thumb.jpg"
        # Download first: ffmpeg reading over HTTP dies on one network hiccup.
        r2.download_file(bucket, source_key, str(source))
        downloaded = time.monotonic()
        info = _probe(source)

        scale = [] if (info["height"] or 0) <= PROXY_HEIGHT else ["-vf", f"scale=-2:{PROXY_HEIGHT}"]
        audio = ["-c:a", "aac", "-b:a", "128k"] if info["has_audio"] else ["-an"]
        _run([
            "ffmpeg", "-v", "error", "-y", "-i", str(source), *scale,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-g", str(KEYFRAME_INTERVAL), *audio, "-movflags", "+faststart", str(proxy),
        ])
        encoded = time.monotonic()
        _run([
            "ffmpeg", "-v", "error", "-y", "-ss", str(min(info["duration"] * 0.1, 60)), "-i", str(proxy),
            "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", str(thumb),
        ])

        r2.upload_file(str(proxy), bucket, proxy_key, ExtraArgs={"ContentType": "video/mp4"})
        r2.upload_file(str(thumb), bucket, thumbnail_key, ExtraArgs={"ContentType": "image/jpeg"})
        proxy_bytes = proxy.stat().st_size

    return {
        "duration_seconds": info["duration"],
        "source_width": info["width"],
        "source_height": info["height"],
        "proxy_key": proxy_key,
        "proxy_bytes": proxy_bytes,
        "thumbnail_key": thumbnail_key,
        "timings_seconds": {
            "download": round(downloaded - started, 1),
            "encode": round(encoded - downloaded, 1),
            "total": round(time.monotonic() - started, 1),
        },
    }


# --- Player detection (GPU) -------------------------------------------------------
# The detector's weights live in the private "aim-models" volume. To ship a new model:
#   backend/.venv/bin/modal volume put aim-models ml/runs/<run>/aim_yolox_m.pth /aim_yolox_m_<run>.pth
# then change MODEL_RUN and redeploy. The tracks file name carries the model, so old
# results stay readable next to new ones.
MODEL_RUN = "v4"
MODEL_VERSION = f"aim-yolox-m-{MODEL_RUN}"
models = modal.Volume.from_name("aim-models", create_if_missing=True)
YOLOX_COMMIT = "6ddff4824372906469a7fae2dc3206c7aa4bbaee"  # same YOLOX as training
gpu_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "build-essential", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.4.1", "torchvision==0.19.1", "numpy<2", "opencv-python-headless==4.10.0.84",
        "supervision==0.26.1", "loguru", "tqdm", "pycocotools", "tabulate", "psutil", "thop", "ninja",
        "boto3==1.40.76", "sentry-sdk==2.71.0",
    )
    .run_commands(f"pip install --no-deps --no-build-isolation git+https://github.com/Megvii-BaseDetection/YOLOX.git@{YOLOX_COMMIT}")
    .add_local_file(Path(__file__).with_name("vision.py"), "/root/vision.py")
)


@app.function(
    image=gpu_image,
    gpu=["L4", "A10G", "L40S"],  # whichever is free first; L4 is cheapest
    secrets=[modal.Secret.from_name("aim-r2"), modal.Secret.from_name("aim-sentry")],
    volumes={"/models": models},
    cpu=8.0,
    memory=16384,
    timeout=90 * 60,
)
def detect_players(source_key: str, environment: str = "development") -> dict:
    """Detect and track players, refs, the ball and rims through a whole game.

    Writes <stem>.tracks-<model>.json.gz next to the original in R2: every frame at 10 fps
    with its boxes ([class, x0, y0, x1, y1, score, track_id]), plus per-track jersey color
    and a two-group color split the backend names Valley/Opponent from the game's colors.
    """
    import sentry_sdk

    _init_sentry(environment)
    sentry_sdk.set_tag("source_key", source_key)
    try:
        return _detect_players(source_key)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(timeout=5)
        raise


def _detect_players(source_key: str) -> dict:
    import gzip
    import sys

    sys.path.insert(0, "/root")
    import vision

    started = time.monotonic()
    bucket = os.environ["R2_BUCKET"]
    r2 = _r2()
    tracks_key = f"{source_key.rsplit('.', 1)[0]}.tracks-{MODEL_VERSION}.json.gz"
    with tempfile.TemporaryDirectory() as tmp:
        source, out = Path(tmp) / "source", Path(tmp) / "tracks.json.gz"
        r2.download_file(bucket, source_key, str(source))
        downloaded = time.monotonic()
        info = _probe(source)
        doc = vision.detect_and_track(source, info, Path(f"/models/aim_yolox_m_{MODEL_RUN}.pth"), MODEL_VERSION,
                                      log=lambda m: print(m, flush=True))
        detected = time.monotonic()
        with gzip.open(out, "wt") as f:
            json.dump(doc, f, separators=(",", ":"))
        r2.upload_file(str(out), bucket, tracks_key, ExtraArgs={"ContentType": "application/json", "ContentEncoding": "gzip"})
        size = out.stat().st_size

    groups = [t["group"] for t in doc["tracks"].values()]
    return {
        "tracks_key": tracks_key,
        "model": MODEL_VERSION,
        "frames": len(doc["frames"]),
        "tracks": len(doc["tracks"]),
        "tracks_by_group": {str(g): groups.count(g) for g in (0, 1, "unsure")},
        "tracks_bytes": size,
        "timings_seconds": {
            "download": round(downloaded - started, 1),
            "detect": round(detected - downloaded, 1),
            "total": round(time.monotonic() - started, 1),
        },
    }


# --- Shot events (CPU) ------------------------------------------------------------
# Drafted shots with team, free throw vs field goal, 2 or 3, make and confidence. Rules live
# in ml/tools (copied into the image at deploy), so redeploy after changing them. Separate
# from detection so it can be rerun on old uploads in a minute or two.
# 2s and 3s need film frames at each shot. Seeking over a signed link proved unreliable
# (OpenCV's reader stalls on partial reads), so the film is downloaded first, the same as in
# make_proxy, and only the frames at the shots are decoded.
# Team rebounds and turnovers (possession_events.py, ml/tools/possession.py) read one frame per
# ball hold from the same downloaded film, front to back (about 2 minutes a game on CPU). The
# original is preferred: the jersey pixel vote was tuned on it, and on the 720p playback copy
# (about half the size) Riordan's Opponent turnovers went from 9 to 12 (Hudl 8). The playback
# copy is the fallback, and if the film can't be read at all rebounds and turnovers use the
# tracker's team split with lower confidence.
_tools = Path(__file__).resolve().parent.parent / "ml" / "tools"
events_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy<3", "opencv-python-headless==4.10.0.84", "pyyaml==6.0.2",
                 "boto3==1.40.76", "sentry-sdk==2.71.0")
    .add_local_file(Path(__file__).with_name("shot_events.py"), "/root/shot_events.py")
    .add_local_file(_tools / "shots.py", "/root/shots.py")
    .add_local_file(_tools / "shot_split.py", "/root/shot_split.py")
    .add_local_file(_tools / "game_window.py", "/root/game_window.py")
    .add_local_file(_tools / "three_point.py", "/root/three_point.py")
    .add_local_file(Path(__file__).with_name("possession_events.py"), "/root/possession_events.py")
    .add_local_file(_tools / "possession.py", "/root/possession.py")
)


@app.function(
    image=events_image,
    secrets=[modal.Secret.from_name("aim-r2"), modal.Secret.from_name("aim-sentry")],
    cpu=4.0,
    memory=8192,
    timeout=25 * 60,  # the backend gives up after EVENTS_STUCK_AFTER (30 min)
)
def make_events(tracks_key: str, valley_jersey: str | None = None, opponent_jersey: str | None = None,
                environment: str = "development", film_key: str | None = None) -> dict:
    """Write <stem>.events.json next to the tracks in R2 and return it (events plus box score).
    Events are shots, team rebounds and turnovers, and hidden steals and assists. film_key is the
    film for 2s and 3s and holders' jerseys; by default the original, else the playback copy,
    found next to the tracks."""
    import sentry_sdk

    _init_sentry(environment)
    sentry_sdk.set_tag("tracks_key", tracks_key)
    try:
        return _make_events(tracks_key, valley_jersey, opponent_jersey, film_key)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(timeout=5)
        raise


VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".mkv", ".avi")


def _find_film(r2, bucket: str, tracks_key: str) -> str | None:
    """The film the tracks came from: tracks are <stem>.tracks-<model>.json.gz next to <stem>.<ext>.
    Prefer the original (the frame size the tracks and the jersey vote were made at), then the
    720p playback copy."""
    stem = tracks_key.split(".tracks-")[0]
    keys = [o["Key"] for o in r2.list_objects_v2(Bucket=bucket, Prefix=stem + ".").get("Contents", [])]
    originals = [k for k in keys if k.lower().endswith(VIDEO_EXTENSIONS) and ".proxy-" not in k]
    if originals:
        return originals[0]
    proxy = f"{stem}.proxy-720p.mp4"
    return proxy if proxy in keys else None


def _make_events(tracks_key: str, valley_jersey: str | None, opponent_jersey: str | None,
                 film_key: str | None = None) -> dict:
    import gzip
    import sys

    sys.path.insert(0, "/root")
    import shot_events

    started = time.monotonic()
    bucket = os.environ["R2_BUCKET"]
    r2 = _r2()
    body = r2.get_object(Bucket=bucket, Key=tracks_key)["Body"].read()
    doc = json.loads(gzip.decompress(body) if tracks_key.endswith(".gz") else body)
    timings = {}
    with tempfile.TemporaryDirectory() as tmp:
        video = None
        try:
            film_key = film_key or _find_film(r2, bucket, tracks_key)
            if film_key:
                video = Path(tmp) / ("film" + Path(film_key).suffix)
                r2.download_file(bucket, film_key, str(video))
        except Exception as exc:  # no film just means no 2s and 3s and rougher teams on rebounds; the shots still go out
            print(f"[EVENTS] Could not get the film for {tracks_key}: {exc}")
            video, film_key = None, None
        timings["film_download"] = round(time.monotonic() - started, 1)
        result = shot_events.build_events(doc, valley_jersey, opponent_jersey, str(video) if video else None)
    stem = tracks_key[:-len(".json.gz")] if tracks_key.endswith(".json.gz") else tracks_key.rsplit(".", 1)[0]
    events_key = f"{stem}.events.json"
    result["film_key"] = film_key
    r2.put_object(Bucket=bucket, Key=events_key, Body=json.dumps(result).encode(), ContentType="application/json")
    result["events_key"] = events_key
    timings["total"] = round(time.monotonic() - started, 1)
    result["timings_seconds"] = timings
    return result


@app.local_entrypoint()
def main(source_key: str, environment: str = "development", detect: bool = False, events: bool = False):
    """--events takes a tracks key as --source-key."""
    fn = make_events if events else detect_players if detect else make_proxy
    result = fn.remote(source_key, environment=environment)
    if events:  # the event list is long; show the summary
        result = {k: v for k, v in result.items() if k != "events"} | {"event_count": len(result["events"])}
    print(json.dumps(result, indent=2))
