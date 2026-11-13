"""First look at the map of the match Roblox is in now (an event match, say): overhead at each
zoom from fully out. Closes nothing but the Forge. Saves cap/look/<name>_in<N>.png and <name>.jpg.
  look_here.py soul_furnace [yaw_counts]"""
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps  # noqa: E402
from macro.platform import open_platform  # noqa: E402

name = sys.argv[1]
yaw = int(sys.argv[2]) if len(sys.argv) > 2 else 0
out = os.path.join(ROOT, "cap", "look")
os.makedirs(out, exist_ok=True)
shots = []
with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    maps.set_overhead_camera(p, maps.MapProfile(name, [], 191.0, yaw, 0), None)
    for n in range(0, 6):
        if n:
            p.hover(720, 300)
            p.scroll(-15)
            p.sleep(0.5)
        p.hover(720, 100)
        p.sleep(0.6)
        frame = p.grab()
        cv2.imwrite(os.path.join(out, f"{name}_in{n}.png"), frame)
        shots.append((f"in{n}", frame))
tiles = []
for label, frame in shots:
    tile = cv2.resize(frame, (720, 405), interpolation=cv2.INTER_AREA)
    cv2.putText(tile, label, (300, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    tiles.append(tile)
cv2.imwrite(os.path.join(out, f"{name}.jpg"), np.vstack([np.hstack(tiles[i:i + 2]) for i in range(0, 6, 2)]),
            [cv2.IMWRITE_JPEG_QUALITY, 85])
