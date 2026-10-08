"""Create the labeling project in a running local Label Studio and import pre-labeled frames.

Usage (with ml/tools/labelstudio.sh running):
    ml/.venv-labelstudio/bin/python ml/tools/labelstudio_setup.py ml/data/labelstudio/<game>.json

Safe to re-run: it reuses the project and skips frames already imported.
"""

import argparse
import json
from pathlib import Path

import requests

ML = Path(__file__).resolve().parents[1]
URL = "http://localhost:8090"
PROJECT_TITLE = "AIM detector"

# Classes and colors; ids and order follow ml/classes.yaml
LABEL_CONFIG = """
<View>
  <Header value="Box every player and referee ON THE COURT, the ball, and each rim. Skip the bench, coaches, crowd and posters."/>
  <Image name="image" value="$image" zoom="true" zoomControl="true" rotateControl="false"/>
  <RectangleLabels name="label" toName="image">
    <Label value="ball" background="#f97316" hotkey="1"/>
    <Label value="player" background="#3b82f6" hotkey="2"/>
    <Label value="referee" background="#a855f7" hotkey="3"/>
    <Label value="rim" background="#ef4444" hotkey="4"/>
  </RectangleLabels>
</View>
"""


def login() -> requests.Session:
    """Sign in like the web page does. Label Studio 1.23 disables legacy API tokens by default."""
    env = dict(l.split("=", 1) for l in (ML / ".labelstudio.env").read_text().splitlines() if "=" in l)
    s = requests.Session()
    s.get(f"{URL}/user/login/")
    r = s.post(f"{URL}/user/login/", data={
        "email": env["LABEL_STUDIO_USERNAME"], "password": env["LABEL_STUDIO_PASSWORD"],
        "csrfmiddlewaretoken": s.cookies.get("csrftoken"),
    }, headers={"Referer": f"{URL}/user/login/"}, allow_redirects=False)
    if r.status_code != 302 or "sessionid" not in s.cookies:
        raise SystemExit(f"Label Studio login failed (HTTP {r.status_code}); is ml/tools/labelstudio.sh running?")
    s.headers.update({"X-CSRFToken": s.cookies.get("csrftoken"), "Referer": URL})
    return s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks_file", type=Path)
    args = parser.parse_args()
    s = login()

    projects = s.get(f"{URL}/api/projects", params={"title": PROJECT_TITLE}).json()
    projects = projects.get("results", projects) if isinstance(projects, dict) else projects
    project = next((p for p in projects if p["title"] == PROJECT_TITLE), None)
    if not project:
        project = s.post(f"{URL}/api/projects", json={
            "title": PROJECT_TITLE,
            "description": "Ball, player, referee and rim boxes for AIM's detector (YOLO format export).",
            "label_config": LABEL_CONFIG,
            "show_collab_predictions": True,  # show YOLOX pre-labels as editable boxes
        }).json()
        print("created project", project["id"])
    pid = project["id"]

    # Local storage grants access to frames served from ml/data (see labelstudio.sh).
    frames_root = (ML / "data" / "frames").resolve()
    storages = s.get(f"{URL}/api/storages/localfiles", params={"project": pid}).json()
    if not any(st.get("path") == str(frames_root) for st in storages):
        r = s.post(f"{URL}/api/storages/localfiles", json={
            "project": pid, "path": str(frames_root), "use_blob_urls": False, "title": "frames",
        })
        r.raise_for_status()
        print("connected local storage", frames_root)

    tasks = json.loads(args.tasks_file.read_text())
    existing, page = set(), 1
    while True:
        r = s.get(f"{URL}/api/tasks", params={"project": pid, "page": page, "page_size": 500, "fields": "all"})
        if r.status_code == 404:
            break
        batch = r.json().get("tasks", [])
        existing |= {t["data"]["image"] for t in batch}
        if len(batch) < 500:
            break
        page += 1
    new = [t for t in tasks if t["data"]["image"] not in existing]
    if new:
        r = s.post(f"{URL}/api/projects/{pid}/import", json=new)
        r.raise_for_status()
        print(f"imported {len(new)} frames with pre-labels")
    total = s.get(f"{URL}/api/projects/{pid}").json().get("task_number")
    print(f"project {pid}: {total} frames -> {URL}/projects/{pid}/data")


if __name__ == "__main__":
    main()
