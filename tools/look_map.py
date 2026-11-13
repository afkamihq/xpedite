"""First look at a map, in a free Sandbox match: its spawn, then each zoom level overhead.
  look_map.py flaming_monastery
Saves cap/look/<map>.jpg. Leaves the match running at the last zoom.
"""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps
from macro.modes import story
from macro.nav.navigator import Navigator
from macro.nav.stages import start_sandbox
from macro.platform import open_platform
from macro.vision.screens import scaled

name = sys.argv[1]
out = os.path.join(ROOT, "cap", "look")
os.makedirs(out, exist_ok=True)
shots = []
with open_platform() as p:
    problem = p.make_game_ready(timeout=30)
    if problem:
        sys.exit(f"game isn't ready: {problem}")
    p.guard.arm()
    nav = Navigator(p, log=print)
    screen = nav.settle()
    if screen in story.RESULT_SCREENS:
        story.leave_results(nav, screen)
    nav.go("lobby")
    start_sandbox(nav, map_button=name)
    p.sleep(2.0)
    shots.append(("spawn", p.grab()))
    maps.set_overhead_camera(p)
    for n in range(0, 5):
        if n:
            p.hover(*scaled(960, 300))
            p.scroll(-15)
            p.sleep(0.5)
        p.hover(720, 100)
        p.sleep(0.6)
        frame = p.grab()
        cv2.imwrite(os.path.join(out, f"{name}_in{n}.png"), frame)
        shots.append((f"in{n}", frame))
tiles = []
for label, frame in shots:
    tile = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
    cv2.putText(tile, label, (250, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    tiles.append(tile)
cv2.imwrite(os.path.join(out, f"{name}.jpg"), np.vstack([np.hstack(tiles[i:i + 3]) for i in range(0, 6, 3)]),
            [cv2.IMWRITE_JPEG_QUALITY, 85])
