"""Run detection on films already in R2, without the website (for research test games).

Usage:
    backend/.venv/bin/python worker/run_detection.py research/valley-vs-archbishop-mitty.mp4 [more keys...]

Starts detect_players on the deployed aim-film app with spawn(), so the GPU job keeps running
on Modal even if this laptop sleeps or drops its connection. It then waits for each result,
reconnecting after drops. Rerun with the same keys to pick up results; finished jobs aren't redone
if their tracks file is already in R2.
"""

import json
import sys
import time

import modal


def main(keys: list[str]) -> None:
    detect = modal.Function.from_name("aim-film", "detect_players")
    calls = {key: detect.spawn(key, environment="research") for key in keys}
    for key, call in calls.items():
        print(f"started {key}: {call.object_id}", flush=True)
    for key, call in calls.items():
        while True:
            try:
                print(key, json.dumps(call.get(timeout=60)), flush=True)
                break
            except TimeoutError:
                continue
            except Exception as exc:  # dropped connection: the job keeps going on Modal
                if "cancelled" in str(exc).lower() or "RemoteError" in type(exc).__name__:
                    raise
                print(f"{key}: lost connection ({type(exc).__name__}), retrying", flush=True)
                time.sleep(30)


if __name__ == "__main__":
    main(sys.argv[1:])
