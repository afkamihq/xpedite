"""Walk by keys, then compare the view with a picture (features, as the position check does).
  walk_check.py PICTURE a:1.2 s:0.6 ...    keys held for seconds, then the check
Saves the frame to cap/after/walk_check.png."""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import open_platform  # noqa: E402
from macro.vision import align  # noqa: E402

ref = align.features(cv2.imread(sys.argv[1]))
with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    for part in sys.argv[2:]:
        key, seconds = part.split(":")
        p.key(key, hold=float(seconds)); p.sleep(0.25)
    p.hover(60, 330); p.sleep(0.6)
    frame = p.grab()
    cv2.imwrite(os.path.join(ROOT, "cap", "after", "walk_check.png"), frame)
    r = align.align(ref, align.features(frame))
    print("no match" if r is None else f"off ({r.dx:.0f}, {r.dy:.0f}) roll {r.roll:.2f} scale {r.scale:.3f}, {r.inliers} agree")
