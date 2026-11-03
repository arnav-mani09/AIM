"""Fine-tune YOLOX-M on AIM's labeled frames using a GPU on Modal.

Run (after ml/tools/export_dataset.py):
    backend/.venv/bin/modal run ml/train_modal.py --name v1
    backend/.venv/bin/modal run ml/train_modal.py --name smoke --epochs 2   # quick check, a few cents
    backend/.venv/bin/modal run ml/train_modal.py --name v1 --fetch-only    # download a finished run
Add `--detach` after `modal run` to keep training going if the laptop disconnects.

What it does:
1. Uploads ml/data/dataset/ and the COCO yolox_m.pth start weights to a private Modal Volume.
2. Trains on train2017 (game 1) and scores on val2017 (game 2) every 10 epochs.
3. Runs the best checkpoint over val2017 and downloads, into ml/runs/<name>/ (gitignored):
     aim_yolox_m.pth         model weights only, for pre-labels and detection
     val_predictions.json    every box the model found on the test frames
     train_log.txt           the full training log
Then run ml/tools/detector_report.py for recall and precision per class.

This is its own app ("aim-train"), separate from the live aim-film app.
"""

import json
import subprocess
from pathlib import Path

import modal

app = modal.App("aim-train")
volume = modal.Volume.from_name("aim-train", create_if_missing=True)
VOL = Path("/vol")

YOLOX_COMMIT = "6ddff4824372906469a7fae2dc3206c7aa4bbaee"  # same YOLOX as ml/.venv
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git", "build-essential", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.4.1", "torchvision==0.19.1", "numpy<2", "opencv-python-headless==4.10.0.84",
        "loguru", "tqdm", "pycocotools", "tabulate", "psutil", "thop", "ninja", "tensorboard",
    )
    # --no-deps skips YOLOX's onnx pins, which only matter for exporting.
    .run_commands(f"pip install --no-deps --no-build-isolation git+https://github.com/Megvii-BaseDetection/YOLOX.git@{YOLOX_COMMIT}")
)

ML = Path(__file__).resolve().parent
INPUT_SIZE = 960  # the ball is a few pixels wide on sideline film; 640 loses it

EXP_TEMPLATE = '''
import os
import torch.multiprocessing
from yolox.exp import Exp as BaseExp

# Containers block passing tensors between data workers by file descriptor; use files instead.
torch.multiprocessing.set_sharing_strategy("file_system")

class Exp(BaseExp):
    def __init__(self):
        super().__init__()
        self.depth, self.width = 0.67, 0.75  # YOLOX-M
        self.num_classes = 4  # ball, player, referee, rim (ml/classes.yaml)
        self.exp_name = "{name}"
        self.output_dir = "{runs}"
        self.data_dir = "{data}"
        self.train_ann = "instances_train2017.json"
        self.val_ann = "instances_val2017.json"
        self.input_size = self.test_size = ({size}, {size})
        self.max_epoch = {epochs}
        self.no_aug_epochs = min(15, max(1, {epochs} // 6))
        self.warmup_epochs = min(3, max(1, {epochs} // 10))
        self.eval_interval = min(10, {epochs})
        self.save_history_ckpt = False  # keep only best and latest
        self.data_num_workers = 4
        # Small dataset: keep augmentation, but milder scaling so the ball isn't shrunk away.
        self.mosaic_scale = (0.5, 1.5)
        self.mixup_prob = 0.5
        self.degrees = 5.0
'''


# Any of these works; Modal takes whichever is free first (L4 is cheapest).
@app.function(image=image, gpu=["L4", "A10G", "L40S"], volumes={VOL: volume}, timeout=3 * 60 * 60)
def train(name: str, epochs: int, batch: int) -> dict:
    import shutil
    import sys

    runs = VOL / "runs"
    data = Path("/tmp/dataset")  # local disk reads faster than the volume on every epoch
    shutil.copytree(VOL / "dataset", data, dirs_exist_ok=True)
    out = runs / name
    if out.exists():
        shutil.rmtree(out)  # a rerun with the same name starts fresh
    exp_file = Path("/tmp/aim_exp.py")
    exp_file.write_text(EXP_TEMPLATE.format(name=name, runs=runs, data=data, size=INPUT_SIZE, epochs=epochs))

    log = []
    cmd = [sys.executable, "-m", "yolox.tools.train", "-f", str(exp_file), "-d", "1", "-b", str(batch),
           "--fp16", "-c", str(VOL / "yolox_m.pth")]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        print(line, end="")
        log.append(line)
    # YOLOX catches its own errors and still exits 0, so check that a model was saved.
    if proc.wait() != 0 or not (out / "best_ckpt.pth").exists():
        raise RuntimeError("training failed; see the log above")

    best = predict_val(out / "best_ckpt.pth", data)
    # Everything the laptop needs goes in the volume, so a dropped connection loses nothing.
    (out / "train_log.txt").write_text("".join(log))
    (out / "val_predictions.json").write_text(json.dumps(best["predictions"], default=float))
    (out / "summary.json").write_text(json.dumps({"best_ap": best["best_ap"]}, default=float))
    volume.commit()


def predict_val(ckpt: Path, data: Path) -> dict:
    """Run the best checkpoint over every test frame and keep weights-only for download."""
    import cv2
    import torch
    from yolox.data.data_augment import ValTransform
    from yolox.utils import postprocess

    from yolox.exp import get_exp

    exp = get_exp("/tmp/aim_exp.py")
    model = exp.get_model()
    state = torch.load(ckpt, map_location="cpu", weights_only=False)
    model.load_state_dict(state["model"])
    model = model.cuda().eval()
    weights = ckpt.parent / "aim_yolox_m.pth"
    torch.save({"model": state["model"], "num_classes": exp.num_classes, "input_size": INPUT_SIZE}, weights)

    coco = json.loads((data / "annotations" / "instances_val2017.json").read_text())
    transform, preds = ValTransform(legacy=False), []
    for im in coco["images"]:
        img = cv2.imread(str(data / "val2017" / im["file_name"]))
        ratio = min(INPUT_SIZE / img.shape[0], INPUT_SIZE / img.shape[1])
        tensor, _ = transform(img, None, (INPUT_SIZE, INPUT_SIZE))
        with torch.no_grad():
            out = postprocess(model(torch.from_numpy(tensor).unsqueeze(0).float().cuda()),
                              exp.num_classes, conf_thre=0.05, nms_thre=0.45)[0]
        for x0, y0, x1, y1, obj, cls_conf, cls in ([] if out is None else out.cpu().tolist()):
            x0, y0, x1, y1 = (v / ratio for v in (x0, y0, x1, y1))
            preds.append({"image_id": im["id"], "category_id": int(cls), "score": obj * cls_conf,
                          "bbox": [x0, y0, x1 - x0, y1 - y0]})
    return {"predictions": preds, "best_ap": float(state.get("best_ap") or 0)}


@app.local_entrypoint()
def main(name: str = "v1", epochs: int = 100, batch: int = 8, fetch_only: bool = False):
    if fetch_only:  # the run finished but the laptop lost the connection
        return fetch(name)
    dataset = ML / "data" / "dataset"
    if not (dataset / "annotations" / "instances_train2017.json").exists():
        raise SystemExit("No dataset yet. Run: ml/.venv-labelstudio/bin/python ml/tools/export_dataset.py")

    # Replace the dataset in the volume so frames from an older export don't linger.
    try:
        volume.remove_file("dataset", recursive=True)
    except Exception:
        pass
    have_weights = any(e.path == "yolox_m.pth" for e in volume.listdir("/"))
    with volume.batch_upload(force=True) as upload:
        upload.put_directory(str(dataset), "/dataset")
        if not have_weights:
            upload.put_file(str(ML / "data" / "weights" / "yolox_m.pth"), "/yolox_m.pth")
    print(f"uploaded dataset; training {name} for {epochs} epochs", flush=True)

    train.remote(name, epochs, batch)
    fetch(name)


def fetch(name: str) -> None:
    """Download a finished run from the volume into ml/runs/<name>/."""
    out = ML / "runs" / name
    out.mkdir(parents=True, exist_ok=True)
    for file in ("aim_yolox_m.pth", "val_predictions.json", "train_log.txt", "summary.json"):
        with open(out / file, "wb") as f:
            for chunk in volume.read_file(f"runs/{name}/{file}"):
                f.write(chunk)
    best_ap = json.loads((out / "summary.json").read_text())["best_ap"]
    print(f"best COCO AP (0.5:0.95) on game 2: {best_ap}")
    print(f"saved to {out}. Next: ml/.venv/bin/python ml/tools/detector_report.py {name}")
