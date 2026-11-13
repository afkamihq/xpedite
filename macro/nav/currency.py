"""The last line of defence for "never spend": watch the account's gems and gold.

Allow-lists stop the macro clicking anything that spends, but a mis-click or a bug might
get past them. So gems and gold are read in the lobby at the start of a run and again
each time it comes back. If either has dropped, the run stops at once. Rewards only ever
add to them, so a drop means something was spent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from macro.vision import ocr
from macro.vision.screens import scaled

# The lobby's currency row, level with the hotbar's top, at 1920x1080. Reading the whole
# row works better than a box per currency, because these widths change. Left to right:
# gems, gold, then event currencies that aren't watched. x ranges say which is which.
ROW = (640, 850, 1280, 925)
GEMS_X = (640, 780)
GOLD_X = (787, 950)
PROPER_NUMBER = re.compile(r"^\d{1,3}(,\d{3})*$")


@dataclass
class Balance:
    gems: int | None
    gold: int | None


class SpendingDetected(RuntimeError):
    """Gems or gold went down during a run."""


def read_balance(frame) -> Balance:
    """Gems and gold from a lobby frame. A value that can't be read is None, not a guess:
    OCR misread a tooltip-covered gold as "26h'" once."""
    x0, y0 = scaled(ROW[0], ROW[1])
    x1, y1 = scaled(ROW[2], ROW[3])
    found = {"gems": None, "gold": None}
    for text, x, _ in ocr.find_words(frame, (x0, y0, x1, y1)):
        text = text.strip()
        if not PROPER_NUMBER.match(text):
            continue
        value = int(text.replace(",", ""))
        if scaled(GEMS_X[0], 0)[0] <= x <= scaled(GEMS_X[1], 0)[0]:
            found["gems"] = value
        elif scaled(GOLD_X[0], 0)[0] <= x <= scaled(GOLD_X[1], 0)[0]:
            found["gold"] = value
    return Balance(found["gems"], found["gold"])


class SpendingWatch:
    """Compare against the first reading of a run. Call in the lobby, with the pointer
    away from the hotbar, whose tooltips cover the row."""

    def __init__(self, log=None):
        self.start: Balance | None = None
        self.log = log or (lambda text: None)

    def check(self, frame) -> Balance:
        now = read_balance(frame)
        if self.start is None:
            self.start = now
            self.log(f"balance at the start: {now.gems} gems, {now.gold} gold")
            return now
        for name, before, after in (("gems", self.start.gems, now.gems), ("gold", self.start.gold, now.gold)):
            if before is None:
                continue
            if after is None:
                self.log(f"couldn't read {name} just now")
            elif after < before:
                raise SpendingDetected(f"{name} went from {before} to {after} during this run")
        # Rewards raise the baseline, so a later spend can't hide behind them.
        self.start = Balance(now.gems if now.gems is not None else self.start.gems,
                             now.gold if now.gold is not None else self.start.gold)
        return now
