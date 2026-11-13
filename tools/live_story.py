"""One real Story match, end to end, with our own placement.

Costs nothing: an already-cleared stage, spending only match Yen. It saves the first frames
of Victory and Defeat as native pictures, since those have only ever been seen on Linux, and
a frame each wave, to prove the digits on real multi-digit numbers. Gems and gold are read
before and after, and a drop stops the run.

  live_story.py ["School Grounds"] [act] [Normal|Hard]

Run from the project root:  .venv-win/Scripts/python.exe tools/live_story.py
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps
from macro.modes import story
from macro.modes.collect import collect_rewards
from macro.nav.currency import SpendingDetected, SpendingWatch
from macro.nav.navigator import NavError, Navigator
from macro.nav.recovery import Recovery, RunStopped
from macro.platform import GuardTripped, PointerLocked, open_platform
from macro.platform.windows import wait_hands_off
from macro.vision.digits import DigitReader
from macro.vision.screens import ROOT as _R, scaled

OUT = os.path.join(ROOT, "cap", "story")
NATIVE = os.path.join(ROOT, "refs", "frames_native")
MAP_FOLDERS = {"School Grounds": "school_grounds", "Crimson Shore": "crimson_shore",
               "Flaming Monastery": "flaming_monastery"}


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(NATIVE, exist_ok=True)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    map_name = args[0] if args else "School Grounds"
    act = int(args[1]) if len(args) > 1 else 1
    difficulty = args[2] if len(args) > 2 else "Normal"
    folder = MAP_FOLDERS[map_name]
    profile = maps.load_profile(folder)
    steps = maps.load_layout(folder, "story")
    team = story.load_team()
    log("waiting for 15 s idle")
    if not wait_hands_off(seconds=15, timeout=300):
        log("the laptop is in use, so nothing was sent")
        return 1
    reader = DigitReader()
    saved = set()
    seen_screens = {}
    last_wave_shot = [None]

    def on_frame(screen, frame):
        seen_screens[screen] = seen_screens.get(screen, 0) + 1
        if screen != "match" and screen not in saved:
            saved.add(screen)
            cv2.imwrite(os.path.join(OUT, f"first_{screen}.png"), frame)
        hud = reader.read_hud(frame) if screen == "match" else None
        if hud and hud["wave"] is not None and hud["wave"] != last_wave_shot[0]:
            last_wave_shot[0] = hud["wave"]
            cv2.imwrite(os.path.join(OUT, f"wave_{hud['wave']:02d}.png"), frame)

    with open_platform() as p:
        try:
            problem = p.make_game_ready(timeout=30)
            if problem:
                log(f"game isn't ready: {problem}")
                return 1
            p.guard.arm()
            nav = Navigator(p, log=lambda t: log(f"    {t}"))
            recovery = Recovery(p, nav, log=lambda t: log(f"    RECOVERY: {t}"))
            watch = SpendingWatch(log=log)
            screen = nav.settle()
            if screen in story.RESULT_SCREENS:
                story.leave_results(nav, screen, on_lost=recovery)
            nav.go("lobby", on_lost=recovery)
            p.hover(*scaled(960, 300))
            p.sleep(0.8)
            watch.check(p.grab())

            story.enter_story(nav, map_name, act, difficulty, on_lost=recovery)
            log("match started")
            result = story.play_match(nav, reader, profile, steps, team, on_lost=recovery, log=log, on_frame=on_frame)
            log(f"RESULT: {result.outcome} after {result.seconds:.0f} s")
            log(f"moves made {result.moves_made} of {len(steps)}, not reached: {result.moves_left}")
            log(f"waves seen: {result.waves_seen}")
            log(f"HUD readings {result.readings}, with Yen or clock unreadable {result.unreadable}")
            log(f"screens seen during the match: {seen_screens}")
            if result.outcome in story.RESULT_SCREENS:
                p.sleep(3.0)  # the window finishes opening, and reward toasts clear
                frame = p.grab()
                name = result.outcome
                log(f"results screen now reads as: {nav.detector.classify(frame).name}")
                cv2.imwrite(os.path.join(OUT, f"result_{name}.png"), frame)
                story.leave_results(nav, name, on_lost=recovery)
                log("back in the lobby")
                for line in collect_rewards(nav, on_lost=recovery, log=log):
                    log(line)
                p.hover(*scaled(960, 300))
                p.sleep(0.8)
                balance = watch.check(p.grab())
                log(f"balance after: {balance.gems} gems, {balance.gold} gold")
                if result.outcome != "victory":
                    return 2
            else:
                cv2.imwrite(os.path.join(OUT, "ended_early.png"), p.grab())
                return 1
        except (GuardTripped, PointerLocked, NavError, RunStopped, SpendingDetected, maps.PositionError) as stopped:
            log(f"STOPPED: {type(stopped).__name__}: {stopped}")
            cv2.imwrite(os.path.join(OUT, "stopped.png"), p.grab())
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
