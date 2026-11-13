"""From the lobby into a Soul Furnace match, stopping at "Start Game?" with the camera set and the
character at the map's set position (the route from spawn, then the position check).
  enter_furnace.py"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps  # noqa: E402
from macro.modes import furnace, story  # noqa: E402
from macro.nav import stages  # noqa: E402
from macro.nav.navigator import Navigator  # noqa: E402
from macro.platform import open_platform  # noqa: E402

with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    nav = Navigator(p, log=print)
    nav.go("soul_furnace_picker")
    stages.start_from_picker(nav, "soul_furnace_picker")
    end = time.time() + 40
    while time.time() < end and not story.start_window_showing(p.grab()):
        p.sleep(0.3)
    furnace.game_auto_play_off(p, print)
    print(maps.find_position(p, maps.load_profile("soul_furnace"), log=print))
