"""How level a map's path lies in each level_view.py try: mask the path (pale, low-colour,
bright), find its long straight stretches, and print their angles. The goal is every long
stretch within a few tenths of a degree of level or upright.
  path_angle.py fairy_king_forest
Saves cap/level/<map>_path_<counts>.png with the stretches drawn.
"""
import glob
import math
import os
import re
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
name = sys.argv[1]
for path in sorted(glob.glob(os.path.join(ROOT, "cap", "level", f"{name}_[+-]*.png")),
                   key=lambda s: int(re.search(r"_([+-]\d+)\.png$", s).group(1))):
    counts = int(re.search(r"_([+-]\d+)\.png$", path).group(1))
    frame = cv2.imread(path)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 1] < 90) & (hsv[..., 2] > 130)).astype(np.uint8) * 255
    mask[:70] = 0          # top HUD
    mask[600:] = 0         # hotbar
    mask[:, 1300:] = 0     # the right edge
    mask[330:, 1200:] = 0  # side buttons
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    lines = cv2.HoughLinesP(mask, 1, np.pi / 720, 50, minLineLength=80, maxLineGap=12)
    level, upright = [], []
    shown = frame.copy()
    for x1, y1, x2, y2 in (lines.reshape(-1, 4) if lines is not None else []):
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        length = math.hypot(x2 - x1, y2 - y1)
        if abs(angle) < 15 or abs(abs(angle) - 180) < 15:
            a = angle if abs(angle) < 90 else angle - math.copysign(180, angle)
            level.append((a, length))
            cv2.line(shown, (x1, y1), (x2, y2), (0, 255, 255), 2)
        elif abs(abs(angle) - 90) < 15:
            a = (angle - 90) if angle > 0 else (angle + 90)
            if abs(((x1 + x2) / 2) - 720) < 300:  # perspective tilts uprights away from the middle
                upright.append((a, length))
                cv2.line(shown, (x1, y1), (x2, y2), (255, 0, 255), 2)

    def mean(items):
        total = sum(length for _, length in items)
        return f"{sum(a * length for a, length in items) / total:+.2f} deg from {len(items)}" if total else "none"
    print(f"{counts:+4d}: level {mean(level)} | upright {mean(upright)}")
    cv2.imwrite(os.path.join(ROOT, "cap", "level", f"{name}_path_{counts:+d}.png"), shown)
