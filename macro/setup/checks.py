"""The setup check for a new user (and for anyone whose macro starts misbehaving): is this PC,
this Roblox and this game set up the way the macro was measured on? Each check says what it
found, whether that's fine, and how to fix it.

PC and Roblox checks only read: Windows settings and Roblox's own settings file on disk
(GlobalBasicSettings_13.xml, never the running game). In-game settings are checked and set by
looking at the game's Settings window (macro/setup/game_settings.py).
"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
from dataclasses import dataclass

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CALIBRATION = os.path.join(ROOT, "data", "calibration", "win32.yaml")
ROBLOX_SETTINGS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Roblox", "GlobalBasicSettings_13.xml")
# What the macro's camera and pictures were measured with (9-10 Nov 2026).
WANT_QUALITY = 1
WANT_SENSITIVITY = 0.2


@dataclass
class Check:
    group: str      # "PC", "Roblox", "Game", "Team"
    name: str
    ok: bool | None  # None: couldn't tell
    found: str
    fix: str = ""


def _roblox_values() -> dict[str, str]:
    try:
        text = open(ROBLOX_SETTINGS, encoding="utf-8", errors="replace").read()
    except OSError:
        return {}
    return dict(re.findall(r'<\w+ name="(\w+)">([^<]*)<', text))


def pc_checks() -> list[Check]:
    checks = []
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    width, height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    checks.append(Check("PC", "Screen", (width, height) == (1920, 1080), f"{width}x{height}",
                        "" if (width, height) == (1920, 1080) else
                        "Set Windows display resolution to 1920x1080 (Settings > System > Display)."))
    try:
        dpi = user32.GetDpiForSystem()
        checks.append(Check("PC", "Display scaling", True, f"{round(dpi / 96 * 100)}%",
                            ""))  # the app works in real pixels whatever the scaling
    except Exception:
        pass
    try:
        scheme = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True,
                                timeout=5).stdout
        name = re.search(r"\((.*)\)", scheme)
        name = name.group(1) if name else "unknown"
        saver = "saver" in name.lower()
        checks.append(Check("PC", "Power plan", not saver, name,
                            "Power saver slows Roblox down: use Balanced or High performance." if saver else ""))
    except Exception:
        pass
    try:
        with open(CALIBRATION, encoding="utf-8") as f:
            measured = (yaml.safe_load(f) or {}).get("mouse_settings") or {}
        from macro.platform.windows import mouse_settings
        now = mouse_settings()
        same = all(now.get(k) == v for k, v in measured.items())
        checks.append(Check("PC", "Mouse settings", same,
                            f"speed {now.get('pointer_speed')}, precision {'on' if now.get('enhance_pointer_precision') else 'off'}",
                            "" if same else "Camera turns were measured with Windows pointer speed "
                            f"{measured.get('pointer_speed')} and Enhance pointer precision "
                            f"{'on' if measured.get('enhance_pointer_precision') else 'off'}; set those back, or "
                            "run tools/calibrate.py."))
    except Exception:
        pass
    return checks


def roblox_checks() -> list[Check]:
    values = _roblox_values()
    if not values:
        return [Check("Roblox", "Settings file", None, "not found",
                      "Open Roblox once (any game), then check again.")]
    checks = []
    quality = values.get("SavedQualityLevel", "?")
    checks.append(Check("Roblox", "Graphics quality", quality == str(WANT_QUALITY), f"level {quality}",
                        "" if quality == str(WANT_QUALITY) else
                        "In Roblox's menu (Esc > Settings), set Graphics Mode to Manual and Graphics Quality to "
                        "the lowest bar. The macro's pictures are all at that level."))
    try:
        sensitivity = float(values.get("MouseSensitivity", "nan"))
        same = abs(sensitivity - WANT_SENSITIVITY) < 0.01
        checks.append(Check("Roblox", "Camera sensitivity", same, f"{sensitivity:.2f}",
                            "" if same else f"In Roblox's menu, set Camera Sensitivity back to {WANT_SENSITIVITY}: "
                            "the macro turns the camera by measured amounts."))
    except ValueError:
        pass
    inverted = values.get("CameraYInverted") == "true"
    checks.append(Check("Roblox", "Camera not inverted", not inverted, "inverted" if inverted else "normal",
                        "Turn off Invert Camera in Roblox's menu." if inverted else ""))
    try:
        cap = int(values.get("FramerateCap", "0"))
        fine = cap == 0 or cap >= 60
        checks.append(Check("Roblox", "Frame rate cap", fine, "no cap" if cap == 0 else f"{cap} fps",
                            "" if fine else "Set Roblox's frame rate cap to 60 or more."))
    except ValueError:
        pass
    return checks


def all_offline_checks() -> list[Check]:
    return pc_checks() + roblox_checks()
