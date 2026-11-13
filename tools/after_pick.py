"""From the Story islands (reached inside a match or in the lobby): choose a stage, press
Select Stage, and save what shows. after_pick.py "Crimson Shore" 1 [Normal]"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.nav import stages
from macro.nav.navigator import Navigator
from macro.platform import open_platform
from macro.platform.windows import wait_hands_off

name, act = sys.argv[1], int(sys.argv[2])
difficulty = sys.argv[3] if len(sys.argv) > 3 else "Normal"
OUT = os.path.join(ROOT, "cap", "after")
wait_hands_off(seconds=10, timeout=300)
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=30) or "yes")
    p.guard.arm()
    nav = Navigator(p, log=lambda t: print(t, flush=True))
    stages.choose_story_stage(nav, name, act, difficulty)
    cv2.imwrite(os.path.join(OUT, "pick_0.png"), p.grab())
    nav.press("story_act", "select_stage")
    for n in range(1, 4):
        p.sleep(1.5)
        frame = p.grab()
        cv2.imwrite(os.path.join(OUT, f"pick_{n}.png"), frame)
        print(n, nav.detector.classify(frame).name if hasattr(nav, "detector") else nav.see(), flush=True)
