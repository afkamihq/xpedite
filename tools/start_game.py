"""Start Roblox (only if it isn't running) and watch it load until the lobby.

Sends F11 if needed and nothing else. Reports each screen it passes, and saves one
frame of each to cap/start/, so loading screens and join popups can be looked at.
Run from the project root:  .venv-win/Scripts/python.exe tools/start_game.py
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import open_platform
from macro.vision.screens import ScreenDetector

OUT = os.path.join(ROOT, "cap", "start")


def main(timeout=150):
    os.makedirs(OUT, exist_ok=True)
    detector = ScreenDetector()
    with open_platform() as p:
        started = time.perf_counter()
        print(f"Roblox running already: {p.game_running()}", flush=True)
        problem = p.make_game_ready()
        print(f"{time.perf_counter() - started:5.1f} s window: {problem or 'in front and fullscreen'}", flush=True)
        if problem:
            return 1
        last, count = None, 0
        while time.perf_counter() - started < timeout:
            frame = p.grab()
            result = detector.classify(frame)
            if result.name != last:
                count += 1
                print(f"{time.perf_counter() - started:5.1f} s sees {result.name} ({result.score:.2f})", flush=True)
                cv2.imwrite(os.path.join(OUT, f"{count:02d}_{result.name}.png"), frame)
                last = result.name
            if result.name == "lobby":
                return 0
            time.sleep(0.25)
        cv2.imwrite(os.path.join(OUT, "timeout.png"), p.grab())
        print(f"not in the lobby after {timeout} s; last saw {last}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
