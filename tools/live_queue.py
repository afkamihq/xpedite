"""Any queue, end to end through the real queue runner, with the log on the console: for testing
Story acts, Challenges and Expeditions one after another. Costs nothing beyond match Yen (no
summons, no gems). Roblox isn't restarted first; nothing goes to Discord or a webhook.

  live_queue.py '[{"mode": "story", "map": "East Town", "act": 1, "difficulty": "Normal", "times": 1}]'
  live_queue.py queue.json

Run from the project root:  .venv-win/Scripts/python.exe tools/live_queue.py ...
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform.windows import wait_hands_off  # noqa: E402
from macro.sched.runner import QueueRunner, clean_entry  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "app"))
from panels import load_settings  # noqa: E402


def main():
    arg = sys.argv[1]
    queue = json.load(open(arg, encoding="utf-8")) if os.path.exists(arg) else json.loads(arg)
    for entry in queue:
        cleaned, why = clean_entry(entry)
        if cleaned is None:
            sys.exit(f"not playable: {entry} ({why})")
    settings = dict(load_settings())
    settings.update(fresh_start=False, webhook="", discord_channel="", discord_token="", shutdown_when_done=False,
                    stop_at_time="", stop_at_candy=0, refresh_hours=0)
    print(f"[{time.strftime('%H:%M:%S')}] waiting for 10 s idle", flush=True)
    wait_hands_off(seconds=10, timeout=300)
    done = []
    runner = QueueRunner(queue, settings,
                         on_log=lambda t: print(f"[{time.strftime('%H:%M:%S')}] {t}", flush=True),
                         on_stats=lambda s: None, on_paused=lambda r: print(f"PAUSED: {r}", flush=True),
                         on_result=lambda path, outcome: print(f"RESULT PICTURE {outcome}: {path}", flush=True),
                         on_finished=lambda why: done.append(why))
    runner.run()
    print(f"[{time.strftime('%H:%M:%S')}] finished: {done[-1] if done else '?'}", flush=True)


if __name__ == "__main__":
    main()
