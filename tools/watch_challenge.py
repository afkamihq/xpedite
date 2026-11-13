"""Play a challenge with its map's plan and keep a picture every 3 s, to see what goes wrong.
  watch_challenge.py regular [plan]      pictures: cap/watch/<n>_wave<w>.jpg
"""
import os
import shutil
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps, plans  # noqa: E402
from macro.control.engine import read_hotbar_costs  # noqa: E402
from macro.modes import challenge, story  # noqa: E402
from macro.nav.navigator import Navigator  # noqa: E402
from macro.nav.recovery import Recovery  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.platform.windows import wait_hands_off  # noqa: E402
from macro.sched.runner import folder_of, playable  # noqa: E402
from macro.vision.digits import DigitReader  # noqa: E402
from macro.vision.screens import scaled  # noqa: E402

kind = sys.argv[1] if len(sys.argv) > 1 else "regular"
plan_name = sys.argv[2] if len(sys.argv) > 2 else "story"
OUT = os.path.join(ROOT, "cap", "watch")
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


last = [0.0, 0]


def keep(screen, frame, hud):
    now = time.perf_counter()
    if frame is not None and now - last[0] >= 3.0:
        last[0] = now
        last[1] += 1
        wave = hud.get("wave") if hud else None
        cv2.imwrite(os.path.join(OUT, f"{last[1]:03d}_wave{wave}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])


wait_hands_off(seconds=10, timeout=300)
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=60) or "yes")
    p.guard.arm()
    nav = Navigator(p, log=log)
    recovery = Recovery(p, nav, log=log)
    screen = nav.settle()
    if screen in story.RESULT_SCREENS:
        story.leave_results(nav, screen, on_lost=recovery)
    nav.go("lobby", on_lost=recovery)
    p.hover(*scaled(960, 300))
    p.sleep(0.8)
    costs = read_hotbar_costs(p.grab())
    nav.go("challenges", on_lost=recovery)
    offers = challenge.read_offers(nav, kind)
    for o in offers:
        log(o.describe())
    offer = challenge.choose(offers, playable, crystals_only=(kind == "regular"))
    if offer is None:
        sys.exit("nothing to play")
    log(f"playing {offer.describe()}")
    folder = folder_of(offer.map)
    challenge.enter(nav, offer)
    result = story.play_match(nav, DigitReader(), maps.load_profile(folder), plans.load(folder, plan_name), costs,
                              on_lost=recovery, log=log, on_frame=keep)
    log(f"RESULT: {result.outcome} after {result.seconds:.0f} s")
    p.sleep(3.0)
    cv2.imwrite(os.path.join(OUT, "results.png"), p.grab())
