"""Pull evenly spaced frames from a game video for labeling.

Usage:
    backend/.venv/bin/python ml/tools/extract_frames.py VIDEO --count 400

Frames land in ml/data/frames/<video name>/ as JPEGs named by timestamp
(e.g. t001234.5.jpg), ready to upload to Roboflow. The first and last
minute are skipped, since they're usually warmups or an empty court.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def duration_seconds(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--count", type=int, default=400)
    parser.add_argument("--skip-seconds", type=float, default=60.0, help="skip this much at the start and end")
    args = parser.parse_args()

    total = duration_seconds(args.video)
    start, end = args.skip_seconds, total - args.skip_seconds
    if end <= start:
        raise SystemExit(f"video is only {total:.0f}s long")
    step = (end - start) / args.count
    out_dir = REPO / "ml" / "data" / "frames" / slug(args.video.stem)
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(args.count):
        t = start + i * step
        dest = out_dir / f"t{t:07.1f}.jpg"
        if dest.exists():
            continue
        # -ss before -i seeks by keyframe, then decodes to the exact time: fast and accurate.
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(args.video),
             "-frames:v", "1", "-q:v", "2", str(dest)],
            check=True,
        )
        if (i + 1) % 50 == 0:
            print(f"{i + 1}/{args.count} frames", flush=True)

    print(f"{args.count} frames every {step:.1f}s in {out_dir.relative_to(REPO)}")


if __name__ == "__main__":
    main()
