"""Swap one team unit for another in the Units window: equipping only.
  equip.py "Black Heart" "Forbidden Teacher"
  equip.py - "Sovereign (Djinn)"      only equip, into the first empty slot
Roblox in the lobby. The old unit is found in the equipped top row by the name under its tile,
the new one through the window's search. Every click on Unequip/Equip needs the selected unit's
name read back from the panel and the button reading exactly "Unequip"/"Equip": Quick Sell, the
bin, Unequip All and Teams sit on the same row and are never pressed. Pictures go to cap/equip/.
"""
import os
import re
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.platform import open_platform  # noqa: E402
from macro.vision.ocr import find_words, read_text  # noqa: E402

OUT = os.path.join(ROOT, "cap", "equip")
os.makedirs(OUT, exist_ok=True)
SEARCH = (780, 139)
BUTTON = (977, 631)           # Equip / Unequip, the rightmost of the bottom row
BUTTON_BOX = (830, 614, 1125, 650)
PANEL_NAME = (835, 226, 1120, 292)  # "<Rarity> Unit" and the name: lower when a second tag row (Shiny, Limited) shows
TITLE_BOX = (285, 115, 360, 145)
COLX = [279, 386, 492, 598, 705]
AWAY = (1300, 720)
CLOSE = (1162, 130)  # the window's red X


def squash(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def same(a, b):
    return squash(a) == squash(b) or (len(squash(b)) > 6 and squash(b) in squash(a))


def shot(p, name):
    frame = p.grab()
    cv2.imwrite(os.path.join(OUT, f"{name}.png"), frame)
    return frame


def window_open(frame):
    return "unit" in read_text(frame, TITLE_BOX).lower()


def press_button(p, want, unit):
    frame = shot(p, f"before_{want}")
    name = read_text(frame, PANEL_NAME)
    button = read_text(frame, BUTTON_BOX).strip()
    print(f"  panel shows {name!r}, button {button!r}", flush=True)
    if not same(name, unit):
        raise SystemExit(f"the panel shows {name!r}, not {unit!r}: nothing pressed")
    if squash(button) != squash(want):
        raise SystemExit(f"the button reads {button!r}, not {want!r}: nothing pressed")
    p.click(*BUTTON)
    p.sleep(1.0)
    p.hover(*AWAY)
    p.sleep(0.4)
    after = read_text(shot(p, f"after_{want}"), BUTTON_BOX).strip()
    print(f"  button now {after!r}", flush=True)
    return after


def clear_search(p):
    p.click(*SEARCH)
    p.sleep(0.2)
    for _ in range(30):
        p.key("backspace")
    p.sleep(0.6)


def main(old, new):
    with open_platform() as p:
        p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
        p.hover(*AWAY); p.sleep(0.3)
        if not window_open(p.grab()):
            p.key("h"); p.sleep(1.5)
        if not window_open(p.grab()):
            raise SystemExit("the Units window didn't open")
        clear_search(p)
        p.hover(540, 400); p.scroll(-900); p.sleep(1.0); p.hover(*AWAY); p.sleep(0.4)
        if old != "-":  # "-": only equip, into an empty slot
            # The old unit: the equipped top row, by the name under each tile.
            frame = shot(p, "top")
            words = find_words(frame, (270, 250, 820, 275))
            hit = next(((t, x) for t, x, y in words if same(t, old)), None)
            print("top row:", [t for t, _, _ in words], flush=True)
            if hit is None:
                raise SystemExit(f"{old!r} isn't in the equipped row")
            col = min(range(5), key=lambda c: abs(COLX[c] + 52 - hit[1]))
            p.click(COLX[col] + 52, 225); p.sleep(0.3); p.hover(*AWAY); p.sleep(0.5)
            if squash(press_button(p, "Unequip", old)) != "equip":
                raise SystemExit("the unequip didn't take")
        # The new unit, by search (the search doesn't match brackets, so the name before them),
        # then the first tile whose panel reads the name.
        p.click(*SEARCH); p.sleep(0.3)
        p.type_text(new.split("(")[0].strip())
        p.sleep(1.2)
        p.hover(*AWAY); p.sleep(0.3)
        shot(p, "search")
        for row in range(2):
            for col in range(5):
                p.click(COLX[col] + 52, 225 + 106 * row); p.sleep(0.3); p.hover(*AWAY); p.sleep(0.5)
                name = read_text(p.grab(), PANEL_NAME)
                print(f"  tile {row},{col}: {name!r}", flush=True)
                if same(name, new):
                    break
            else:
                continue
            break
        else:
            raise SystemExit(f"no tile for {new!r} in the search")
        if squash(press_button(p, "Equip", new)) != "unequip":
            raise SystemExit("the equip didn't take")
        clear_search(p)
        p.click(*CLOSE); p.sleep(1.0)  # not H: the search box still has the keyboard
        p.hover(720, 300); p.sleep(0.5)
        shot(p, "hotbar")
        print("done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
