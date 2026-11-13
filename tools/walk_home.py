"""Walk the character back home from one of the Soul Furnace views (its route reversed), then
confirm against the home picture. For a match whose setup lost its way.
  walk_home.py VIEW_FOLDER     e.g. soul_furnace_rightup
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps  # noqa: E402
from macro.modes import furnace  # noqa: E402
from macro.platform import open_platform  # noqa: E402

view = maps.load_profile(sys.argv[1])
home = maps.load_profile("soul_furnace")
with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    for key, seconds in reversed(view.route):
        p.key(furnace.BACK[key], hold=seconds)
        p.sleep(0.25)
    result = maps.correct_position(p, home, print, search=False)
    print("home:", result.inliers, "features")
