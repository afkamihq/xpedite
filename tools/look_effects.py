"""Open a challenge's details and hover each stage-effect icon, saving the tooltips.
  look_effects.py regular 1      (tab, row)   -> cap/challenges/effects_<n>.png"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.nav.navigator import Navigator  # noqa: E402
from macro.nav.recovery import Recovery  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.platform.windows import wait_hands_off  # noqa: E402
from macro.vision.screens import scaled  # noqa: E402

kind, row = sys.argv[1], int(sys.argv[2])
OUT = os.path.join(ROOT, "cap", "challenges")
wait_hands_off(seconds=10, timeout=300)
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=60) or "yes")
    p.guard.arm()
    nav = Navigator(p, log=print)
    recovery = Recovery(p, nav, may_restart=False, log=print)
    nav.go("challenges", on_lost=recovery)
    nav.press("challenges", "tab_regular" if kind == "regular" else "tab_daily")
    time.sleep(1.0)
    nav.press("challenges", f"row_{row}")
    print("detail:", nav.wait_for("challenge_detail", 10))
    time.sleep(0.8)
    cv2.imwrite(os.path.join(OUT, "detail.png"), p.grab())
    for n, x in enumerate((525, 572, 620, 668, 714, 762)):
        p.hover(x, 440)
        time.sleep(0.9)
        cv2.imwrite(os.path.join(OUT, f"effects_{n}.png"), p.grab())
    p.hover(*scaled(960, 120))
    nav.go("lobby", on_lost=recovery)
