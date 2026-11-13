"""Go to a screen with the navigator and save a picture after each step, to see where a route
breaks. The app's run must be stopped.
  look_nav.py SCREEN [press:BUTTON ...]    e.g. look_nav.py soul_furnace_picker press:select_stage
Pictures: cap/after/nav_<n>_<screen>.png
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.nav.navigator import Navigator  # noqa: E402
from macro.platform import open_platform  # noqa: E402

OUT = os.path.join(ROOT, "cap", "after")
os.makedirs(OUT, exist_ok=True)
target, steps = sys.argv[1], sys.argv[2:]
with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.4); p.guard.arm()
    nav = Navigator(p, log=print)
    n = 0

    def shot(label):
        global n
        n += 1
        screen = nav.detector.classify(p.grab()).name
        path = os.path.join(OUT, f"nav_{n}_{label}_{screen}.png")
        cv2.imwrite(path, p.grab())
        print("saved", path, "screen:", screen, flush=True)

    shot("start")
    if target != "-":
        nav.go(target)
        shot("at_" + target)
    for step in steps:
        kind, _, value = step.partition(":")
        if kind == "press":
            nav.press(nav.settle(), value)
            p.sleep(2.0)
            shot("after_" + value)
