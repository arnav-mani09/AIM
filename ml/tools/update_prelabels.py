"""Replace the pre-labels on unlabeled frames with boxes from a trained AIM detector.

Usage (with ml/tools/labelstudio.sh running, after ml/train_modal.py and detector_report.py):
    ml/.venv/bin/python ml/tools/update_prelabels.py v1
    ml/.venv/bin/python ml/tools/update_prelabels.py v1 --dry-run --limit 3   # print, change nothing

Only frames with no saved annotation are touched; your labels are never changed.
Each class uses the confidence cutoff from ml/runs/<name>/report.json, lowered a bit,
because deleting a wrong box is faster than drawing a missed one.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import torch
import yaml
from yolox.data.data_augment import ValTransform
from yolox.exp import get_exp
from yolox.utils import postprocess

ML = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from labelstudio_setup import PROJECT_TITLE, URL, login  # noqa: E402

FRAMES = ML / "data" / "frames"
LOWER_CUTOFF_BY = 0.1


def load(run: Path):
    state = torch.load(run / "aim_yolox_m.pth", map_location="cpu", weights_only=False)
    exp = get_exp(None, "yolox-m")
    exp.num_classes = state["num_classes"]
    size = state["input_size"]
    model = exp.get_model()
    model.load_state_dict(state["model"])
    return exp, model.eval(), size


def detect(exp, model, size, image, names, cutoffs):
    h, w = image.shape[:2]
    ratio = min(size / h, size / w)
    tensor, _ = ValTransform(legacy=False)(image, None, (size, size))
    with torch.no_grad():
        out = postprocess(model(torch.from_numpy(tensor).unsqueeze(0).float()), exp.num_classes,
                          conf_thre=min(cutoffs.values()), nms_thre=0.45)[0]
    result = []
    for x0, y0, x1, y1, obj, cls_conf, cls in ([] if out is None else out.tolist()):
        name, score = names[int(cls)], obj * cls_conf
        if score < cutoffs[name]:
            continue
        x0, y0 = max(0.0, x0 / ratio), max(0.0, y0 / ratio)
        x1, y1 = min(float(w), x1 / ratio), min(float(h), y1 / ratio)
        result.append({
            "id": f"p{len(result)}", "from_name": "label", "to_name": "image", "type": "rectanglelabels",
            "original_width": w, "original_height": h, "score": round(score, 3),
            "value": {"x": 100 * x0 / w, "y": 100 * y0 / h, "width": 100 * (x1 - x0) / w,
                      "height": 100 * (y1 - y0) / h, "rotation": 0, "rectanglelabels": [name]},
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run = ML / "runs" / args.name
    names = yaml.safe_load((ML / "classes.yaml").read_text())["names"]
    report = json.loads((run / "report.json").read_text())
    cutoffs = {n: max(0.05, report[n]["cutoff"] - LOWER_CUTOFF_BY) for n in names.values()}
    exp, model, size = load(run)
    version = f"aim-yolox-m-{args.name}"

    s = login()
    projects = s.get(f"{URL}/api/projects", params={"title": PROJECT_TITLE}).json()
    projects = projects.get("results", projects) if isinstance(projects, dict) else projects
    pid = next(p for p in projects if p["title"] == PROJECT_TITLE)["id"]
    tasks, page = [], 1
    while True:
        r = s.get(f"{URL}/api/tasks", params={"project": pid, "page": page, "page_size": 500, "fields": "all"})
        if r.status_code == 404:
            break
        batch = r.json().get("tasks", [])
        tasks += batch
        if len(batch) < 500:
            break
        page += 1
    todo = [t for t in tasks if not t.get("annotations") and not t.get("total_annotations")]
    todo.sort(key=lambda t: t["id"])
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} unlabeled frames; cutoffs {cutoffs}")

    started, boxes = time.monotonic(), 0
    for i, task in enumerate(todo, 1):
        image = cv2.imread(str(FRAMES / task["data"]["image"].split("?d=frames/", 1)[1]))
        result = detect(exp, model, size, image, names, cutoffs)
        boxes += len(result)
        if args.dry_run:
            counts = {}
            for b in result:
                counts[b["value"]["rectanglelabels"][0]] = counts.get(b["value"]["rectanglelabels"][0], 0) + 1
            print(task["id"], counts)
            continue
        for old in s.get(f"{URL}/api/predictions", params={"task": task["id"]}).json():
            s.delete(f"{URL}/api/predictions/{old['id']}").raise_for_status()
        s.post(f"{URL}/api/predictions", json={
            "task": task["id"], "result": result, "model_version": version,
            "score": sum(b["score"] for b in result) / max(1, len(result)),
        }).raise_for_status()
        if i % 25 == 0:
            print(f"{i}/{len(todo)} frames", flush=True)
    print(f"{'checked' if args.dry_run else 'updated'} {len(todo)} frames, {boxes} boxes, "
          f"{time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    main()
