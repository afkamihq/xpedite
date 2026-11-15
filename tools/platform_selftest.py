"""Checks the Windows platform layer without touching the game.

The only input it sends: one-pixel mouse moves that it undoes, F24 (a key nothing
uses), and a split-second F8 that this test itself has registered. No clicks. It waits until you've been hands-off for 3 s, because touching the mouse or
keyboard during the guard section trips the guard, as it should.
Run from the project root:  .venv-win/Scripts/python.exe tools/platform_selftest.py
"""
import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from macro.platform import GuardTripped
from macro.platform import windows as w

failures = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {name}{'  ' + str(detail) if detail else ''}")
    if not ok:
        failures.append(name)


def wait_for(condition, timeout=2.0):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        if condition():
            return True
        time.sleep(0.002)
    return condition()


# ---------------------------------------------------------------- pure logic
# Windows maps the range back to a pixel as value * size / 65536.
for size in (1920, 1080):
    bad = [p for p in range(size) if w.to_absolute(p, 0, size) * size // 65536 != p]
    check(f"every pixel of {size} maps back to itself", not bad, bad[:3])
check("WASD scan codes", [w.scan_code(k)[0] for k in "wasd"] == [0x11, 0x1E, 0x1F, 0x20])
check("hotbar keys 1-6", [w.scan_code(k)[0] for k in "123456"] == [2, 3, 4, 5, 6, 7])
check("other keys the game uses", [w.scan_code(k)[0] for k in "hjftrxzc"] == [0x23, 0x24, 0x21, 0x14, 0x13, 0x2D, 0x2C, 0x2E])
check("key name forms", w.scan_code("Return") == (0x1C, False) and w.scan_code("F11") == (0x57, False)
      and w.scan_code("End") == (0x4F, True) and w.scan_code("tab") == (0x0F, False))

# ---------------------------------------------------------------- the machine
sw, sh = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
check("DPI aware: real pixels, not scaled ones", (sw, sh) == (1920, 1080), f"{sw}x{sh}")
print("     mouse settings:", w.mouse_settings())
print("     Roblox running:", w.WindowsPlatform().game_running())

# -------------------------------------------------------------------- capture
with w.WindowsPlatform() as p:
    frame = p.grab()
    # The capture is the game's picture: the docked frame from data/display.yaml, or the
    # whole 1920x1080 screen when there's no frame.
    want_h, want_w = (w.FRAME[3], w.FRAME[2]) if w.FRAME else (1080, 1920)
    check(f"capture is {want_w}x{want_h}", frame.shape == (want_h, want_w, 3), frame.shape)
    check("capture isn't black", frame.std() > 1, f"std {frame.std():.1f}")
    times = []
    for _ in range(30):
        t = time.perf_counter()
        p.grab()
        times.append(time.perf_counter() - t)
        time.sleep(0.01)
    times.sort()
    print(f"     grab: median {times[15] * 1000:.1f} ms, worst {times[-1] * 1000:.1f} ms")

# ----------------------------------------- refusing while the game isn't ready
with w.WindowsPlatform() as p:
    problem = w.game_window_problem()
    print("     game window right now:", problem or "ready")
    try:
        p.move(0, 0)
        check("input refused before arming", False)
    except GuardTripped:
        check("input refused before arming", True)
    if problem:
        try:
            p.guard.arm()
            check("arming refused while Roblox isn't ready", False)
        except GuardTripped as e:
            check("arming refused while Roblox isn't ready", True, e)

# -------------------------------------- the guard itself, with the window check
# faked as "fine". Input the test sends goes to whatever is in front, so it stays
# harmless: no distance, and a key nothing uses.
print("     waiting until you've been hands-off for 3 s...", flush=True)
if not w.wait_hands_off():
    sys.exit("gave up: input kept arriving for 60 s")
window = {"problem": None}
p = w.WindowsPlatform(window_problem=lambda: window["problem"])
g = p.guard
g.arm()
try:
    p._do(p._rel, 1, 0)
    p._do(p._rel, -1, 0)
    check("hook sees our own mouse events", wait_for(lambda: g.seen >= 2), f"sent {g.sent}, seen {g.seen}")
    p.key("f24", hold=0.02)
    check("hook sees our own keys", wait_for(lambda: g.seen >= 4), f"sent {g.sent}, seen {g.seen}")
    check("our own input doesn't trip the guard", not g.tripped, g.reason)

    # Key held, then a key press that isn't ours: must pause and let go.
    p.key_down("f24")
    seen = g.seen
    t = time.perf_counter()
    p._send(p._keyboard(0x76, w.KEYEVENTF_SCANCODE, tag=0), p._keyboard(0x76, w.KEYEVENTF_SCANCODE | w.KEYEVENTF_KEYUP, tag=0))
    check("a foreign key press trips it", wait_for(lambda: g.tripped), g.reason)
    check("held key released after the trip", wait_for(lambda: not p._held_keys and g.seen > seen))
    print(f"     pause-to-released: {(time.perf_counter() - t) * 1000:.0f} ms")
    try:
        p._do(p._rel, 1, 0)
        check("input refused after a trip", False)
    except GuardTripped as e:
        check("input refused after a trip", True, e)

    g.arm()
    check("arm() resumes after a pause", not g.tripped)
    p._send(p._mouse(w.MOUSEEVENTF_MOVE, dx=1, tag=0))
    check("a foreign mouse event trips it", wait_for(lambda: g.tripped), g.reason)
    p._send(p._mouse(w.MOUSEEVENTF_MOVE, dx=-1))

    g.arm()
    window["problem"] = "Roblox is not in front (test)"
    check("losing the window trips it, with no input sent", wait_for(lambda: g.tripped), g.reason)
    window["problem"] = None

    # Needs a quiet second; real input during it just means trying again.
    for attempt in range(8):
        w.wait_hands_off(timeout=20)
        g.arm()
        g.sent += 1
        g._last_sent = time.perf_counter()
        wait_for(lambda: g.tripped, 2.5)
        if "hook" in g.reason:
            break
        print(f"     (real input interfered: {g.reason}; trying again)", flush=True)
    check("a dropped hook trips it", "hook" in g.reason, g.reason)

    # A pause right after a resume must still let go of what's held.
    w.wait_hands_off(timeout=20)
    g.arm()
    p.key_down("f24")
    g.trip("first test trip")
    check("held key released on a first trip", wait_for(lambda: not p._held_keys))
    g.arm()
    p.key_down("f24")
    g.trip("quick second test trip")
    check("held key released on an immediate second trip", wait_for(lambda: not p._held_keys))

    # The stop hotkey, sent with our tag so only the hotkey path can react.
    g.arm()
    scan = w.scan_code("f8")[0]
    p._send(p._keyboard(scan, w.KEYEVENTF_SCANCODE), p._keyboard(scan, w.KEYEVENTF_SCANCODE | w.KEYEVENTF_KEYUP))
    check("stop hotkey stops it", wait_for(lambda: g.stopped), g.reason)
    try:
        g.arm()
        check("no resuming after the stop hotkey", False)
    except GuardTripped as e:
        check("no resuming after the stop hotkey", True, e)
finally:
    p.close()

# A second run can't hold the hotkey at the same time, which also stops two macros
# fighting over the mouse.
a, b = w.WindowsPlatform(window_problem=lambda: None), w.WindowsPlatform(window_problem=lambda: None)
try:
    a.guard.start()
    try:
        b.guard.start()
        check("a second run is refused", False)
    except RuntimeError as e:
        check("a second run is refused", True, e)
finally:
    a.close()
    b.close()

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
