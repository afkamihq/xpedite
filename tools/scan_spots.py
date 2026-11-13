"""Find where units can go on a map: hold a unit and move it across a grid, and see whether
the game draws its ghost blue (valid) or red (not). Nothing gets placed. Saves the picture
with the spots marked. Use in a Sandbox match with the map's camera already set.
  scan_spots.py crimson_shore [slot]
"""
import os, sys, time
import cv2
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control.placing import on_hud
from macro.platform import open_platform

name = sys.argv[1]
slot = sys.argv[2] if len(sys.argv) > 2 else "1"
STEP = 50
HALF = 34
with open_platform() as p:
    import time as _t
    p.focus_game(); p.guard.start(); _t.sleep(0.3); p.guard.arm()
    p.hover(720, 100); p.sleep(0.4)
    base = p.grab()
    p.key(slot); p.sleep(0.4)
    marks = []
    for y in range(110, 650, STEP):
        for x in range(190, 1270, STEP):
            if on_hud(x, y):
                continue
            p.move(x, y); p.move_rel(1, 0); p.move(x, y)
            p.sleep(0.16)
            frame = p.grab()
            a = base[y - HALF:y + HALF, x - HALF:x + HALF].astype(float)
            b = frame[y - HALF:y + HALF, x - HALF:x + HALF].astype(float)
            blue_gain = (b[:, :, 0] - a[:, :, 0]).mean()
            red_gain = (b[:, :, 2] - a[:, :, 2]).mean()
            marks.append((x, y, blue_gain, red_gain))
    p.key("z"); p.sleep(0.2); p.hover(720, 100)
gaps = [m[2] - m[3] for m in marks]
print("blue minus red: min %.1f median %.1f max %.1f" % (min(gaps), np.median(gaps), max(gaps)))
picture = base.copy()
good = []
for x, y, blue, red in marks:
    ok = blue - red > 8
    cv2.circle(picture, (x, y), 7, (0, 255, 0) if ok else (0, 0, 255), -1)
    cv2.circle(picture, (x, y), 7, (0, 0, 0), 1)
    if ok:
        good.append((x, y))
out = os.path.join(ROOT, "cap", "scan")
os.makedirs(out, exist_ok=True)
cv2.imwrite(os.path.join(out, f"{name}.jpg"), picture)
print(len(good), "of", len(marks), "valid:", good)
