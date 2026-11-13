"""In a match: measure the view against the map's reference picture, turn by what it says,
and measure again. probe_roll.py crimson_shore [extra_counts]"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cv2
from macro.control import maps
from macro.vision import align
from macro.platform import open_platform
from macro.platform.windows import wait_hands_off

profile = maps.load_profile(sys.argv[1])
extra = int(sys.argv[2]) if len(sys.argv) > 2 else 0

wait_hands_off(seconds=10, timeout=300)
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=30) or "yes")
    p.guard.arm()
    p.grab()
    reference = align.features(cv2.imread(profile.reference_path))

    def measure(label):
        p.sleep(0.6)
        r = align.align(reference, align.features(p.grab()))
        print(label, None if r is None else (round(r.dx, 1), round(r.dy, 1), round(r.roll, 2), round(r.scale, 3), r.inliers), flush=True)
        return r
    r = measure("before")
    if extra:
        p.turn(extra, 0); p.move_rel(1, 0); p.move_rel(-1, 0)
        r = measure(f"after {extra} counts")
    if r is not None and abs(r.roll) > 0.2:
        counts = round(r.roll / 0.079)
        p.turn(counts, 0); p.move_rel(1, 0); p.move_rel(-1, 0)
        measure(f"after turning {counts}")
    cv2.imwrite(os.path.join(ROOT, "cap", "after", "roll.png"), p.grab())
