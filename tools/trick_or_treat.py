"""Trick or Treat by itself, for testing: walk to a door, knock whenever it lets you, close
Treats, and play Tricks with our own team and our plan for the map.
  .venv-win/Scripts/python.exe tools/trick_or_treat.py [knocks]      (Roblox in the lobby)
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps, plans  # noqa: E402
from macro.control.engine import read_hotbar_costs  # noqa: E402
from macro.modes import story, trick  # noqa: E402
from macro.nav.navigator import Navigator  # noqa: E402
from macro.nav.navigator import NavError  # noqa: E402
from macro.nav.recovery import Recovery, RunStopped  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.sched.runner import auto_priorities, folder_of, playable, slot_roles  # noqa: E402
from macro.vision.digits import DigitReader  # noqa: E402

OUT = os.path.join(ROOT, "cap", "tt")
os.makedirs(OUT, exist_ok=True)
knocks = int(sys.argv[1]) if len(sys.argv) > 1 else 20


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}".encode("ascii", "replace").decode(), flush=True)


def load_plan(map_name):
    folder = folder_of(map_name)
    plan = plans.load(folder, "story")
    roles, priorities = slot_roles(), auto_priorities()
    for unit in plan.units:
        unit.farm = roles.get(unit.slot) == "farm"
    # the same auto mode as the runner: place in plan order, the game upgrades by priority
    steps = [st for st in plan.steps if st["do"] != "upgrade"]
    on = {(st["slot"], st["spot"]) for st in steps if st["do"] == "auto"}
    rest = sorted(((u.slot, i) for u in plan.units for i in range(len(u.used_spots)) if (u.slot, i) not in on),
                  key=lambda k: priorities.get(k[0], 6))
    plan.steps = steps + [{"do": "auto", "slot": s, "spot": i} for s, i in rest]
    for unit in plan.units:
        unit.auto_upgrade, unit.auto_on_place = True, False
        unit.auto_priority = priorities.get(unit.slot, 6)
    return maps.load_profile(folder), plan


with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    nav = Navigator(p, log=lambda t: log(f"  {t}"))
    recovery = Recovery(p, nav, may_restart=False, log=lambda t: log(f"  RECOVERY: {t}"))
    reader = DigitReader()
    nav.go("lobby", on_lost=recovery)
    p.hover(720, 300); p.sleep(0.5)
    costs = read_hotbar_costs(p.grab())
    log(f"unit prices: {costs}")
    tally = {"treat": 0, "trick": 0, "won": 0, "lost": 0}
    at_door = False

    def back_to_lobby():
        """After a disconnect or a failed teleport: Recovery presses Reconnect; if that doesn't
        bring the lobby back, Roblox is started again."""
        try:
            nav.go("lobby", on_lost=recovery)
        except Exception as problem:  # noqa: BLE001
            log(f"recovery couldn't reach the lobby ({problem}); restarting Roblox")
            p.guard.disarm(); p.close_game()
            log(f"restart: {p.make_game_ready(timeout=120) or 'ok'}")
            p.guard.arm(); recovery.wait_until_in_game(); nav.go("lobby", on_lost=recovery)

    for n in range(knocks):
        try:
            # At the door, its prompt comes back about 40 s after a knock: wait there for it.
            # Each door has its own cooldown (about 10 min), so go round to the next ready one.
            found, soonest = trick.go_to_door(p, log, start=n)
            if not found:
                wait = min(600, (soonest or 60) + 5)
                log(f"no door ready anywhere; the soonest is in {soonest} s, waiting {wait} s")
                end = time.time() + wait
                while time.time() < end:
                    p.sleep(5)
                continue
            outcome = trick.knock(nav, log)
            tally[outcome] = tally.get(outcome, 0) + 1
            log(f"knock {n + 1}: {outcome}  {tally}")
            if outcome != "trick":
                continue
            at_door = False
            if not trick.wait_for_match(nav, 90):
                log("no match after the trick's teleport"); nav.go("lobby", on_lost=recovery); continue
            frame = p.grab()
            cv2.imwrite(os.path.join(OUT, f"trick_{time.strftime('%H%M%S')}.png"), frame)
            map_name, act = trick.stage_of_trick(frame)
            log(f"trick stage: {map_name} act {act}")
            own = trick.use_own_team(p, log)
            cv2.imwrite(os.path.join(OUT, f"trick_team_{time.strftime('%H%M%S')}.png"), p.grab())
            if not own or not map_name or not playable(map_name):
                log(f"can't play it with our plan (own team {own}, map {map_name}): Auto Play instead")
                p.click(1352, 519); p.sleep(1.0)
                story.press_start(nav, log) if story.start_window_showing(p.grab()) else None
                end = time.time() + 600
                while time.time() < end and nav.detector.classify(p.grab()).name not in story.RESULT_SCREENS:
                    p.sleep(3)
                outcome = nav.detector.classify(p.grab()).name
            else:
                profile, plan = load_plan(map_name)
                result = story.play_match(nav, reader, profile, plan, costs, on_lost=recovery, log=log)
                outcome = result.outcome
            tally["won" if outcome == "victory" else "lost"] += 1
            p.sleep(3); cv2.imwrite(os.path.join(OUT, f"trick_result_{time.strftime('%H%M%S')}.png"), p.grab())
            log(f"TRICK RESULT: {outcome}  {tally}")
            screen = nav.settle()
            if screen in story.RESULT_SCREENS:
                story.leave_results(nav, screen, on_lost=recovery)
            nav.go("lobby", on_lost=recovery)
        except (trick.NoDoor, NavError, RunStopped) as problem:
            log(f"trouble: {problem}")
            at_door = False
            back_to_lobby()
    log(f"done: {tally}")
