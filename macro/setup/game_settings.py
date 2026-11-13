"""The game's own settings that the macro relies on, checked and set through the game's
Settings window: type a setting's name into its search box, check the first result is that
setting (by its words), read its toggle (green tick = on, red cross = off) and click it only
if it's wrong, then look again to confirm.

Never press Ctrl with the game in front: the search box is cleared with Backspace.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

import numpy as np

from macro.nav.navigator import NavError, Navigator
from macro.vision import ocr
from macro.vision.screens import SCALE

# (what to search, the setting's name as the game shows it, wanted state, why)
WANTED = (
    ("auto vote", "Auto Vote Start", False, "the macro starts each match itself, once its camera is set"),
    ("auto skip", "Auto Skip Waves", True, "faster matches"),
    # "auto-upgrade" typed returns nothing (the hyphen), and "upgrade" lists it second, right column.
    ("upgrade", "Auto-Upgrade Placed Units", False, "upgrades follow the plan, unit by unit"),
    ("select unit", "Select Unit on Placement", False, "a panel popping up hides the map"),
    ("pinned", "Display Pinned Objectives", False, "its tracker covers unit panels"),
    ("match end", "Show Match End Rewards", False, "pop-ups cover the results window"),
    ("auto retry", "Auto Retry", False, "the macro chooses what comes next"),
    ("low detail", "Low Detail Mode", True, "the same picture for everyone, and lighter"),
    ("camera shake", "Camera Shake", False, "a steady view to place by"),
    ("auto abilit", "Auto Abilities on Placement", True, "abilities like Atom's nuke fire by themselves"),
)
RESULTS = (600, 253, 1560, 560)  # 1920x1080: where search results list, in two columns
TOGGLE_X = (1035, 1516)          # each column's toggle, 1920x1080
COLUMN_SPLIT = 1080              # a name left of this is in the left column


@dataclass
class SettingState:
    name: str
    wanted: bool
    found: bool | None  # None: couldn't find or read it
    changed: bool = False
    why: str = ""


def _toggle_state(frame: np.ndarray, point) -> bool | None:
    x, y = point  # the framed game's pixels
    crop = frame[y - 12:y + 12, x - 12:x + 12].reshape(-1, 3).astype(int)
    b, g, r = crop.mean(axis=0)
    if g > 110 and g - r > 50 and g - b > 50:
        return True   # green tick (155, 82 red)
    if r > 110 and r - g > 60 and r - b > 60:
        return False  # red cross (150, 54 green)
    return None


def _similar(a: str, b: str) -> float:
    a, b = re.sub(r"[^a-z]", "", a.lower()), re.sub(r"[^a-z]", "", b.lower())
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _find_row(frame, name: str):
    """The toggle (game pixels) on the row of the result whose title matches, or None."""
    box = tuple(round(v * SCALE) for v in RESULTS)
    best, score = None, 0.0
    for text, x, y in ocr.find_words(frame, box):
        s = _similar(text, name)
        if s > score:
            best, score = (x, y), s
    if best is None or score < 0.75:
        return None
    x, y = best
    column = 0 if x < COLUMN_SPLIT * SCALE else 1
    return round(TOGGLE_X[column] * SCALE), y + round(6 * SCALE / 0.75)


def search(nav: Navigator, words: str):
    p = nav.p
    p.click(*nav.detector.button("game_settings", "search"))
    p.sleep(0.2)
    for _ in range(24):
        p.key("backspace", hold=0.02)
    p.type_text(words)
    p.sleep(0.9)


def check_and_fix(nav: Navigator, fix: bool = True, log=None, on_lost=None) -> list[SettingState]:
    log = log or (lambda text: None)
    nav.go("game_settings", on_lost=on_lost)
    p = nav.p
    states = []
    for words, name, wanted, why in WANTED:
        search(nav, words)
        frame = p.grab()
        toggle = _find_row(frame, name)
        state = SettingState(name, wanted, None, why=why)
        if toggle is None:
            log(f"setting {name!r}: not found by searching {words!r}")
            states.append(state)
            continue
        state.found = _toggle_state(frame, toggle)
        if fix and state.found is not None and state.found != wanted:
            p.hover(*toggle)
            p.sleep(0.1)
            p.click(*toggle)
            p.sleep(0.6)
            now = _toggle_state(p.grab(), toggle)
            state.changed = now == wanted
            log(f"setting {name!r}: {'on' if state.found else 'off'} -> {'on' if now else 'off'}"
                + ("" if state.changed else " (didn't change)"))
            state.found = now
        else:
            log(f"setting {name!r}: {'on' if state.found else 'off' if state.found is False else 'unreadable'}")
        states.append(state)
    search(nav, "")
    nav.press("game_settings", "close")
    if nav.wait_for("lobby", 6.0) is None:
        raise NavError(f"the Settings window didn't close; on {nav.settle()}")
    return states
