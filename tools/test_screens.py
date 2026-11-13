"""Checks the screen detector against every saved picture. Doesn't touch the game.

These are the pictures the anchors were built from, so this catches mistakes but
doesn't prove the detector works on new frames. tools/live_screens.py does that.
Run from the project root:  .venv-win/Scripts/python.exe tools/test_screens.py
"""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.vision.screens import GAME_HEIGHT, GAME_WIDTH, ScreenDetector, load_frame

# Words no clickable button may contain: the rule is never to spend or sell.
FORBIDDEN = ("store", "summon", "shop", "sell", "buy", "purchase", "robux", "feed", "reroll", "battlepass",
             "gamepass", "evolve", "craft")

detector = ScreenDetector()
wrong, times, weakest = [], [], {}
for screen, definition in detector.definitions.items():
    for name in definition["frames"]:
        result = detector.classify(load_frame(name))
        times.append(result.ms)
        if result.name != screen:
            wrong.append((name, screen, result.name))
        else:
            weakest[screen] = min(weakest.get(screen, 1.0), result.score)

total = len(times)
print(f"{total - len(wrong)} of {total} pictures recognised correctly")
for name, expected, got in wrong:
    print(f"  WRONG {name}: should be {expected}, got {got}")
print(f"time per frame: median {np.median(times):.1f} ms, worst {max(times):.1f} ms")
print("no anchors:", [s for s in detector.definitions if s not in detector.anchors] or "none")

bad_buttons = [f"{screen}.{button}" for screen, definition in detector.definitions.items()
               for button in definition.get("buttons") or {}
               if any(word in button.lower() for word in FORBIDDEN)]
# Screens with paid buttons next to the free one: nothing else may ever be on their lists.
ONLY_THESE = {"battlepass": {"claim_all", "close"}, "event_pass": {"claim_all", "back"}}
for screen, allowed in ONLY_THESE.items():
    extra = set(detector.definitions[screen].get("buttons") or {}) - allowed
    if extra:
        bad_buttons.append(f"{screen} also lists {sorted(extra)}")
print("buttons that could spend or sell:", bad_buttons or "none")

# Noise shouldn't look like any screen, and neither should black.
rng = np.random.default_rng(1)
false_hits = []
for label, expected, frame in (("black", "black", np.zeros((GAME_HEIGHT, GAME_WIDTH, 3), np.uint8)),
                               ("grey", "unknown", np.full((GAME_HEIGHT, GAME_WIDTH, 3), 128, np.uint8)),
                               ("noise", "unknown", rng.integers(0, 255, (GAME_HEIGHT, GAME_WIDTH, 3), dtype=np.uint8))):
    result = detector.classify(frame)
    if result.name != expected:
        false_hits.append((label, result.name))
print("blank frames mistaken for a screen:", false_hits or "none")

sys.exit(1 if wrong or bad_buttons or false_hits else 0)
