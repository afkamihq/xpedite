"""The platform layer against the real game, with the user watching.

Start in the lobby. It waits up to 90 s for Roblox to be in front and fullscreen,
and it won't send anything unless it can see the lobby's Play button. It only opens
the Play menu and backs out, turns the camera, zooms and takes a short walk, undoing
each one. The user can't see a terminal over the fullscreen game, so beeps cue them:

  1 beep:   started, keep your hands off
  2 beeps:  guard test, touch the mouse or a key now
  3 beeps:  hotkey test, press F8 now
  long low: finished or stopped

Frames go to cap/live/. Run from the project root:
  .venv-win/Scripts/python.exe tools/live_test.py
"""
import os
import sys
import time
import winsound

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import GuardTripped
from macro.platform import windows as w

OUT = os.path.join(ROOT, "cap", "live")
PLAY = (171, 660)  # lobby's Play button (docs/GAME.md)
BACK = (150, 1014)  # Play menu's back button
BANNER = (1000, 92)  # Play menu's "Progressive" banner
SAFE_HOVER = (960, 300)  # open sky/world, no button listed there in docs/GAME.md
MATCH_MIN = 0.6


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def beep(count, freq=1000):
    for _ in range(count):
        winsound.Beep(freq, 180)
        time.sleep(0.15)


def save(name, frame):
    cv2.imwrite(os.path.join(OUT, name + ".png"), frame)


def crop_around(image, centre, half_w, half_h):
    x, y = centre
    return image[y - half_h:y + half_h, x - half_w:x + half_w]


def play_score(frame, template):
    """How well the Play button's place on screen matches the reference (-1..1)."""
    region = crop_around(frame, PLAY, 60 + 30, 25 + 30)
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    return float(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED).max())


def wait_until(p, seen, timeout=10.0):
    """Seconds until seen(frame) is true, or None. Stops if the guard trips."""
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        if seen(p.grab()):
            return time.perf_counter() - start
        p.sleep(0.03)
    return None


def difference(a, b):
    return float(np.mean(cv2.absdiff(a, b)))


def hover_until_stopped(p, seconds):
    """Harmless moves, with F24 held so a real release gets exercised. Returns
    how long input carried on after the guard tripped, in ms, or None."""
    end = time.perf_counter() + seconds
    p.key_down("f24")
    i = 0
    try:
        while time.perf_counter() < end:
            i += 1
            p.move(SAFE_HOVER[0] + (i % 2) * 40, SAFE_HOVER[1])
            p.sleep(0.05)
    except GuardTripped:
        time.sleep(0.1)
        return (time.perf_counter() - p.guard.trip_time) * 1000 - 100, not p._held_keys
    finally:
        p.key_up("f24")
    return None, not p._held_keys


def run(p):
    log("waiting up to 90 s for Roblox in front and fullscreen (F11)...")
    end = time.perf_counter() + 90
    while (problem := w.game_window_problem()) and time.perf_counter() < end:
        time.sleep(0.2)
    if problem:
        log(f"gave up: {problem}. Nothing was sent.")
        return 1
    beep(1)
    log("Roblox ready; waiting for 3 s hands-off")
    if not w.wait_hands_off(timeout=30):
        log("input kept arriving. Nothing was sent.")
        return 1

    if "--auto" in sys.argv:
        return auto_guard(p)
    if "--watch" in sys.argv:
        return watch(p)
    if "--guard-only" in sys.argv:
        p.guard.arm()
        return guard_tests(p)

    reference = cv2.imread(os.path.join(ROOT, "refs", "frames", "lobby.png"))
    template = cv2.cvtColor(crop_around(reference, PLAY, 60, 25), cv2.COLOR_BGR2GRAY)
    base = p.grab()
    save("0_start", base)
    log(f"frame: {base.shape}, brightness std {base.std():.1f} (near 0 means capture is black)")
    menu_ref = cv2.imread(os.path.join(ROOT, "refs", "frames", "play_menu_top.png"))
    banner = cv2.cvtColor(crop_around(menu_ref, BANNER, 110, 25), cv2.COLOR_BGR2GRAY)

    def in_lobby(frame):
        return play_score(frame, template) >= MATCH_MIN

    def in_menu(frame):
        region = cv2.cvtColor(crop_around(frame, BANNER, 110 + 30, 25 + 30), cv2.COLOR_BGR2GRAY)
        return float(cv2.matchTemplate(region, banner, cv2.TM_CCOEFF_NORMED).max()) >= MATCH_MIN

    lobby_now, menu_now = in_lobby(base), in_menu(base)
    log(f"Play button match against the Linux reference: {play_score(base, template):.2f} "
        f"(need {MATCH_MIN}); in Play menu: {menu_now}")
    if not lobby_now and not menu_now:
        log("not sure where this is. Nothing was sent. See cap/live/0_start.png.")
        return 1

    p.guard.arm()
    if menu_now:
        p.click(*BACK)
        seconds = wait_until(p, in_lobby)
        if seconds is None:
            log("started in the Play menu, but Back didn't reach the lobby. Stopping.")
            return 1
        log(f"started in the Play menu; Back reached the lobby in {seconds:.2f} s")
        p.sleep(1.0)

    p.move(*PLAY)
    p.sleep(0.2)
    log(f"pointer asked for {PLAY}, Windows says {w.cursor_pos()}")

    p.click(*PLAY)
    seconds = wait_until(p, in_menu)
    save("1_play_menu", p.grab())
    if seconds is None:
        log("Play menu didn't appear within 10 s. Stopping. See cap/live/1_play_menu.png.")
        return 1
    log(f"Play menu appeared {seconds:.2f} s after the click")
    p.sleep(1.0)  # let it finish animating before clicking inside it

    p.click(*BACK)
    seconds = wait_until(p, in_lobby)
    save("2_back", p.grab())
    if seconds is None:
        log("didn't get back to the lobby within 10 s. Stopping. See cap/live/2_back.png.")
        return 1
    log(f"back in the lobby {seconds:.2f} s after the click")
    p.sleep(1.0)

    p.move(*SAFE_HOVER)
    p.sleep(0.2)
    before = p.grab()
    p.turn(200, 0)
    p.sleep(0.5)
    turned = p.grab()
    save("3_turned", turned)
    p.turn(-200, 0)
    p.move_rel(1, 0)
    p.move_rel(-1, 0)
    p.sleep(0.5)
    after = p.grab()
    save("4_turned_back", after)
    log(f"camera turn 200 counts: changed {difference(before, turned):.1f}; "
        f"after turning back, off by {difference(before, after):.1f}")

    p.scroll(15)
    p.sleep(0.5)
    zoomed = p.grab()
    save("5_zoomed", zoomed)
    p.scroll(-15)
    p.sleep(0.5)
    log(f"zoom one notch: changed {difference(after, zoomed):.1f}")

    start = p.grab()
    p.key("w", hold=0.25)
    p.sleep(0.5)
    walked = p.grab()
    save("6_walked", walked)
    p.key("s", hold=0.25)
    p.sleep(0.5)
    returned = p.grab()
    save("7_walked_back", returned)
    log(f"walk 0.25 s: changed {difference(start, walked):.1f}; back, off by {difference(start, returned):.1f}")
    return guard_tests(p)


def auto_guard(p):
    """The guard with the game really fullscreen and nobody at the laptop. Events
    without our tag stand in for real hands: they reach the same hooks. Only a
    one-pixel move, F24 and the stop hotkey are sent."""
    g, good = p.guard, True

    def wait_trip():
        end = time.perf_counter() + 2
        while time.perf_counter() < end and not g.tripped:
            time.sleep(0.002)
        return g.tripped

    def report(name, ok, detail=""):
        nonlocal good
        good = good and ok
        log(f"{'ok  ' if ok else 'FAIL'} {name}  {detail}")

    g.arm()
    p.key_down("f24")
    p._send(p._mouse(w.MOUSEEVENTF_MOVE, dx=1, tag=0))
    report("outside mouse event pauses it", wait_trip() and "mouse" in g.reason, g.reason)
    time.sleep(0.2)
    report("held key released", not p._held_keys)
    p._send(p._mouse(w.MOUSEEVENTF_MOVE, dx=-1))
    try:
        p.move(*SAFE_HOVER)
        report("input refused while paused", False)
    except GuardTripped:
        report("input refused while paused", True)

    g.arm()
    p._send(p._keyboard(0x76, w.KEYEVENTF_SCANCODE, tag=0),
            p._keyboard(0x76, w.KEYEVENTF_SCANCODE | w.KEYEVENTF_KEYUP, tag=0))
    report("outside key press pauses it", wait_trip() and "key" in g.reason, g.reason)

    g.arm()
    scan = w.scan_code("f8")[0]
    p._send(p._keyboard(scan, w.KEYEVENTF_SCANCODE), p._keyboard(scan, w.KEYEVENTF_SCANCODE | w.KEYEVENTF_KEYUP))
    end = time.perf_counter() + 2
    while time.perf_counter() < end and not g.stopped:
        time.sleep(0.002)
    report("stop hotkey stops it", g.stopped, g.reason)
    try:
        g.arm()
        report("no resuming after the hotkey", False)
    except GuardTripped:
        report("no resuming after the hotkey", True)
    return 0 if good else 1


def watch(p):
    """Sends nothing. After 2 beeps, watches for 30 s whether real input reaches
    the hooks, and compares with two signals that don't depend on them: Windows'
    own last-input time, and the pointer's position."""
    g = p.guard
    beep(2)
    log("watching for 30 s: move the mouse now")
    start, before, pointer = time.perf_counter(), g.foreign, w.cursor_pos()
    idle_at_start = w.idle_seconds()
    while time.perf_counter() - start < 30:
        elapsed = time.perf_counter() - start
        windows_saw = w.idle_seconds() < idle_at_start + elapsed - 0.5
        if g.foreign > before or windows_saw or w.cursor_pos() != pointer:
            time.sleep(0.5)  # let the slower signals catch up
            break
        time.sleep(0.01)
    else:
        log("no input of any kind in 30 s: nothing was touched, so this proves nothing")
        return 1
    hooks, moved = g.foreign - before, w.cursor_pos() != pointer
    windows_saw = w.idle_seconds() < idle_at_start + (time.perf_counter() - start) - 0.5
    log(f"after {time.perf_counter() - start:.1f} s: hooks saw {hooks} events; "
        f"Windows saw input: {windows_saw}; pointer moved: {moved}")
    if hooks:
        log("PASS: real input reaches the hooks with the game fullscreen")
        return 0
    log("FAIL: real input arrived, but the hooks can't see it with the game fullscreen")
    return 1


def guard_tests(p):
    log("guard test: 2 beeps, touch the mouse or a key (30 s)")
    beep(2)
    before = p.guard.foreign
    late, released = hover_until_stopped(p, 30)
    log(f"guard test: the hooks saw {p.guard.foreign - before} events that weren't ours, "
        f"and {p.guard.seen} of our {p.guard.sent}")
    if late is None:
        log("guard test: no touch noticed in 30 s")
        return 1
    log(f"guard test: paused because \"{p.guard.reason}\"; all keys released: {released}")

    log("hotkey test: hands off, then 3 beeps, then press F8 (30 s)")
    if not w.wait_hands_off(seconds=2, timeout=30):
        log("input kept arriving, so skipping the hotkey test")
        return 1
    p.guard.arm()
    beep(3)
    late, released = hover_until_stopped(p, 30)
    log(f"hotkey test: \"{p.guard.reason}\", stop latched: {p.guard.stopped}; all keys released: {released}")
    return 0 if p.guard.stopped else 1


def main():
    os.makedirs(OUT, exist_ok=True)
    log(f"mouse settings: {w.mouse_settings()}")
    with w.WindowsPlatform() as p:
        p.guard.start()
        try:
            code = run(p)
        except GuardTripped as stopped:
            log(f"stopped early: {stopped}")
            code = 1
    beep(1, freq=400)
    log("all done" if code == 0 else "ended early")
    return code


if __name__ == "__main__":
    sys.exit(main())
