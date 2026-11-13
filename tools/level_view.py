"""Find a map's straight view: try rotations in a Sandbox match, with level guide lines.

  level_view.py crimson_shore crimson_shore -40 -55 -70
    map folder, Sandbox picker button, then rotation counts to try from the map's zoom

Saves cap/level/<map>.jpg with each try and its guide lines, and each full picture beside
it. Rotation in the file is ignored here: these are counts from the unrotated view.
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

name, button = sys.argv[1], sys.argv[2]
tries = [int(v) for v in sys.argv[3:]]
out = os.path.join(ROOT, "cap", "level")
os.makedirs(out, exist_ok=True)
shots = []
with open_platform() as p:
    problem = p.make_game_ready(timeout=30)
    if problem:
        sys.exit(f"game isn't ready: {problem}")
    p.guard.arm()
    nav = Navigator(p, log=print)
    screen = nav.settle()
    if screen in story.RESULT_SCREENS and button != "here":
        story.leave_results(nav, screen)
    if button != "here":  # "here": already in a match on this map (a challenge, say)
        nav.go("lobby")
        start_sandbox(nav, map_button=button)
        p.sleep(2.0)
    profile = maps.load_profile(name)
    profile.yaw_counts = 0
    maps.set_overhead_camera(p, profile)
    turned = 0
    for counts in tries:
        p.turn(counts - turned, 0)
        turned = counts
        p.sleep(0.3)
        p.hover(720, 100)
        p.sleep(0.6)
        frame = p.grab()
        cv2.imwrite(os.path.join(out, f"{name}_{counts:+d}.png"), frame)
        shots.append((counts, frame))
    p.turn(-turned, 0)
tiles = []
for counts, frame in shots:
    tile = frame.copy()
    for y in range(90, 810, 90):
        cv2.line(tile, (0, y), (1440, y), (255, 255, 255), 1)
    for x in range(180, 1440, 180):
        cv2.line(tile, (x, 0), (x, 810), (255, 255, 255), 1)
    cv2.putText(tile, f"{counts:+d}", (640, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 255, 255), 3)
    tiles.append(cv2.resize(tile, (960, 540), interpolation=cv2.INTER_AREA))
while len(tiles) % 2:
    tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(os.path.join(out, f"{name}.jpg"), np.vstack([np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles), 2)]),
            [cv2.IMWRITE_JPEG_QUALITY, 85])
