"""The map position and placement engine against the real game, in free Sandbox matches.

Run 1 goes to the map's set position and places the test layout. Run 2 does the same in a
new match, to prove the position repeats, after deliberately walking off course. Gems and
gold are read in the lobby before and after every match, and a drop stops the run.
Pictures, with the layout's spots drawn on, go to cap/place/.
Run from the project root:  .venv-win/Scripts/python.exe tools/live_place.py
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps
from macro.control.placing import Placer, on_hud, run_layout
from macro.nav.currency import SpendingDetected, SpendingWatch
from macro.nav.navigator import NavError, Navigator
from macro.nav.recovery import Recovery, RunStopped
from macro.nav.stages import start_sandbox
from macro.platform import GuardTripped, PointerLocked, open_platform
from macro.platform.windows import wait_hands_off
from macro.vision import ocr
from macro.vision.digits import YEN_BOX, DigitReader
from macro.vision.screens import scaled

OUT = os.path.join(ROOT, "cap", "place")
MAP = "school_grounds"
results = []


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def check(name, ok, detail=""):
    results.append((name, ok))
    log(f"{'ok  ' if ok else 'FAIL'} {name}  {detail}")


def lobby_balance(p, nav, watch, recovery):
    nav.go("lobby", on_lost=recovery)
    p.hover(*scaled(960, 300))  # hotbar tooltips cover the currency row
    p.sleep(0.8)
    balance = watch.check(p.grab())
    log(f"balance: {balance.gems} gems, {balance.gold} gold")


def one_match(p, nav, reader, profile, steps, recovery, label, push_off_course):
    start_sandbox(nav, on_lost=recovery)
    p.sleep(2.0)
    alignment = maps.go_to_position(p, profile, log=lambda t: log(f"    {t}"))
    check(f"{label}: reached the set position", True, f"off by ({alignment.dx:.1f}, {alignment.dy:.1f}) px")

    if push_off_course:
        p.key("a", hold=0.35)
        p.key("w", hold=0.25)
        p.sleep(0.4)
        alignment = maps.correct_position(p, profile, log=lambda t: log(f"    {t}"))
        check(f"{label}: walked itself back after being pushed off", True,
              f"off by ({alignment.dx:.1f}, {alignment.dy:.1f}) px")

    placed = run_layout(Placer(p, reader, log=lambda t: log(f"    {t}")), steps, alignment)
    p.sleep(1.5)  # the Yen counts down for a moment after the last purchase
    frame = p.grab()
    marked = frame.copy()
    for step, result in zip(steps, placed):
        spot = alignment.to_live(*step["at"])
        cv2.circle(marked, spot, 14, (0, 255, 255), 2)
        if result.at:
            cv2.circle(marked, result.at, 5, (0, 255, 0), -1)
    cv2.imwrite(os.path.join(OUT, f"{label}.jpg"), marked)
    for step, result in zip(steps, placed):
        check(f"{label}: slot {step['slot']} placed", result.ok,
              f"{result.yen_before} -> {result.yen_after}, tries {len(result.tries)} {result.why}")
    # Each drop was seen, so the last reading has to be the current Yen, and lower than it began.
    final = reader.read_yen(frame)
    check(f"{label}: Yen went down overall", final is not None and placed[0].yen_before is not None
          and final < placed[0].yen_before, f"{placed[0].yen_before} -> {final}")

    # An independent check, as a digit once went missing while the Yen still went down.
    x0, y0, _, y1 = YEN_BOX
    by_ocr = ocr.read_number(frame, (x0 + 60, y0, x0 + 240, y1))
    check(f"{label}: settled Yen agrees with OCR", final is not None and final == by_ocr, f"{final} vs {by_ocr}")

    # Being strict mustn't mean refusing all the time.
    readings = []
    for _ in range(100):
        readings.append(reader.read_yen(p.grab()))
        p.sleep(0.02)
    refused = sum(r is None for r in readings)
    others = {r for r in readings if r is not None and r != final}
    check(f"{label}: 100 frames in a row read the same", refused <= 5 and not others, f"{refused} refused, other values: {others}")


def main():
    os.makedirs(OUT, exist_ok=True)
    check("points over the HUD are refused", on_hud(*scaled(1803, 552)) and on_hud(*scaled(960, 980)) and on_hud(-1, 5)
          and not on_hud(*scaled(833, 573)))
    profile = maps.load_profile(MAP)
    steps = maps.load_layout(MAP, "test")
    log("waiting for 15 s idle")
    if not wait_hands_off(seconds=15, timeout=300):
        log("the laptop is in use, so nothing was sent")
        return 1
    reader = DigitReader()
    code = 1
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
            lobby_balance(p, nav, watch, recovery)
            one_match(p, nav, reader, profile, steps, recovery, "run1", push_off_course=False)
            lobby_balance(p, nav, watch, recovery)
            one_match(p, nav, reader, profile, steps, recovery, "run2", push_off_course=True)
            lobby_balance(p, nav, watch, recovery)
            check("no gems or gold spent", True)
            code = 0 if all(ok for _, ok in results) else 1
        except (GuardTripped, PointerLocked, NavError, RunStopped, SpendingDetected, maps.PositionError) as stopped:
            log(f"STOPPED: {type(stopped).__name__}: {stopped}")
            cv2.imwrite(os.path.join(OUT, "stopped.png"), p.grab())
        finally:
            log(f"{sum(ok for _, ok in results)} of {len(results)} checks passed")
    return code


if __name__ == "__main__":
    sys.exit(main())
