"""The team: read which units are on the hotbar (hover each slot in the lobby and read its
card), look them up in data/units.yaml, and say how the team compares with a good shape
(2 DPS / 2 support / 2 farms for regular modes, 3 / 2 / 1 for harder ones). It also writes the
team preset the plans use (slot, name, price, placement limit).
"""
from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

import yaml

from macro.control.engine import SLOT_X, read_hotbar_costs
from macro.nav.navigator import Navigator
from macro.vision import ocr

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UNITS = os.path.join(ROOT, "data", "units.yaml")
PRESET = os.path.join(ROOT, "data", "presets", "current_team.yaml")
HOTBAR_Y = 730  # where to hover a slot, in the framed game's pixels
CARD_AREA = (0, 300, 1440, 690)


@dataclass
class Slot:
    slot: int
    name: str | None
    rarity: str = ""
    cost: int | None = None
    role: str | None = None
    limit: int | None = None
    known: bool = False
    note: str = ""


def _simple(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def load_units() -> dict:
    with open(UNITS, encoding="utf-8") as f:
        return yaml.safe_load(f)


def lookup(name: str, units: dict) -> tuple[str | None, dict]:
    best, score = None, 0.0
    for known in units:
        s = SequenceMatcher(None, _simple(known), _simple(name)).ratio()
        if s > score:
            best, score = known, s
    return (best, units[best]) if best and score >= 0.85 else (None, {})


def read_card(frame) -> tuple[str | None, str]:
    """The hovered unit's name and rarity: the name is the line just above "<Rarity> Unit"."""
    words = ocr.find_words(frame, CARD_AREA)
    for text, x, y in words:
        simple = text.replace(" ", "").lower()
        if simple.endswith("unit") and not simple.startswith("select") and len(simple) > 6:
            above = [(t, xx) for t, xx, yy in words if 8 <= y - yy <= 30 and abs(xx - x) < 140]
            if above:
                return " ".join(t for t, _ in sorted(above, key=lambda w: w[1])), text[:-4].strip()
    return None, ""


def read_team(nav: Navigator, log=None) -> list[Slot]:
    """In the lobby: hover each hotbar slot and read its card."""
    log = log or (lambda text: None)
    p = nav.p
    units = load_units()["units"]
    p.hover(720, 300)
    p.sleep(0.6)
    costs = read_hotbar_costs(p.grab())
    team = []
    for slot, x in enumerate(SLOT_X, start=1):
        p.hover(x, HOTBAR_Y)
        p.sleep(1.0)
        name, rarity = read_card(p.grab())
        entry = Slot(slot, name, rarity, costs.get(slot))
        if name:
            known, info = lookup(name, units)
            if known:
                entry.name, entry.known = known, True
                entry.role, entry.limit, entry.note = info.get("role"), info.get("limit"), info.get("note", "")
        log(f"slot {slot}: {entry.name or 'empty or unreadable'}"
            + (f" ({entry.role})" if entry.role else " (not in the unit list)" if name else ""))
        team.append(entry)
    p.hover(720, 300)
    return team


def judge(team: list[Slot], shape: str = "regular") -> list[str]:
    """Advice, in plain words: what the team has against what a good team has."""
    want = load_units()["shapes"][shape]
    have = Counter(s.role for s in team if s.role)
    advice = []
    for role, count in want.items():
        if have.get(role, 0) < count:
            advice.append(f"Fewer {role} units than a good team has ({have.get(role, 0)} of {count}).")
        elif have.get(role, 0) > count:
            advice.append(f"More {role} units than needed ({have.get(role, 0)} of {count}).")
    if not any(s.name and "Stone Alchemist" in s.name for s in team):
        advice.append("No Stone Alchemist: it's cheap, easy to get and pays for the whole match. "
                      "Plans still work without it, more slowly.")
    unknown = [s for s in team if s.name and not s.known]
    for s in unknown:
        advice.append(f"Slot {s.slot}, {s.name}: not in the unit list, so its role is a guess. "
                      "Its wiki page says what it does.")
    if not advice:
        advice.append(f"A good {shape} team: {', '.join(f'{v} {k}' for k, v in want.items())}.")
    return advice


def write_preset(team: list[Slot]):
    """The preset the plans use, from what was read. Keeps anything the old one had that
    wasn't read (upgrade costs)."""
    try:
        with open(PRESET, encoding="utf-8") as f:
            old = (yaml.safe_load(f) or {}).get("slots") or {}
    except OSError:
        old = {}
    slots = {}
    for s in team:
        if not s.name:
            continue
        # Only the same unit keeps what was read before (upgrade costs): a new unit in the slot
        # mustn't inherit the old one's farm flag or trait (11 Nov 2026).
        before = old.get(s.slot) or {}
        entry = dict(before) if before.get("unit") == s.name else {}
        entry["unit"] = s.name
        if s.cost:
            entry["cost"] = s.cost
        if s.limit:
            entry["limit"] = s.limit
        if s.role == "farm":
            entry["farm"] = True
        slots[s.slot] = entry
    os.makedirs(os.path.dirname(PRESET), exist_ok=True)
    with open(PRESET, "w", encoding="utf-8") as f:
        f.write("# Written by the setup from the hotbar (names from each unit's card, prices from the\n"
                "# hotbar, limits from data/units.yaml). Plans only name slots.\n")
        yaml.safe_dump({"slots": slots}, f, sort_keys=False, allow_unicode=True)
