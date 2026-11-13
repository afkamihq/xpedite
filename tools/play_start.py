"""Start a Story match and set the camera, then stop, so a person (or Claude, one move at
a time with act.py) can play it and learn how to win before anything is automated.
  play_start.py "School Grounds" 1 Normal
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps
from macro.modes import story
from macro.nav.navigator import Navigator
from macro.platform import open_platform

name, act, difficulty = (sys.argv[1:] + ["School Grounds", "1", "Normal"][len(sys.argv) - 1:])[:3]
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=30) or "yes")
    p.guard.arm()
    nav = Navigator(p, log=print)
    screen = nav.settle()
    if screen in story.RESULT_SCREENS:
        story.leave_results(nav, screen)
    nav.go("lobby")
    story.enter_story(nav, name, int(act), difficulty)
    maps.set_overhead_camera(p, maps.load_profile(name.lower().replace(" ", "_")))
    print("match started, camera set")
