"""Watch the match Roblox is in until its results, touching nothing (unless --auto-play: press the
game's Auto Play and Start first). A picture every N seconds to cap/watch_match/<name>/ and the
HUD in the log.
  watch_match.py NAME [seconds] [--auto-play] [--zoom-out]
--zoom-out sets the overhead camera fully out first (after Start), to see the whole map.
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps  # noqa: E402
from macro.modes import story  # noqa: E402
from macro.nav.navigator import Navigator  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.vision.digits import DigitReader  # noqa: E402

AUTO_PLAY = (1352, 519)
name = sys.argv[1]
every = float(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2][0].isdigit() else 10.0
out = os.path.join(ROOT, "cap", "watch_match", name)
os.makedirs(out, exist_ok=True)


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    nav = Navigator(p, log=log)
    reader = DigitReader()
    if "--auto-play" in sys.argv:
        p.click(*AUTO_PLAY); p.sleep(1.0)
    if story.start_window_showing(p.grab()):
        story.press_start(nav, log)
    if "--zoom-out" in sys.argv:
        p.sleep(1.0)
        maps.set_overhead_camera(p)
    started, last = time.time(), 0.0
    while time.time() - started < 3 * 3600:
        frame = p.grab()
        screen = nav.detector.classify(frame).name
        if screen in story.RESULT_SCREENS:
            p.sleep(3.0)
            cv2.imwrite(os.path.join(out, "results.png"), p.grab())
            log(f"results: {screen}")
            break
        if time.time() - last >= every:
            last = time.time()
            hud = reader.read_hud(frame)
            t = int(last - started)
            cv2.imwrite(os.path.join(out, f"t{t:05d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            log(f"t {t} {screen} wave {hud['wave']} enemies {hud['enemies']} health {hud['health']} "
                f"yen {hud['yen']} souls {hud.get('souls')} candy {hud.get('candy')}")
        p.sleep(0.5)
