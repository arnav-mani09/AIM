"""AIM film worker on Modal: heavy video work that doesn't belong on the web server.

Deploy:  backend/.venv/bin/modal deploy worker/film_worker.py
Run one: backend/.venv/bin/modal run worker/film_worker.py --source-key teams/1/film/abc.mp4 [--detect]

The backend starts `make_proxy` when an upload completes and polls the call
for its result, then starts `detect_players` (GPU) the same way.
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
MODEL_RUN = "v3"
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


@app.local_entrypoint()
def main(source_key: str, environment: str = "development", detect: bool = False):
    fn = detect_players if detect else make_proxy
    print(json.dumps(fn.remote(source_key, environment=environment), indent=2))
