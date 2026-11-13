"""Placing units: slot key, move, click, then check the Yen really dropped.

Clicks land on the 3D world, so a click in the wrong spot could hit a HUD button. Unit
Manager has a Sell All, for one. So points over the HUD are refused before anything is
pressed, and the pointer is moved off the new unit before reading, because its tooltip
covers the Yen.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import cv2

from macro.platform import Platform
from macro.vision.digits import DigitReader
from macro.vision.screens import ROOT, SCALE, scaled

# Parts of the screen that are HUD in a match, at 1920x1080. Never click the world here.
HUD_AREAS = ((0, 0, 1920, 90),  # top bar and pills
             (0, 850, 1920, 1080),  # Yen, hotbar, level bar
             (1600, 500, 1920, 760),  # stage name, Unit Manager, Auto Play, Sandbox Controls
             (0, 930, 230, 1080),  # Units, Items and Quests icons
             (0, 300, 110, 600))  # Pinned Objectives
# Event matches (Soul Furnace) add the Forge button above the hotbar (with a margin: a placement
# at its corner opened the Forge, 11 Nov 2026), the Heat bars and the Start Game window. Only
# while such a match is played (EXTRA_AREAS is set by the mode), as Story plans use that ground.
EVENT_AREAS = ((830, 790, 1090, 870), (650, 120, 1290, 225), (750, 145, 1170, 370))
EXTRA_AREAS: list = []
AWAY = (960, 110)  # somewhere to rest the pointer, clear of the HUD and of units
AFTER_KEY = 0.3
AFTER_HOVER = 0.25
YEN_WAIT = 2.0
COST_SHARE = 0.9  # the drop must cover this much of the unit's cost
SPOT_HALF = 30  # pixels each way around a placement, to see if a unit appeared
SPOT_CHANGED = 12.0  # mean change that means something appeared there
SPIRAL = ((0, 0), (24, 0), (-24, 0), (0, 24), (0, -24), (24, 24), (-24, -24), (48, 0), (-48, 0), (0, 48), (0, -48))


def on_hud(x: int, y: int) -> bool:
    """Whether a point in game pixels is over the HUD, or off the picture."""
    from macro.vision.screens import GAME_HEIGHT, GAME_WIDTH

    if not (0 <= x < GAME_WIDTH and 0 <= y < GAME_HEIGHT):
        return True
    return any(a * SCALE <= x < c * SCALE and b * SCALE <= y < d * SCALE
               for a, b, c, d in (*HUD_AREAS, *EXTRA_AREAS))


@dataclass
class Placed:
    ok: bool
    slot: int
    at: tuple[int, int] | None = None
    yen_before: int | None = None
    yen_after: int | None = None
    tries: list = field(default_factory=list)
    why: str = ""


class Placer:
    def __init__(self, platform: Platform, reader: DigitReader | None = None, log=None):
        self.p = platform
        self.reader = reader or DigitReader()
        self.log = log or (lambda text: None)

    def _yen(self, timeout: float = 3.0) -> int | None:
        """Yen once it has settled: the number counts down over a moment after a purchase,
        so two readings in a row must agree. None if it never does."""
        end = time.perf_counter() + timeout
        last, frame = None, None
        while time.perf_counter() < end:
            frame = self.p.grab()
            value = self.reader.read_yen(frame)
            if value is not None and value == last:
                return value
            last = value
            self.p.sleep(0.15)
        if frame is not None:
            folder = os.path.join(ROOT, "logs")
            os.makedirs(folder, exist_ok=True)
            cv2.imwrite(os.path.join(folder, f"unread-yen-{time.strftime('%H%M%S')}.png"), frame)
        return None

    def _spot(self, frame, x: int, y: int):
        half = SPOT_HALF
        return frame[max(y - half, 0):y + half, max(x - half, 0):x + half].copy()

    def _try_once(self, slot: int, x: int, y: int, before: int, cost: int | None) -> int | None:
        """One attempt. Returns the new Yen if the unit went down, else None.

        Any drop isn't proof: Auto-Upgrade spends Yen too. So the drop must cover the unit's
        cost, or if income might be hiding that, the spot itself must have changed."""
        spot_before = self._spot(self.p.grab(), x, y)
        self.p.key(str(slot))
        self.p.sleep(AFTER_KEY)
        self.p.hover(x, y)
        self.p.sleep(AFTER_HOVER)
        self.p.click(x, y)
        self.p.hover(*scaled(*AWAY))
        end = time.perf_counter() + YEN_WAIT
        lowest = None
        while time.perf_counter() < end:
            frame = self.p.grab()
            now = self.reader.read_yen(frame)
            if now is not None and now < before:
                lowest = now if lowest is None else min(lowest, now)
                if cost is None or before - now >= cost * COST_SHARE:
                    return now
            self.p.sleep(0.05)
        if lowest is not None:
            changed = float(cv2.absdiff(spot_before, self._spot(self.p.grab(), x, y)).mean())
            self.log(f"Yen fell by {before - lowest}, under the {cost} cost; the spot changed by {changed:.1f}")
            if changed >= SPOT_CHANGED:
                return lowest
        return None

    def place(self, slot: int, x: int, y: int, cost: int | None = None) -> Placed:
        """Place the unit in a hotbar slot near a point on screen. Spots that fail are
        nudged in a small spiral, and each one is checked against the HUD."""
        self.p.hover(*scaled(*AWAY))
        before = self._yen()
        if before is None:
            return Placed(False, slot, why="couldn't read the Yen before placing")
        result = Placed(False, slot, yen_before=before)
        for ox, oy in SPIRAL:
            at_x, at_y = x + ox, y + oy
            if on_hud(at_x, at_y):
                continue
            result.tries.append((at_x, at_y))
            now = self._try_once(slot, at_x, at_y, before, cost)
            if now is not None:
                result.ok, result.at, result.yen_after = True, (at_x, at_y), now
                self.log(f"slot {slot} placed at ({at_x}, {at_y}): Yen {before} -> {now}")
                return result
            # It may still be holding the unit. Z cancels, so the next try starts clean.
            self.p.key("z")
            self.p.sleep(0.2)
        result.why = f"Yen never dropped after {len(result.tries)} spots"
        self.log(f"slot {slot} NOT placed near ({x}, {y}): {result.why}")
        return result


def run_layout(placer: Placer, steps: list[dict], alignment, log=None) -> list[Placed]:
    """Place a layout's steps in order, mapping each point from the reference picture to
    where it is on screen now."""
    results = []
    for step in steps:
        x, y = alignment.to_live(*step["at"])
        results.append(placer.place(int(step["slot"]), x, y))
    return results
