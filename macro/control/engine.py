"""Carrying out a plan in a match, trusting the game over whatever was typed.

Plans can ask for impossible things, so nothing here assumes they're right:
- More placements than the unit's limit: the game says "Max placement limit reached!", so that
  slot is done, and the plan carries on.
- A spot the game refuses: "You cannot place a unit there!", so it tries a few nearby spots, then
  skips it.
- Upgrade to 9 when the max is 7: the panel says "Maxed", so that unit is done, and the plan
  carries on.
- A step for a unit that never got placed: skipped.

Costs are read from the game too (hotbar prices, the upgrade button), so any team works.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from dataclasses import dataclass

import cv2
import numpy as np

from macro.control.placing import AWAY, on_hud
from macro.control.plans import TARGETING, Plan
from macro.platform import Platform
from macro.vision import ocr
from macro.vision.digits import DigitReader
from macro.vision.screens import scaled

SLOT_X = (502, 587, 674, 762, 850, 937)  # hotbar slots in the framed game's pixels
PRICE_ROW = (744, 772)
TOAST = (440, 60, 1000, 95)
TOAST_TEXT = (500, 62, 940, 92)
TOAST_RED = 0.04  # share of red pixels that may be a warning toast
PANEL_AREA = (0, 240, 480, 640)
PANEL_CLOSE = (461, 257)
# The unit's own Auto Upgrade button (circling arrows, tooltip "Enable Auto Upgrade"), from the
# Priority button's top left. Left click only: right click sets its priority instead. Sell sits
# left of Upgrade, far from here.
AUTO_FROM_PRIORITY = (332, 24)  # Sandbox only; real panels differ, see find_auto_button
OPEN_WAIT = 1.2
NUDGES = ((0, 0), (20, 0), (-20, 0), (0, 20), (0, -20), (35, 35), (-35, -35))
MAX_TARGETING_PRESSES = 8
COST_RECHECK = 30.0  # a price that looks misread is read again this often
UNKNOWN_COST_RETRY = 5.0  # with no readable cost, how often to just try
MAX_FAILED_UPGRADES = 6
AUTO_TRIES = 3  # tries at switching a unit's Auto Upgrade on
AUTO_RETRY_AFTER = 5.0  # seconds between them
# Where Auto Upgrade sits right of the Priority button: Sandbox panels (a Move button follows)
# and real matches (none). Measured on 55 saved panels, 10 Nov 2026.
AUTO_OFFSETS = ((320, 345), (380, 400))


def _digits(text: str) -> int | None:
    found = re.sub(r"\D", "", text)
    return int(found) if found else None


HOTBAR_PRICES = (450, 742, 990, 774)


def _hotbar_prices(frame: np.ndarray, scale: float) -> dict[int, int]:
    x0, y0, x1, y1 = HOTBAR_PRICES
    crop = frame[y0:y1, x0:x1]
    if scale != 1.0:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    result, _ = ocr._get_engine()(crop, use_cls=False)
    found = {}
    for corners, text, _ in result or []:
        middle = x0 + sum(c[0] for c in corners) / 4 / scale
        slot = min(range(6), key=lambda i: abs(SLOT_X[i] - middle)) + 1
        value = _digits(text)
        if value and abs(SLOT_X[slot - 1] - middle) < 40:
            found[slot] = value
    return found


def read_hotbar_costs(frame: np.ndarray) -> dict[int, int]:
    """What each slot costs, from the hotbar. A price that can't be read is left out, and that
    slot is just tried when there's some money. The whole row in one read, twice at different
    sizes (about 2 s; it was 12 reads and 8 s, 11 Nov 2026), and a price counts only when both
    agree: 1,600 once came back as 16001 and held its unit until wave 9."""
    first, second = _hotbar_prices(frame, 1.0), _hotbar_prices(frame, 2.0)
    return {slot: value for slot, value in first.items() if second.get(slot) == value}


def toast_text(frame: np.ndarray) -> str:
    """The red warning at the top of the screen, lower case, or "". Red ground passes the colour
    check on some maps, so the words decide."""
    x0, y0, x1, y1 = TOAST
    crop = frame[y0:y1, x0:x1].astype(int)
    red = (crop[:, :, 2] > 120) & (crop[:, :, 1] < 60) & (crop[:, :, 0] < 60)
    if red.mean() < TOAST_RED:
        return ""
    return ocr.read_line(frame, TOAST_TEXT, scale=1.5).lower()


def _after_yen_sign(frame: np.ndarray, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """box without its first white glyph, the Yen sign. The glyphs are white with a dark outline,
    so each is its own run of columns. The box comes back whole if that can't be seen."""
    x0, y0, x1, y1 = box
    white = (frame[y0:y1, x0:x1].min(axis=2) > 215).sum(axis=0) >= 2
    runs, start = [], None  # each glyph as (first column, one past its last)
    for column, lit in enumerate(np.append(white, False)):
        if lit and start is None:
            start = column
        elif not lit and start is not None:
            if column - start >= 5:  # thinner than that is the edge of the T key, or a comma
                runs.append((start, column))
            start = None
    if len(runs) < 2 or runs[0][1] - runs[0][0] > 16:
        return box
    return x0 + runs[0][1], y0, x1, y1


@dataclass
class PanelRead:
    maxed: bool
    cost: int | None
    level: int | None
    max_level: int | None
    priority: str | None
    row_y: int


def auto_state(tooltip: str) -> str | None:
    """"off" if the tooltip reads Enable Auto Upgrade, "on" for Disable, None if neither: OCR
    garbles it ("enablautuprade"), so the closer of the two wins, if close enough."""
    text = re.sub(r"[^a-z]", "", tooltip.lower())
    if not text:
        return None
    # The first word survives OCR best, even over bright ground ("enableaugae lilco").
    if text.startswith(("decr", "disab")) or ("prior" in text and "hold" in text):
        return "on"
    if text.startswith(("enab", "enbl", "enal")):
        return "off"
    def near(word):
        return max(SequenceMatcher(None, word, text[i:i + len(word)]).ratio()
                   for i in range(max(1, len(text) - len(word) + 1)))
    enable, disable = near("enableautoupgrade"), near("disableautoupgrade")
    # Once on, the button shows its auto-upgrade priority (1, 2, ...) and its tooltip becomes
    # "Decrease Priority (Hold to Disable)" (seen 10 Nov 2026).
    priority = near("decreasepriority")
    if max(enable, disable, priority) < 0.6:
        return None
    if priority >= max(enable, disable):
        return "on"
    return "on" if disable > enable + 0.05 else "off"


def auto_button_lit(frame: np.ndarray, x: int, y: int) -> bool:
    """Off, the Auto Upgrade button is plain grey; on, it turns teal and shows its priority."""
    crop = frame[y - 16:y + 16, x - 16:x + 16].reshape(-1, 3).astype(int)
    b, g, r = crop.mean(axis=0)
    return b - r > 25 and g - r > 10


PANEL_BOX = (20, 240, 480, 575)  # where a unit's panel covers the map


def under_panel(x: int, y: int) -> bool:
    x0, y0, x1, y1 = PANEL_BOX
    return x0 <= x <= x1 and y0 <= y <= y1


def find_auto_button(frame: np.ndarray, row: tuple[int, int]) -> tuple[int, int] | None:
    """The Auto Upgrade button: the plain grey square right of the Upgrade button, at the end of
    the panel's Priority / Sell / Upgrade row (a Move button may follow it in Sandbox).
    Returns its centre."""
    px, py = row
    x0, x1 = px + 300, min(frame.shape[1], px + 470)
    band = frame[py + 4:py + 40, x0:x1].astype(int)
    b, g, r = band[..., 0], band[..., 1], band[..., 2]
    # Its face is ~90 normally but ~50 while that unit's Upgrade is unaffordable (the row dims):
    # a cut-off of 60 missed it then (10 Nov 2026).
    grey = (np.abs(r - g) < 14) & (np.abs(g - b) < 14) & (g > 30) & (g < 190)
    teal = (b - r > 25) & (g - r > 10)  # the button once it's on, showing its priority
    columns = (grey | teal).mean(axis=0) > 0.45
    runs, start = [], None
    for i, on in enumerate(list(columns) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append((start, i))
            start = None
    # A run from the band's left edge is the end of the Upgrade button (grey when it's dimmed).
    runs = [(a, z) for a, z in runs if 28 <= z - a <= 70 and a > 2]
    if not runs:
        return None
    a, z = runs[0]  # the first grey square after Upgrade
    return x0 + (a + z) // 2, py + 22


def find_panel_row(frame: np.ndarray) -> tuple[int, int] | None:
    """A placed unit's panel, found by its blue Priority button and the red Sell beside it, which
    stay put relative to each other whatever unit it is. Returns the blue button's x and y."""
    x0, y0, x1, y1 = PANEL_AREA
    crop = frame[y0:y1, x0:x1].astype(int)
    blue = ((crop[:, :, 0] > 170) & (crop[:, :, 2] < 110)).astype(np.uint8)
    red = ((crop[:, :, 2] > 170) & (crop[:, :, 0] < 90) & (crop[:, :, 1] < 90)).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(blue, connectivity=8)
    for i in range(1, count):
        x, y, w, h = (int(v) for v in stats[i][:4])
        if 70 <= w <= 120 and 20 <= h <= 60:
            beside = red[y:y + h, x + w:x + w + 60]
            if beside.size and beside.mean() > 0.15:
                return x0 + x, y0 + y
    return None


def read_panel(frame: np.ndarray, full: bool = False) -> PanelRead | None:
    """The open unit panel's upgrade button, or None if no panel is open. full also reads its
    level and priority. Each read is about 50 ms, and matches are short on time."""
    found = find_panel_row(frame)
    if found is None:
        return None
    x, y = found
    # Relative to the Priority button: Upgrade starts 188 px right of it. Level, then cost below.
    cost_text = ocr.read_line(frame, (x + 188, y + 6, x + 302, y + 34), scale=2.0)
    maxed = "max" in cost_text.lower()
    if not maxed:
        # The Yen sign gets read as a 3 now and then (4,150 became 34,150 and stalled a match),
        # so the price is read again with the sign cut off.
        cost_text = ocr.read_line(frame, _after_yen_sign(frame, (x + 188, y + 6, x + 302, y + 34)), scale=2.0)
    level, top, priority = None, None, None
    if full:
        match = re.search(r"(\d+)\s*/\s*(\d+)", ocr.read_line(frame, (x + 218, y - 6, x + 302, y + 9), scale=3.0))
        if match:
            level, top = int(match.group(1)), int(match.group(2))
        words = ocr.read_line(frame, (x + 4, y + 10, x + 94, y + 40), scale=2.0).lower()
        priority = next((t for t in TARGETING if t.lower() in words), None)
    return PanelRead(maxed, None if maxed else _digits(cost_text), level, top, priority, y)


@dataclass
class SpotState:
    placed: bool = False
    failed: bool = False
    done: bool = False  # nothing more to upgrade
    level: int = 0
    cost: int | None = None  # the next upgrade's, once read
    targeted: bool = False
    auto: bool = False  # its Auto Upgrade has been switched on
    auto_tries: int = 0
    tried_at: float = 0.0
    failed_upgrades: int = 0


class PlanEngine:
    """Call tick() every frame of a match: it makes at most one move, then returns."""

    def __init__(self, platform: Platform, reader: DigitReader, plan: Plan, alignment, costs: dict[int, int], log=None):
        self.p = platform
        self.reader = reader
        self.plan = plan
        self.alignment = alignment
        self.costs = costs
        self.log = log or (lambda text: None)
        self.states: dict[tuple[int, int], SpotState] = {}
        self.full: set[int] = set()
        self.queue = list(plan.steps)
        self.moves_made = 0
        self.finishing_noted = False
        self._quiet_at: dict[str, float] = {}

    def state(self, slot: int, spot: int) -> SpotState:
        return self.states.setdefault((slot, spot), SpotState())

    # ------------------------------------------------------------- choosing the next move
    def _skip(self, step: dict) -> str | None:
        """Why a step will never happen now, or None if it still can."""
        unit = self.plan.unit(step["slot"])
        state = self.state(step["slot"], step["spot"])
        if step["do"] == "place":
            if step["slot"] in self.full:
                return f"slot {step['slot']} is at the game's placement limit"
            if state.placed:
                return "already placed"
            if state.failed:
                return "that spot was refused"
            return None
        if state.failed or (not state.placed and step["slot"] in self.full):
            return "that unit never got placed"
        if step["do"] == "auto":
            if state.auto:
                return "already on"
            if state.auto_tries >= AUTO_TRIES:
                return f"Auto Upgrade couldn't be switched on in {AUTO_TRIES} tries"
            return None
        if unit.auto_upgrade:
            return "it upgrades itself"
        if state.done:
            return "already at its top level"
        if unit.upgrade_to is not None and state.level >= unit.upgrade_to:
            state.done = True
            return f"reached the plan's upgrade {unit.upgrade_to}"
        return None

    def _finishing_steps(self) -> list[dict]:
        """Once the order is used up: one more upgrade each, by priority, until all are done."""
        steps = []
        for unit in self.plan.by_priority():
            for spot in range(len(unit.used_spots)):
                state = self.state(unit.slot, spot)
                wanted = (unit.upgrade_to is None or state.level < unit.upgrade_to) and not unit.auto_upgrade
                if state.placed and not state.done and wanted:
                    steps.append({"do": "upgrade", "slot": unit.slot, "spot": spot})
        return steps

    def next_step(self, wave: int | None) -> dict | None:
        while True:
            for index, step in enumerate(self.queue):
                why = self._skip(step)
                if why:
                    if why not in ("already placed", "already at its top level", "it upgrades itself", "already on"):
                        self.log(f"skipped slot {step['slot']} #{step['spot'] + 1} {step['do']}: {why}")
                    self.queue.pop(index)
                    break
                unit = self.plan.unit(step["slot"])
                if wave is not None and wave < unit.from_wave:
                    continue  # not its wave yet: the rest of the order can go ahead
                if step["do"] in ("upgrade", "auto") and not self.state(step["slot"], step["spot"]).placed:
                    continue  # its placement is still waiting
                return step
            else:
                if self.queue:
                    self._quiet(f"waiting: next is {self.queue[0]}, held back for its wave or placement")
                    return None  # all held back for now
                more = self._finishing_steps()
                if not more:
                    return None
                if not self.finishing_noted:
                    self.finishing_noted = True
                    self.log("the build order is finished; upgrading what's left")
                self.queue = more

    @property
    def finished(self) -> bool:
        return not self.queue and not self._finishing_steps()

    # -------------------------------------------------------------------------- moves
    def tick(self, yen: int | None, wave: int | None) -> bool:
        """Maybe make a move. True if it did something."""
        if yen is None:
            return False
        step = self.next_step(wave)
        if step is None:
            return False
        state = self.state(step["slot"], step["spot"])
        now = self.p.now()
        if step["do"] == "auto":
            if now - state.tried_at < AUTO_RETRY_AFTER:
                return False
            state.tried_at = now
            self._switch_on_auto(step, state, f"slot {step['slot']} #{step['spot'] + 1}")
            self.moves_made += 1
            return True
        if step["do"] == "place":
            cost = self.costs.get(step["slot"])
            if cost is None and now - state.tried_at < UNKNOWN_COST_RETRY:
                return False
            if cost is not None and yen < cost and not self._doubt_cost(cost, state, yen, now):
                if self._farm_meanwhile(yen, wave, cost):
                    return True
                self._quiet(f"slot {step['slot']} #{step['spot'] + 1}: waiting for {cost} Yen to place, have {yen}")
                return False
            state.tried_at = now
            self._place(step, state, yen)
        else:
            if state.cost is not None and yen < state.cost and not self._doubt_cost(state.cost, state, yen, now):
                if self._farm_meanwhile(yen, wave, state.cost):
                    return True
                self._quiet(f"slot {step['slot']} #{step['spot'] + 1}: waiting for {state.cost} Yen, have {yen}")
                return False
            if state.cost is None and state.failed_upgrades and now - state.tried_at < UNKNOWN_COST_RETRY:
                return False
            state.tried_at = now
            self._upgrade(step, state, yen)
        self.moves_made += 1
        return True

    def _farm_meanwhile(self, yen: int, wave: int | None, waiting_for: int | None = None) -> bool:
        """While the next move waits for Yen, a farm placement further down the order that the
        Yen covers now goes ahead: a farm placed sooner pays every wave after (user, 10 Nov:
        900 Yen sat idle at wave 2 while an Atom was saved for). Not when the waiting move is
        closer than the farm's own price: Ramen Guy bought at 1,213 Yen held the first Atom
        (1,250) back a wave (10 Nov)."""
        for step in self.queue:
            if step["do"] != "place":
                continue
            unit = self.plan.unit(step["slot"])
            if not unit.farm or self._skip(step) or (wave is not None and wave < unit.from_wave):
                continue
            cost = self.costs.get(step["slot"])
            if cost is None or yen < cost:
                continue
            if waiting_for is not None and waiting_for - yen < cost:
                return False
            state = self.state(step["slot"], step["spot"])
            state.tried_at = self.p.now()
            self.log(f"slot {step['slot']} #{step['spot'] + 1}: placing this farm early, while the next move waits")
            self._place(step, state, yen)
            self.moves_made += 1
            return True
        return False

    def _doubt_cost(self, cost: int, state: SpotState, yen: int, now: float) -> bool:
        """A price never keeps a match waiting on one reading: if it would be affordable without
        its first or last digit (a misread Yen sign, or a stray mark), the move is tried every so
        often anyway. Too little Yen just makes the game refuse."""
        text = str(cost)
        if len(text) < 5 or yen < min(int(text[1:]), int(text[:-1])) or now - state.tried_at < COST_RECHECK:
            return False
        self.log(f"trying despite a price of {cost}, which may have been misread")
        return True

    def _quiet(self, text: str, frame=None):
        """Things that aren't moves, logged at most every 10 s each, with a picture to look at."""
        now = self.p.now()
        if now - self._quiet_at.get(text[:40], -99) < 10:
            return
        self._quiet_at[text[:40]] = now
        self.log(text)
        if frame is not None:
            import os
            from macro.vision.screens import ROOT
            folder = os.path.join(ROOT, "logs", "engine")
            os.makedirs(folder, exist_ok=True)
            cv2.imwrite(os.path.join(folder, f"{int(now)}.png"), frame)

    def _point(self, step: dict) -> tuple[int, int]:
        return self.alignment.to_live(*self.plan.point(step))

    def _place(self, step: dict, state: SpotState, yen: int):
        slot, name = step["slot"], f"slot {step['slot']} #{step['spot'] + 1}"
        base_x, base_y = self._point(step)
        self.p.key(str(slot))
        self.p.sleep(0.2)
        for ox, oy in NUDGES:
            x, y = base_x + ox, base_y + oy
            if on_hud(x, y):
                continue
            self.p.hover(x, y)
            self.p.sleep(0.15)
            self.p.click(x, y)
            self.p.sleep(0.15)
            words = toast_text(self.p.grab())
            if "limit" in words:
                self.full.add(slot)
                state.failed = True
                self.log(f"{name}: the game's placement limit is reached, so moving on")
                break
            if "cannot" in words:
                self.log(f"{name}: the game refused ({x}, {y})")
                # The toast has to be gone before the next try can be judged: one still
                # showing made a spot that took the unit look refused, and the unit was
                # then looked for in the wrong place all match.
                end = self.p.now() + 3.0
                while self.p.now() < end:
                    self.p.sleep(0.25)
                    if "cannot" not in toast_text(self.p.grab()):
                        break
                continue
            if "yen" in words or "afford" in words or "enough" in words:
                self.log(f"{name}: not enough Yen yet")
                break
            state.placed = True
            where = f"({x}, {y})" + (" near its spot" if (ox, oy) != (0, 0) else "")
            self.log(f"{name} placed at {where}, Yen was {yen}")
            # A nudged unit has to be found there for its upgrades.
            self.plan.unit(slot).spots[step["spot"]] = list(self._to_reference(x, y)) if (ox, oy) != (0, 0) \
                else self.plan.unit(slot).spots[step["spot"]]
            break
        else:
            state.failed = True
            self.log(f"{name}: no spot near there was allowed, so skipping it")
        self.p.hover(*scaled(*AWAY))
        self.p.key("z")  # lets go of the unit if it's still held
        self.p.sleep(0.25)
        unit = self.plan.unit(slot)
        if state.placed and unit.auto_upgrade and unit.auto_on_place and not state.auto:
            self._switch_on_auto(step, state, name)
        if state.placed and unit.targeting and not state.targeted:
            state.targeted = True
            panel = self._open_panel(step)
            if panel is None:
                self.log(f"{name}: couldn't open its panel to set its priority")
                self.p.hover(*scaled(*AWAY))
            else:
                self._set_targeting(unit.targeting, panel, name)
                self._close_panel()

    def _switch_on_auto(self, step: dict, state: SpotState, name: str):
        """Open its panel and press Auto Upgrade, once it has been confirmed as that button.
        A try that can't confirm the button or the result is counted, and the step comes back
        a few seconds later, up to AUTO_TRIES; an already-on button is never pressed."""
        state.auto_tries += 1
        if self._open_panel(step) is None:
            self.log(f"{name}: couldn't open its panel to switch on Auto Upgrade")
            self.p.hover(*scaled(*AWAY))
            return
        found = find_panel_row(self.p.grab())
        if found is None:
            self.log(f"{name}: its panel closed before Auto Upgrade could be pressed")
            return
        button = find_auto_button(self.p.grab(), found)
        if button is None:
            self._quiet(f"{name}: no Auto Upgrade button on its panel, picture saved", self.p.grab())
            self.log(f"{name}: no Auto Upgrade button found on its panel")
            self._close_panel()
            return
        x, y = button
        offset = x - found[0]
        if not (AUTO_OFFSETS[0][0] <= offset <= AUTO_OFFSETS[0][1] or AUTO_OFFSETS[1][0] <= offset <= AUTO_OFFSETS[1][1]):
            self._quiet(f"{name}: a grey square at ({x}, {y}) isn't where Auto Upgrade sits, so it wasn't "
                        "clicked; picture saved", self.p.grab())
            self.log(f"{name}: Auto Upgrade not switched on: its button wasn't where expected")
            self._close_panel()
            return
        # Off, the button is plain grey; on, it turns teal and shows its priority. That colour is
        # the state: the tooltip under it ("Enable Auto Upgrade") reads too poorly over bright
        # maps to rely on (10 Nov 2026), so it is only a second opinion. An already-on button is
        # never clicked, as a click would only change its priority.
        frame = self.p.grab()
        if auto_button_lit(frame, x, y):
            state.auto = True
            self.log(f"{name}: Auto Upgrade was already on")
            self._close_panel()
            return
        self.p.hover(x, y)
        self.p.sleep(0.15)
        self.p.click(x, y)
        self.p.hover(*scaled(*AWAY))  # off the button: hovering changes its colour
        end = self.p.now() + 1.5
        lit = False
        while self.p.now() < end and not lit:
            self.p.sleep(0.2)
            after_frame = self.p.grab()
            lit = auto_button_lit(after_frame, x, y)
        level = read_panel(after_frame, full=True)
        upgraded = f", already at {level.level}/{level.max_level}" if level and level.level is not None else ""
        if lit or (level and level.maxed):
            state.auto = True
            priority = max(1, min(6, self.plan.unit(step["slot"]).auto_priority))
            # Each further click lowers its priority by one: 1, 2, ... 6.
            for _ in range(priority - 1):
                self.p.hover(x, y)
                self.p.sleep(0.12)
                self.p.click(x, y)
                self.p.sleep(0.25)
            self.p.hover(*scaled(*AWAY))
            self.log(f"{name}: Auto Upgrade on, priority {priority} (its button turned teal{upgraded})")
        else:
            self._quiet(f"{name}: clicked Auto Upgrade but its button didn't turn teal{upgraded}; picture saved",
                        after_frame)
            self.log(f"{name}: Auto Upgrade NOT confirmed")
        self._close_panel()

    @staticmethod
    def _auto_tooltip(frame: np.ndarray, x: int, y: int) -> str:
        """The words of the tooltip that shows under-right of the Auto Upgrade button."""
        return ocr.read_line(frame, (x - 10, y + 2, x + 290, y + 40), 2.0).lower()

    def _to_reference(self, x: int, y: int) -> tuple[int, int]:
        inverse = cv2.invertAffineTransform(self.alignment.matrix)
        px, py = inverse @ np.array([x, y, 1.0])
        return round(float(px)), round(float(py))

    def _open_panel(self, step: dict) -> PanelRead | None:
        x, y = self._point(step)
        # A unit can stand where panels open (bottom left). With a panel already open, a click
        # there would land on that panel, maybe on Sell: close it first, and refuse if it stays.
        if find_panel_row(self.p.grab()) is not None:
            self._close_panel()
            self.p.sleep(0.2)
            if under_panel(x, y) and find_panel_row(self.p.grab()) is not None:
                self.log(f"a panel won't close, so ({x}, {y}) under it isn't clicked")
                return None
        self.p.click(x, y)
        # Off the panel at once: a pointer resting on its Sell button changes Sell's colour,
        # and the panel then can't be found (East Town and Hollow Desert, 10 Nov 2026).
        self.p.hover(*scaled(*AWAY))
        end = self.p.now() + OPEN_WAIT
        while self.p.now() < end:
            frame = self.p.grab()
            if find_panel_row(frame) is not None:
                self.p.sleep(0.1)
                return read_panel(self.p.grab(), full=True)
            self.p.sleep(0.05)
        return None

    def _close_panel(self):
        self.p.click(*PANEL_CLOSE)
        self.p.sleep(0.1)
        self.p.hover(*scaled(*AWAY))

    def _upgrade(self, step: dict, state: SpotState, yen: int):
        name = f"slot {step['slot']} #{step['spot'] + 1}"
        unit = self.plan.unit(step["slot"])
        panel = self._open_panel(step)
        if panel is None:
            state.failed_upgrades += 1
            self.log(f"{name}: clicking it didn't open its panel ({state.failed_upgrades} of {MAX_FAILED_UPGRADES})")
            self._quiet(f"{name}: no panel after a click at {self._point(step)}, picture saved", self.p.grab())
            self.p.hover(*scaled(*AWAY))
            if state.failed_upgrades >= MAX_FAILED_UPGRADES:
                state.done = True
                self.log(f"{name}: giving up on upgrading it")
            return
        state.failed_upgrades = 0
        if panel.level is not None:
            state.level = panel.level
        if panel.maxed:
            state.done = True
            self.log(f"{name}: the game says it's maxed" + (f", under the {unit.upgrade_to} asked for"
                                                            if unit.upgrade_to else ""))
            self._close_panel()
            return
        if unit.upgrade_to is not None and state.level >= unit.upgrade_to:
            state.done = True
            self.log(f"{name}: at the plan's upgrade {unit.upgrade_to}")
            self._close_panel()
            return
        state.cost = panel.cost
        if panel.cost is not None and yen < panel.cost:
            self._close_panel()  # comes back when the Yen covers it
            self._quiet(f"{name}: next upgrade costs {panel.cost}, Yen {yen}")
            return
        self.p.key("t")
        # The new price can take a moment to show, and T is pressed once only, so look a few times.
        after = None
        for _ in range(4):
            self.p.sleep(0.2)
            after = read_panel(self.p.grab())
            if after is not None and (after.maxed or after.cost != panel.cost):
                break
        self._close_panel()
        changed = after is not None and (after.maxed or after.cost != panel.cost)
        if changed:
            state.level += 1
            state.cost = after.cost
            state.done = after.maxed
            self.log(f"{name} upgraded to {state.level}, next costs "
                     + ("nothing, it's maxed" if after.maxed else f"{after.cost}") + f", Yen was {yen}")
            state.failed_upgrades = 0
            # One upgrade per step: a step that's used up leaves the queue.
            if self.queue and self.queue[0] is step:
                self.queue.pop(0)
            elif step in self.queue:
                self.queue.remove(step)
        else:
            state.failed_upgrades += 1
            state.cost = None
            self._quiet(f"{name}: T made no change it could see (before {panel}, after {after})", self.p.grab())
            if state.failed_upgrades >= MAX_FAILED_UPGRADES:
                state.done = True
                self.log(f"{name}: T did nothing {MAX_FAILED_UPGRADES} times, so giving up on it")

    def _set_targeting(self, wanted: str, panel: PanelRead, name: str):
        current = panel.priority
        for _ in range(MAX_TARGETING_PRESSES):
            if current == wanted:
                self.log(f"{name}: priority set to {wanted}")
                return
            self.p.key("r")
            self.p.sleep(0.3)
            after = read_panel(self.p.grab(), full=True)
            current = after.priority if after else None
        self.log(f"{name}: couldn't set priority to {wanted}, so left it as it was")


