"""Export labeled frames from local Label Studio into a training dataset.

Usage (with ml/tools/labelstudio.sh running):
    ml/.venv-labelstudio/bin/python ml/tools/export_dataset.py

Writes ml/data/dataset/ (gitignored, the film shows minors):
    train2017/, val2017/                 images, split by game using ml/games.yaml
    annotations/instances_*.json         COCO boxes, which YOLOX trains on
    labels/train2017/, labels/val2017/   the same boxes in YOLO .txt format
Frames listed in ml/exclude_frames.yaml and frames that were skipped are left out.
"""

import json
import shutil
from collections import Counter
from pathlib import Path

import yaml

from labelstudio_setup import ML, PROJECT_TITLE, URL, login

OUT = ML / "data" / "dataset"
FRAMES = ML / "data" / "frames"
SPLIT_DIR = {"train": "train2017", "eval": "val2017"}


def main() -> None:
    names = yaml.safe_load((ML / "classes.yaml").read_text())["names"]
    class_id = {name: i for i, name in names.items()}
    games = {g["id"]: g["split"] for g in yaml.safe_load((ML / "games.yaml").read_text())["games"]}
    excluded = set((yaml.safe_load((ML / "exclude_frames.yaml").read_text()) or {}).get("exclude") or {})

    s = login()
    projects = s.get(f"{URL}/api/projects", params={"title": PROJECT_TITLE}).json()
    projects = projects.get("results", projects) if isinstance(projects, dict) else projects
    pid = next(p for p in projects if p["title"] == PROJECT_TITLE)["id"]
    r = s.get(f"{URL}/api/projects/{pid}/export", params={"exportType": "JSON", "download_all_tasks": "false"})
    r.raise_for_status()
    tasks = r.json()

    if OUT.exists():
        shutil.rmtree(OUT)
    coco = {split: {"images": [], "annotations": [], "categories": [{"id": i, "name": n} for i, n in names.items()]}
            for split in SPLIT_DIR.values()}
    counts = {split: Counter() for split in SPLIT_DIR.values()}
    left_out = Counter()

    for task in sorted(tasks, key=lambda t: t["id"]):
        done = [a for a in task["annotations"] if not a.get("was_cancelled")]
        if not done:
            left_out["skipped"] += 1
            continue
        if task["id"] in excluded:
            left_out["exclude list"] += 1
            continue
        rel = task["data"]["image"].split("?d=frames/", 1)[1]
        game = rel.split("/", 1)[0]
        split = SPLIT_DIR[games[game]]
        src = FRAMES / rel
        name = rel.replace("/", "__")  # frame names repeat across games
        (OUT / split).mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, OUT / split / name)

        boxes = [b for b in done[-1]["result"] if b.get("type") == "rectanglelabels"]
        width = boxes[0]["original_width"] if boxes else None
        height = boxes[0]["original_height"] if boxes else None
        if width is None:
            import cv2  # only needed for frames with no boxes
            height, width = cv2.imread(str(src)).shape[:2]
        image_id = task["id"]
        coco[split]["images"].append({"id": image_id, "file_name": name, "width": width, "height": height})

        lines = []
        for b in boxes:
            v = b["value"]
            cls = class_id[v["rectanglelabels"][0]]
            x, y = v["x"] / 100 * width, v["y"] / 100 * height
            w, h = v["width"] / 100 * width, v["height"] / 100 * height
            coco[split]["annotations"].append({
                "id": len(coco[split]["annotations"]) + 1, "image_id": image_id, "category_id": cls,
                "bbox": [x, y, w, h], "area": w * h, "iscrowd": 0,
            })
            lines.append(f"{cls} {(x + w / 2) / width:.6f} {(y + h / 2) / height:.6f} {w / width:.6f} {h / height:.6f}")
            counts[split][names[cls]] += 1
        counts[split]["frames"] += 1
        (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / split / f"{Path(name).stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))

    (OUT / "annotations").mkdir(parents=True, exist_ok=True)
    for split, data in coco.items():
        (OUT / "annotations" / f"instances_{split}.json").write_text(json.dumps(data))
        c = counts[split]
        print(f"{split}: {c['frames']} frames, " + ", ".join(f"{n} {c[n]}" for n in names.values()))
    print("left out:", dict(left_out) or "none")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
