"""Do a few things in the game and save a picture after each, for looking around by hand.
  poke.py NAME c:X,Y h:X,Y k:KEY w:SECONDS s:AMOUNT
c clicks, h hovers, k presses a key (never Ctrl), w waits, s scrolls at the last point.
Coordinates are the framed game's pixels. Pictures go to cap/after/NAME_<n>.png, and the
screen each one reads as is printed.
"""
import os
import sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import open_platform
from macro.platform.windows import wait_hands_off
from macro.vision.screens import ScreenDetector

OUT = os.path.join(ROOT, "cap", "after")
os.makedirs(OUT, exist_ok=True)
name, actions = sys.argv[1], sys.argv[2:]
detector = ScreenDetector()
wait_hands_off(seconds=10, timeout=300)
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=30) or "yes")
    p.guard.arm()
    at = (720, 400)
    for n, action in enumerate(actions or ["w:0"]):
        kind, _, value = action.partition(":")
        if kind in "ch":
            at = tuple(int(v) for v in value.split(","))
            (p.click if kind == "c" else p.hover)(*at)
        elif kind == "k":
            if "ctrl" in value.lower() or "control" in value.lower():
                raise SystemExit("never Ctrl with the game in front")
            p.key(value)
        elif kind == "s":
            p.scroll_at(*at, int(value)) if hasattr(p, "scroll_at") else p.scroll(int(value))
        elif kind == "w":
            p.sleep(float(value))
        p.sleep(0.8)
        frame = p.grab()
        cv2.imwrite(os.path.join(OUT, f"{name}_{n}.png"), frame)
        print(n, action, "->", detector.classify(frame).name, flush=True)
