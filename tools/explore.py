"""Walk the character by keys and keep an overhead picture after each move, to map a stage.
  explore.py NAME w:1.0 d:2.0 ...      pictures: cap/explore/NAME_<n>.jpg (and the start, _0)
Nothing is clicked. Roblox must be in a match (before Start is fine: the clock waits)."""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import open_platform  # noqa: E402

name = sys.argv[1]
out = os.path.join(ROOT, "cap", "explore")
os.makedirs(out, exist_ok=True)
with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    p.hover(60, 330); p.sleep(0.4)
    cv2.imwrite(os.path.join(out, f"{name}_0.jpg"), p.grab())
    for n, part in enumerate(sys.argv[2:], start=1):
        key, seconds = part.split(":")
        p.key(key, hold=float(seconds))
        p.sleep(0.6)
        cv2.imwrite(os.path.join(out, f"{name}_{n}.jpg"), p.grab())
        print(n, part, flush=True)
