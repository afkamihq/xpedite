"""The screen detector against the real game, on frames it has never seen.

Walks through every safe menu and a free Sandbox match, using only allow-listed
buttons, and after each one waits until the detector sees the expected screen. Stops
at the first thing it doesn't expect, and saves that frame. Start in the lobby.
Run from the project root:  .venv-win/Scripts/python.exe tools/live_screens.py
"""
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import GuardTripped, PointerLocked, open_platform
from macro.vision.screens import ScreenDetector, scaled

OUT = os.path.join(ROOT, "cap", "live_screens")
SCROLL = ("scroll",)
ROUTE = [
    # (button on the current screen, or SCROLL), screen expected next, optional timeout
    ("play", "play_menu_top"),
    ("story", "story_maps"), ("first_island", "story_act"), ("tab_infinite", "story_infinite"),
    ("tab_mastery", "story_mastery"), ("tab_1", "story_act"), ("close", "story_maps"), ("back", "play_menu_top"),
    ("raid", "raid_maps"), ("first_island", "raid_act_picker"), ("close", "raid_maps"), ("back", "play_menu_top"),
    ("boss_rush", "boss_rush"), ("back", "play_menu_top"),
    ("challenge", "challenges"), ("row_1", "challenge_detail"), ("close", "play_menu_top"),
    ("expedition", "expedition"), ("back", "play_menu_top"),
    ("trials", "quests"), ("close", "lobby"),
    ("events", "events"), ("halloween", "events"), ("event_gamemode", "soul_furnace_picker"), ("close", "events"),
    ("back", "lobby"),
    ("play", "play_menu_top"), (SCROLL, "play_menu_bottom"),
    ("tournament", "tournament"), ("close", "play_menu_top"), (SCROLL, "play_menu_bottom"),
    ("global_tournament", "global_tournament"), ("close", "play_menu_top"), (SCROLL, "play_menu_bottom"),
    ("tower", "tower"), ("back", "play_menu_top"), (SCROLL, "play_menu_bottom"),
    ("sandbox", "sandbox_picker"), ("school_grounds", "sandbox_picker"), ("select_map", "party_room"),
    ("start_sandbox", "match", 90),
    (("key", "f"), "unit_manager"), ("close", "match"),
    ("sandbox_controls", "sandbox_controls"), ("close", "match"),
    ("autoplay_gear", "autoplay_settings"), ("close", "match"),
    (("key", "escape"), "esc_menu"), (("key", "escape"), "match"),
    ("back_to_lobby", "exit_confirm"), ("return_to_lobby", "lobby", 60),
]


SHORT_ROUTE = [
    ("play", "play_menu_top"), (SCROLL, "play_menu_bottom"),
    ("sandbox", "sandbox_picker"), ("school_grounds", "sandbox_picker"), ("select_map", "party_room"),
    ("start_sandbox", "match", 90),
    ("back_to_lobby", "exit_confirm"), ("return_to_lobby", "lobby", 60),
]
NATIVE = os.path.join(ROOT, "refs", "frames_native")


def save_native(screen, frame):
    """--capture: keep a picture of this screen at the current game size."""
    os.makedirs(NATIVE, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(NATIVE, f"{screen}__{n}.png")):
        n += 1
    if n <= 3:
        cv2.imwrite(os.path.join(NATIVE, f"{screen}__{n}.png"), frame)


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def wait_for(p, detector, expected, timeout, seen_all, step_name):
    """Poll until the expected screen has held for 0.3 s: animations flicker through
    other screens for a frame or two. Returns seconds or None. Keeps one frame of
    each other screen passed on the way."""
    start = time.perf_counter()
    since, last, saved = None, None, set()
    next_keep = start
    while time.perf_counter() - start < timeout:
        frame = p.grab()
        result = detector.classify(frame)
        seen_all.append(result.ms)
        # On a long wait, keep unrecognised frames: these are loading screens.
        if timeout > 30 and result.name == "unknown" and time.perf_counter() >= next_keep:
            next_keep = time.perf_counter() + 2
            cv2.imwrite(os.path.join(OUT, f"{step_name}__loading_{time.perf_counter() - start:04.1f}.png"), frame)
        if result.name != last:
            log(f"    {time.perf_counter() - start:5.2f} s  sees {result.name} ({result.score:.2f})")
            if result.name != expected and result.name not in saved:
                saved.add(result.name)
                if "--capture" in sys.argv and result.name in ("roblox_teleport", "game_loading"):
                    save_native(result.name, frame)
                cv2.imwrite(os.path.join(OUT, f"{step_name}__{result.name}.png"), frame)
            since = time.perf_counter()
        last = result.name
        if result.name == expected and time.perf_counter() - since >= 0.3:
            return time.perf_counter() - start
        p.sleep(0.03)
    cv2.imwrite(os.path.join(OUT, f"{step_name}__TIMEOUT.png"), p.grab())
    return None


def main():
    os.makedirs(OUT, exist_ok=True)
    detector = ScreenDetector()
    times, reached = [], []
    with open_platform() as p:
        try:
            if hasattr(p, "focus_game"):
                from macro.platform.windows import wait_hands_off

                # Don't grab the screen from someone using the laptop.
                careful = "--short" in sys.argv or "--capture" in sys.argv
                idle_needed = 30 if careful else 5
                log(f"waiting until the mouse and keyboard have been idle for {idle_needed} s")
                if not wait_hands_off(seconds=idle_needed, timeout=180 if careful else 600):
                    log("the laptop is in use, so nothing was sent")
                    return 1
                p.focus_game()
                p.guard.start()
                time.sleep(0.5)
            p.guard.arm()
            screen = detector.classify(p.grab()).name
            log(f"starting on: {screen}")
            route = SHORT_ROUTE if "--short" in sys.argv else ROUTE
            if screen == "match":  # pick up where an interrupted run stopped
                route = route[route.index(("start_sandbox", "match", 90)) + 1:]
            elif screen != "lobby":
                log("not the lobby or a match, so nothing was sent")
                return 1
            for index, step in enumerate(route):
                action, expected = step[0], step[1]
                timeout = step[2] if len(step) > 2 else 12
                label = action[0] if isinstance(action, tuple) else action
                log(f"{index:02d} {screen}: {label} -> {expected}")
                if action == SCROLL:
                    p.hover(*scaled(1350, 700))
                    p.scroll(150)
                elif isinstance(action, tuple):
                    p.key(action[1])
                else:
                    p.click(*detector.button(screen, action))
                seconds = wait_for(p, detector, expected, timeout, times, f"{index:02d}_{label}")
                if seconds is None:
                    log(f"FAILED: never saw {expected} within {timeout} s. Frame saved in cap/live_screens.")
                    return 1
                reached.append((index, expected, seconds))
                screen = expected
                p.sleep(0.8)  # let it finish animating
                if "--capture" in sys.argv:
                    save_native(expected, p.grab())
        except (GuardTripped, PointerLocked) as stopped:
            log(f"STOPPED: {stopped}")
            return 1
        finally:
            if times:
                log(f"{len(reached)} steps reached; {len(times)} frames classified, "
                    f"median {np.median(times):.1f} ms, worst {max(times):.1f} ms")
    log("ALL STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
