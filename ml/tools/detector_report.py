"""Score a trained detector on the test frames (game 2) and show its mistakes.

Usage (after ml/train_modal.py):
    ml/.venv/bin/python ml/tools/detector_report.py v1

For each class it prints recall (share of labeled objects found) and precision
(share of the model's boxes that are right) at the confidence cutoff that does best
for that class. A box counts as found when it overlaps a label by IoU 0.5 or more.
Writes ml/runs/<name>/report.json and mistakes_*.jpg sheets: green = found,
yellow = missed label, red = box with no matching label.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ML = Path(__file__).resolve().parents[1]
DATA = ML / "data" / "dataset"
IOU = 0.5
CEILING_LINE = 0.22  # a rim whose box ends above this share of the frame height is a ceiling hoop
TARGETS = {"player": 0.95, "rim": 0.95, "referee": 0.90, "ball": 0.70}  # recall targets


def iou(a, b):
    ax1, ay1, bx1, by1 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    w = max(0.0, min(ax1, bx1) - max(a[0], b[0]))
    h = max(0.0, min(ay1, by1) - max(a[1], b[1]))
    inter = w * h
    return inter / (a[2] * a[3] + b[2] * b[3] - inter + 1e-9)


def match(labels, preds, cls, cutoff):
    """Greedy match per image, best scores first. Returns (found, missed, wrong) lists."""
    found, missed, wrong = [], [], []
    for image_id in set(labels) | set(preds):
        gts = [g for g in labels.get(image_id, []) if g["category_id"] == cls]
        ps = sorted((p for p in preds.get(image_id, []) if p["category_id"] == cls and p["score"] >= cutoff),
                    key=lambda p: -p["score"])
        used = set()
        for p in ps:
            best, best_iou = None, IOU
            for i, g in enumerate(gts):
                if i not in used and (v := iou(p["bbox"], g["bbox"])) >= best_iou:
                    best, best_iou = i, v
            if best is None:
                wrong.append(p)
            else:
                used.add(best)
                found.append(p)
        missed += [g for i, g in enumerate(gts) if i not in used]
    return found, missed, wrong


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    args = parser.parse_args()
    run = ML / "runs" / args.name
    coco = json.loads((DATA / "annotations" / "instances_val2017.json").read_text())
    names = {c["id"]: c["name"] for c in coco["categories"]}
    labels, preds = defaultdict(list), defaultdict(list)
    for a in coco["annotations"]:
        labels[a["image_id"]].append(a)
    test_ids = {im["id"] for im in coco["images"]}
    for p in json.loads((run / "val_predictions.json").read_text()):
        if p["image_id"] in test_ids:  # an older run may have scored a bigger test set
            preds[p["image_id"]].append(p)

    report, cutoffs = {}, {}
    print(f"{args.name} on game 2 ({len(coco['images'])} frames), IoU {IOU}")
    print(f"{'class':8} {'cutoff':>6} {'recall':>7} {'precision':>9} {'target':>7}")
    for cls, name in names.items():
        best = None
        for cutoff in np.arange(0.05, 0.96, 0.05):
            f, m, w = match(labels, preds, cls, cutoff)
            r = len(f) / max(1, len(f) + len(m))
            p = len(f) / max(1, len(f) + len(w))
            f1 = 2 * r * p / max(1e-9, r + p)
            if best is None or f1 > best["f1"]:
                best = {"cutoff": round(float(cutoff), 2), "recall": r, "precision": p, "f1": f1,
                        "labels": len(f) + len(m)}
        report[name], cutoffs[cls] = best, best["cutoff"]
        hit = "yes" if best["recall"] >= TARGETS[name] else "no"
        print(f"{name:8} {best['cutoff']:>6.2f} {best['recall']:>7.0%} {best['precision']:>9.0%} "
              f"{TARGETS[name]:>6.0%} {hit}")
    # Rims split: retracted ceiling hoops on side courts don't affect stats; main hoops do.
    heights = {im["id"]: im["height"] for im in coco["images"]}
    rim = next(c for c, n in names.items() if n == "rim")
    is_ceiling = lambda b: (b["bbox"][1] + b["bbox"][3]) / heights[b["image_id"]] < CEILING_LINE
    found, missed, _ = match(labels, preds, rim, cutoffs[rim])
    for kind, test in (("main hoops", lambda b: not is_ceiling(b)), ("ceiling hoops", is_ceiling)):
        f, m = sum(map(test, found)), sum(map(test, missed))
        report[f"rim_{kind.split()[0]}"] = {"recall": f / max(1, f + m), "labels": f + m}
        print(f"  {kind}: {f}/{f + m} found ({f / max(1, f + m):.0%})")
    (run / "report.json").write_text(json.dumps(report, indent=2))

    # Mistake sheets: the 12 test frames with the most misses plus wrong boxes.
    colors = {"found": (80, 200, 80), "missed": (0, 230, 255), "wrong": (60, 60, 240)}
    per_image = defaultdict(lambda: defaultdict(list))
    for cls in names:
        for kind, items in zip(("found", "missed", "wrong"), match(labels, preds, cls, cutoffs[cls])):
            for it in items:
                per_image[it["image_id"]][kind].append((cls, it["bbox"]))
    files = {im["id"]: im["file_name"] for im in coco["images"]}
    worst = sorted(per_image, key=lambda i: -(len(per_image[i]["missed"]) + len(per_image[i]["wrong"])))[:12]
    tiles = []
    for image_id in worst:
        img = cv2.imread(str(DATA / "val2017" / files[image_id]))
        for kind, items in per_image[image_id].items():
            for cls, (x, y, w, h) in items:
                cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), colors[kind], 3)
                if kind != "found":
                    cv2.putText(img, names[cls], (int(x), int(y) - 6), 0, 0.9, colors[kind], 2)
        img = cv2.resize(img, (800, 450))
        cv2.putText(img, f"task {image_id}", (10, 40), 0, 1.2, (255, 255, 255), 3)
        tiles.append(img)
    for n in range(0, len(tiles), 6):
        chunk = tiles[n:n + 6]
        chunk += [np.zeros_like(tiles[0])] * (6 - len(chunk))
        sheet = np.vstack([np.hstack(chunk[i:i + 3]) for i in (0, 3)])
        cv2.imwrite(str(run / f"mistakes_{n // 6 + 1}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(f"wrote {run}/report.json and mistake sheets")


if __name__ == "__main__":
    main()
