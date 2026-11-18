"""Sync planning/deadlines.json into an "AIM" calendar in the Mac Calendar app.

Usage:
    python3 planning/sync_calendar.py            # apply
    python3 planning/sync_calendar.py --dry-run  # show what would change

Each deadline becomes an all-day event on its due date. Only events in the "AIM"
calendar that carry an "id: aim-..." line in their notes are touched, so events
you add to that calendar by hand are left alone. Done deadlines get a ✓ in front
of the title. The first run creates the calendar if it doesn't exist.

Needs permission for your terminal to control Calendar:
System Settings > Privacy & Security > Automation > (your terminal) > Calendar.
"""

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

DEADLINES = Path(__file__).with_name("deadlines.json")
CALENDAR = "AIM"
PREFIX = "aim-"
SEP = "\x1f"  # separates fields in osascript output


def osascript(source: str) -> str:
    res = subprocess.run(["osascript", "-"], input=source, capture_output=True, text=True)
    if res.returncode != 0:
        err = res.stderr.strip()
        if "-1743" in err or "Not authorized" in err:
            raise SystemExit(
                "macOS is blocking access to Calendar. Turn it on in System Settings > "
                "Privacy & Security > Automation > (your terminal app) > Calendar, then retry."
            )
        raise SystemExit(f"osascript failed: {err}")
    return res.stdout.strip()


def q(text: str) -> str:
    """Quote a Python string as an AppleScript string literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def date_expr(var: str, ymd: str) -> str:
    """AppleScript lines that set `var` to midnight on ymd, independent of locale."""
    d = datetime.strptime(ymd, "%Y-%m-%d")
    return (
        f"set {var} to current date\n"
        f"set day of {var} to 1\n"
        f"set year of {var} to {d.year}\n"
        f"set month of {var} to {d.month}\n"
        f"set day of {var} to {d.day}\n"
        f"set time of {var} to 0\n"
    )


def event_fields(d: dict, plan_url: str) -> tuple[str, str]:
    title = ("✓ " if d.get("done") else "") + d["title"]
    notes = d["phase"] + f" · priority: {d['priority']}"
    if d.get("notes"):
        notes += f"\n\n{d['notes']}"
    notes += f"\n\nPlan: {plan_url}\nid: {d['id']}"
    return title, notes


def existing_ids() -> list[str]:
    out = osascript(f'''
tell application "Calendar"
    if not (exists calendar {q(CALENDAR)}) then return ""
    set out to {{}}
    repeat with e in (every event of calendar {q(CALENDAR)})
        set n to description of e
        if n is missing value then set n to ""
        set end of out to n
    end repeat
    set AppleScript's text item delimiters to {q(SEP)}
    return out as text
end tell
''')
    ids = []
    for notes in out.split(SEP) if out else []:
        for line in notes.splitlines():
            if line.startswith("id: " + PREFIX):
                ids.append(line[4:].strip())
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    spec = json.loads(DEADLINES.read_text())
    for d in spec["deadlines"]:
        assert d["id"].startswith(PREFIX), d["id"]
        assert d["priority"] in ("low", "medium", "high"), d
        datetime.strptime(d["due"], "%Y-%m-%d")

    have = existing_ids()
    wanted = {d["id"]: d for d in spec["deadlines"]}
    added = [i for i in wanted if i not in have]
    updated = [i for i in wanted if i in have]
    removed = sorted({i for i in have if i not in wanted})

    for label, ids in (("add", added), ("update", updated)):
        for i in ids:
            d = wanted[i]
            print(f"  {label:6} {d['due']}  [{d['priority']:6}] {d['title']}")
    for i in removed:
        print(f"  remove {i}")
    if args.dry_run:
        print("dry run: nothing written")
        return

    lines = [
        'tell application "Calendar"',
        f'if not (exists calendar {q(CALENDAR)}) then make new calendar with properties {{name:{q(CALENDAR)}}}',
        f'set cal to calendar {q(CALENDAR)}',
    ]
    for i in removed:
        lines.append(f'delete (every event of cal whose description contains {q("id: " + i)})')
    for d in spec["deadlines"]:
        title, notes = event_fields(d, spec["plan_url"])
        lines.append(date_expr("startD", d["due"]).rstrip())
        lines.append("set endD to startD + (1 * days)")
        lines.append(f'set hits to (every event of cal whose description contains {q("id: " + d["id"])})')
        lines.append("if (count of hits) is 0 then")
        lines.append(
            f"make new event at end of events of cal with properties "
            f"{{summary:{q(title)}, description:{q(notes)}, start date:startD, end date:endD, allday event:true}}"
        )
        lines.append("else")
        lines.append("set e to item 1 of hits")
        lines.append(f"set summary of e to {q(title)}")
        lines.append(f"set description of e to {q(notes)}")
        lines.append("set start date of e to startD")
        lines.append("set end date of e to endD")
        lines.append("set allday event of e to true")
        lines.append("end if")
    lines.append("end tell")
    osascript("\n".join(lines))

    after = existing_ids()
    missing = [i for i in wanted if i not in after]
    assert not missing, f"events missing after sync: {missing}"
    print(f"Synced to the {CALENDAR!r} calendar: {len(added)} added, {len(updated)} updated, {len(removed)} removed.")


if __name__ == "__main__":
    main()
