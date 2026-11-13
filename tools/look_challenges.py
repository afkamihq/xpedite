"""Open Challenges, photograph the Regular and Daily tabs (and each regular row scrolled into
view), then go back to the lobby. Pictures: cap/challenges/<name>.png.
  .venv-win/Scripts/python.exe tools/look_challenges.py"""
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

OUT = os.path.join(ROOT, "cap", "challenges")
os.makedirs(OUT, exist_ok=True)
wait_hands_off(seconds=10, timeout=300)
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=60) or "yes")
    p.guard.arm()
    nav = Navigator(p, log=print)
    recovery = Recovery(p, nav, may_restart=False, log=print)
    nav.go("challenges", on_lost=recovery)

    def save(name):
        time.sleep(0.8)
        cv2.imwrite(os.path.join(OUT, name + ".png"), p.grab())
        print("saved", name, "screen:", nav.settle())

    nav.press("challenges", "tab_regular")
    save("regular")
    p.hover(*scaled(1100, 600))
    p.scroll(150)
    save("regular_scrolled")
    nav.press("challenges", "tab_daily")
    save("daily")
    nav.press("challenges", "tab_weekly") if "tab_weekly" in (nav.detector.definitions["challenges"].get("buttons") or {}) else None
    nav.go("lobby", on_lost=recovery)
    print("back:", nav.settle())
