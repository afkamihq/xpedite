"""Without going through the lobby: click something that starts a match (Start in the
in-match party screen, Next Stage, Repeat Stage), time the trip, play the map's plan and
stop on the results window.
  play_from_here.py "Crimson Shore" story c:854,532
Pictures go to cap/after/: trip_<n>.png each second until the match shows, then results.png.
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps, plans
from macro.control.engine import read_hotbar_costs
from macro.modes import story
from macro.nav.navigator import Navigator
from macro.platform import open_platform
from macro.platform.windows import wait_hands_off
from macro.vision.digits import DigitReader

name, plan_name, click = sys.argv[1], sys.argv[2], sys.argv[3]
folder = name.lower().replace(" ", "_").replace("'", "")
OUT = os.path.join(ROOT, "cap", "after")


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


wait_hands_off(seconds=10, timeout=300)
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=30) or "yes")
    p.guard.arm()
    nav = Navigator(p, log=log)
    reader = DigitReader()
    costs = read_hotbar_costs(p.grab())
    log(f"prices here: {costs}")
    p.click(*(int(v) for v in click[2:].split(",")))
    began, seen, last = p.now(), [], None
    wave_one = None
    for n in range(90):
        p.sleep(1.0)
        frame = p.grab()
        screen = nav.detector.classify(frame).name
        if screen != last:
            log(f"{p.now() - began:.0f} s: {screen}")
            cv2.imwrite(os.path.join(OUT, f"trip_{n}_{screen}.png"), frame)
            last = screen
        if screen == "match":
            hud = reader.read_hud(frame)
            # The old match's HUD stays up for a moment: wait for a fresh one.
            if hud["wave"] is not None and hud["wave"] <= 1 and n >= 2:
                log(f"fresh match after {p.now() - began:.0f} s: {hud}")
                cv2.imwrite(os.path.join(OUT, "fresh_match.png"), frame)
                break
    if not costs:
        costs = read_hotbar_costs(p.grab())
        log(f"prices in the match: {costs}")
    p.sleep(2.0)
    result = story.play_match(nav, reader, maps.load_profile(folder), plans.load(folder, plan_name), costs, log=log)
    log(f"RESULT: {result.outcome} after {result.seconds:.0f} s, {result.moves_made} moves")
    p.sleep(3.0)
    cv2.imwrite(os.path.join(OUT, "results.png"), p.grab())
