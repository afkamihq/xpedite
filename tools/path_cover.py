"""Where units cover the most path: in a view's reference picture, the path is found by its cyan
arrows (shown before Start), and each valid spot (from the spot scan's picture) is scored by the
path within a unit's range. Picks spots greedily, each counting only path the earlier ones don't
already cover, so they spread along the path rather than pile up.
  path_cover.py soul_furnace_down 4 [radius_px]
Saves cap/scan/<view>_cover.jpg with the picks numbered and their circles."""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import placing  # noqa: E402

view, count = sys.argv[1], int(sys.argv[2])
radius = int(sys.argv[3]) if len(sys.argv) > 3 else 100
ref = cv2.imread(os.path.join(ROOT, "data", "maps", view, "reference.png"))
scan = cv2.imread(os.path.join(ROOT, "cap", "scan", f"{view}.jpg"))
placing.EXTRA_AREAS[:] = placing.EVENT_AREAS
f = ref.astype(int)
arrows = (f[:, :, 0] > 200) & (f[:, :, 1] > 200) & (f[:, :, 2] < 150)
h, w = arrows.shape
for y in range(0, h, 4):
    for x in range(0, w, 4):
        if placing.on_hud(x, y):
            arrows[y:y + 4, x:x + 4] = False
# Thicken the arrows into a band along the path, so gaps between them count as path too.
band = cv2.dilate(arrows.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
valid = []
for y in range(110, 650, 50):
    for x in range(190, 1270, 50):
        b, g, r = scan[y, x].astype(int)
        if g > 200 and r < 80 and b < 80:
            valid.append((x, y))
yy, xx = np.mgrid[0:h, 0:w]
covered = np.zeros_like(band)
picks = []
for _ in range(count):
    best, best_gain = None, 0
    for x, y in valid:
        if any((x - px) ** 2 + (y - py) ** 2 < 45 ** 2 for px, py, _ in picks):
            continue
        disk = (xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2
        gain = int((band & disk & (covered == 0)).sum())
        if gain > best_gain:
            best, best_gain = (x, y), gain
    if best is None:
        break
    picks.append((*best, best_gain))
    covered |= ((xx - best[0]) ** 2 + (yy - best[1]) ** 2 <= radius ** 2).astype(np.uint8) & band
out = ref.copy()
out[band > 0] = (out[band > 0] * 0.5 + np.array([255, 255, 0]) * 0.5).astype(np.uint8)
for n, (x, y, gain) in enumerate(picks, 1):
    cv2.circle(out, (x, y), radius, (0, 255, 255), 2)
    cv2.circle(out, (x, y), 8, (0, 0, 255), -1)
    cv2.putText(out, str(n), (x + 10, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
for x, y in valid:
    cv2.circle(out, (x, y), 3, (0, 255, 0), -1)
cv2.imwrite(os.path.join(ROOT, "cap", "scan", f"{view}_cover.jpg"), out)
print(f"{len(valid)} valid spots; path band {int(band.sum())} px")
for n, (x, y, gain) in enumerate(picks, 1):
    print(f"  {n}: ({x}, {y}) covers {gain} px of path not yet covered")
