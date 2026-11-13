"""Open Hollow Desert's Story picker ("4th Gate") and photograph each tab.
  look_gate.py      -> cap/gate/tab_<name>.png"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.modes import story  # noqa: E402
from macro.nav import stages  # noqa: E402
from macro.nav.navigator import Navigator  # noqa: E402
from macro.nav.recovery import Recovery  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.platform.windows import wait_hands_off  # noqa: E402
from macro.vision.screens import scaled  # noqa: E402

OUT = os.path.join(ROOT, "cap", "gate")
os.makedirs(OUT, exist_ok=True)
TABS = {"gate": (411, 317), "1": (411, 419), "2": (411, 512), "3": (411, 605)}
wait_hands_off(seconds=10, timeout=300)
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=60) or "yes")
    p.guard.arm()
    nav = Navigator(p, log=print)
    recovery = Recovery(p, nav, log=print)
    screen = nav.settle()
    if screen in story.RESULT_SCREENS:
        story.leave_results(nav, screen, on_lost=recovery)
    nav.go("story_maps", on_lost=recovery)
    nav.scroll_at(*stages.ROW_CENTRE, stages.SCROLL_ALL_LEFT)
    stages._wait_row_still(nav)
    x = None
    for _ in range(stages.MAX_SCROLLS + 4):
        x = stages.find_island(nav.last_frame, "Hollow Desert")
        if x is not None:
            break
        nav.scroll_at(*stages.ROW_CENTRE, stages.SCROLL_STEP)
        stages._wait_row_still(nav)
    print("island x:", x)
    p.click(x, stages.ISLAND_CLICK_Y)
    print("picker:", nav.wait_for({"story_gate", "story_act"}, 10))
    time.sleep(1.0)
    for name, point in TABS.items():
        p.click(*scaled(*point))
        time.sleep(1.0)
        cv2.imwrite(os.path.join(OUT, f"tab_{name}.png"), p.grab())
        print("saved", name, nav.settle())
