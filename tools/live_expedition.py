"""Expeditions end to end through the real queue runner, with the log on the console.

Costs nothing: starting and restarting an Expedition is free (checked 15 Nov 2026), and only
match Yen is spent. Roblox isn't restarted and nothing is sent to Discord or a webhook.

  live_expedition.py ["School Grounds"] [difficulty 1-3] [runs]

Run from the project root:  .venv-win/Scripts/python.exe tools/live_expedition.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform.windows import wait_hands_off  # noqa: E402
from macro.sched.runner import QueueRunner  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "app"))
from panels import load_settings  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    map_name = args[0] if args else "School Grounds"
    difficulty = int(args[1]) if len(args) > 1 else 1
    runs = int(args[2]) if len(args) > 2 else 1
    settings = dict(load_settings())
    settings.update(fresh_start=False, webhook="", discord_channel="", discord_token="", shutdown_when_done=False,
                    stop_at_time="", stop_at_candy=0, refresh_hours=0)
    print(f"[{time.strftime('%H:%M:%S')}] waiting for 10 s idle", flush=True)
    wait_hands_off(seconds=10, timeout=300)
    queue = [{"mode": "expedition", "map": map_name, "difficulty": difficulty, "times": runs}]
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
