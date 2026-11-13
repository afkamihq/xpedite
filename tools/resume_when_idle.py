"""Watch the app's log and press Resume (F6) for it once a pause has had IDLE seconds with nobody
at the mouse or keyboard: the user's rule for unattended runs is "if a touch pauses it, wait for
idle and carry on". F6 goes in as a real (untagged) key press, like a person's.
  resume_when_idle.py [IDLE=60]          runs until killed
"""
import ctypes
import datetime
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform.windows import idle_seconds  # noqa: E402

IDLE = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
F6_SCAN = 0x40
KEYEVENTF_SCANCODE, KEYEVENTF_KEYUP = 0x0008, 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def press_f6():
    down = INPUT(type=1)
    down.ki = KEYBDINPUT(0, F6_SCAN, KEYEVENTF_SCANCODE, 0, 0)
    up = INPUT(type=1)
    up.ki = KEYBDINPUT(0, F6_SCAN, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, 0)
    for event in (down, up):
        ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        time.sleep(0.05)


def last_state(path):
    """'paused' if the log's latest pause/resume line is a pause, else 'running'."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-200:]
    except OSError:
        return "running"
    for line in reversed(lines):
        if "PAUSED:" in line and "F8" in line or "can't resume yet" in line:
            return "paused"
        if "resuming once" in line or "starting a queue" in line or "stopped" in line.lower():
            return "running"
    return "running"


while True:
    path = os.path.join(ROOT, "logs", f"app-{datetime.date.today():%Y%m%d}.log")
    if last_state(path) == "paused" and idle_seconds() >= IDLE:
        print(f"[{time.strftime('%H:%M:%S')}] paused and {idle_seconds():.0f} s idle: pressing F6", flush=True)
        press_f6()
        time.sleep(15)
    time.sleep(2)
