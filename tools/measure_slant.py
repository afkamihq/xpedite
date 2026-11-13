"""How slanted each try from level_view.py is: long straight edges near level or upright,
on the game's picture without the HUD.
  measure_slant.py flaming_monastery
Prints, per rotation, the length-weighted angle of near-level and near-upright edges. Both
near 0 is the goal. Upright edges lean inward away from the middle (perspective), so only
those close to the screen's middle count for them. Saves the lines for looking at.
"""
import glob
import os
import re
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
name = sys.argv[1]
MIDDLE = 720
paths = glob.glob(os.path.join(ROOT, "cap", "level", f"{name}_*.png"))
for path in sorted(paths, key=lambda s: int(re.search(r"([+-]\d+)\.png", s).group(1))):
    counts = int(re.search(r"([+-]\d+)\.png", path).group(1))
    frame = cv2.imread(path)
    edges = cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 60, 160)
    mask = np.zeros_like(edges)
    mask[90:640, 180:1260] = 255
    mask[640:690, 0:440] = 255
    mask[640:690, 1000:1440] = 255
    edges = cv2.bitwise_and(edges, mask)
    found = cv2.HoughLinesP(edges, 1, np.pi / 1440, 70, minLineLength=110, maxLineGap=6)
    level, upright = [], []
    picture = frame.copy()
    for x0, y0, x1, y1 in (np.array(found).reshape(-1, 4) if found is not None else []):
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        length = float(np.hypot(x1 - x0, y1 - y0))
        angle = float(np.degrees(np.arctan2(y1 - y0, x1 - x0)))
        if angle <= -90:
            angle += 180
        if angle > 90:
            angle -= 180
        if abs(angle) < 8:
            level.append((angle, length))
            cv2.line(picture, (x0, y0), (x1, y1), (0, 255, 255), 2)
        elif abs(abs(angle) - 90) < 8 and abs((x0 + x1) / 2 - MIDDLE) < 130:
            upright.append(((angle - 90) if angle > 0 else (angle + 90), length))
            cv2.line(picture, (x0, y0), (x1, y1), (255, 255, 0), 2)
    cv2.imwrite(os.path.join(ROOT, "cap", "level", f"lines_{name}_{counts:+d}.jpg"), picture)

    def summary(items):
        if not items:
            return "none"
        angles = np.array([a for a, _ in items])
        weights = np.array([w for _, w in items])
        return f"{np.average(angles, weights=weights):+.2f} deg from {len(items)} edges"

    print(f"{counts:+4d}: level {summary(level)} | upright {summary(upright)}")
