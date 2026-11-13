"""Launch Roblox through a private server link and check where it landed.
  .venv-win/Scripts/python.exe tools/test_private_server.py "<link>"
Closes Roblox, launches the converted roblox:// address, waits for the lobby, then saves the Esc
menu's "In this server" list to cap/ps/ (a private server lists only you) and closes the menu.
An empty link tests a public server."""
import os
import subprocess
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import open_platform  # noqa: E402
from macro.platform.links import to_launch_uri  # noqa: E402
from macro.platform.windows import WindowsPlatform  # noqa: E402
from macro.vision.ocr import find_words  # noqa: E402
from macro.vision.screens import ScreenDetector  # noqa: E402

OUT = os.path.join(ROOT, "cap", "ps")
os.makedirs(OUT, exist_ok=True)
arg = sys.argv[1] if len(sys.argv) > 1 else ""
uri = arg if arg.startswith("roblox://") else to_launch_uri(arg)  # a raw roblox:// address is tried as is
kind = "share" if "share_links" in uri else ("start" if "experiences/start" in uri else ("game" if "linkCode" in uri else "public"))
print("launching", uri.split("code=")[0] + ("code=..." if "code=" in uri else ""), flush=True)
w = WindowsPlatform()
w.close_game(); time.sleep(2)
subprocess.Popen(f'cmd.exe /d /c start "" "{uri}"', close_fds=True, creationflags=0x00000008 | 0x00000200)
t0 = time.time()
# Wait for the process before make_game_ready: it launches the public game if it sees none, and
# that second copy took the join every time (10 Nov 2026: three "failed" tests were this).
while not w.game_running() and time.time() - t0 < 30:
    time.sleep(0.3)
problem = w.make_game_ready(timeout=120)
w.close()
print("ready:", problem or "yes", f"after {time.time() - t0:.0f} s", flush=True)
detector = ScreenDetector()
with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3)
    end, last = time.time() + 150, None
    while time.time() < end:
        name = detector.classify(p.grab()).name
        if name != last:
            print(f"  {time.time() - t0:5.0f} s  {name}", flush=True); last = name
        if name == "lobby":
            break
        time.sleep(1)
    p.guard.arm()
    p.sleep(3)
    p.key("escape"); p.sleep(1.5)
    frame = p.grab()
    path = os.path.join(OUT, f"{kind}_{time.strftime('%H%M%S')}.png")
    cv2.imwrite(path, frame)
    words = [t for t, x, y in find_words(frame, (220, 320, 1220, 660))]
    print("in this server:", ", ".join(t for t in words if t.startswith("@")) or words[:12], flush=True)
    p.key("escape"); p.sleep(0.8)
    print("saved", path)
