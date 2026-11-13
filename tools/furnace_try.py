"""Play the Soul Furnace match Roblox is in now (waiting at "Start Game?") with the map's plan,
to learn from: a picture every 20 s to cap/furnace/, the HUD and the heat bar in the log, until
the results. The Forge is left as it is (switch SPA's auto forge on by hand first).
  furnace_try.py [plan]
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps, plans  # noqa: E402
from macro.control.engine import PlanEngine, read_hotbar_costs  # noqa: E402
from macro.modes import story  # noqa: E402
from macro.nav.navigator import Navigator  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.sched.runner import auto_priorities, slot_roles  # noqa: E402
from macro.vision import ocr  # noqa: E402
from macro.vision.digits import DigitReader  # noqa: E402

OUT = os.path.join(ROOT, "cap", "furnace")
os.makedirs(OUT, exist_ok=True)
HEAT_TEXT = (870, 92, 960, 114)


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


plan_name = sys.argv[1] if len(sys.argv) > 1 else "story"
profile = maps.load_profile("soul_furnace")
plan = plans.load("soul_furnace", plan_name)
roles, priorities = slot_roles(), auto_priorities()
for unit in plan.units:
    unit.farm = roles.get(unit.slot) == "farm"
    unit.auto_upgrade, unit.auto_on_place = True, False
    unit.auto_priority = priorities.get(unit.slot, 6)
steps = [st for st in plan.steps if st["do"] != "upgrade"]
on = {(st["slot"], st["spot"]) for st in steps if st["do"] == "auto"}
rest = [(u.slot, i) for u in plan.units for i in range(len(u.used_spots)) if (u.slot, i) not in on]
rest.sort(key=lambda key: priorities.get(key[0], 6))
plan.steps = steps + [{"do": "auto", "slot": slot, "spot": i} for slot, i in rest]

with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    nav = Navigator(p, log=log)
    reader = DigitReader()
    p.hover(720, 300); p.sleep(0.3)
    costs = read_hotbar_costs(p.grab())
    log(f"costs {costs}")
    started = time.time()
    alignment = maps.go_to_position(p, profile, log=log)
    engine = PlanEngine(p, reader, plan, alignment, costs, log=log)
    if story.start_window_showing(p.grab()):
        hud = reader.read_hud(p.grab())
        engine.tick(hud["yen"], None)
        story.press_start(nav, log)
    last_pic = last_heat = 0
    wave_last = None
    while time.time() - started < 3 * 3600:
        frame = p.grab()
        screen = nav.detector.classify(frame).name
        if screen in story.RESULT_SCREENS:
            log(f"results: {screen}")
            p.sleep(3.0)
            cv2.imwrite(os.path.join(OUT, "results.png"), p.grab())
            break
        now = time.time()
        if now - last_pic > 20:
            last_pic = now
            cv2.imwrite(os.path.join(OUT, f"t{int(now - started):05d}.png"), frame)
        if screen == "match":
            hud = reader.read_hud(frame)
            if now - last_heat > 10:
                last_heat = now
                heat = ocr.read_line(frame, HEAT_TEXT, scale=2.0)
                log(f"wave {hud['wave']} yen {hud['yen']} souls {hud['souls']} candy {hud['candy']} "
                    f"enemies {hud['enemies']} health {hud['health']} clock {hud['seconds']} heat '{heat}'")
            if hud["wave"] is not None and hud["wave"] != wave_last:
                wave_last = hud["wave"]
            engine.tick(hud["yen"], hud["wave"])
        else:
            log(f"screen {screen}")
            if nav.settle(1.5) not in ("match",) + tuple(story.RESULT_SCREENS):
                cv2.imwrite(os.path.join(OUT, f"odd_{int(now - started):05d}.png"), frame)
                nav.go("match", max_steps=3)
        p.sleep(0.25)
    log(f"done after {time.time() - started:.0f} s, {engine.moves_made} moves")
