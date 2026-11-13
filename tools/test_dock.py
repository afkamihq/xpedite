"""Dock Roblox, undock it, dock it again, and check its picture never changed size: a
resize while Roblox is loading hangs it (see undock_game). Starts Roblox if needed.
  .venv-win/Scripts/python.exe tools/test_dock.py"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import windows as win

p = win.WindowsPlatform()
problem = p.make_game_ready(timeout=120)
print("ready:", problem or "yes")
hwnd = p._game_windows()[0]
sizes = [("docked", win.client_rect(hwnd), win.has_title_bar(hwnd))]
for step in range(2):
    p.undock_game()
    time.sleep(1.5)
    sizes.append(("undocked", win.client_rect(hwnd), win.has_title_bar(hwnd)))
    p.dock_game()
    time.sleep(1.5)
    sizes.append(("docked", win.client_rect(hwnd), win.has_title_bar(hwnd)))
# The title bar left on, as closing the app leaves it: getting ready must take it off.
p.undock_game()
time.sleep(1.5)
print("ready again:", p.make_game_ready(timeout=30) or "yes")
sizes.append(("ready", win.client_rect(hwnd), win.has_title_bar(hwnd)))
for name, rect, titled in sizes:
    print(f"{name:9} {rect}  title bar: {titled}")
ok = all(rect[2:] == tuple(win.FRAME[2:]) for _, rect, _ in sizes) and \
    all(titled == (name == "undocked") for name, _, titled in sizes)
time.sleep(5)
print("responding:", not p.game_frozen())
print("PASSED" if ok else "FAILED: the picture changed size or the title bar is wrong")
