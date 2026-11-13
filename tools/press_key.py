"""Press one function key as a real (untagged) key press, like a person: the app's global hotkeys
(F6 pause/resume, F8 stop) for driving it from outside.  press_key.py F8"""
import ctypes
import sys
import time

SCANS = {f"F{n}": 0x3A + n for n in range(1, 11)}  # F1 0x3B ... F10 0x44
KEYEVENTF_SCANCODE, KEYEVENTF_KEYUP = 0x0008, 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def press(name: str):
    scan = SCANS[name.upper()]
    for flags in (KEYEVENTF_SCANCODE, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP):
        event = INPUT(type=1)
        event.ki = KEYBDINPUT(0, scan, flags, 0, 0)
        ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        time.sleep(0.05)


if __name__ == "__main__":
    press(sys.argv[1])
