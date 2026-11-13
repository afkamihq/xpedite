"""One Soul Furnace run with furnace.play_furnace, from the match waiting at "Start Game?" or
from its last results (Repeat Stage). Pictures every 15 s to cap/furnace/<plan>/.
  furnace_run.py PLAN [--fresh] [--spa N]
"""
import os
import sys
import threading
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps, plans  # noqa: E402
from macro.modes import furnace, story  # noqa: E402
from macro.nav.navigator import Navigator  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.vision.digits import DigitReader  # noqa: E402

plan_name = sys.argv[1]
spa = int(sys.argv[sys.argv.index("--spa") + 1]) if "--spa" in sys.argv else furnace.SPA_TARGET
out = os.path.join(ROOT, "cap", "furnace", plan_name)
os.makedirs(out, exist_ok=True)


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


last = [0.0]
t0 = time.time()


def on_frame(screen, frame, hud):
    if hud and time.time() - last[0] > 15:
        last[0] = time.time()
        cv2.imwrite(os.path.join(out, f"t{int(last[0] - t0):05d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])


def pause_until_idle(p, quiet: float = 3.0):
    """Someone touched the laptop: everything waits (the match plays on) until mouse and keyboard
    have been still for `quiet` seconds, then carries on where it was."""
    from macro.platform.windows import idle_seconds

    def wait(reason):
        log(f"paused ({reason}); waiting for {quiet:.0f} s of quiet")
        while True:
            while idle_seconds() < quiet:
                time.sleep(0.5)
            p.focus_game()
            time.sleep(0.3)
            try:
                problem = p.make_game_ready(timeout=20)
                if problem:
                    raise RuntimeError(problem)
                p.guard.arm()
                log("resumed")
                return
            except Exception as error:  # noqa: BLE001 - try again after more quiet
                log(f"can't resume yet: {error}")
    p.guard.pausable = True
    p.guard.pause_callback = wait


with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    pause_until_idle(p)
    nav = Navigator(p, log=log)
    reader = DigitReader()
    screen = nav.settle()
    if "--resume" in sys.argv:
        screen = "resume"
    if screen == "match" and not story.start_window_showing(p.grab()) and reader.read_hud(p.grab())["health"] == 0:
        # A lost match whose results were closed: Forge or Game Results show instead.
        furnace.Forge(p).close()
        p.click(720, 617)  # Game Results
        p.sleep(1.5)
        screen = nav.settle()
    if screen in story.RESULT_SCREENS:
        nav.press(screen, "repeat_stage")
    end = time.time() + (0 if screen == "resume" else 40)
    while time.time() < end and not story.start_window_showing(p.grab()):
        p.sleep(0.3)
    profile = maps.load_profile("soul_furnace")
    plan = furnace.load_paths_plan(plan_name) if plan_name == "paths" else plans.load("soul_furnace", plan_name)
    if "--tomed" in sys.argv:  # our units have their tomes already (a rescued match)
        plan = dict(plan, souls={**(plan.get("souls") or {}), "unbound": {}})
    if "--placed" in sys.argv:
        plan = {"views": plan.get("views"), "steps": []}
    r = furnace.play_furnace(nav, reader, profile, plan, fresh="--fresh" in sys.argv, spa_target=spa, log=log,
                             on_frame=on_frame, economy_first="--econ" in sys.argv, resume="--resume" in sys.argv,
                             after_spa=sys.argv[sys.argv.index("--after") + 1] if "--after" in sys.argv else "random_unit")
    log(f"RESULT {r}")
    p.sleep(3)
    cv2.imwrite(os.path.join(out, "results.png"), p.grab())
