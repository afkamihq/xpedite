"""Play a match from a short list of moves, at game speed, keeping a picture every 10 s to
learn from. Each move happens exactly once, when the Yen covers it, with no retries:
  slot:cost:x:y      place the unit in that hotbar slot
  up:x:y:cost        select the placed unit there and upgrade it once with T
Prints what the Yen did after each move, so a move that did nothing shows up.
  play_steps.py 6:550:600:330 1:1250:700:330 up:700:330:2850
"""
import os, sys, time
import cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import GuardTripped, open_platform
from macro.vision.digits import DigitReader
from macro.vision.screens import ScreenDetector

OUT = os.path.join(ROOT, "cap", "play")
AWAY = (720, 100)
PANEL_CLOSE = (461, 257)
moves = sys.argv[1:]
reader, detector = DigitReader(), ScreenDetector()
def log(t): print(f"[{time.strftime('%H:%M:%S')}] {t}", flush=True)
with open_platform() as p:
    p.guard.arm()
    last_shot, n = 0.0, 0
    last_match = last_yen = time.perf_counter()
    try:
        while True:
            frame = p.grab()
            screen = detector.classify(frame).name
            now = time.perf_counter()
            if screen in ("victory", "defeat"):
                log(f"RESULT {screen}, moves not reached: {moves}")
                cv2.imwrite(os.path.join(OUT, f"result_{screen}.png"), frame)
                break
            if screen == "match":
                last_match = now
            elif now - last_match > 45:
                log(f"giving up: on {screen} for 45 s, not a match")
                cv2.imwrite(os.path.join(OUT, "not_a_match.png"), frame)
                sys.exit(1)
            hud = reader.read_hud(frame) if screen == "match" else {}
            if hud.get("yen") is not None:
                last_yen = now
            elif screen == "match" and now - last_yen > 20:
                log("giving up: can't read the Yen for 20 s, so no move can be made")
                cv2.imwrite(os.path.join(OUT, "no_yen.png"), frame)
                sys.exit(1)
            if now - last_shot >= 10:
                last_shot = now
                n += 1
                cv2.imwrite(os.path.join(OUT, f"s{n:02d}.jpg"), cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA))
                log(f"s{n:02d} {screen} wave {hud.get('wave')}/{hud.get('wave_total')} yen {hud.get('yen')} enemies {hud.get('enemies')} health {hud.get('health')} clock {hud.get('seconds')} moves left {len(moves)}")
            if moves and screen == "match" and hud.get("yen") is not None:
                parts = moves[0].split(":")
                cost = int(parts[3]) if parts[0] == "up" else int(parts[1])
                if hud["yen"] >= cost:
                    before = hud["yen"]
                    if parts[0] == "up":
                        x, y = int(parts[1]), int(parts[2])
                        p.click(x, y); p.sleep(0.3); p.key("t"); p.sleep(0.2)
                        p.click(*PANEL_CLOSE); what = f"upgrade ({x},{y})"
                    else:
                        slot, cost, x, y = map(int, parts)
                        p.key(str(slot)); p.sleep(0.2); p.hover(x, y); p.sleep(0.15); p.click(x, y)
                        what = f"slot {slot} at ({x},{y})"
                    p.hover(*AWAY)
                    p.key("z") if parts[0] != "up" else None
                    p.sleep(0.9)
                    log(f"{what}: yen {before} -> {reader.read_yen(p.grab())}, wanted to spend {cost}")
                    moves.pop(0)
            p.sleep(0.15)
    except GuardTripped as e:
        log(f"paused: {e}")
