"""Put Roblox in the frame, starting it if needed, and save the whole screen so the fit
can be checked. Doesn't click anything.
Run from the project root:  .venv-win/Scripts/python.exe tools/dock.py
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import windows as w

with w.WindowsPlatform() as p:
    problem = p.make_game_ready(timeout=30)
    print("docked:", problem or "yes", "| picture at", w.client_rect(w.user32.GetForegroundWindow()))
    time.sleep(1.5)
    game = p.grab()
    print("game picture:", game.shape)
    os.makedirs(os.path.join(ROOT, "cap", "dock"), exist_ok=True)
    cv2.imwrite(os.path.join(ROOT, "cap", "dock", "game.png"), game)
    p.origin, p.width, p.height = (0, 0), 1920, 1080
    time.sleep(0.2)
    cv2.imwrite(os.path.join(ROOT, "cap", "dock", "screen.jpg"),
                cv2.resize(p.grab(), (1280, 720), interpolation=cv2.INTER_AREA))
