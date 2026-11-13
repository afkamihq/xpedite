"""Navigation, recovery and the digit reader against the real game.

Everything it does costs nothing: it selects Story stages without starting them, and
plays only a free Sandbox match, placing one unit with free Yen. Allow about 3 minutes.
It needs 30 s of idle first, and gives up if the laptop is in use. Touching anything
pauses it. Frames go to cap/live_nav/.
Run from the project root:  .venv-win/Scripts/python.exe tools/live_nav.py
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.nav import stages
from macro.nav.navigator import NavError, Navigator
from macro.nav.recovery import Recovery, RunStopped
from macro.platform import GuardTripped, PointerLocked, open_platform
from macro.platform.windows import wait_hands_off
from macro.vision import digits as d
from macro.vision.screens import ScreenDetector, scaled

OUT = os.path.join(ROOT, "cap", "live_nav")
results = []


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def check(name, ok, detail=""):
    results.append((name, ok))
    log(f"{'ok  ' if ok else 'FAIL'} {name}  {detail}")


def clock_test(p, reader, seconds=25):
    """The clock counts up, so each frame's true time is known. That tests the digits on
    every value it shows, and supplies shapes for rare ones like 7."""
    samples, start = [], time.perf_counter()
    while time.perf_counter() - start < seconds:
        frame = p.grab()
        reading = reader.pill_reading(frame, "time")
        samples.append((time.perf_counter() - start, frame, reading))
        p.sleep(0.5)
    values = [(t, int(r.text[:2]) * 60 + int(r.text[2:])) for t, _, r in samples
              if r.text.isdigit() and len(r.text) == 4 and r.confidence >= d.MIN_CONFIDENCE]
    refused = len(samples) - len(values)
    if not values:
        check("clock readable", False, "no confident readings")
        return
    offset = sorted(v - t for t, v in values)[len(values) // 2]
    wrong = [(round(t, 1), v) for t, v in values if abs(v - t - offset) > 1.5]
    seen = "".join(sorted({c for _, _, r in samples for c in r.text}))
    check("clock reads correctly as it counts", not wrong, f"{len(values)} read, {refused} refused, wrong: {wrong[:5]}, digits seen: {seen}")
    # Save the shapes, labelled from the known time, for rebuilding the reader later.
    harvest = os.path.join(ROOT, "refs", "clock_native")
    os.makedirs(harvest, exist_ok=True)
    for i, (t, frame, _) in enumerate(samples):
        true = int(round(t + offset))
        cv2.imwrite(os.path.join(harvest, f"{i:03d}_{true // 60:02d}{true % 60:02d}.png"), frame[0:80])


def run(p, nav, reader, recovery):
    # Getting around, and the edges that have never been tried on Windows.
    check("reaches the lobby", nav.go("lobby", on_lost=recovery) == "lobby")
    if "--quick" in sys.argv:
        # A long scroll back from the far end, which is where the row was still gliding.
        stages.choose_story_stage(nav, "Flaming Monastery", 1, "Normal", on_lost=recovery)
        stages.choose_story_stage(nav, "School Grounds", 1, "Normal", on_lost=recovery)
        check("long scroll back lands on School Grounds, set to Normal", True)
        match_part(p, nav, reader, recovery)
        return
    check("reaches the Sandbox picker", nav.go("sandbox_picker", on_lost=recovery) == "sandbox_picker")
    nav.press("sandbox_picker", "close")
    arrived = nav.settle()
    check("Sandbox picker's close button", arrived in ("play_menu_top", "play_menu_bottom"), arrived)

    # Choosing stages by name, without starting them.
    for map_name, act, difficulty in (("School Grounds", 1, "Normal"), ("School Grounds", 2, "Hard"),
                                      ("Crimson Shore", 1, "Normal"), ("Flaming Monastery", 1, "Normal")):
        try:
            stages.choose_story_stage(nav, map_name, act, difficulty, on_lost=recovery)
            cv2.imwrite(os.path.join(OUT, f"stage_{map_name.replace(' ', '_')}_{act}_{difficulty}.png"), nav.last_frame)
            check(f"chose {map_name} act {act} {difficulty}", True)
        except NavError as e:
            check(f"chose {map_name} act {act} {difficulty}", False, e)
            cv2.imwrite(os.path.join(OUT, f"refused_{map_name.replace(' ', '_')}.png"), nav.last_frame)
    # Its picker is laid out differently and has no Normal, so this has to be refused.
    try:
        stages.choose_story_stage(nav, "Hollow Desert", 1, "Normal", on_lost=recovery)
        check("refuses Hollow Desert's different picker", False)
    except NavError as e:
        check("refuses Hollow Desert's different picker", True, e)
    check("gets out of that picker", nav.go("story_maps", on_lost=recovery) == "story_maps")
    # Leave School Grounds on Normal, as it was.
    try:
        stages.choose_story_stage(nav, "School Grounds", 1, "Normal", on_lost=recovery)
    except NavError as e:
        log(f"couldn't set School Grounds back to Normal: {e}")

    # The party room's way out.
    nav.press("story_act", "select_stage")
    nav.wait_for("party_room")
    nav.p.sleep(0.8)
    nav.press("party_room", "leave_party")
    arrived = nav.settle()
    check("party room's Leave Party button", arrived in ("play_menu_top", "play_menu_bottom", "story_maps", "story_act"), arrived)

    match_part(p, nav, reader, recovery)


def match_part(p, nav, reader, recovery):
    # A free Sandbox match, reading numbers throughout.
    nav.go("sandbox_picker", on_lost=recovery)
    nav.press("sandbox_picker", "school_grounds")
    nav.p.sleep(0.6)
    nav.press("sandbox_picker", "select_map")
    nav.wait_for("party_room")
    nav.p.sleep(0.8)
    nav.press("party_room", "start_sandbox")
    check("Sandbox match started", nav.wait_for("match", 90) == "match")
    p.sleep(1.5)

    frame = p.grab()
    hud = reader.read_hud(frame)
    cv2.imwrite(os.path.join(OUT, "hud_start.png"), frame)
    check("HUD reads at the start", hud["yen"] == 1_000_000 and hud["health"] == 3 and hud["wave"] == 1 and hud["enemies"] == 0, hud)
    clock_test(p, reader)

    # Yen as the placement engine will use it: place a unit and see it drop.
    before = reader.read_yen(p.grab())
    p.key("6")
    p.sleep(0.5)
    p.hover(*scaled(600, 720))
    p.sleep(0.4)
    p.click(*scaled(600, 720))
    # The pointer on a new unit raises a tooltip that covers the Yen, so move it off.
    p.hover(*scaled(1500, 250))
    p.sleep(1.5)
    frame = p.grab()
    after = reader.read_yen(frame)
    cv2.imwrite(os.path.join(OUT, "hud_placed.png"), frame)
    check("Yen drops when a unit is placed", before is not None and after is not None and after < before, f"{before} -> {after}")
    from macro.vision import ocr
    x0, y0, x1, y1 = d.YEN_BOX
    check("digit reader agrees with OCR on Yen", ocr.read_number(frame, (x0 + 60, y0, x0 + 240, y1)) == after)

    # Timing, in the conditions it'll really run in.
    start = time.perf_counter()
    for _ in range(20):
        reader.read_hud(p.grab())
    log(f"grab and read all numbers: {(time.perf_counter() - start) / 20 * 1000:.1f} ms a frame")

    check("back to the lobby from a match", nav.go("lobby", on_lost=recovery) == "lobby")


def main():
    os.makedirs(OUT, exist_ok=True)
    log("waiting until the mouse and keyboard have been idle for 30 s")
    if not wait_hands_off(seconds=30, timeout=60):
        log("the laptop is in use, so nothing was sent")
        return 1
    detector = ScreenDetector()
    reader = d.DigitReader()
    code = 1
    with open_platform() as p:
        try:
            p.focus_game()
            p.guard.start()
            time.sleep(0.5)
            problem = p.make_game_ready()
            if problem:
                log(f"game isn't ready: {problem}")
                return 1
            p.guard.arm()
            nav = Navigator(p, detector, log=lambda text: log(f"    {text}"))
            recovery = Recovery(p, nav, log=lambda text: log(f"    RECOVERY: {text}"))
            run(p, nav, reader, recovery)
            code = 0 if all(ok for _, ok in results) else 1
        except (GuardTripped, PointerLocked, NavError, RunStopped) as stopped:
            log(f"STOPPED: {type(stopped).__name__}: {stopped}")
        finally:
            passed = sum(ok for _, ok in results)
            log(f"{passed} of {len(results)} checks passed")
    return code


if __name__ == "__main__":
    sys.exit(main())
