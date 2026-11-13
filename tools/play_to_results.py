"""Win a Story stage with its plan and stop on the results window, leaving it open, so what
comes after a match (Next Stage, Repeat Stage, the window's X) can be looked at and tried.
  play_to_results.py "Flaming Monastery" 1 [Normal] [plan]
Then look and click with tools/poke.py.
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps, plans
from macro.control.engine import read_hotbar_costs
from macro.modes import story
from macro.nav.navigator import Navigator
from macro.nav.recovery import Recovery
from macro.platform import open_platform
from macro.platform.windows import wait_hands_off
from macro.vision.digits import DigitReader
from macro.vision.screens import scaled

args = sys.argv[1:] + ["Flaming Monastery", "1", "Normal", "story"][len(sys.argv) - 1:]
name, act, difficulty, plan_name = args[:4]
folder = name.lower().replace(" ", "_").replace("'", "")
OUT = os.path.join(ROOT, "cap", "after")
os.makedirs(OUT, exist_ok=True)


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


wait_hands_off(seconds=15, timeout=300)
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=60) or "yes")
    p.guard.arm()
    nav = Navigator(p, log=log)
    recovery = Recovery(p, nav, log=log)
    recovery.wait_until_in_game()
    screen = nav.settle()
    if screen in story.RESULT_SCREENS:
        story.leave_results(nav, screen, on_lost=recovery)
    nav.go("lobby", on_lost=recovery)
    p.hover(*scaled(960, 300))
    p.sleep(0.8)
    costs = read_hotbar_costs(p.grab())
    story.enter_story(nav, name, int(act), difficulty, on_lost=recovery)
    result = story.play_match(nav, DigitReader(), maps.load_profile(folder), plans.load(folder, plan_name), costs,
                              on_lost=recovery, log=log)
    log(f"RESULT: {result.outcome} after {result.seconds:.0f} s")
    p.sleep(3.0)
    cv2.imwrite(os.path.join(OUT, "results.png"), p.grab())
