"""Sync planning/deadlines.json into the Flux Planner app running on this laptop.

Usage:
    python3 planning/sync_flux.py            # apply
    python3 planning/sync_flux.py --dry-run  # show what would change

Only tasks whose id starts with "aim-" are touched; every other Flux task is left
exactly as it is. Done checkmarks set in Flux are kept. Flux's tasks.json is backed
up before each write. Flux loads tasks when its window opens, so reload it (Cmd+R)
after a sync.
"""

import argparse
import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FLUX_API = "http://localhost:5183/api/tasks"
FLUX_DATA = Path.home() / "Documents" / "GitHub" / "flux-planner" / "data"
DEADLINES = Path(__file__).with_name("deadlines.json")
PREFIX = "aim-"
KEEP_BACKUPS = 20


def flux(method: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(FLUX_API, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read())


def backup() -> Path:
    src = FLUX_DATA / "tasks.json"
    folder = FLUX_DATA / "backups"
    folder.mkdir(exist_ok=True)
    dest = folder / f"tasks-{datetime.now():%Y%m%d-%H%M%S}.json"
    shutil.copy2(src, dest)
    for old in sorted(folder.glob("tasks-*.json"))[:-KEEP_BACKUPS]:
        old.unlink()
    return dest


def build(deadline: dict, existing: dict | None, plan_url: str) -> dict:
    notes = f"{deadline['phase']}" + (f" · {deadline['notes']}" if deadline.get("notes") else "") + f"\nPlan: {plan_url}"
    task = dict(existing or {})  # keeps fields set in Flux: done, dueTime, reminders, attachments
    task.update({
        "id": deadline["id"],
        "title": deadline["title"],
        "notes": notes,
        "dueDate": deadline["due"],
        "priority": deadline["priority"],
    })
    if deadline.get("done"):
        task["done"] = True  # marked done here; a done checkmark set in Flux is also kept
    task.setdefault("done", False)
    task.setdefault("createdAt", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    return task


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    spec = json.loads(DEADLINES.read_text())
    for d in spec["deadlines"]:
        assert d["id"].startswith(PREFIX), d["id"]
        assert d["priority"] in ("low", "medium", "high"), d
        datetime.strptime(d["due"], "%Y-%m-%d")

    try:
        current = flux("GET")
    except OSError as exc:
        raise SystemExit(f"Flux isn't reachable at {FLUX_API} ({exc}). Open the Flux Planner app and retry.")

    by_id = {t["id"]: t for t in current}
    wanted = {d["id"]: build(d, by_id.get(d["id"]), spec["plan_url"]) for d in spec["deadlines"]}
    others = [t for t in current if not t["id"].startswith(PREFIX)]
    added = [i for i in wanted if i not in by_id]
    changed = [i for i in wanted if i in by_id and wanted[i] != by_id[i]]
    removed = [t["id"] for t in current if t["id"].startswith(PREFIX) and t["id"] not in wanted]

    for label, ids in (("add", added), ("update", changed), ("remove", removed)):
        for i in ids:
            t = wanted.get(i) or by_id[i]
            print(f"  {label:6} {t['dueDate']}  [{t['priority']:6}] {t['title']}")
    if not (added or changed or removed):
        print("Flux already matches planning/deadlines.json")
        return
    if args.dry_run:
        print("dry run: nothing written")
        return

    saved = backup()
    flux("PUT", others + sorted(wanted.values(), key=lambda t: t["dueDate"]))
    after = flux("GET")
    assert len([t for t in after if not t["id"].startswith(PREFIX)]) == len(others), "other Flux tasks changed!"
    print(f"Synced: {len(added)} added, {len(changed)} updated, {len(removed)} removed; "
          f"{len(others)} other tasks untouched. Backup: {saved}. Reload Flux (Cmd+R).")


if __name__ == "__main__":
    main()
