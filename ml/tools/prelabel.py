"""Pre-label frames with YOLOX's COCO model so labeling starts from boxes, not a blank image.

Usage:
    ml/.venv/bin/python ml/tools/prelabel.py ml/data/frames/<game>

COCO "person" becomes `player` and "sports ball" becomes `ball`; referees come out as
players and rims aren't detected, so the labeler re-tags refs and adds rims. Writes a
Label Studio import file to ml/data/labelstudio/<game>.json.
"""

import argparse
import json
import time
from pathlib import Path

import cv2
import torch
from yolox.data.data_augment import ValTransform
from yolox.exp import get_exp
from yolox.utils import postprocess

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "ml" / "data"
WEIGHTS = DATA / "weights" / "yolox_m.pth"

COCO_TO_AIM = {0: "player", 32: "ball"}  # COCO class id -> our label
# The ball is a few pixels wide on sideline film, so run above YOLOX's 640 default.
INPUT_SIZE = (960, 960)
# Low thresholds on purpose: deleting a wrong box is faster than drawing a missed one.
MIN_SCORE = {"player": 0.5, "ball": 0.15}


def load_model(device: str):
    exp = get_exp(None, "yolox-m")
    exp.test_size = INPUT_SIZE
    model = exp.get_model()
    model.load_state_dict(torch.load(WEIGHTS, map_location="cpu", weights_only=False)["model"])
    return exp, model.to(device).eval()


def detect(model, exp, image, device: str):
    height, width = image.shape[:2]
    ratio = min(INPUT_SIZE[0] / height, INPUT_SIZE[1] / width)
    tensor, _ = ValTransform(legacy=False)(image, None, INPUT_SIZE)
    tensor = torch.from_numpy(tensor).unsqueeze(0).float().to(device)
    with torch.no_grad():
        out = postprocess(model(tensor), exp.num_classes, conf_thre=min(MIN_SCORE.values()), nms_thre=0.45, class_agnostic=False)[0]
    boxes = []
    if out is None:
        return boxes
    for x0, y0, x1, y1, obj, cls_conf, cls in out.cpu().tolist():
        label = COCO_TO_AIM.get(int(cls))
        score = obj * cls_conf
        if not label or score < MIN_SCORE[label]:
            continue
        x0, y0, x1, y1 = (v / ratio for v in (x0, y0, x1, y1))
        x0, y0 = max(0.0, x0), max(0.0, y0)
        x1, y1 = min(float(width), x1), min(float(height), y1)
        boxes.append((label, score, x0, y0, x1, y1))
    return boxes


def to_task(rel_path: str, width: int, height: int, boxes) -> dict:
    result = [
        {
            "id": f"p{i}",
            "from_name": "label",
            "to_name": "image",
            "type": "rectanglelabels",
            "original_width": width,
            "original_height": height,
            "score": round(score, 3),
            "value": {
                "x": 100 * x0 / width,
                "y": 100 * y0 / height,
                "width": 100 * (x1 - x0) / width,
                "height": 100 * (y1 - y0) / height,
                "rotation": 0,
                "rectanglelabels": [label],
            },
        }
        for i, (label, score, x0, y0, x1, y1) in enumerate(boxes)
    ]
    return {
        # Served by Label Studio's local file storage, rooted at ml/data
        "data": {"image": f"/data/local-files/?d={rel_path}"},
        "predictions": [{"model_version": "yolox-m-coco", "result": result}],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("frames_dir", type=Path)
    args = parser.parse_args()

    # YOLOX 0.3.0 decodes outputs with tensor.type(<type name>), which fails on Apple MPS; use the CPU.
    device = "cuda" if torch.cuda.is_available() else "cpu"
    exp, model = load_model(device)
    frames = sorted(args.frames_dir.resolve().glob("*.jpg"))
    tasks, counts, started = [], {"player": 0, "ball": 0}, time.monotonic()
    for i, frame in enumerate(frames, 1):
        image = cv2.imread(str(frame))
        boxes = detect(model, exp, image, device)
        for b in boxes:
            counts[b[0]] += 1
        tasks.append(to_task(str(frame.relative_to(DATA)), image.shape[1], image.shape[0], boxes))
        if i % 50 == 0:
            print(f"{i}/{len(frames)} frames", flush=True)

    out = DATA / "labelstudio" / f"{args.frames_dir.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tasks))
    with_ball = sum(any(r["value"]["rectanglelabels"] == ["ball"] for r in t["predictions"][0]["result"]) for t in tasks)
    print(
        f"{len(frames)} frames in {time.monotonic() - started:.0f}s on {device}: "
        f"{counts['player']} player boxes ({counts['player'] / max(len(frames), 1):.1f}/frame), "
        f"{counts['ball']} ball boxes, ball found in {with_ball}/{len(frames)} frames -> {out.relative_to(REPO)}"
    )


if __name__ == "__main__":
    main()
