"""One Soul Furnace step on the match going on now, by hand (to test a step live, or to rescue a
match whose run stopped). Run the app's run must be stopped first (F3).
  soul_step.py look                 hotbar slots lit / tomes, Souls, wave; saves cap/furnace/souls/look.png
  soul_step.py bin SLOT             drag a hotbar slot into the bin
  soul_step.py random [SPOT_INDEX]  buy one Random Unit and place it (spots: souls.DEFAULT_SPOTS)
  soul_step.py place SLOT [SPOT_INDEX]  place what's in a slot on a spot
  soul_step.py tome NAME            buy an Unbound Tome and use it on the first NAME without Unbound
  soul_step.py cards                every Unit Manager card at the bottom of the list
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps  # noqa: E402
from macro.modes import furnace, souls  # noqa: E402
from macro.nav.navigator import Navigator  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.vision.digits import DigitReader  # noqa: E402


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


OUT = os.path.join(ROOT, "cap", "furnace", "souls")
os.makedirs(OUT, exist_ok=True)
command, args = sys.argv[1], sys.argv[2:]
with open_platform() as p:
    p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    nav = Navigator(p, log=log)
    reader = DigitReader()
    profile = maps.load_profile("soul_furnace")
    plan = furnace.load_paths_plan("paths")
    config = souls.SoulConfig.from_plan(plan)
    forge = furnace.Forge(p, log=log)
    spender = souls.SoulSpender(p, nav, forge, profile, config, log)
    spender.spa_done = True
    p.hover(720, 82)
    p.sleep(0.3)
    frame = p.grab()
    hud = reader.read_hud(frame)
    lit = sorted(souls.lit_slots(frame))
    log(f"wave {hud['wave']}, Yen {hud['yen']}, Souls {hud.get('souls')}; lit slots {lit}; "
        f"tomes in {sorted(souls.tome_slots(frame))}")
    for s in range(1, 11):
        if s not in lit:
            spender.slots.pop(s, None)
    if command == "look":
        cv2.imwrite(os.path.join(OUT, "look.png"), frame)
    elif command == "bin":
        spender.bin_slot(int(args[0]))
    elif command == "random":
        spender.spot_index = int(args[0]) if args else 0
        spender._buy_random()
    elif command == "place":
        slot = int(args[0])
        spender.spot_index = int(args[1]) if len(args) > 1 else 0
        spender.slots[slot] = souls.Slot("extra")
        spender._place_extra(slot)
    elif command == "tome":
        card = furnace.tome_target(p, nav, args[0], log)
        if card is None:
            log(f"no {args[0]} without Unbound")
        else:
            spender._buy_and_use_tome(card, args[0])
    elif command == "cards":
        for card in spender._bottom_cards():
            log(f"{card.name}: x {card.x}, y {card.y}, on {card.on}, priority {card.priority}, "
                f"level {card.level}/{card.top}, maxed {card.maxed}")
        furnace.close_unit_manager(p, nav)
    p.hover(720, 82)
    p.sleep(0.3)
    cv2.imwrite(os.path.join(OUT, f"after_{command}.png"), p.grab())
