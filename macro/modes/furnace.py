"""The Halloween event's Soul Furnace, Infinite Hard (11 Nov 2026).

Endless waves on one map, three paths ending in the furnace. What makes it work:
- The whole layout is placed BEFORE Start Game, as phantom units: the game builds each as the
  Yen comes, in order. Start moves the character and lets the camera zoom further out, so
  anything aimed after Start would need a second reference; before it, the view is the map's
  set one (data/maps/soul_furnace/).
- The Soul Forge (in-match shop, priced in Souls) has an auto forge per recipe: right-click its
  circular button for a priority menu (off, 1-6). SPA Boost goes on auto from the start; after
  SPA_TARGET boosts it goes off and Souls go to the user's next choice (Unbound Tomes or Random
  Units). Boosts are counted from the Heat bar, which fills with every Soul collected.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field

from macro.control import maps
from macro.control.engine import PlanEngine
from macro.vision import ocr

FORGE_BUTTON = (720, 623)
GAME_RESULTS = (720, 617)  # under the Forge button once a run is lost and its results were closed
FORGE_CLOSE = (1132, 165)
FORGE_TITLE = (296, 150, 420, 184)
# The Self recipes' row with the Forge scrolled to the top: (Buy button, auto forge button).
RECIPES = {"dmg": ((410, 476), (495, 476)), "rng": ((595, 476), (680, 476)),
           "spa": ((780, 476), (864, 476)), "random_unit": ((965, 476), (1049, 476))}
# The priority menu a right-click on an auto forge button opens, from that button: off, then 1-3
# on the first row and 4-6 on the second.
MENU = {0: (-104, 59), 1: (-34, 59), 2: (36, 59), 3: (106, 59), 4: (-104, 107), 5: (-34, 107), 6: (36, 107)}
HEAT_TEXT = (870, 92, 960, 114)
AUTO_PLAY = (1352, 519)
AUTO_PLAY_TEXT = (1310, 505, 1428, 534)  # "Auto Play", or "Auto Playing" while the game plays itself  # "<souls in this bar> / <bar size>"
SPA_PRICE = 20
SPA_TARGET = 50


def bar_size(n: int) -> int:
    """Souls the (n+1)th Heat bar takes (wiki: 100 x 1.35^n, rounded up)."""
    return math.ceil(100 * 1.35 ** n - 1e-9)


def souls_collected(progress: int, size: int) -> int | None:
    """Every Soul collected this match, from the Heat bar's "progress / size": the size says how
    many bars are already full."""
    for n in range(40):
        if bar_size(n) == size:
            return sum(bar_size(k) for k in range(n)) + progress
        if bar_size(n) > size:
            break
    return None


def read_heat(frame) -> tuple[int, int] | None:
    text = ocr.read_line(frame, HEAT_TEXT, scale=2.0).replace(" ", "")
    found = re.fullmatch(r"(\d+)/(\d+)", text.replace(",", ""))
    return (int(found.group(1)), int(found.group(2))) if found else None


def game_auto_play_off(p, log) -> bool:
    """The game's own Auto Play stays on through Repeat Stage (seen 11 Nov 2026): make sure it's off,
    as it places units of its own. True once the button reads "Auto Play"."""
    for _ in range(3):
        text = ocr.read_line(p.grab(), AUTO_PLAY_TEXT, scale=2.0).lower().replace(" ", "")
        if "autoplaying" not in text:
            return "autoplay" in text
        log("the game's Auto Play is on: switching it off")
        p.click(*AUTO_PLAY)
        p.sleep(0.8)
        p.hover(720, 82)
    return False


def auto_forge_on(frame, x: int, y: int) -> bool:
    """A recipe's auto forge button is teal (with its priority number) when on, grey when off."""
    patch = frame[y - 10:y + 10, x - 14:x + 14].astype(int)
    return (patch[:, :, 1] - patch[:, :, 2]).mean() > 20


def forge_open(frame) -> bool:
    return "forge" in ocr.read_line(frame, FORGE_TITLE, scale=2.0).lower()


@dataclass
class Forge:
    """Opening the Soul Forge and setting a recipe's auto forge. Every action checks the window
    is really open first: its buttons sit over the map, where a stray click would place nothing
    but could select a unit."""
    p: object
    log: object = None
    auto: dict = field(default_factory=dict)  # recipe -> priority, or 0 for off
    nav: object = None  # when set, nothing is clicked unless the match is on screen

    def _log(self, text):
        if self.log:
            self.log(text)

    def open(self) -> bool:
        p = self.p
        for _ in range(3):
            if self.nav is not None and self.nav.detector.classify(p.grab()).name != "match":
                # 11 Nov 2026, 16:07: the Defeat came mid-step and the Forge click hit the results'
                # View Party; the run then wandered off to the lobby instead of Retry.
                self._log("the match isn't on screen: no Forge")
                return False
            p.click(*FORGE_BUTTON)
            end = time.monotonic() + 2.0
            while time.monotonic() < end:
                p.sleep(0.25)
                if forge_open(p.grab()):
                    # The list may still be scrolled to the tomes from the last visit: every
                    # click here assumes the top (Self recipes' row).
                    p.hover(720, 450)
                    p.scroll(-2000)
                    p.sleep(0.4)
                    return True
        self._log("the Soul Forge didn't open")
        return False

    def close(self):
        p = self.p
        if forge_open(p.grab()):
            p.click(*FORGE_CLOSE)
            p.sleep(0.6)
        p.hover(720, 82)

    def set_auto(self, recipe: str, priority: int) -> bool:
        """Auto forge for a recipe: priority 1-6, or 0 for off. Through the right-click menu, as a
        left click only cycles the priority."""
        if not self.open():
            return False
        p = self.p
        _, (x, y) = RECIPES[recipe]
        p.click(x, y, "right")
        p.sleep(0.5)
        dx, dy = MENU[priority]
        p.click(x + dx, y + dy)
        p.sleep(0.4)
        self.auto[recipe] = priority
        self._log(f"Soul Forge: {recipe} auto forge {'off' if priority == 0 else f'on, priority {priority}'}")
        self.close()
        return True

    def set_autos(self, wanted: dict) -> bool:
        """Several recipes' auto forge in one visit (recipe -> priority, 0 for off). The settings
        last through Repeat Stage (11 Nov 2026: Random Unit's from one run took Souls in the next),
        so every run sets all of them."""
        if not self.open():
            return False
        import os
        import cv2
        p = self.p
        folder = os.path.join(maps.ROOT, "cap", "furnace", "forge_set")
        os.makedirs(folder, exist_ok=True)
        cv2.imwrite(os.path.join(folder, "0_open.png"), p.grab())
        for n, (recipe, priority) in enumerate(wanted.items(), 1):
            _, (x, y) = RECIPES[recipe]
            p.click(x, y, "right")
            p.sleep(0.45)
            cv2.imwrite(os.path.join(folder, f"{n}a_{recipe}_menu.png"), p.grab())
            dx, dy = MENU[priority]
            p.click(x + dx, y + dy)
            p.sleep(0.35)
            cv2.imwrite(os.path.join(folder, f"{n}b_{recipe}_set.png"), p.grab())
            self.auto[recipe] = priority
        p.hover(720, 640)
        p.sleep(0.3)
        frame = p.grab()
        states = {r: auto_forge_on(frame, *RECIPES[r][1]) for r in wanted}
        self._log("Soul Forge auto: " + ", ".join(f"{r} {'off' if v == 0 else v}" for r, v in wanted.items())
                  + "; buttons read " + ", ".join(f"{r} {'on' if on else 'off'}" for r, on in states.items()))
        self.close()
        return all(states[r] == (v > 0) for r, v in wanted.items())

    def buy(self, recipe: str, times: int = 1) -> bool:
        if not self.open():
            return False
        (x, y), _ = RECIPES[recipe]
        for _ in range(times):
            self.p.click(x, y)
            self.p.sleep(0.3)
        self.close()
        return True


# ------------------------------------------------------------------ placing from several views
NUDGES = ((0, 0), (20, 0), (-20, 0), (0, 20), (0, -20), (28, 28), (-28, -28), (28, -28), (-28, 28))
BACK = {"w": "s", "s": "w", "a": "d", "d": "a"}


def load_paths_plan(name: str = "paths") -> dict:
    import os
    import yaml
    with open(os.path.join(maps.MAPS, "soul_furnace", "layouts", f"{name}.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def place_one(p, alignment, slot: int, point, log) -> bool:
    """One phantom placement at a point of a view's reference picture, nudged a little if the
    game refuses the exact spot. Before Start the Yen doesn't drop, so the toast is the only
    sign: "cannot" (refused), "limit" (that unit is all placed)."""
    from macro.control import placing
    from macro.control.engine import toast_text
    x0, y0 = alignment.to_live(*point)
    p.key("0" if slot == 10 else str(slot))
    p.sleep(0.2)
    try:
        for ox, oy in NUDGES:
            x, y = x0 + ox, y0 + oy
            if placing.on_hud(x, y):
                continue
            p.hover(x, y)
            p.sleep(0.12)
            p.click(x, y)
            p.sleep(0.15)
            words = toast_text(p.grab())
            if "limit" in words:
                log(f"slot {slot}: placement limit reached")
                return False
            if "cannot" in words:
                end = p.now() + 3.0
                while p.now() < end and "cannot" in toast_text(p.grab()):
                    p.sleep(0.2)
                continue
            log(f"slot {slot} queued at ({x}, {y})" + (" (nudged)" if (ox, oy) != (0, 0) else ""))
            return True
        log(f"slot {slot}: no spot near {tuple(point)} was allowed")
        return False
    finally:
        p.hover(720, 82)
        p.key("z")
        p.sleep(0.2)


def place_from_views(p, plan: dict, home: maps.MapProfile, log, record: list | None = None) -> int:
    """Every step of a several-view plan, in order: walk to each step's view (home, then that
    view's route), confirm it against its picture, queue the phantom. Ends back home. `record`
    gets (slot, view, point) for each placement queued (the tome's map fallback uses them)."""
    from macro.control import placing
    placing.EXTRA_AREAS[:] = placing.EVENT_AREAS
    views = {"home": home}
    for key, folder in (plan.get("views") or {}).items():
        views[key] = maps.load_profile(folder)
    here, alignment, placed = "home", None, 0
    queue = list(plan.get("steps") or [])
    try:
        alignment = _home(p, home, log, views)
        while queue:
            step = queue.pop(0)
            view = step.get("view", "home")
            if view not in views:
                log(f"no view {view!r}: skipped {step}")
                continue
            if view != here:
                if here != "home":
                    for key, seconds in reversed(views[here].route):
                        p.key(BACK[key], hold=seconds)
                        p.sleep(0.2)
                    alignment = _home(p, home, log, views)
                    here = "home"
                if view != "home":
                    maps.walk_route(p, views[view])
                    try:
                        alignment = maps.correct_position(p, views[view], log, search=False)
                        here = view
                    except maps.PositionError as error:
                        log(f"couldn't confirm the {view} view ({error}); back home")
                        for key, seconds in reversed(views[view].route):
                            p.key(BACK[key], hold=seconds)
                            p.sleep(0.2)
                        alignment, here = _home(p, home, log, views), "home"
                        if not step.get("_retried"):
                            # Once more at the end (16:49: a miss left the bottom path's Atom out).
                            queue.append(dict(step, _retried=True))
                        continue
            if place_one(p, alignment, int(step["place"]), step["at"], log):
                placed += 1
                if record is not None:
                    record.append((int(step["place"]), view, tuple(step["at"])))
        if here != "home":
            for key, seconds in reversed(views[here].route):
                p.key(BACK[key], hold=seconds)
                p.sleep(0.2)
            try:
                _home(p, home, log, views)
            except maps.PositionError as error:
                # Every phantom is queued: home is only needed again around wave 40 (Random
                # Units), and looked for then. Not worth the run (12 Nov 2026, 01:12).
                log(f"couldn't get back home after the last phantom ({error}); carrying on")
    finally:
        placing.EXTRA_AREAS[:] = []
    log(f"{placed} phantom placements queued over {len(views)} views")
    return placed


def _home(p, home, log, views: dict | None = None):
    """Back to the home position: by its picture; else by any view's picture that matches (walk
    to that view's spot, then back along its route); else the look-all-round search."""
    try:
        return maps.correct_position(p, home, log, search=False)
    except maps.PositionError:
        pass
    import cv2
    from macro.vision import align
    if views is None:
        plan = load_paths_plan()
        views = {k: maps.load_profile(v) for k, v in (plan.get("views") or {}).items()}
    live = align.features(p.grab())
    best = None
    for name, profile in views.items():
        if name == "home":
            continue
        result = align.align(align.features(cv2.imread(profile.reference_path)), live)
        if result is not None and abs(result.scale - 1) < 0.1 and (best is None or result.inliers > best[1].inliers):
            best = (profile, result)
    if best is not None and best[1].inliers >= 60:
        profile = best[0]
        log(f"lost: the view looks like {profile.name}'s ({best[1].inliers} features), going home from there")
        try:
            maps.correct_position(p, profile, log, search=False)
        except maps.PositionError:
            pass
        for key, seconds in reversed(profile.route):
            p.key(BACK[key], hold=seconds)
            p.sleep(0.2)
        try:
            return maps.correct_position(p, home, log, search=False)
        except maps.PositionError:
            pass
    return maps.find_position(p, home, log)


def place_phantoms(p, engine: PlanEngine, log) -> int:
    """Every placement in the plan, before Start, in order. Before Start the Yen doesn't drop, so
    each becomes a phantom the game builds when the Yen covers it."""
    from macro.control import placing
    placing.EXTRA_AREAS[:] = placing.EVENT_AREAS
    placed = 0
    for step in engine.plan.steps:
        if step["do"] != "place":
            continue
        state = engine.state(step["slot"], step["spot"])
        if state.placed or state.failed:
            continue
        engine._place(step, state, 0)
        if state.placed:
            placed += 1
    log(f"{placed} phantom placements queued")
    return placed


def set_position(p, profile: maps.MapProfile, log):
    return maps.go_to_position(p, profile, log=log)


# ------------------------------------------------------------------ Unit Manager's Auto Upgrade
# The Unit Manager (F) lists every unit placed, phantoms included, in the order they were placed:
# each card has its name, "Upgrade n/m", the next upgrade's price ("Maxed" at the top), Targeting,
# a sell bin and an "Auto Upgrade" button (grey off, teal on) with a priority box right of it
# once on. A click on the box (or on that spot of a grey button) steps the cycle
# off -> 1 -> 2 ... -> 6 -> off. Above the list, "Auto Upgrading" and "Phantom Placing" toggles:
# teal "Active", red "Paused". Game settings this relies on (Settings > Units, already set): Strict
# Auto-Upgrade Priority (1 is upgraded fully before 2), Strict Phantom Placement (built in the order
# queued), Prioritize Phantom Placement (phantoms are built before any auto upgrade).
UM_PANEL = (950, 150, 1440, 750)  # the list of placed units, left of nothing but the map
UM_SCROLL_AT = (1190, 450)
UM_OFF_CARDS = (1200, 790)  # a hover spot where no tooltip hides a button
PHANTOM_TOGGLE = (1317, 111)
AUTO_TOGGLE = (1202, 111)  # "Auto Upgrading", left of Phantom Placing
# Scrolling 15 moves the list ~102 px; rows are ~283 px apart and a card is ~150 px tall, so 75
# (~510 px) shows every card whole on some page (the last ones once the list stops at its end).
UM_PAGE_SCROLL = 75
BOX_FROM_TEAL = 73  # a teal button's text centre -> its priority box's centre
TEAL_FROM_GREY = -17  # a grey button's text centre -> the same button's once teal (it narrows)
_PRIORITY_DIGITS: dict = {}


def _auto_upgrade_on(frame, x: int, y: int) -> bool:
    """A card's Auto Upgrade button is teal once on, grey while off."""
    patch = frame[y - 8:y + 8, x - 55:x + 45].astype(int)
    return (patch[:, :, 1] - patch[:, :, 2]).mean() > 8


def _simple(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def read_priority(frame, x: int, y: int) -> int | None:
    """The number (1-6) in the box right of a teal Auto Upgrade button whose text centre is
    (x, y), by its picture (OCR misses a lone digit). Templates: data/digits/priority/."""
    import os
    import cv2
    if not _PRIORITY_DIGITS:
        folder = os.path.join(os.path.dirname(maps.MAPS), "digits", "priority")
        for n in range(1, 7):
            _PRIORITY_DIGITS[n] = cv2.imread(os.path.join(folder, f"{n}.png"), cv2.IMREAD_GRAYSCALE)
    cx = x + BOX_FROM_TEAL
    window = cv2.cvtColor(frame[y - 16:y + 16, cx - 20:cx + 22], cv2.COLOR_BGR2GRAY)
    best, score = None, 0.0
    for n, template in _PRIORITY_DIGITS.items():
        if template is None or window.shape[0] < template.shape[0] or window.shape[1] < template.shape[1]:
            continue
        value = float(cv2.matchTemplate(window, template, cv2.TM_CCOEFF_NORMED).max())
        if value > score:
            best, score = n, value
    return best if score > 0.8 else None


@dataclass
class Card:
    name: str  # simplified: "stonealchemist", "atomtotality", ...
    x: int  # the Auto Upgrade button's text centre as it is now
    y: int
    on: bool
    priority: int | None  # 1-6 when on (None if unread), 0 when off
    level: int | None = None  # "Upgrade n/m"
    top: int | None = None
    maxed: bool = False

    @property
    def box(self) -> tuple[int, int]:
        """Where a click steps the priority cycle (the box when on, the same spot on the grey
        button when off)."""
        return (self.x if self.on else self.x + TEAL_FROM_GREY) + BOX_FROM_TEAL, self.y


def read_cards(frame, words) -> list[Card]:
    """Every card whose Auto Upgrade button shows in the panel, from one OCR read of it."""
    cards = []
    for text, x, y in words:
        if _simple(text) != "autoupgrade" or y > UM_PANEL[3] - 10:
            continue
        near = [(t, nx, ny) for t, nx, ny in words if abs(nx - x) < 75 and 0 < y - ny < 150]
        name = _simple(" ".join(t for t, nx, ny in sorted(near, key=lambda w: (w[2] // 6, w[1]))
                                if 100 < y - ny < 150))
        level = top = None
        for t, nx, ny in near:
            found = re.search(r"upgrade\s*(\d+)\s*/\s*(\d+)", t.lower())
            if found and 80 < y - ny < 115:
                level, top = int(found.group(1)), int(found.group(2))
        maxed = any(_simple(t) == "maxed" and 60 < y - ny < 100 for t, nx, ny in near) or (
            level is not None and level == top)
        on = _auto_upgrade_on(frame, x, y)
        cards.append(Card(name, x, y, on, (read_priority(frame, x, y) if on else 0), level, top, maxed))
    return cards


# The game's Auto Upgrade priority per unit (1 is spent on first, and fully, before 2). User, 11 Nov
# 2026: Stone Alchemist and 8th Sword 1, Atom 2 (much stronger than Sovereign), Sovereign last.
UPGRADE_ORDER = {"alchemist": 1, "8thsword": 1, "atom": 2, "blade": 3, "teacher": 4, "sovereign": 5}
DEFAULT_PRIORITY = 4


ROLE_PRIORITY = {"farm": 1, "dps": 3, "support": 5}  # for a unit the layout's priorities don't name
_ROLES: dict = {}


def unit_role(name: str) -> str | None:
    """A card's role from data/units.yaml (farm, dps, support), matched on the simplified name, so
    any user's team gets a sensible order without naming every unit (12 Nov 2026)."""
    import os
    import yaml
    if not _ROLES:
        try:
            with open(os.path.join(os.path.dirname(maps.MAPS), "units.yaml"), encoding="utf-8") as f:
                units = (yaml.safe_load(f) or {}).get("units") or {}
            for unit, info in units.items():
                _ROLES[_simple(unit)] = (info or {}).get("role")
        except OSError:
            _ROLES["-"] = None
    best = max((k for k in _ROLES if k and (name.startswith(k) or k.startswith(name))), key=len, default=None)
    return _ROLES.get(best) if best else None


def wanted_priority(name: str, order: dict | None = None) -> int:
    named = next((v for k, v in (order or UPGRADE_ORDER).items() if k in name), None)
    if named is not None:
        return named
    return ROLE_PRIORITY.get(unit_role(name) or "", DEFAULT_PRIORITY)


def open_unit_manager(p, nav, log=None) -> bool:
    if nav.detector.classify(p.grab()).name == "unit_manager":
        return True
    p.key("f")
    if nav.wait_for("unit_manager", 3.0) is None:
        if log:
            log("the Unit Manager didn't open")
        return False
    return True


def close_unit_manager(p, nav):
    if nav.detector.classify(p.grab()).name == "unit_manager":
        p.key("f")
        p.sleep(0.4)
    p.hover(720, 82)


def _toggle_paused(frame, x: int, y: int) -> bool:
    patch = frame[y - 8:y + 8, x - 40:x + 40].astype(int)
    return (patch[:, :, 2] - patch[:, :, 1]).mean() > 40  # red "Paused"; teal "Active"


def set_auto_upgrading(p, nav, active: bool, log) -> bool:
    """The Unit Manager's Auto Upgrading toggle (the game keeps it from one match to the next:
    an Expedition run that paused it to keep Yen for the shop left every later Soul Furnace run
    without upgrades, all lost at wave 9 on 15 Nov 2026). Leaves the Unit Manager open."""
    if not open_unit_manager(p, nav, log):
        return False
    for _ in range(3):
        p.hover(*UM_OFF_CARDS)
        p.sleep(0.2)
        if _toggle_paused(p.grab(), *AUTO_TOGGLE) != active:
            return True
        log(f"Auto Upgrading was {'paused' if active else 'active'}: switching it")
        p.click(*AUTO_TOGGLE)
        p.sleep(0.5)
    log("the Auto Upgrading toggle didn't change")
    return False


def set_phantom_placing(p, nav, active: bool, log) -> bool:
    """The Unit Manager's Phantom Placing toggle: Active builds queued phantoms as the Yen comes,
    Paused leaves the Yen to Auto Upgrade. Leaves the Unit Manager open."""
    if not open_unit_manager(p, nav, log):
        return False
    for _ in range(3):
        p.hover(*UM_OFF_CARDS)
        p.sleep(0.2)
        if _toggle_paused(p.grab(), *PHANTOM_TOGGLE) != active:
            log(f"Phantom Placing {'active' if active else 'paused'}")
            return True
        p.click(*PHANTOM_TOGGLE)
        p.sleep(0.5)
    log("the Phantom Placing toggle didn't change")
    return False


def _top_of_list(p):
    p.hover(*UM_SCROLL_AT)
    p.scroll(-2000)
    p.sleep(0.5)


def _step_box(p, at: tuple, steps: int, was_on: bool = True):
    """Step a priority box `steps` times: the first click arrives and hovers like any (Roblox reads
    hover), the rest press again where the pointer already is (0.2 s each instead of 0.5 s). On a
    grey button the first click turns it on and only then does the box appear where the pointer
    is: a second click before that lands on the teal button and turns it off again (seen live,
    11 Nov 2026: two Atoms left off), so it waits for the box first."""
    if steps <= 0:
        return
    p.click(*at)
    if not was_on and steps > 1:
        p.sleep(0.5)
    for _ in range(steps - 1):
        p.sleep(0.14)
        p.button_down("left")
        try:
            p.sleep(0.05)
        finally:
            p.button_up("left")
    p.sleep(0.2)


def set_auto_upgrades(p, nav, log, order: dict | None = None, pages: int = 8) -> tuple[int, int]:
    """Auto Upgrade on, at its UPGRADE_ORDER priority, for every card in the Unit Manager (phantoms
    included, so this is done once, before Start). Reads each page once, steps each card's
    priority box as many times as it needs (no reading in between: the cycle is known), checks the
    boxes by their pictures, then scrolls. Maxed cards are left alone (their button can't come on).
    Returns (cards changed, cards already right). Leaves the Unit Manager open."""
    set_auto_upgrades.problems = 0
    if not open_unit_manager(p, nav, log):
        set_auto_upgrades.problems = 1  # nothing was checked
        return 0, 0
    _top_of_list(p)
    changed = right = 0
    seen: set = set()
    frame = p.grab()
    for _ in range(pages):
        p.hover(*UM_OFF_CARDS)
        p.sleep(0.25)
        frame = p.grab()
        cards = [c for c in read_cards(frame, ocr.find_words(frame, UM_PANEL)) if c.name]
        acted = []
        for card in cards:
            if card.maxed:
                continue
            target = wanted_priority(card.name, order)
            if card.on and card.priority is None:
                log(f"couldn't read {card.name}'s priority")
                set_auto_upgrades.problems += 1
                continue
            steps = (target - card.priority) % 7
            if steps == 0:
                right += 1
                continue
            _step_box(p, card.box, steps, was_on=card.on)
            acted.append(card)
            changed += 1
        for attempt in range(2):
            if not acted:
                break
            p.hover(*UM_OFF_CARDS)
            p.sleep(0.3)
            frame = p.grab()
            wrong = []
            for card in acted:
                x = card.x if card.on else card.x + TEAL_FROM_GREY
                got = read_priority(frame, x, card.y) if _auto_upgrade_on(frame, x, card.y) else 0
                target = wanted_priority(card.name, order)
                if got != target:
                    if attempt == 0 and got is not None:
                        _step_box(p, (x + BOX_FROM_TEAL, card.y), (target - got) % 7, was_on=got > 0)
                        wrong.append(card)
                    else:
                        log(f"{card.name} reads priority {got}, wanted {target}")
                        set_auto_upgrades.problems += 1
            acted = wrong
        before = frame[UM_PANEL[1]:UM_PANEL[3], UM_PANEL[0]:UM_PANEL[2]]
        p.hover(*UM_SCROLL_AT)
        p.scroll(UM_PAGE_SCROLL)
        p.sleep(0.5)
        p.hover(*UM_OFF_CARDS)
        p.sleep(0.2)
        after = p.grab()[UM_PANEL[1]:UM_PANEL[3], UM_PANEL[0]:UM_PANEL[2]]
        if abs(after.astype(int) - before.astype(int)).mean() < 2:  # the end of the list
            break
    shown = order or UPGRADE_ORDER
    log(f"Unit Manager: Auto Upgrade set on {changed} cards ({right} reads already right); priorities "
        + ", ".join(f"{k} {v}" for k, v in sorted(shown.items(), key=lambda kv: kv[1])))
    return changed, right


def farm_levels(p, nav, log) -> list[int]:
    """The Stone Alchemists' upgrade levels, from the top of the Unit Manager (placed first, so
    their cards come first). Leaves the Unit Manager open."""
    if not open_unit_manager(p, nav, log):
        return []
    _top_of_list(p)
    p.hover(*UM_OFF_CARDS)
    p.sleep(0.25)
    frame = p.grab()
    cards = read_cards(frame, ocr.find_words(frame, UM_PANEL))
    return [(c.top if c.maxed and c.top else c.level) for c in cards
            if "alchemist" in c.name and (c.level is not None or c.maxed)]


# ------------------------------------------------------------------ Mythic Traits: tomes (11 Nov 2026)
# The Forge's last row (scrolled to its end) sells tomes for Souls: Draconic, Forsaken, Primordial
# 100, Unbound 250. A tome takes the first free hotbar slot (7-10), so it can't be bought while
# Random Units fill them. To use one: click it in the hotbar ("Apply Unbound Tome: select a unit"),
# open the Unit Manager, click the unit's card portrait; the unit's panel opens showing the new
# trait (it replaces the old one). Unbound (+350% damage, -5% SPA, +10% range) on an Atom: 155,820
# damage, DPS ~496k/s against ~12k/s on a First Blade. User: all three Atoms can take one.
TOME_BUY = {"draconic": (410, 599), "forsaken": (595, 599), "primordial": (780, 599), "unbound": (965, 599)}
TOME_PRICE = {"draconic": 100, "forsaken": 100, "primordial": 100, "unbound": 250}
HOTBAR_EXTRA = {7: 850, 8: 937, 9: 1024, 10: 1111}  # the slots Forge items land in
HOTBAR_Y = 730
HOTBAR_WORDS = (810, 690, 1160, 775)
APPLY_BANNER = (520, 500, 920, 545)  # "Apply Unbound Tome" / "Select a unit to apply ..."
UNIT_PANEL_TAGS = (40, 252, 440, 282)  # the selected unit's trait and element tags
UNIT_PANEL_CLOSE = (460, 259)
PORTRAIT_FROM_GREY = (-37, -147)  # a card's portrait from its grey Auto Upgrade text centre


def tome_slot(frame) -> int | None:
    """The hotbar slot (1-10) holding a tome, read off its "Tome" label. Any slot: once our own
    slots are binned, a tome lands in the first free one."""
    from macro.modes import souls
    found = souls.tome_slots(frame)
    return min(found) if found else None


def applying(frame) -> bool:
    """The "Apply ... Tome / Select a unit to apply ..." banner is up."""
    return "apply" in ocr.read_text(frame, APPLY_BANNER, scale=1.5).lower()


def buy_tome(forge: "Forge", kind: str = "unbound") -> bool:
    """Buy one tome from the Forge's Mythic Traits row. True once the hotbar shows it: its "Tome"
    label, or a slot that lit up (11 Nov 2026, 15:30: the label wasn't read, so a second tome
    was bought for nobody)."""
    from macro.modes import souls
    p = forge.p
    p.hover(720, 82)
    p.sleep(0.2)
    lit_before = souls.lit_slots(p.grab())
    if not forge.open():
        return False
    p.hover(720, 450)
    p.scroll(600)  # to the end of the list, where the tomes are
    p.sleep(0.7)
    p.click(*TOME_BUY[kind])
    p.sleep(0.8)
    forge.close()
    end = p.now() + 2.5
    while True:
        p.hover(720, 82)
        p.sleep(0.3)
        frame = p.grab()
        if tome_slot(frame) is not None or souls.lit_slots(frame) - lit_before:
            return True
        if p.now() > end:
            return False


CARD_SCROLL = 30  # finer than a page: every card's portrait is clear of the header on some step
PORTRAIT_SAFE = (200, 690)  # portrait y inside the list (higher, the header hides the card)


def _shift(previous: list, now: list, last: float) -> float:
    """How far the list moved up between two steps (px): the median move of cards read on both
    (same name, same column). Cards repeat every row, so a picture match can lock onto the wrong
    row; names can't. Falls back to the last step's move."""
    moves = sorted(a.y - b.y for a in previous for b in now
                   if a.name and a.name == b.name and abs(a.x - b.x) < 25 and 60 < a.y - b.y < 500)
    return float(moves[len(moves) // 2]) if moves else last


def unit_cards(p, nav, name: str, log, steps: int = 30, visit=None) -> list[Card]:
    """Every card whose name holds `name`, top to bottom, each with the scroll step (from the top
    of the list) at which its portrait is well inside the list. Cards aren't all one height
    (Atoms have an ability row under them), so the list's movement is measured from the cards.
    visit(card), if given, is called for each card the moment its portrait is clear, with the
    list where it was read; True from it ends the scan there (the list is left as it is).
    Leaves the Unit Manager open at the top otherwise."""
    if not open_unit_manager(p, nav, log):
        return []
    _top_of_list(p)
    found = []  # (column x, content y, card, portrait clear of the header)
    offset, last_move, previous = 0.0, 250.0, []
    for step in range(steps):
        p.hover(*UM_OFF_CARDS)
        p.sleep(0.25)
        frame = p.grab()
        cards = read_cards(frame, ocr.find_words(frame, UM_PANEL))
        if step:
            last_move = _shift(previous, cards, last_move)
            offset += last_move
        for card in cards:
            if name not in card.name:
                continue
            card.page = step
            safe = PORTRAIT_SAFE[0] <= card.y + PORTRAIT_FROM_GREY[1] <= PORTRAIT_SAFE[1]
            grey_x = card.x if not card.on else card.x - TEAL_FROM_GREY
            content_y = card.y + offset
            same = next((i for i, (gx, cy, c, ok) in enumerate(found)
                         if abs(gx - grey_x) < 40 and abs(cy - content_y) < 80), None)
            fresh = False
            if same is None:
                found.append((grey_x, content_y, card, safe))
                fresh = safe
            elif safe and not found[same][3]:
                found[same] = (grey_x, content_y, card, safe)
                fresh = True
            if fresh and visit is not None:
                card.index = sum(1 for f in found if f[3]) - 1
                if visit(card):
                    found.sort(key=lambda f: (f[1], f[0]))
                    return [c for _, _, c, ok in found if ok]
        previous = cards
        before = frame[UM_PANEL[1]:UM_PANEL[3], UM_PANEL[0]:UM_PANEL[2]]
        p.hover(*UM_SCROLL_AT)
        p.scroll(CARD_SCROLL)
        p.sleep(0.45)
        p.hover(*UM_OFF_CARDS)
        p.sleep(0.2)
        after = p.grab()[UM_PANEL[1]:UM_PANEL[3], UM_PANEL[0]:UM_PANEL[2]]
        if abs(after.astype(int) - before.astype(int)).mean() < 2:  # the end of the list
            break
    _top_of_list(p)
    found.sort(key=lambda f: (f[1], f[0]))
    return [card for _, _, card, safe in found if safe]


def _go_to_page(p, page: int):
    """Back to the scroll step a card was read at (unit_cards: CARD_SCROLL each)."""
    _top_of_list(p)
    for _ in range(page):
        p.hover(*UM_SCROLL_AT)
        p.scroll(CARD_SCROLL)
        p.sleep(0.45)
    p.hover(*UM_OFF_CARDS)
    p.sleep(0.2)


def _portrait(card) -> tuple[int, int]:
    grey_x = card.x if not card.on else card.x - TEAL_FROM_GREY
    return grey_x + PORTRAIT_FROM_GREY[0], card.y + PORTRAIT_FROM_GREY[1]


def card_traits(p, nav, card, log) -> str:
    """The tags on a unit's panel (trait, element, archetype), opened from its card and closed
    again. Leaves the Unit Manager open."""
    _go_to_page(p, getattr(card, "page", 0))
    p.click(*_portrait(card))
    p.sleep(0.9)
    tags = ocr.read_text(p.grab(), UNIT_PANEL_TAGS, scale=1.5).lower()
    p.click(*UNIT_PANEL_CLOSE)
    p.sleep(0.4)
    return tags


def tome_target(p, nav, target: str, log, trait: str = "unbound"):
    """The first card whose name holds `target` and whose unit doesn't have the trait yet (each
    one's panel is looked at: the user may have used a tome by hand), or None if all have it.
    Each panel is opened the moment its card shows and the search stops at the first without
    the trait (11 Nov 2026: scanning the whole list first, then going back to each card, took
    over 2 minutes a tome while the furnace lost health)."""
    started = p.now()
    result = {"card": None, "seen": 0}

    def visit(card):
        p.click(*_portrait(card))
        p.sleep(0.9)
        tags = ocr.read_text(p.grab(), UNIT_PANEL_TAGS, scale=1.5).lower()
        p.click(*UNIT_PANEL_CLOSE)
        p.sleep(0.4)
        p.hover(*UM_OFF_CARDS)
        p.sleep(0.2)
        result["seen"] += 1
        if not tags.strip():  # the panel didn't open: unknown, so never a target
            log(f"{card.name}'s panel didn't open")
            return False
        if trait not in tags:
            result["card"] = card
            return True
        return False

    cards = unit_cards(p, nav, target, log, visit=visit)
    found = result["card"]
    close_unit_manager(p, nav)
    if found is None:
        log(f"every {target} ({len(cards)}) has {trait} already ({p.now() - started:.0f} s)")
    else:
        log(f"{found.name} #{found.index + 1} has no {trait} yet ({p.now() - started:.0f} s)")
    return found


def use_tome(p, nav, card, log, trait: str = "unbound") -> bool:
    """Use the tome in the hotbar on `card` (from tome_target), through the Unit Manager. True
    when the unit's panel then shows the trait and the tome is gone from the hotbar."""
    close_unit_manager(p, nav)
    p.hover(720, 82)  # an item's tooltip would cover the banner and the Souls
    p.sleep(0.4)
    slot = tome_slot(p.grab())
    if slot is None:
        log("no tome in the hotbar")
        return False
    if not applying(p.grab()):
        # The slot's number key picks the tome up, pressed ONCE: a second press puts it down
        # again (11 Nov 2026: clicks on the slot went unseen, and three tries toggled apply mode
        # on, off, on while Souls piled up). If the banner still isn't read, the card is clicked
        # anyway: outside apply mode that only opens the unit's panel.
        p.key("0" if slot == 10 else str(slot))
        end = p.now() + 1.2  # the banner is seldom read (11 Nov 2026): the card is clicked anyway
        while p.now() < end and not applying(p.grab()):
            p.sleep(0.25)
        if not applying(p.grab()):
            log("no apply banner seen after picking the tome up; clicking the unit anyway")
    if not open_unit_manager(p, nav, log):
        return False
    # In apply mode the list is the same as outside it (seen live, 11 Nov 2026, 15:59): back to
    # the step the card was read at, and click the card with the same name at the same place.
    _go_to_page(p, getattr(card, "page", 0))
    frame = p.grab()
    here = [c for c in read_cards(frame, ocr.find_words(frame, UM_PANEL)) if c.name == card.name
            and abs(c.y - card.y) < 40 and abs((c.x if not c.on else c.x - TEAL_FROM_GREY)
                                               - (card.x if not card.on else card.x - TEAL_FROM_GREY)) < 40]
    if here:
        card = here[0]
    else:
        log(f"{card.name} isn't where it was read in apply mode: clicking where it was")
    p.click(*_portrait(card))
    p.sleep(1.0)
    tags = ocr.read_text(p.grab(), UNIT_PANEL_TAGS, scale=1.5).lower()
    p.hover(720, 82)
    p.sleep(0.3)
    from macro.modes import souls
    done = trait in tags and slot not in souls.tome_slots(p.grab())  # that slot's tome is gone
    log(f"tome on {card.name}: {'applied' if done else 'not applied'} (panel reads {tags!r})")
    p.click(*UNIT_PANEL_CLOSE)
    p.sleep(0.4)
    close_unit_manager(p, nav)
    return done


# ------------------------------------------------------------------ extra units (11 Nov 2026)
# Random Unit (Forge, 100 Souls) puts a temporary limit-1 unit in the first free hotbar slot (7-10);
# the game doesn't place it. After Start the home view still matches the home reference at scale
# 1.0, so they go on spots of the home picture: where the three paths end at the furnace, which
# every enemy the Atoms miss walks past. Spots from tools/path_cover.py soul_furnace.
EXTRA_SPOTS = [(990, 360), (640, 360), (790, 510), (840, 360)]
SLOT_LIT = 40  # an empty extra slot is dark (V ~17); one holding something is bright (68+)


def lit_extra_slots(frame) -> list[int]:
    import cv2
    import numpy as np
    out = []
    for slot, x in HOTBAR_EXTRA.items():
        patch = cv2.cvtColor(frame[700:765, x - 38:x + 38], cv2.COLOR_BGR2HSV)
        if np.median(patch[:, :, 2]) > SLOT_LIT:
            out.append(slot)
    return out


def place_extra(p, nav, home: maps.MapProfile, slot: int, spot, log) -> bool:
    """Place the unit in hotbar slot `slot` on `spot` of the home picture (nudged if refused)."""
    import cv2
    from macro.control import placing
    from macro.vision import align
    close_unit_manager(p, nav)
    alignment = align.align(align.features(cv2.imread(home.reference_path)), align.features(p.grab()))
    if alignment is None or alignment.inliers < 150 or abs(alignment.scale - 1) > 0.08:
        log(f"the home view isn't on screen ({alignment and alignment.inliers} features): extra unit waits")
        return False
    placing.EXTRA_AREAS[:] = placing.EVENT_AREAS
    try:
        return place_one(p, alignment, slot, spot, log)
    finally:
        placing.EXTRA_AREAS[:] = []


# ------------------------------------------------------------------------------ one run
MATCH_LIMIT = 4 * 3600.0
STUCK_AFTER = 120.0
# Economy first (11 Nov 2026): the plan's first three phantoms are the Stone Alchemists. Once they're
# built, Phantom Placing is paused so the Yen goes into their upgrades (priority 1) until each is at
# FARM_LEVEL, then the rest is built. Wiki: 550/wave placed, 1,100 at UPG 1 (costs 1,100), 2,750 at
# UPG 2 (2,200), 3,500 at UPG 3 (4,500), +25% from the trait: UPG 2 pays back in about a wave, UPG 3
# in five, so UPG 3 waits until everything is built (it still comes first after that).
FARM_COUNT = 3
FARM_PRICE = 550
FARM_LEVEL = 2
FARM_CHECK = 15.0  # seconds between looks at the farms' levels while they upgrade
FARMS_BY_WAVE = 3  # pause by this wave even if a build was missed in the Yen
FARMS_UNTIL_WAVE = 7  # build the rest from this wave whatever the farms' levels
RECHECK_WAVE = 9  # one more Auto Upgrade pass here (by then every phantom is a unit), if needed
# Only when the pass before Start had trouble (a priority it couldn't read or confirm) or set fewer
# cards than phantoms were placed: 34 of 41 re-checks changed nothing and each held the Unit
# Manager open ~25-30 s around wave 9 (12-13 Nov 2026 logs).
# Souls after the SPA boosts (+50% is the most the Forge sells; while it buys, Souls never reach a
# tome's price): an Unbound Tome on each Atom (user, 11 Nov 2026), then AFTER_TOMES on auto.
TOME_TARGET = "atom"
TOME_COUNT = 3
AFTER_TOMES = {"random_unit": 1, "dmg": 2, "rng": 3}  # extra units first (user), then boosts
EXTRA_CHECK = 8.0  # seconds between looks at hotbar slots 7-10 for a new unit to place


def _team_names() -> dict:
    """Hotbar slot -> the unit's simplified name, from the team preset."""
    import os
    import yaml
    try:
        with open(os.path.join(os.path.dirname(maps.MAPS), "presets", "current_team.yaml"), encoding="utf-8") as f:
            slots = (yaml.safe_load(f) or {}).get("slots") or {}
        return {int(k): _simple(str(v.get("unit", ""))) for k, v in slots.items()}
    except OSError:
        return {}


@dataclass
class FurnaceResult:
    outcome: str
    seconds: float
    wave: int | None = None
    souls: int | None = None  # collected this run (the Heat bar's total)
    candy: int | None = None  # Candy Corn shown in the match's row at the end
    heat_bars: int = 0
    spa_boosts: int = 0
    phantoms: int = 0
    tomes: int = 0  # Unbound Tomes put on Atoms
    extras: int = 0  # Random Units placed
    bins: tuple = (0, 0)  # hotbar bin drags (worked, tried)
    boosts_from: int | None = None  # wave the DMG/RNG boosts went on, if they did
    moves_made: int = 0
    waves_seen: list = field(default_factory=list)


def heat_bars_of(size: int) -> int:
    for n in range(40):
        if bar_size(n) == size:
            return n
    return 0


def play_furnace(nav, reader, profile, plan, *, fresh: bool, spa_target: int = SPA_TARGET, after_spa: str = "random_unit",
                 economy_first: bool = False, resume: bool = False, tomes: bool = True, log=None, on_frame=None,
                 should_stop=None) -> FurnaceResult:
    """One Soul Furnace run, from the match waiting at "Start Game?" to its results.

    fresh: the match was entered from the lobby, so the character is at spawn and walks the
    map's route; after Repeat Stage it is still where the last run left it (Start doesn't move it),
    so only the position check runs."""
    from macro.control import placing
    from macro.modes import story

    log = log or (lambda text: None)
    p = nav.p
    started = p.now()
    result = FurnaceResult("unfinished", 0.0)
    close_unit_manager(p, nav)  # it hides the map the position is checked on
    placed_at: list = []  # (slot, view, point) of each phantom queued
    if resume:  # a match already set up and started: only watch it to its end (the plan's
        # priorities and Soul settings still count)
        plan = {"views": {}, "steps": [], **{k: plan[k] for k in ("priorities", "souls")
                                              if isinstance(plan, dict) and k in plan}}
    else:
        game_auto_play_off(p, lambda t: log(f"  {t}"))
    if resume:
        pass
    elif isinstance(plan, dict):
        # A several-view plan (layouts/paths.yaml): home found by looking round, then every view.
        if fresh:
            maps.find_position(p, profile, log=lambda t: log(f"  {t}"))
        result.phantoms = place_from_views(p, plan, profile, lambda t: log(f"  {t}"), record=placed_at)
    else:
        if fresh:
            alignment = maps.go_to_position(p, profile, log=lambda t: log(f"  {t}"))
        else:
            maps.set_overhead_camera(p, profile)
            alignment = maps.correct_position(p, profile, log=lambda t: log(f"  {t}"))
        engine = PlanEngine(p, reader, plan, alignment, {}, log=lambda t: log(f"  {t}"))
        try:
            result.phantoms = place_phantoms(p, engine, log)
        finally:
            placing.EXTRA_AREAS[:] = []
    result.moves_made = result.phantoms
    um_log = lambda t: log(f"  {t}")  # noqa: E731
    # Every unit's Auto Upgrade and priority, set on the phantoms' cards before the clock runs.
    forge = Forge(p, log=um_log, nav=nav)
    # The plan's own priorities (layouts/paths.yaml "priorities:", unit name part -> 1-6), read every
    # run so they can be changed without a restart; UPGRADE_ORDER otherwise.
    order = {str(k).lower().replace(" ", ""): int(v) for k, v in ((plan.get("priorities") if isinstance(plan, dict) else None)
                                                             or {}).items()} or None
    recheck_needed = True
    if not resume:
        set_phantom_placing(p, nav, True, um_log)
        set_auto_upgrading(p, nav, True, um_log)
        changed, _ = set_auto_upgrades(p, nav, um_log, order=order)
        recheck_needed = getattr(set_auto_upgrades, "problems", 1) > 0 or changed < result.phantoms
        close_unit_manager(p, nav)
        if not forge.set_autos({"spa": 1 if spa_target > 0 else 0, "random_unit": 0, "dmg": 0, "rng": 0}):
            forge.set_auto("spa", 1 if spa_target > 0 else 0)
            forge.set_auto("random_unit", 0)
    yen_before = reader.read_hud(p.grab())["yen"]
    if story.start_window_showing(p.grab()):
        story.press_start(nav, log)
    economy = "farms" if economy_first and not resume else "done"
    farms_built, last_yen, farm_check = 0, yen_before, 0.0
    rechecked = False
    # Where the Souls go once SPA is maxed (macro/modes/souls.py: the user's plan, its settings in
    # the layout's "souls:" section).
    spender = None
    if tomes:
        from macro.modes import souls as soul_plan
        config = soul_plan.SoulConfig.from_plan(plan)
        team = _team_names()
        views = {}
        for key, folder in ((plan.get("views") or {}).items() if isinstance(plan, dict) else []):
            try:
                views[key] = maps.load_profile(folder)
            except Exception:  # noqa: BLE001 - only the map fallback needs them
                pass
        placements = [soul_plan.Placement(team.get(slot, ""), view, point) for slot, view, point in placed_at]
        spender = soul_plan.SoulSpender(p, nav, forge, profile, config, um_log, order=order,
                                        placements=placements, views=views)
        log(f"  Souls: {config.describe()}")
    # With tomes, SPA stays on auto: the Forge stops selling it at +50%, and only then can Souls
    # reach a tome's price. Without, the old count turns it off at spa_target for after_spa.
    phase = "spa" if spa_target > 0 and not tomes else "after"
    clock_last, clock_moved = None, p.now()
    last_heat, collected, spent_other = 0.0, 0, 0
    lost_tries = 0
    while p.now() - started < MATCH_LIMIT:
        if should_stop and should_stop():
            result.outcome = "stopped"
            break
        frame = p.grab()
        screen = nav.detector.classify(frame).name
        nav._last_frame = frame
        if screen in story.RESULT_SCREENS:
            result.outcome = screen
            break
        if screen == "match" and story.start_window_showing(frame):
            story.press_start(nav, log)
            continue
        if screen != "match":
            if screen in ("unit_manager",):
                p.key("f")
            elif nav.settle(1.5) not in ("match", *story.RESULT_SCREENS):
                if screen in ("lobby", "play_menu_top", "play_menu_bottom", "events", "soul_furnace_picker"):
                    result.outcome = f"left the match ({screen})"  # nothing in a match leads here
                    break
                log(f"  {screen} is covering the match")
                try:
                    nav.go("match", max_steps=3)
                except Exception as error:  # noqa: BLE001 - keep playing; results end the loop
                    log(f"  couldn't get back to the match: {error}")
                    lost_tries += 1
                    if lost_tries >= 5:
                        result.outcome = f"lost on {screen}"
                        break
            continue
        hud = reader.read_hud(frame)
        if on_frame:
            on_frame(screen, frame, hud)
        wave = hud["wave"] or 0
        if hud["wave"] is not None and (not result.waves_seen or result.waves_seen[-1][0] != hud["wave"]):
            result.waves_seen.append((hud["wave"], None))
            result.wave = hud["wave"]
            log(f"  wave {hud['wave']}, Yen {hud['yen']}, Souls {hud.get('souls')}, Candy Corn {hud.get('candy')}, "
                f"enemies {hud['enemies']}, health {hud['health']}")
        if hud.get("candy") is not None:
            result.candy = hud["candy"]
        if hud.get("health") == 0:
            # The furnace is gone: the results come up in a moment. Nothing else may act now (12 Nov
            # 2026, 03:03: placements at health 0 closed the Defeat window, and the run then sat as
            # "stuck" and went to the lobby instead of Retry). If the results were closed, the
            # match's own "Game Results" button opens them again.
            end = p.now() + 8
            while p.now() < end and nav.detector.classify(p.grab()).name not in story.RESULT_SCREENS:
                p.sleep(0.5)
            screen = nav.detector.classify(p.grab()).name
            if screen not in story.RESULT_SCREENS:
                close_unit_manager(p, nav)
                Forge(p).close()
                p.key("z")
                p.click(*GAME_RESULTS)
                p.sleep(2.0)
                screen = nav.settle(2.0)
            if screen in story.RESULT_SCREENS:
                result.outcome = screen
                break
        if hud["seconds"] is not None and hud["seconds"] != clock_last:
            clock_last, clock_moved = hud["seconds"], p.now()
        elif p.now() - clock_moved > STUCK_AFTER:
            result.outcome = "stuck: the clock stopped"
            break
        now = p.now()
        yen = hud["yen"]
        if economy == "farms":
            # Each farm built takes its price out of the Yen at once (phantoms are built before any
            # upgrade), so drops of about that size count them.
            if yen is not None:
                if last_yen is not None and yen <= last_yen - FARM_PRICE * 0.75:
                    farms_built += 1
                    log(f"  Stone Alchemist {farms_built} built (Yen {last_yen} -> {yen})")
                last_yen = yen
            if farms_built >= FARM_COUNT or wave >= FARMS_BY_WAVE:
                set_phantom_placing(p, nav, False, um_log)
                close_unit_manager(p, nav)
                log(f"  farms first: the rest waits until the Stone Alchemists reach UPG {FARM_LEVEL}")
                economy, farm_check = "upgrading", now
        elif economy == "upgrading" and now - farm_check > FARM_CHECK:
            farm_check = now
            levels = farm_levels(p, nav, um_log)
            if (len(levels) >= FARM_COUNT and min(levels) >= FARM_LEVEL) or wave >= FARMS_UNTIL_WAVE:
                set_phantom_placing(p, nav, True, um_log)
                log(f"  Stone Alchemists at {levels} by wave {wave}: building the rest")
                economy = "done"
            close_unit_manager(p, nav)
            farm_check = p.now()
        elif economy == "done" and not rechecked and wave >= RECHECK_WAVE:
            rechecked = True
            if recheck_needed:
                set_auto_upgrades(p, nav, um_log, order=order)
                close_unit_manager(p, nav)
            else:
                log("  Auto Upgrade was all set before Start: no second Unit Manager pass")
        souls = hud.get("souls")
        if spender is not None:
            if spender.tick(frame, wave, souls, collected or None, health=hud.get("health"),
                            heat_bars=result.heat_bars or None, enemies=hud.get("enemies"),
                            candy=hud.get("candy")):
                result.tomes, result.extras = spender.tomes_used, spender.extras_placed
                result.bins = (len(spender.binned), spender.bin_tries)
                result.boosts_from = spender.boosts_started_wave
                continue
        if now - last_heat > 5.0:
            last_heat = now
            heat = read_heat(frame)
            if heat:
                total = souls_collected(*heat)
                if total is not None and total >= collected:
                    collected = total
                    result.souls, result.heat_bars = total, heat_bars_of(heat[1])
            if phase == "spa" and hud.get("souls") is not None:
                result.spa_boosts = max(0, (collected - hud["souls"] - spent_other) // SPA_PRICE)
                if result.spa_boosts >= spa_target:
                    log(f"  {result.spa_boosts} SPA boosts bought: SPA auto forge off, Souls go to {after_spa}")
                    forge.set_auto("spa", 0)
                    if after_spa in RECIPES:
                        forge.set_auto(after_spa, 1)
                    phase = "after"
        p.sleep(0.3)
    else:
        result.outcome = "ran out of time"
    result.seconds = p.now() - started
    return result
