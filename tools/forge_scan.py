"""Open the Soul Forge in the match going on, scroll it in small steps and print what OCR reads at
each step (titles and their positions), saving cap/furnace/forge_scan/<step>.png. Closes it again.
Pause the app's run first (F6).
  forge_scan.py [scroll_per_step=40] [steps=16]
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.modes import furnace  # noqa: E402
from macro.nav.navigator import Navigator  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.vision import ocr  # noqa: E402

per_step = int(sys.argv[1]) if len(sys.argv) > 1 else 40
steps = int(sys.argv[2]) if len(sys.argv) > 2 else 16
out = os.path.join(ROOT, "cap", "furnace", "forge_scan")
os.makedirs(out, exist_ok=True)
with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    nav = Navigator(p, log=print)
    forge = furnace.Forge(p, log=print, nav=nav)
    if not forge.open():
        sys.exit("no Forge")
    for step in range(steps):
        frame = p.grab()
        cv2.imwrite(os.path.join(out, f"{step:02d}.png"), frame)
        words = [(t, x, y) for t, x, y in ocr.find_words(frame, (300, 190, 1130, 655)) if len(t) > 3]
        print(step, [(t, x, y) for t, x, y in words if not t.lower().startswith(("buy", "apply", "increase", "reduce", "adds", "placed", "unit to", "match"))][:12], flush=True)
        p.hover(720, 450)
        p.scroll(per_step)
        p.sleep(0.45)
    forge.close()
