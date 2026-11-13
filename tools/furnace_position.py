"""Set up one of the Soul Furnace's placing positions, before Start: from the set position (the
furnace's), walk the route, save data/maps/soul_furnace_<name>/ (profile + reference picture), show
Atom's range there, and scan valid spots (nothing is placed). Walks back afterwards.
  furnace_position.py down s:1.5
"""
import os
import subprocess
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps  # noqa: E402
from macro.platform import open_platform  # noqa: E402

name, route = sys.argv[1], [[k, float(v)] for k, v in (part.split(":") for part in sys.argv[2:])]
folder = f"soul_furnace_{name}"
home = maps.load_profile("soul_furnace")
profile = maps.MapProfile(folder, route, home.walk_px_per_s, 0, 0)
os.makedirs(profile.folder, exist_ok=True)
with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    try:
        maps.correct_position(p, home, print)
    except maps.PositionError as e:
        print('home check:', e)
    maps.walk_route(p, profile)
    p.sleep(0.8)
    p.hover(60, 330); p.sleep(0.5)
    frame = p.grab()
    profile.save()
    cv2.imwrite(profile.reference_path, frame)
    p.key("1"); p.sleep(0.4); p.hover(720, 420); p.sleep(0.5)
    cv2.imwrite(os.path.join(ROOT, "cap", "explore", f"range_{name}.jpg"), p.grab())
    p.key("z"); p.sleep(0.3); p.hover(60, 330)
subprocess.run([sys.executable, os.path.join(ROOT, "tools", "scan_spots.py"), folder, "5"])
with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    back = {"w": "s", "s": "w", "a": "d", "d": "a"}
    for key, seconds in reversed(route):
        p.key(back[key], hold=seconds); p.sleep(0.25)
    try:
        print(maps.correct_position(p, home, print))
    except maps.PositionError as e:
        print('home check after:', e)
