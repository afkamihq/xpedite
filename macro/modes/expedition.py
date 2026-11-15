"""Expeditions: Play -> Expedition (built 15 Nov 2026). What was seen is in docs/EXPEDITION.md.

A run escorts the payload through ten columns of nodes to a Boss. What makes the macro work:
- **Reroll first.** Restart Game (Settings) gives a new map of nodes in ~3 s and costs nothing.
  The Expedition Map's Route Rewards strip shows the chosen route's total; clicking a node re-routes
  through it. A roll is kept once a route meets the user's minimums.
- **The tail, not the head.** The payload drives down the screen in the overhead view: its tail is
  the TOP end and takes most of the enemies (user, 15 Nov 2026). Damage dealers go there, the farm
  on the head. Units can be placed at any time on a valid spot, one placement per unit.
- **The Unit Manager** lists units in placement order, so upgrades are clicks on known buttons.
- Payload level-ups stop play with three cards; the user's priority list picks one.
All coordinates are the docked 1440x810 frame's pixels.
"""
from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass, field

import cv2
import numpy as np
import yaml

from macro.control import maps
from macro.nav.start_game import START_GAME, start_window_showing
from macro.vision import ocr
from macro.vision.screens import scaled

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data", "expedition")
SETTINGS_FILE = os.path.join(ROOT, "data", "expedition.yaml")
ANVIL_CATALOG = os.path.join(DATA, "anvil_cards.yaml")

MAPS = ["School Grounds", "Flower Forest", "Rose Kingdom", "East Town"]
MAP_BUTTONS = {"School Grounds": (147, 190), "Flower Forest": (147, 322),
               "Rose Kingdom": (147, 454), "East Town": (147, 586)}
MATERIAL = {"School Grounds": "Cursed Timber", "Flower Forest": "Lush Dirt",
            "Rose Kingdom": "Aqua Shard", "East Town": "Mechanical Scrap"}
RESOURCES = ["Cursed Timber", "Lush Dirt", "Aqua Shard", "Mechanical Scrap", "Expedition Coin",
             "Fuel Cell", "Equipment Scrap", "Equipment Reroll", "Equipment Lock", "Tome", "Yen",
             "Payload EXP", "Player EXP"]

# Picker and party room.
DIFF_MINUS, DIFF_PLUS = (354, 518), (552, 518)
DIFF_TEXT = (390, 515, 518, 546)  # "Difficulty N" (read_text: read_line drops the digit on D2/D3)
SELECT_STAGE = (452, 771)
PARTY_START = (854, 563)
# In a run.
MAP_BUTTON = (1352, 519)
MAP_BACK = (126, 732)
START_CONTINUE = (720, 613)
CHECKPOINT_CONTINUE, EXTRACT = (800, 611), (644, 611)
CONFIRM_CONTINUE, CONFIRM_CANCEL = (616, 452), (822, 452)
SETTINGS_GEAR, RESTART_GAME, RESTART_CONFIRM = (289, 42), (777, 422), (617, 443)
SETTINGS_CLOSE = (1183, 150)
LEVELUP_CARDS = [(347, 560), (720, 560), (1093, 560)]
LEVELUP_TITLES = [(250, 383, 445, 405), (620, 386, 822, 408), (998, 383, 1193, 405)]
# Stat Anvil cards share the level-up layout: an orange title, a rarity line ("Epic Upgrade") and a
# white "Gain +26% Follow-Up Damage" line on black, which reads best.
ANVIL_X = [(248, 445), (622, 820), (996, 1194)]
RARITIES = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Secret"]
UM_UPGRADE = [(1032, 266), (1189, 266), (1347, 266), (1032, 545), (1189, 545), (1347, 545)]
UM_UPGRADE_TEXT = [(x - 62, y - 22, x + 62, y - 6) for x, y in UM_UPGRADE]  # "Upgrade 3/8" / "Maxed"
UM_CLOSE = (1030, 777)
AWAY = (720, 120)
# Route Rewards: tiles 81 px apart from x 250, count badge on top, white name label under the icon.
REWARD_LEFT, REWARD_STEP = 250, 81
BADGE_ROW = (245, 698, 1385, 722)
# Where units go on the payload, with the overhead camera zoomed in 4 notches (it follows the
# payload). Tail = top end. Spots tested live on 15 Nov 2026.
TAIL_SPOTS = [(705, 320), (655, 345), (755, 345), (705, 378), (655, 392), (755, 405)]
MIDDLE_SPOTS = [(650, 420), (715, 470), (660, 475)]
HEAD_SPOTS = [(705, 515), (650, 530)]
ZOOM_IN_NOTCHES = 4

TEMPLATE_BOXES = {  # where each screen's mark is looked for (padded box)
    "levelup": (600, 110, 840, 175),
    "um_title": (930, 70, 1150, 140),
    "extract": (520, 570, 760, 650),
    "continue": (560, 570, 900, 650),
    "leave": (780, 640, 1060, 740),  # the grey Leave of a hire or encounter dialog
    "shop_title": (60, 80, 280, 140),
    "restart_row": (430, 380, 640, 460),  # "Restart Game" in the in-run Settings
    "restart_confirm": (600, 320, 840, 400),  # "Restart Confirmation"
    "start_title": (600, 90, 850, 200),  # the "Start Game?" window's title
    "map_title": (40, 60, 300, 140),  # "Expedition Map"
    "anvil": (600, 110, 840, 175),  # "Stat Anvil: Select a stat upgrade!" (three cards, like a level-up)
}


def _load_templates() -> dict[str, np.ndarray]:
    out = {}
    for name in TEMPLATE_BOXES:
        path = os.path.join(DATA, f"{name}.png")
        if os.path.exists(path):
            out[name] = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    return out


TEMPLATES = _load_templates()


def start_window(frame) -> bool:
    """The "Start Game?" window, by its title: its button is bright green at a run's start but a
    darker green at some later nodes (15 Nov 2026: a node waited 16 minutes under the dark one,
    unseen by the colour check, until the server sent the game away)."""
    return start_window_showing(frame) or seen(frame, "start_title") > 0.75


def run_started(frame) -> bool:
    """A run is ready to play: its start's Continue, or (Auto Vote Start off, the macro's setting)
    the "Start Game?" window it waits under with the clock stopped."""
    return seen(frame, "continue") > 0.9 or start_window(frame)


def press_start(p, log=None) -> bool:
    """Press Start Game while its window is up; True once it's gone."""
    for _ in range(3):
        if not start_window(p.grab()):
            return True
        p.hover(*scaled(*START_GAME))
        p.sleep(0.15)
        p.click(*scaled(*START_GAME))
        end = time.time() + 3
        while time.time() < end:
            p.sleep(0.25)
            if not start_window(p.grab()):
                if log:
                    log("pressed Start Game")
                return True
    return False


def where(frame: np.ndarray, name: str) -> tuple[float, tuple[int, int]]:
    """A screen mark's score and the centre of its best match, in frame pixels."""
    tpl = TEMPLATES.get(name)
    if tpl is None:
        return 0.0, (0, 0)
    x0, y0, x1, y1 = TEMPLATE_BOXES[name]
    gray = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
    _, best, _, at = cv2.minMaxLoc(result)
    return float(best), (x0 + at[0] + tpl.shape[1] // 2, y0 + at[1] + tpl.shape[0] // 2)


def seen(frame: np.ndarray, name: str) -> float:
    """How well a screen's mark matches where it belongs (0-1)."""
    tpl = TEMPLATES.get(name)
    if tpl is None:
        return 0.0
    x0, y0, x1, y1 = TEMPLATE_BOXES[name]
    gray = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return float(cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED).max())


# ----------------------------------------------------------------------------- settings
DEFAULT_RULE = {
    "reroll": True,
    "match": "all",  # "all": every minimum that's on; "any": one of them is enough
    "minimums": {},  # resource -> {"on": bool, "min": int}
    "max_rerolls": 50,
    "when_none": "best",  # best (play the best roll seen) | current | skip | stop
    "capped_counts_zero": True,
    "avoid_assault_first": True,
}
DEFAULT_SETTINGS = {
    "maps": {},  # "<map>|<difficulty>" -> rule (missing keys take DEFAULT_RULE)
    "placement": "tail",  # tail-first placement from the team's roles (data/presets/current_team.yaml)
    "upgrade_order": ["farm", "dps", "support"],
    "upgrades": "auto",  # auto: each card's Auto Upgrade, farms first; manual: the macro clicks them
    "levelup_priority": ["Fortified Cargo", "Yen Hunger", "Amplifier", "Relentless Pursuit",
                         "Gale Mastery", "Hydro Mastery", "Flame Mastery", "Iron Flesh"],
    # A used Stat Anvil offers three cards (user, 15 Nov 2026). The first stat in this list that's
    # offered is taken (the rarest copy of it); with none offered, the rarest card. The user's order:
    # Bonus Match, then Critical Chance, then anything. Seen cards go to data/expedition/anvil_cards.yaml.
    "anvil_priority": ["Bonus Match", "Critical Chance", "Crit Chance", "Critical Damage", "Damage",
                       "Attack Speed", "Cooldown", "Yen", "Range"],
    "hire": {"on": True, "max": 4, "keep_yen": 2000, "names": []},
    "shop": {"tomes": True, "repair_below": 0, "hammers": True, "anvils": True, "keep_for_shop": 10000,
             "refresh": True,
             # A tome used in an Expedition changes the unit's trait for good: an Unbound Tome on
             # the player's Atom (15 Nov 2026) left it Unbound (one placement) outside Expeditions
             # too, and a Bolt Tome had replaced its Primordial. Off: tomes only on hired units.
             "tomes_on_own": False},
    "use_dropped_tomes": True,
    "encounter": "leave",
    "extract": {"rule": "never", "hp_below": 250, "after_nodes": 10, "route_check": True},
    "stop": {"runs": 0, "minutes": 0, "totals": {}},
    "after_run": "repeat",
}


def load_settings() -> dict:
    data = {}
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_SETTINGS.items()}
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def save_settings(settings: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(settings, f, sort_keys=False, allow_unicode=True)


def rule_for(settings: dict, map_name: str, difficulty: int) -> dict:
    rule = dict(DEFAULT_RULE)
    rule.update((settings.get("maps") or {}).get(f"{map_name}|{difficulty}", {}) or {})
    rule["minimums"] = {k: dict(v) for k, v in (rule.get("minimums") or {}).items()}
    return rule


# ----------------------------------------------------------------------------- stat anvils
def _compact(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def parse_anvil_card(title: str, rarity_text: str, desc: str) -> dict:
    """One card from its three lines: stat, value (percent) and rarity."""
    value, stat = None, ""
    m = re.search(r"\+\s*(\d+(?:[.,\s]\d+)?)\s*%?\s*(.*)", desc or "")
    if m:
        try:
            value = float(re.sub(r"[,\s]", ".", m.group(1)))
        except ValueError:
            value = None
        stat = re.sub(r"[^A-Za-z\- ]", "", m.group(2)).strip()
    name = re.sub(r"[^A-Za-z\- ]", "", title or "").strip()
    low = _compact(rarity_text or "")
    rarity = next((r for r in reversed(RARITIES) if r.lower() in low), "")
    if len(stat) < 4 or (len(_compact(name)) > len(_compact(stat)) and _compact(name).startswith(_compact(stat))):
        stat = name  # the description line got cut short ("Gain +2.6% Rang")
    return {"stat": stat, "title": name, "value": value, "rarity": rarity}


def read_anvil_cards(frame) -> list[dict]:
    cards = []
    for x0, x1 in ANVIL_X:
        title = ocr.read_text(frame, (x0 - 5, 384, x1 + 5, 406), scale=2.0)
        rarity = ocr.read_line(frame, (x0 + 30, 403, x1 - 30, 421), scale=3.0)
        desc = ocr.read_line(frame, (x0 + 2, 464, x1 - 2, 488), scale=2.0)
        cards.append(parse_anvil_card(title, rarity, desc))
    return cards


def choose_anvil_card(cards: list[dict], priority: list[str]) -> int:
    """The first stat in the priority that's offered (its rarest, biggest copy); else the rarest card."""
    def rank(i):
        c = cards[i]
        return (RARITIES.index(c["rarity"]) if c["rarity"] in RARITIES else -1, c["value"] or 0)
    for wanted in priority:
        key = _compact(wanted)
        hits = [i for i, c in enumerate(cards) if key and key in _compact(c["stat"] + " " + c["title"])]
        if hits:
            return max(hits, key=rank)
    return max(range(len(cards)), key=rank) if cards else 1


def record_anvil_cards(cards: list[dict], map_name: str = "") -> None:
    """Every anvil card read where title and description agree goes in a catalog: stat, the rarities
    it came in and the values seen, so the priority list can name every card there is."""
    import difflib
    try:
        with open(ANVIL_CATALOG, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except OSError:
        data = {}
    known = data.setdefault("cards", {})
    changed = False
    for c in cards:
        stat, title = c["stat"], c["title"]
        if len(stat) < 4 or difflib.SequenceMatcher(None, _compact(stat), _compact(title)).ratio() < 0.75:
            continue
        name = next((k for k in known if _compact(k) == _compact(stat)), stat)
        entry = known.setdefault(name, {"rarities": {}, "maps": []})
        if c["rarity"] and c["value"] is not None:
            lo, hi = (entry["rarities"].get(c["rarity"]) or [c["value"], c["value"]])
            entry["rarities"][c["rarity"]] = [min(lo, c["value"]), max(hi, c["value"])]
        if map_name and map_name not in entry["maps"]:
            entry["maps"].append(map_name)
        changed = True
    if changed:
        try:
            with open(ANVIL_CATALOG, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=True, allow_unicode=True)
        except OSError:
            pass


# ----------------------------------------------------------------------------- route rewards
@dataclass
class Rewards:
    items: dict[str, int] = field(default_factory=dict)
    capped: set[str] = field(default_factory=set)
    unknown: int = 0  # tiles whose item wasn't recognised

    def value(self, name: str, capped_zero: bool = True) -> int:
        if capped_zero and name in self.capped:
            return 0
        return self.items.get(name, 0)

    def text(self) -> str:
        parts = [f"{n} {v:,}" + (" (capped)" if n in self.capped else "") for n, v in self.items.items()]
        return ", ".join(parts) or "nothing read"


def _label_mask(frame: np.ndarray, k: int) -> np.ndarray:
    left = REWARD_LEFT + REWARD_STEP * k
    crop = frame[752:774, left + 2:left + 72]
    return (crop.min(axis=2) > 190).astype(np.uint8) * 255


def _item_masks() -> dict[str, np.ndarray]:
    folder = os.path.join(DATA, "items")
    out = {}
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.endswith(".png"):
                key = name[:-4].replace("_", " ")
                proper = next((r for r in RESOURCES if r.lower() == key), key.title())
                out[proper] = cv2.imread(os.path.join(folder, name), cv2.IMREAD_GRAYSCALE)
    return out


ITEM_MASKS = _item_masks()


def _tile_present(frame: np.ndarray, k: int) -> bool:
    """A tile is there when its white name label is (tile colours shimmer, so not by colour)."""
    if REWARD_LEFT + REWARD_STEP * k + 72 > frame.shape[1]:
        return False
    return int((_label_mask(frame, k) > 0).sum()) >= 25


def _tile_capped(frame: np.ndarray, k: int) -> bool:
    """The red Inventory Limit triangle at the tile's top right."""
    left = REWARD_LEFT + REWARD_STEP * k
    patch = frame[703:722, left + 54:left + 74].astype(int)
    red = (patch[:, :, 2] > 180) & (patch[:, :, 1] < 80) & (patch[:, :, 0] < 80)
    return int(red.sum()) >= 40  # a capped tile's triangle has ~113 red pixels here


def identify_tile(frame: np.ndarray, k: int, learn: bool = True) -> str | None:
    mask = _label_mask(frame, k)
    best, best_score = None, 0.0
    for name, tpl in ITEM_MASKS.items():
        score = float(cv2.matchTemplate(mask, tpl[2:-2, 4:-4], cv2.TM_CCOEFF_NORMED).max())
        if score > best_score:
            best, best_score = name, score
    if best_score >= 0.9:
        return best
    if not learn:
        return None
    # A new item: read its name once and keep its label for next time.
    left = REWARD_LEFT + REWARD_STEP * k
    words = ocr.read_text(frame, (left, 748, left + 76, 778), scale=2.5)
    name = _resource_from_words(words)
    if name:
        cv2.imwrite(os.path.join(DATA, "items", name.lower().replace(" ", "_") + ".png"), mask)
        ITEM_MASKS[name] = mask
    return name


def _resource_from_words(words: str) -> str | None:
    squashed = re.sub(r"[^a-z]", "", words.lower())
    for name in sorted(RESOURCES, key=len, reverse=True):
        if re.sub(r"[^a-z]", "", name.lower()) in squashed:
            return name
    return None


def _badge_number(text: str) -> int | None:
    """The game's badge font reads 1 as 'b' and x as 'c' now and then."""
    t = text.lower().replace("×", "x").replace("b", "1").replace("o", "0").replace("l", "1")
    t = t.replace("c", "x").replace(",", "").replace(".", "")
    found = re.match(r"(\d+)x?$", t.strip())
    if found:
        return int(found.group(1))
    if t.strip() in ("x", ""):
        return 1  # a lone "1x" sometimes comes back as just "x"
    return None


def read_route_rewards(frame: np.ndarray) -> Rewards:
    """The Route Rewards strip of an open Expedition Map."""
    rewards = Rewards()
    tiles = [k for k in range(14) if _tile_present(frame, k)]
    counts: dict[int, int] = {}
    x0, y0, x1, y1 = BADGE_ROW
    crop = cv2.copyMakeBorder(frame[y0:y1, x0:x1], 10, 10, 10, 10, cv2.BORDER_CONSTANT)
    result, _ = ocr._get_engine()(crop, use_cls=False)
    for corners, text, _ in result or []:
        cx = x0 + sum(p[0] for p in corners) / 4 - 10
        left_edge = x0 + min(p[0] for p in corners) - 10
        k = int(round((left_edge - REWARD_LEFT) / REWARD_STEP))
        if not 0 <= k < 14 or abs(cx - (REWARD_LEFT + REWARD_STEP * k)) > 75:
            continue
        number = _badge_number(text)
        if number is not None:
            counts[k] = number
    for k in tiles:
        name = identify_tile(frame, k)
        if name is None:
            rewards.unknown += 1
            continue
        rewards.items[name] = counts.get(k, 1)
        if _tile_capped(frame, k):
            rewards.capped.add(name)
    return rewards


def meets(rewards: Rewards, rule: dict) -> bool:
    wanted = [(name, int(m.get("min", 0))) for name, m in (rule.get("minimums") or {}).items()
              if m.get("on")]
    if not wanted:
        return True
    zero = rule.get("capped_counts_zero", True)
    hits = [rewards.value(name, zero) >= least for name, least in wanted]
    return all(hits) if rule.get("match", "all") == "all" else any(hits)


def score(rewards: Rewards, rule: dict) -> float:
    """How close a roll comes to the minimums: the share of each wanted amount, capped at 1 each,
    so the best roll seen can be played when none meets them all."""
    wanted = [(name, int(m.get("min", 0))) for name, m in (rule.get("minimums") or {}).items()
              if m.get("on") and int(m.get("min", 0)) > 0]
    zero = rule.get("capped_counts_zero", True)
    if not wanted:
        return float(sum(rewards.value(n, zero) for n in rewards.items if n not in ("Yen", "Player EXP", "Payload EXP")))
    return sum(min(1.0, rewards.value(n, zero) / least) for n, least in wanted) / len(wanted)


# ----------------------------------------------------------------------------- the map's nodes
NODE_TYPES = ("defense", "elite", "assault", "checkpoint", "encounter", "unknown", "boss")
COLUMN_X = [225, 366, 507, 649, 790, 932, 1073, 1214]


def _node_templates() -> dict[str, np.ndarray]:
    folder = os.path.join(DATA, "nodes")
    out = {}
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.endswith(".png"):
                out[name[:-4]] = cv2.imread(os.path.join(folder, name), cv2.IMREAD_GRAYSCALE)
    return out


NODE_TEMPLATES = _node_templates()


def find_nodes(frame: np.ndarray, column: int) -> list[tuple[str, int, int]]:
    """Node icons in one column of the open map: (type, x, y), top to bottom."""
    x = COLUMN_X[column]
    strip = cv2.cvtColor(frame[140:650, x - 30:x + 30], cv2.COLOR_BGR2GRAY)
    found = []
    for name, tpl in NODE_TEMPLATES.items():
        kind = name.split("_")[0]
        result = cv2.matchTemplate(strip, tpl, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(result >= 0.8)
        for yy, xx in zip(ys, xs):
            cy = 140 + yy + tpl.shape[0] // 2
            if all(abs(cy - f[2]) > 25 for f in found):
                found.append((kind, x - 30 + xx + tpl.shape[1] // 2, cy))
    return sorted(found, key=lambda f: f[2])


def _keep_last_runs(folder: str, keep: int) -> None:
    """Old runs' pictures are dropped, the newest few kept (cap/ is on disk, not in git)."""
    import shutil
    runs = sorted(d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d)))
    for old in runs[:-keep]:
        shutil.rmtree(os.path.join(folder, old), ignore_errors=True)


def names_of_team() -> dict[int, str]:
    """Each slot's unit name from the team preset, e.g. "Atom (Totality)"."""
    try:
        with open(os.path.join(ROOT, "data", "presets", "current_team.yaml"), encoding="utf-8") as f:
            slots = (yaml.safe_load(f) or {}).get("slots") or {}
    except OSError:
        return {}
    return {int(k): str(v.get("unit") or "") for k, v in slots.items()}


def card_key(name: str) -> str:
    """The part of a unit's name a Unit Manager card is matched on: "Black Heart (Revived)" ->
    "blackheart" (the bracket is often cut or misread)."""
    return re.sub(r"[^a-z0-9]", "", name.split("(")[0].lower())


def traits_of_team() -> dict[int, str]:
    """Each slot's trait from the team preset (data/presets/current_team.yaml), e.g. Unbound."""
    try:
        with open(os.path.join(ROOT, "data", "presets", "current_team.yaml"), encoding="utf-8") as f:
            slots = (yaml.safe_load(f) or {}).get("slots") or {}
    except OSError:
        return {}
    return {int(k): str(v.get("trait") or "") for k, v in slots.items()}


# ----------------------------------------------------------------------------- run state
@dataclass
class RunResult:
    outcome: str = "unknown"  # victory | defeat | extracted | stopped | unknown
    rerolls: int = 0
    rewards: Rewards | None = None  # the route's promised rewards
    seconds: float = 0.0
    nodes: int = 0
    levelups: list[str] = field(default_factory=list)
    placed: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Expedition:
    """One Expedition run on a docked, in-run Roblox: the caller has started it from the picker
    (or Repeat Stage) and the run's first screen is showing."""

    def __init__(self, p, reader, settings: dict, team: dict[int, str], log=None, should_stop=None):
        self.p = p
        self.reader = reader  # DigitReader for the Yen
        self.settings = settings
        self.team = team  # slot -> role (dps / support / farm)
        self.log = log or (lambda text: None)
        self.should_stop = should_stop or (lambda: False)
        # Placed units in placement order = the Unit Manager's order. Hotbar slots get reused (a hire
        # lands in a slot an own unit has left), so a unit is known by its index here, not its slot.
        self.units: list[dict] = []
        self.farm_slots: set[int] = set()  # hotbar slots holding a hired farm, until placed
        self.maxed: set[int] = set()  # unit indexes
        self.pending = self._placement_plan()
        self.used_spots: list[tuple[int, int]] = []
        self.tries: dict[int, int] = {}
        self.route_checked: set[int] = set()
        self.rule: dict | None = None  # the map's reroll rule, for the checks at checkpoints
        self.map_name = ""
        self.talked: set[int] = set()
        self.hired = 0
        self.placer = None
        self.tomes_bought: list[tuple[str, int]] = []
        self.folder = None
        self.hammers = 0
        self.hammer_slots: set[int] = set()
        self.tomed: set[int] = set()  # unit indexes
        self.max_hp = 1000
        self.detector = None
        self.camera_set = False
        self.nav = None
        self.auto_dirty = False
        self.anvils = 0
        self.anvils_used = 0
        self.upgrades_paused = False
        self.bank_toggles = 0
        self.last_bank_check = 0.0
        self.traits = traits_of_team()
        self.names = names_of_team()
        self.hire_names: list[str] = []  # names of hires waiting to be placed, in order

    @property
    def placed_order(self) -> list[int]:
        return [u["slot"] for u in self.units]

    @placed_order.setter
    def placed_order(self, slots: list[int]) -> None:
        self.units = []
        for slot in slots:
            self._add_unit(slot)

    def _add_unit(self, slot: int) -> None:
        """A unit just placed from a hotbar slot: the team's own unit the first time that slot is
        used, a hire or an encounter's unit after (damage dealer, no trait known)."""
        own = slot in self.team and slot not in [u["slot"] for u in self.units if u["own"]]
        role = self.team.get(slot, "dps") if own else ("farm" if slot in self.farm_slots else "dps")
        self.farm_slots.discard(slot) if not own else None
        name = self.names.get(slot, "") if own else (self.hire_names.pop(0) if self.hire_names else "")
        self.units.append({"slot": slot, "own": own, "role": role, "name": name,
                           "trait": self.traits.get(slot, "") if own else ""})

    # ------------------------------------------------------------ placement
    def _placement_plan(self) -> list[tuple[int, tuple[int, int]]]:
        """Slot -> spot, in order. The payload plan (Main window, map "Expedition payload") when it
        has one; otherwise damage dealers and supports on the tail (the top end), farms on the head,
        supports right by the first damage dealer (Teacher-style buffs have short range)."""
        layout = os.path.join(ROOT, "data", "maps", "expedition_payload", "layouts",
                              f"{self.settings.get('placement', 'tail')}.yaml")
        if os.path.exists(layout):
            with open(layout, encoding="utf-8") as f:
                steps = (yaml.safe_load(f) or {}).get("steps") or []
            plan = [(int(st["place"]), tuple(int(v) for v in st["at"])) for st in steps
                    if "place" in st and "at" in st and int(st["place"]) in self.team]
            if plan:
                return plan
        dps = [s for s, r in sorted(self.team.items()) if r == "dps"]
        support = [s for s, r in sorted(self.team.items()) if r == "support"]
        farm = [s for s, r in sorted(self.team.items()) if r == "farm"]
        tail = list(TAIL_SPOTS) + list(MIDDLE_SPOTS)
        head = list(HEAD_SPOTS) + list(MIDDLE_SPOTS[::-1])
        plan = []
        order = dps[:1] + support[:1] + dps[1:] + support[1:]
        for slot in order:
            plan.append((slot, tail.pop(0)))
        for slot in farm:
            plan.append((slot, head.pop(0)))
        # What goes down first with the starting ¥3,500: the first damage dealer, a cheap support,
        # the farm; the rest as the Yen comes.
        return plan

    def place_pending(self, placer, yen: int | None, costs: dict[int, int]) -> None:
        score_, scale, px, py = find_payload(self.p.grab())
        if scale < 0.9:
            setup_camera(self.p, self.log)
            score_, scale, px, py = find_payload(self.p.grab())
        dx, dy = (round(px - PAYLOAD_HOME[0]), round(py - PAYLOAD_HOME[1])) if score_ > 0.3 else (0, 0)
        for slot, (x, y) in list(self.pending):
            x, y = x + dx, y + dy
            cost = costs.get(slot)
            if yen is not None and cost is not None and yen < cost:
                continue
            at = self.place_unit(slot, x, y)
            home = (x - dx, y - dy)
            self.pending.remove((slot, home))
            if at:
                self._add_unit(slot)
                self.used_spots.append((at[0] - dx, at[1] - dy))
                yen = self.reader.read_yen(self.p.grab())
                self.log(f"slot {slot} placed at {at}")
                self.auto_dirty = True
            else:
                self.tries[slot] = self.tries.get(slot, 0) + 1
                self.log(f"slot {slot} couldn't go down near ({x}, {y})")
                self.used_spots.append(home)  # refused: don't offer it again
                if self.tries[slot] < 3:
                    self.pending.append((slot, self.free_spot()))
            if self.should_stop():
                return

    def slot_has_card(self, slot: int, frame=None) -> bool:
        """A unit card in that hotbar slot (bright, or dimmed when it can't be afforded) rather than
        the empty dark slot. A placed unit's card leaves the hotbar, so this is the proof."""
        frame = self.p.grab() if frame is None else frame
        x = SLOT_X[slot - 1]
        patch = cv2.cvtColor(frame[700:768, x - 34:x + 34], cv2.COLOR_BGR2HSV)
        return float(patch[:, :, 2].mean()) > 36

    def place_unit(self, slot: int, x: int, y: int) -> tuple[int, int] | None:
        """Place a slot's unit at (or near) a spot; the spot it went to, or None. Checked by its
        card leaving the hotbar (a Yen drop is hidden by income too often)."""
        if not self.slot_has_card(slot):
            return None
        for ox, oy in ((0, 0), (0, 16), (16, 0), (-16, 0), (0, -16), (16, 16), (-16, 16), (0, 32)):
            self.p.key(str(slot))
            self.p.sleep(0.3)
            self.p.hover(x + ox, y + oy)
            self.p.sleep(0.4)
            self.p.click(x + ox, y + oy)
            self.p.hover(*AWAY)
            for _ in range(6):
                self.p.sleep(0.2)
                if not self.slot_has_card(slot):
                    return x + ox, y + oy
            self.p.key("z")  # still holding the unit: let go before the next spot
            self.p.sleep(0.2)
        return None

    # ------------------------------------------------------------ upgrades
    def _upgrade_order(self) -> list[int]:
        """Unit indexes in the user's role order, maxed ones left out."""
        order = []
        for role in self.settings.get("upgrade_order", ["farm", "dps", "support"]):
            order += [i for i, u in enumerate(self.units) if u["role"] == role]
        order += [i for i in range(len(self.units)) if i not in order]
        return [i for i in order if i not in self.maxed]

    def open_unit_manager(self) -> bool:
        for _ in range(2):
            if seen(self.p.grab(), "um_title") > 0.8:
                return True
            self.p.key("f")
            self.p.sleep(0.6)
        return seen(self.p.grab(), "um_title") > 0.8

    AUTO_ORDER = {"alchemist": 1, "atom": 2}  # then by role: farm 1, dps 3, support 5 (furnace.ROLE_PRIORITY)

    def set_auto_upgrades(self) -> None:
        """Every placed card's Auto Upgrade on, at its priority: farms first, so the Yen grows,
        then Atom, then the other damage dealers, supports last (Strict Auto-Upgrade Priority is
        set in the game: 1 is upgraded fully before 2)."""
        from macro.modes import furnace
        from macro.nav.navigator import Navigator
        if self.nav is None:
            self.nav = Navigator(self.p, log=lambda t: None)
        if not self.upgrades_paused:
            # The game keeps Auto Upgrading paused from match to match: a run that ended while the
            # Yen bank had it paused would leave the next run (any mode) without upgrades.
            furnace.set_auto_upgrading(self.p, self.nav, True, self.log)
        changed, right = furnace.set_auto_upgrades(self.p, self.nav, self.log, order=self.AUTO_ORDER, pages=3)
        self.close_unit_manager()
        self.auto_dirty = False

    AUTO_TOGGLE = (1202, 111)  # the Unit Manager's "Auto Upgrading": teal Active, red Paused

    def auto_upgrading(self) -> bool | None:
        """Whether the Unit Manager's Auto Upgrading is Active (opens it)."""
        if not self.open_unit_manager():
            return None
        x, y = self.AUTO_TOGGLE
        b, g, r = self.p.grab()[y - 6:y + 6, x - 30:x + 30].reshape(-1, 3).mean(axis=0)
        return g > r + 20

    def set_auto_upgrading(self, active: bool) -> None:
        state = self.auto_upgrading()
        if state is not None and state != active:
            self.p.click(*self.AUTO_TOGGLE)
            self.p.sleep(0.5)
            self.bank_toggles += 1
            if self.bank_toggles == 1:
                self.log("keeping 10,000 Yen for the shop: Auto Upgrading pauses under it from now on")
        self.close_unit_manager()
        self.upgrades_paused = not active

    def keep_yen_for_shop(self, yen: int | None, run_seconds: float) -> None:
        """Once the farms have had time to grow (2.5 min), keep a bank for the Checkpoint Shop's
        Anvils (user: "the anvil system and yen is very important"): pause Auto Upgrading under
        the bank, resume once it's 5,000 over."""
        keep = int((self.settings.get("shop") or {}).get("keep_for_shop", 10000) or 0)
        if not keep or yen is None or run_seconds < 150 or self.settings.get("upgrades", "auto") != "auto":
            return
        if not self.upgrades_paused and yen < keep:
            self.set_auto_upgrading(False)
        elif self.upgrades_paused and yen > keep + 5000:
            self.set_auto_upgrading(True)

    def upgrade_step(self) -> None:
        """One upgrade click on the first unit in the user's order that isn't maxed."""
        order = self._upgrade_order()
        if not order or not self.open_unit_manager():
            return
        index = order[0]
        slot = self.units[index]["slot"]
        if index >= len(UM_UPGRADE):
            self.maxed.add(index)  # beyond two rows the list scrolls: those stay as they are
            return
        text = ocr.read_line(self.p.grab(), UM_UPGRADE_TEXT[index], scale=2.5).lower()
        found = re.search(r"(\d+)\s*/\s*(\d+)", text)
        if "max" in text or (found and found.group(1) == found.group(2)):
            self.maxed.add(index)
            self.log(f"unit {index + 1} (slot {slot}) is maxed")
            return
        self.p.click(*UM_UPGRADE[index])

    # ------------------------------------------------------------ level-ups
    def pick_levelup(self, frame, priority_key: str = "levelup_priority", mark: str = "levelup") -> str:
        # The cards slide in: read once they're still (titles are words, not the payload's HP).
        names = []
        cards = []
        for _ in range(6):
            self.p.sleep(0.35)
            frame = self.p.grab()
            if mark == "anvil":
                cards = read_anvil_cards(frame)
                names = [" ".join(x for x in (c["rarity"], c["stat"], f"+{c['value']:g}%" if c["value"] else "") if x)
                         for c in cards]
                if sum(len(c["stat"]) >= 4 for c in cards) >= 2:
                    break
                continue
            names = [ocr.read_line(frame, box, scale=2.0) for box in LEVELUP_TITLES]
            if sum(bool(re.search(r"[A-Za-z]{4}", n)) for n in names) >= 2:
                break
        if mark == "anvil" and cards:
            choice = choose_anvil_card(cards, self.settings.get(priority_key, []))
            record_anvil_cards(cards, self.map_name)
            self.log("anvil cards: " + " | ".join(names))
        else:
            order = [n.lower() for n in self.settings.get(priority_key, [])]
            choice = 1
            for wanted in order:
                hit = [i for i, n in enumerate(names) if wanted.replace(" ", "") in n.lower().replace(" ", "")]
                if hit:
                    choice = hit[0]
                    break
        for _ in range(3):
            self.p.click(*LEVELUP_CARDS[choice])
            for _ in range(10):  # the cards take a moment to go
                self.p.sleep(0.25)
                if seen(self.p.grab(), mark) < 0.8:
                    return names[choice] or f"card {choice + 1}"
        return names[choice] or f"card {choice + 1}"


    # ------------------------------------------------------------ the run
    def close_unit_manager(self) -> None:
        if seen(self.p.grab(), "um_title") > 0.8:
            self.p.click(*UM_CLOSE)
            self.p.sleep(0.4)

    def play(self, placer, detector) -> RunResult:
        """Play the run to its results. The camera is set once; it follows the payload."""
        result = RunResult()
        start = time.time()
        self.placer = placer
        self.detector = detector
        self.run_start = start
        if not start_window(self.p.grab()):  # the window covers the payload's top
            setup_camera(self.p, self.log)
            self.camera_set = True
        costs = {} if start_window(self.p.grab()) else read_hotbar_costs(self.p.grab())
        if costs:
            self.log(f"hotbar prices: {costs}")
        last_upgrade = 0.0
        last_shot, last_hp, last_hp_read = 0.0, None, 0.0
        folder = os.path.join(ROOT, "cap", "expedition", time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(folder, exist_ok=True)
        self.folder = folder
        WALK_DEBUG_FOLDER[0] = folder
        _keep_last_runs(os.path.dirname(folder), 4)
        while not self.should_stop():
            frame = self.p.grab()
            screen = detector.classify(frame).name
            if time.time() - last_shot >= 10:  # a picture every 10 s, to see how a run went
                last_shot = time.time()
                cv2.imwrite(os.path.join(folder, f"{int(last_shot - start):05d}.jpg"),
                            cv2.resize(frame, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
                            [cv2.IMWRITE_JPEG_QUALITY, 80])
            if time.time() - last_hp_read >= 3:  # the Boss can take 1,000 HP in 30 s
                last_hp_read = time.time()
                hp = self.payload_hp(frame)
                if hp is not None and hp != last_hp:
                    self.log(f"payload {hp} HP at {time.time() - start:.0f} s")
                    last_hp = hp
                    self.max_hp = max(self.max_hp, hp)
                    self.use_hammer(hp)
            if screen in ("victory", "defeat"):
                result.outcome = screen
                break
            if screen in ("lobby", "game_loading", "black"):
                # Sent out of the run (a disconnect, a teleport): the runner's recovery takes over.
                away_since = away_since or time.time()
                if time.time() - away_since > 60:
                    self.log(f"out of the run for a minute ({screen}): giving it up")
                    result.outcome = "left"
                    break
            else:
                away_since = None
            if seen(frame, "anvil") > 0.85:
                picked = self.pick_levelup(frame, "anvil_priority", "anvil")
                result.notes.append(f"anvil: {picked}")
                self.log(f"Stat Anvil: {picked}")
                continue
            if seen(frame, "levelup") > 0.8:
                picked = self.pick_levelup(frame)
                result.levelups.append(picked)
                self.log(f"payload level-up: {picked}")
                continue
            if start_window(frame):
                # Units placed under this window are only phantoms (built later, cards kept), so
                # it's pressed first: the start is a checkpoint and waits for Continue anyway.
                self.close_unit_manager()
                press_start(self.p, self.log)
                if self.placed_order == [] and not self.camera_set:
                    setup_camera(self.p, self.log)
                    self.camera_set = True
                # Under that window the hotbar is the lobby's six slots: prices only now.
                self.p.sleep(0.5)
                costs.clear()
                costs.update(read_hotbar_costs(self.p.grab()))
                self.log(f"hotbar prices: {costs}")
                self.queue_new_cards(costs)
                continue
            if seen(frame, "map_title") > 0.8:
                # The Expedition Map, open when nothing asked for it (a click meant for a closed
                # Unit Manager card landed on its button): the run waits behind it.
                self.log("the Expedition Map was open: closing it")
                close_map(self.p)
                continue
            if seen(frame, "leave") > 0.85:
                self.log("an NPC dialog was left open: leaving it")
                leave_dialog(self.p)
                continue
            if seen(frame, "shop_title") > 0.85:
                self.p.click(*SHOP_BACK)
                self.p.sleep(0.8)
                continue
            score_c, at = where(frame, "continue")
            if score_c > 0.9:
                self.at_stop(frame, at, result, costs)
                if result.outcome == "extracted":
                    break
                continue
            yen = self.reader.read_yen(frame)
            if self.pending and yen is not None and any(yen >= costs.get(s, 0) for s, _ in self.pending):
                self.close_unit_manager()
                self.place_pending(placer, yen, costs)
                continue
            if self.settings.get("upgrades", "auto") == "auto":
                if self.auto_dirty and not self.pending_affordable(costs):
                    self.set_auto_upgrades()
                elif time.time() - self.last_bank_check > 4:
                    self.last_bank_check = time.time()
                    self.keep_yen_for_shop(yen, time.time() - start)
            elif time.time() - last_upgrade > 1.2:
                self.upgrade_step()
                last_upgrade = time.time()
            self.p.sleep(0.4)
        else:
            result.outcome = "stopped"
        result.seconds = time.time() - start
        result.placed = list(self.placed_order)
        return result

    def at_stop(self, frame, continue_at, result: RunResult, costs: dict[int, int]) -> None:
        """The start, a checkpoint or an encounter: nothing attacks, so spend, talk, then go on."""
        self.close_unit_manager()
        yen = self.reader.read_yen(self.p.grab())
        if self.pending:
            self.place_pending(self.placer, yen, costs)
        frame = self.p.grab()
        extract_here = seen(frame, "extract") > 0.8
        if extract_here and result.nodes not in self.route_checked:
            self.route_checked.add(result.nodes)
            if not self.route_ahead_ok(result):
                self.extract(result)
                return
        if extract_here and self.wants_extract(frame, result):
            self.extract(result)
            return
        if result.nodes not in self.talked:
            self.talked.add(result.nodes)
            zoom_out_for_npcs(self.p, self.log)
            frame = self.p.grab()
            if self.folder:
                cv2.imwrite(os.path.join(self.folder, f"stop{result.nodes}.jpg"),
                            cv2.resize(frame, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
            labels = find_label(frame, ("encounter", "hireable unit", "checkpoint shop"))
            self.log("at the stop: " + (", ".join(t for t, _, _ in labels) or "no NPCs read"))
            for text, x, y in labels:
                if "encounter" in text.lower().replace(" ", ""):
                    self.encounter(frame, x, y, result)
                    return  # the game moves on by itself after most encounters
            # The shop first (Anvils: the user's priority), hires with what's left.
            self.shop(find_label(self.p.grab(), ("checkpoint shop",)), result)
            self.hire(find_label(self.p.grab(), ("hireable unit",)) or labels, result, costs)
            self.use_items(result)
            self.keep_yen_for_shop(self.reader.read_yen(self.p.grab()), time.time() - self.run_start)
        new = read_hotbar_costs(self.p.grab())
        costs.update(new)
        self.queue_new_cards(new)
        # NPCs first (anvils, tomes and hires want the Yen), then upgrades while it's quiet.
        if self.settings.get("upgrades", "auto") == "auto":
            if self.auto_dirty:
                self.set_auto_upgrades()
        else:
            for _ in range(12):
                self.upgrade_step()
                self.p.sleep(0.25)
        self.close_unit_manager()
        frame = self.p.grab()
        score_c, at = where(frame, "continue")
        if score_c > 0.9:
            self.p.click(*at)
            self.p.sleep(0.8)
            self.p.click(*CONFIRM_CONTINUE)
            self.p.sleep(1.5)
            result.nodes += 1
            self.log(f"left node {result.nodes}")

    def encounter(self, frame, x: int, y: int, result: RunResult) -> None:
        names = [t for t, lx, ly in ocr.find_words(frame, (x - 160, y - 40, x + 160, y - 5))]
        name = max(names, key=len) if names else "?"
        table = dict(DEFAULT_ENCOUNTERS)
        table.update(self.settings.get("encounters") or {})
        choice = next((c for n, c in table.items() if n.lower() in name.lower()), "leave")
        self.log(f"encounter: {name} -> {choice}")
        result.notes.append(f"encounter {name}: {choice}")
        if choice == "leave":
            return
        if not walk_and_open(self.p, ("encounter",), lambda: wait_for(self.p, "leave", 1.5), (x, y + 45), log=self.log):
            self.log("couldn't reach the encounter")
            return
        talk_through(self.p, choice, self.log)
        self.p.sleep(1.0)
        if choice == "barter" and "hero" in name.lower():
            self.hire_names.append("The Hero")
        # A unit from the encounter (The Hero) lands in the hotbar: queue it for the tail.
        self.queue_new_cards(read_hotbar_costs(self.p.grab()))

    def hire(self, labels, result: RunResult, costs: dict[int, int]) -> None:
        cfg = self.settings.get("hire") or {}
        if not cfg.get("on") or self.hired >= int(cfg.get("max", 2)):
            return
        for text, x, y in labels:
            if "hireable" not in text.lower().replace(" ", "") or self.hired >= int(cfg.get("max", 2)):
                continue
            yen = self.reader.read_yen(self.p.grab()) or 0
            if yen < int(cfg.get("keep_yen", 5000)) + 3000:
                return
            if not walk_and_open(self.p, ("hireable unit",), lambda: wait_for(self.p, "leave", 1.5),
                                 (x, y + 45), log=self.log):
                self.log("couldn't reach a hire")
                continue
            if self.open_shop(quick=True) and seen(self.p.grab(), "shop_title") > 0.85:
                self.p.click(*SHOP_BACK)  # the shop opened instead: not a hire
                self.p.sleep(0.8)
                continue
            frame = self.p.grab()
            price = ocr.read_text(frame, (440, 680, 712, 718), scale=2.0).lower()
            found = re.search(r"([\d.,]+)\s*k", price)
            cost = float(found.group(1).replace(",", ".")) * 1000 if found else None
            unit = ocr.read_line(frame, (725, 288, 900, 306), scale=2.0)
            element = ocr.read_text(frame, (725, 320, 990, 345), scale=2.0).lower()
            is_farm = "farm" in element
            wanted = cfg.get("names") or []
            if is_farm:
                wanted = []  # a farm is always welcome (user: "focus on farms")
            if cost is None or cost > yen - int(cfg.get("keep_yen", 5000)) or (wanted and not any(w.lower() in unit.lower() for w in wanted)):
                leave_dialog(self.p)
                continue
            self.p.click(*HIRE_BUTTON)
            if not wait_for(self.p, "leave", 3.0, gone=True):
                leave_dialog(self.p)
                continue
            self.hired += 1
            self.log(f"hired {unit or 'a unit'} for about {cost:,.0f} Yen" + (" (a farm)" if is_farm else ""))
            result.notes.append(f"hired {unit}")
            self.next_hire_farm = is_farm
            self.hire_names.append(unit)
            self.p.sleep(0.8)
            self.queue_new_cards(read_hotbar_costs(self.p.grab()))

    # ------------------------------------------------------------ hotbar items (tomes, hammers, potions)
    def hotbar_items(self) -> dict[int, str]:
        """Item cards in the hotbar, by their label: slot -> "tome" / "hammer" / "potion" / text."""
        out = {}
        for text, x, y in ocr.find_words(self.p.grab(), (280, 740, 1160, 780)):
            if "¥" in text or re.search(r"\d{3}", text):
                continue  # a unit's price
            slot = min(range(10), key=lambda i: abs(SLOT_X[i] - x)) + 1
            low = text.lower()
            kind = "tome" if "tome" in low else "hammer" if ("hammer" in low or "repair" in low) else                 "anvil" if "anvil" in low else "potion" if "potion" in low else low
            out[slot] = kind
        return out

    def _item_name(self, slot: int) -> str:
        """The item's full name from its tooltip (hovering the hotbar card)."""
        self.p.hover(SLOT_X[slot - 1], 730)
        self.p.sleep(0.6)
        frame = self.p.grab()
        x = SLOT_X[slot - 1]
        return ocr.read_line(frame, (x - 175, 583, x + 60, 603), scale=2.0) or             ocr.read_text(frame, (x - 200, 570, x + 120, 615), scale=2.0)

    def _portrait(self, index: int) -> tuple[int, int] | None:
        if index >= len(self.units) or index >= len(UM_UPGRADE):
            return None
        bx, by = UM_UPGRADE[index]
        return bx - 35, by - 66

    def use_tome(self, item_slot: int, target: int, name: str) -> bool:
        """Tome in item_slot onto placed unit number target: its card found by name in the Unit
        Manager (summons get cards too, so places in the list can't be counted), the tome's key
        pressed ONCE (a second press puts it down again), the card's portrait clicked. Done when
        the tome's card leaves the hotbar."""
        from macro.modes import furnace
        from macro.nav.navigator import Navigator
        if self.nav is None:
            self.nav = Navigator(self.p, log=lambda t: None)
        key = card_key(self.units[target].get("name") or "")
        if not key:
            return False
        cards = furnace.unit_cards(self.p, self.nav, key, self.log, steps=8)
        if not cards:
            self.log(f"no {key} card in the Unit Manager for {name}")
            self.close_unit_manager()
            return False
        card = cards[0]
        self.close_unit_manager()
        self.p.hover(720, 120)
        self.p.sleep(0.3)
        self.p.key("0" if item_slot == 10 else str(item_slot))
        self.p.sleep(0.8)
        if not self.open_unit_manager():
            self.p.key("z")  # put the tome back rather than click about
            return False
        furnace._go_to_page(self.p, getattr(card, "page", 0))
        frame = self.p.grab()
        here = [c for c in furnace.read_cards(frame, ocr.find_words(frame, furnace.UM_PANEL)) if key in c.name]
        self.p.click(*furnace._portrait(here[0] if here else card))
        self.p.sleep(1.0)
        self.p.click(*furnace.UNIT_PANEL_CLOSE)  # the unit's panel opens either way
        self.p.sleep(0.4)
        self.close_unit_manager()
        self.p.hover(720, 120)
        self.p.sleep(0.4)
        if not self.slot_has_card(item_slot):
            self.log(f"{name} used on {self.units[target].get('name') or key}")
            self.units[target]["trait"] = name.replace("Tome", "").strip() or name
            self.tomed.add(target)
            return True
        self.p.key("z")  # still holding the tome: put it back
        self.log(f"{name} in slot {item_slot} didn't go onto {key}")
        return False

    def use_items(self, result: RunResult) -> None:
        """Tomes onto units (the user's rule for Unbound/Investor; another tome only onto a unit with
        no tome yet and no Unbound), kept hammers counted. Once per stop."""
        for slot, kind in sorted(self.hotbar_items().items()):
            if kind == "anvil":
                self.use_anvils(slot, result)
                continue
            if kind == "hammer":
                self.hammer_slots.add(slot)
                continue
            if kind != "tome" or not self.settings.get("use_dropped_tomes", True):
                continue
            name = self._item_name(slot) or "Tome"
            target = self.tome_wanted(name)
            if target is None and not any(k in name.lower() for k in ("unbound", "investor")):
                # A free tome only on a unit with no trait at all (it replaces the old one: a Bolt
                # Tome took Atom's Primordial on 15 Nov 2026).
                target = next((i for i in self._upgrade_order() + list(range(len(self.units)))
                               if self.units[i]["role"] != "farm" and i not in self.tomed
                               and not self.units[i]["trait"].strip() and self.may_tome(i)), None)
            if target is not None and self.use_tome(slot, target, name):
                result.notes.append(f"{name} on unit {target + 1}")

    def use_anvils(self, slot: int, result: RunResult) -> None:
        """Every Stat Anvil in a hotbar slot (they stack: "4x"): its key opens three stat cards,
        one is picked by the anvil priority (they'd auto-pick after ~25 s otherwise)."""
        for _ in range(12):
            if not self.slot_has_card(slot):
                return
            self.close_unit_manager()
            self.p.key("0" if slot == 10 else str(slot))
            if not wait_for(self.p, "anvil", 3.0):
                self.p.key("z")
                return
            picked = self.pick_levelup(self.p.grab(), "anvil_priority", "anvil")
            self.anvils_used += 1
            self.log(f"Stat Anvil {self.anvils_used}: {picked}")
            result.notes.append(f"anvil: {picked}")

    def use_hammer(self, hp: int | None) -> None:
        """A kept Repair Hammer (+500 HP) when the payload is hurt (under 60% of its health).
        Counted as used only when the payload's health rises: a selected card dims, which once
        passed for used while both hammers stayed in the hotbar (15 Nov 2026)."""
        if not self.hammer_slots or hp is None or hp >= 0.6 * max(self.max_hp, 1000):
            return
        slot = min(self.hammer_slots)
        self.p.key("0" if slot == 10 else str(slot))
        self.p.sleep(0.5)
        for at in (None, PAYLOAD_HOME, scaled(*START_GAME) if False else None):
            if at is not None:
                self.p.click(*at)
                self.p.sleep(0.6)
            after = self.payload_hp(self.p.grab())
            if after is not None and after >= hp + 300:
                self.hammer_slots.discard(slot)
                self.log(f"Repair Hammer used: {hp} -> {after} HP")
                return
        self.p.key("z")
        self.log(f"the Repair Hammer in slot {slot} didn't heal ({hp} HP): how it's used is still unknown")
        self.hammer_tries = getattr(self, "hammer_tries", 0) + 1
        if self.hammer_tries >= 2:
            self.hammer_slots.clear()  # don't keep trying mid-fight

    # ------------------------------------------------------------ the Checkpoint Shop
    def may_tome(self, index: int) -> bool:
        """Tomes change a unit's trait for good, so the player's own units only take one when
        the setting says so; units hired in the run always may."""
        return (not self.units[index].get("own")
                or bool((self.settings.get("shop") or {}).get("tomes_on_own", False)))

    def tome_wanted(self, tome: str) -> int | None:
        """The unit (index) a tome is for, by the user's rule: Unbound Tomes for normal units that
        aren't Unbound yet, Investor Tomes for farms that aren't Investor yet; nothing else."""
        tome = tome.lower()
        order = [i for i in self._upgrade_order() + list(range(len(self.units))) if self.may_tome(i)]
        if "unbound" in tome:
            for i in order:
                if self.units[i]["role"] != "farm" and "unbound" not in self.units[i]["trait"].lower():
                    return i
        if "investor" in tome:
            for i in order:
                if self.units[i]["role"] == "farm" and "investor" not in self.units[i]["trait"].lower():
                    return i
        return None

    def shop(self, labels, result: RunResult) -> None:
        cfg = self.settings.get("shop") or {}
        hp = self.payload_hp(self.p.grab())
        # One hammer a checkpoint (wiki), kept in the hotbar for the Boss, or bought when hurt.
        want_hammer = bool(cfg.get("hammers", True)) or (hp is not None and hp < int(cfg.get("repair_below", 0) or 0))
        yen = self.reader.read_yen(self.p.grab()) or 0
        if yen < 5000:
            self.log(f"shop skipped: {yen:,} Yen")
            return
        shop_at = next(((x, y) for t, x, y in labels if "checkpointshop" in t.lower().replace(" ", "")), None)
        if shop_at is None:
            self.log("shop skipped: Ramen Guy not in sight")
            return
        def shop_open() -> bool:
            return self.open_shop(quick=True)

        if not walk_and_open(self.p, ("checkpoint shop",), shop_open, (shop_at[0], shop_at[1] + 45),
                             log=self.log, avoid=lambda: leave_dialog(self.p)):
            self.log("shop skipped: couldn't open Ramen Guy's shop")
            leave_dialog(self.p)
            return
        def yen() -> int:
            """The shop hides the HUD's Yen and shows its own at the bottom right."""
            text = ocr.read_line(self.p.grab(), SHOP_YEN, scale=2.5)
            digits = re.sub(r"\D", "", text)
            return int(digits) if digits else 0

        self.log(f"shop open with {yen():,} Yen")

        def buy(at, price: int, what: str) -> bool:
            before = yen()
            if before < price:
                return False
            self.p.click(*at)
            self.p.sleep(1.0)
            after = yen()
            if after <= before - price * 0.9:
                self.log(f"bought {what} ({before:,} -> {after:,} Yen)")
                result.notes.append(what)
                return True
            self.log(f"{what} didn't sell ({before:,} -> {after:,} Yen)")
            return False

        for round_ in range(2 if cfg.get("refresh", True) else 1):
            # Anvils first (user, 15 Nov 2026: "the anvil system and yen is very important"): a random
            # Stat Anvil for the whole team, 5,000 Yen.
            if cfg.get("anvils", True) and buy(SHOP_ANVIL, 5000, "an Anvil"):
                self.anvils += 1
            for x, y in SHOP_TOMES:
                if not cfg.get("tomes", True) or yen() < 5000:
                    break
                self.p.hover(x, y)
                self.p.sleep(0.5)
                name = ocr.read_line(self.p.grab(), (x + 40, y - 45, x + 260, y - 25), scale=2.0)
                target = self.tome_wanted(name)
                if target is not None and buy((x, y), 5000, name or "a tome"):
                    self.tomes_bought.append((name, target))
            if want_hammer and buy(SHOP_HAMMER, 10000, f"a Repair Hammer (payload at {hp})"):
                self.hammers += 1
                want_hammer = False
            if round_ == 0 and cfg.get("refresh", True) and yen() >= 5000:
                self.p.click(*SHOP_REFRESH)  # new offers: maybe another Anvil or an Unbound Tome
                self.p.sleep(1.2)
            else:
                break
        for _ in range(3):
            self.p.click(*SHOP_BACK)
            if wait_for(self.p, "shop_title", 2.5, gone=True):
                break

    def open_shop(self, quick: bool = False) -> bool:
        """E at Ramen Guy opens the shop, or first a dialog whose buttons include the shop."""
        end = time.time() + (1.5 if quick else 5)
        while time.time() < end:
            frame = self.p.grab()
            if seen(frame, "shop_title") > 0.85:
                self.p.sleep(0.3)
                return True
            if seen(frame, "leave") > 0.85:
                self.p.sleep(0.4)
                words = ocr.find_words(self.p.grab(), (330, 670, 1110, 730))
                self.log("shop dialog buttons: " + ", ".join(t for t, _, _ in words))
                pick = [(t, x, y) for t, x, y in words if any(k in t.lower() for k in ("shop", "browse", "buy", "trade", "store"))]
                if not pick:
                    return False
                self.p.click(pick[0][1], pick[0][2])
                return wait_for(self.p, "shop_title", 4.0)
            self.p.sleep(0.15)
        return False

    def payload_hp(self, frame) -> int | None:
        text = ocr.read_line(frame, PAYLOAD_HP, scale=2.5).replace(" ", "")
        found = re.match(r"([\d,]+)/", text)
        return int(found.group(1).replace(",", "")) if found else None

    def pending_affordable(self, costs: dict[int, int]) -> bool:
        yen = self.reader.read_yen(self.p.grab()) or 0
        return any(yen >= costs.get(s, 10 ** 9) for s, _ in self.pending)

    def queue_new_cards(self, costs: dict[int, int]) -> None:
        """A priced card in the hotbar that's neither placed nor waiting (a hire, an encounter's unit)
        is queued for the next free spot, tail first."""
        waiting = {s for s, _ in self.pending}
        for slot in costs:  # a placed unit's card leaves the hotbar: a priced card isn't placed
            if slot not in waiting and self.tries.get(slot, 0) < 3:
                farm = getattr(self, "next_hire_farm", False)
                self.pending.append((slot, self.free_spot(head=farm)))
                if farm:
                    self.farm_slots.add(slot)
                    self.next_hire_farm = False
                self.log(f"slot {slot} (new card, {costs[slot]:,} Yen) queued for the payload")

    def free_spot(self, head: bool = False) -> tuple[int, int]:
        taken = set(self.used_spots) | {sp for _, sp in self.pending}
        for spot in (HEAD_SPOTS + MIDDLE_SPOTS + TAIL_SPOTS) if head else (TAIL_SPOTS + MIDDLE_SPOTS + HEAD_SPOTS):
            if spot not in taken:
                return spot
        return MIDDLE_SPOTS[0]

    def route_ahead_ok(self, result: RunResult) -> bool:
        """At a checkpoint (where Extract is offered): does the rest of the route still meet the
        map's minimums? Each node of the next column is tried (the game routes the rest) and the
        best one is left selected. When none does, the run is extracted (it keeps what it has
        earned) and a fresh one rerolled (user, 15 Nov 2026). No minimums set: always yes."""
        rule = self.rule or {}
        wanted = [k for k, m in (rule.get("minimums") or {}).items() if m.get("on")]
        if not wanted or not (self.settings.get("extract") or {}).get("route_check", True):
            return True
        if not open_map(self.p):
            return True
        column = next_column(self.p.grab())
        if column is None:
            close_map(self.p)
            return True  # the Boss is next: finish the run
        # Route Rewards mid-run count only the nodes ahead, so the minimums are scaled to the share
        # of the route that's left: half the route ahead needs half of each minimum to beat a reroll.
        share = ahead_share(column)
        scaled_rule = dict(rule, minimums={k: {**m, "min": math.ceil(int(m.get("min", 0)) * share)}
                                           for k, m in (rule.get("minimums") or {}).items()})
        rewards, ok = choose_route(self.p, scaled_rule, self.log, column=column)
        close_map(self.p)
        need = ", ".join(f"{k} {m['min']}" for k, m in scaled_rule["minimums"].items() if m.get("on"))
        self.log(f"route ahead from column {column + 1} (needs {need}): {rewards.text()}"
                 + (" -> continuing" if ok else " -> below the minimums, extracting"))
        result.notes.append(f"checkpoint at column {column + 1}: {'continue' if ok else 'extract'}")
        return ok

    def wants_extract(self, frame, result: RunResult) -> bool:
        cfg = self.settings.get("extract") or {}
        rule = cfg.get("rule", "never")
        if rule == "after_nodes":
            return result.nodes >= int(cfg.get("after_nodes", 10))
        if rule == "hp_below":
            hp = ocr.read_line(frame, (650, 377, 790, 392), scale=2.5)
            found = re.match(r"([\d,]+)", hp.replace(" ", ""))
            return bool(found) and int(found.group(1).replace(",", "")) < int(cfg.get("hp_below", 250))
        return False

    def extract(self, result: RunResult) -> None:
        """Extract: the run ends here and keeps what it has earned. Confirms whatever the game asks
        and waits for the results window."""
        self.log("extracting: the run ends here with what it has earned")
        if self.upgrades_paused:
            self.set_auto_upgrading(True)  # the game would keep it paused for the next match
        self.close_unit_manager()
        self.p.click(*EXTRACT)
        self.p.sleep(1.2)
        for _ in range(3):
            frame = self.p.grab()
            if self.detector is not None and self.detector.classify(frame).name in ("victory", "defeat"):
                break
            buttons = [(t, x, y) for t, x, y in ocr.find_words(frame, (300, 250, 1140, 600))
                       if any(k in t.lower() for k in ("extract", "yes", "confirm"))]
            if buttons:
                self.log("extract dialog: " + ", ".join(t for t, _, _ in buttons))
                self.p.click(buttons[-1][1], buttons[-1][2])
            self.p.sleep(2.0)
        end = time.time() + 20
        while time.time() < end:
            if self.detector is not None and self.detector.classify(self.p.grab()).name in ("victory", "defeat"):
                break
            self.p.sleep(0.5)
        result.outcome = "extracted"


# ----------------------------------------------------------------------------- rerolling
def open_map(p) -> bool:
    """Open the Expedition Map and wait until it has drawn: Route Rewards and the first column's
    nodes both showing (it fades in; at 30 fps a read straight away found nothing)."""
    p.click(*MAP_BUTTON)
    end = time.time() + 6
    while time.time() < end:
        p.sleep(0.2)
        frame = p.grab()
        if _tile_present(frame, 0) and find_nodes(frame, 0):
            p.sleep(0.3)
            return True
    return _tile_present(p.grab(), 0)


def close_map(p) -> None:
    p.click(*MAP_BACK)
    p.sleep(0.5)


def ensure_started(p, log=None) -> None:
    """Past the "Start Game?" window: before it's pressed, Settings has no Restart Game (Back To
    Lobby sits where it would be), and units placed are only phantoms."""
    if start_window(p.grab()):
        press_start(p, log)
        end = time.time() + 6
        while time.time() < end and seen(p.grab(), "continue") < 0.9:
            p.sleep(0.3)


def restart_run(p, log=None) -> bool:
    """Settings -> Restart Game -> Restart: a fresh map in ~3 s, at no cost. Each screen is checked
    before its click: a click into that Settings list where Restart Game isn't would flip a setting
    (on 15 Nov 2026 Auto Vote Start was found switched on, which broke the Soul Furnace farm)."""
    ensure_started(p, log)
    p.click(*SETTINGS_GEAR)
    if not wait_for(p, "restart_row", 3.0):
        if log:
            log("Settings didn't show Restart Game: closing it")
        p.click(*SETTINGS_CLOSE)
        p.sleep(0.6)
        return False
    p.click(*RESTART_GAME)
    if not wait_for(p, "restart_confirm", 3.0):
        if log:
            log("no Restart Confirmation: closing Settings")
        p.click(*SETTINGS_CLOSE)
        p.sleep(0.6)
        return False
    p.click(*RESTART_CONFIRM)
    end = time.time() + 15
    while time.time() < end:  # the new run's start
        p.sleep(0.4)
        if run_started(p.grab()):
            return True
    return False


OPENER_ORDER = ("defense", "checkpoint", "encounter", "unknown", "elite", "assault")  # safest first node first


MAP_PROGRESS = (95, 166, 214, 187)  # "Map Progress 4 / 10"


_HERE = None


def next_column(frame) -> int | None:
    """The column after the payload's place on the open map, by the gold wheel that marks it
    (OCR of "Map Progress n/10" read a 7 as a 1 once); None at the Boss."""
    global _HERE
    if _HERE is None:
        _HERE = cv2.cvtColor(cv2.imread(os.path.join(DATA, "here.png")), cv2.COLOR_BGR2GRAY)
    gray = cv2.cvtColor(frame[140:660, 40:1300], cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(gray, _HERE, cv2.TM_CCOEFF_NORMED)
    _, value, _, at = cv2.minMaxLoc(result)
    if value < 0.7:
        progress = map_progress(frame)
        return None if progress is None else progress - 1
    x = 40 + at[0] + _HERE.shape[1] // 2
    if x < 150:
        return 0  # still at the start
    here = min(range(len(COLUMN_X)), key=lambda i: abs(COLUMN_X[i] - x))
    return here + 1 if here + 1 < len(COLUMN_X) else None


def ahead_share(column: int) -> float:
    """The share of a route still ahead when the next column is `column` (0-based; the Boss after
    the last column counts as one more node)."""
    nodes = len(COLUMN_X) + 1
    return max(1, min(nodes, nodes - column)) / nodes


def map_progress(frame) -> int | None:
    found = re.search(r"(\d+)\s*/\s*10", ocr.read_line(frame, MAP_PROGRESS, scale=2.5))
    return int(found.group(1)) if found else None


def choose_route(p, rule: dict, log, column: int = 0) -> tuple[Rewards, bool]:
    """With the map open: route through a first-column node (the game routes the rest) and read
    Route Rewards. The safest opener is tried first (an Assault opener with only the starting Yen
    lost every time on 15 Nov 2026, so it's refused when the rule says so); the others only when it
    doesn't qualify. The best one tried is left selected. Returns (its rewards, met?)."""
    frame = p.grab()
    first = sorted(find_nodes(frame, column), key=lambda n: OPENER_ORDER.index(n[0]) if n[0] in OPENER_ORDER else 9)
    safe_only = rule.get("avoid_assault_first", True) and column == 0
    if not first:  # no node recognised: the route as it is
        current = read_route_rewards(frame)
        return current, meets(current, rule)
    tried: list[tuple[bool, float, Rewards, tuple[int, int], str]] = []
    for kind, x, y in first:
        if safe_only and kind == "assault" and tried:
            break  # a safer opener was there and didn't qualify: an Assault won't be taken anyway
        p.click(x, y)
        p.sleep(0.6)
        p.hover(*AWAY)
        p.sleep(0.25)
        rewards = read_route_rewards(p.grab())
        ok = meets(rewards, rule) and not (safe_only and kind == "assault")
        tried.append((ok, score(rewards, rule), rewards, (x, y), kind))
        if ok:
            break
    best = max(tried, key=lambda c: (c[0], c[1]))
    if best is not tried[-1]:
        p.click(*best[3])
        p.sleep(0.6)
    log(f"route through the {'first-column' if column == 0 else 'next'} {best[4]}" + ("" if best[0] else " (doesn't qualify)"))
    return best[2], best[0]


def reroll(p, rule: dict, log, should_stop) -> tuple[Rewards | None, int]:
    """Restart until a route meets the rule. Returns the rewards of the route left selected and the
    number of restarts; None when the user's "when none qualifies" says skip or stop."""
    best_seen: tuple[float, int] | None = None
    rolls = 0
    while True:
        if should_stop():
            return None, rolls
        if not open_map(p):
            log("the Expedition Map didn't open")
            return None, rolls
        rewards, ok = choose_route(p, rule, log)
        log(f"roll {rolls + 1}: {rewards.text()}" + (" -> keeping it" if ok else ""))
        if ok or not rule.get("reroll", True):
            close_map(p)
            return rewards, rolls
        here = score(rewards, rule)
        if best_seen is None or here > best_seen[0]:
            best_seen = (here, rolls)
        if rolls >= int(rule.get("max_rerolls", 50)):
            what = rule.get("when_none", "best")
            close_map(p)
            log(f"no roll met the minimums in {rolls} restarts: {what}")
            if what in ("current", "best"):
                # The best roll can't be brought back once restarted away from; the current one
                # is played (it's the last of the best ones when "best" scores tie).
                return rewards, rolls
            return None, rolls
        close_map(p)
        if not restart_run(p, log):
            log("the restart didn't go through: trying once more")
            if not restart_run(p, log):
                return rewards, rolls  # play this one rather than click about blind
        rolls += 1


PAYLOAD_TEMPLATE = os.path.join(DATA, "payload.png")
PAYLOAD_HOME = (710, 408)  # the payload's centre in the placing view (reference.png)
_payload_tpl = None


def find_payload(frame) -> tuple[float, float, float, float]:
    """(score, scale, x, y) of the payload against the placing view's picture of it. The score is
    modest (units and ground change), but the scale is a reliable guide to the zoom."""
    global _payload_tpl
    if _payload_tpl is None:
        _payload_tpl = cv2.cvtColor(cv2.imread(PAYLOAD_TEMPLATE), cv2.COLOR_BGR2GRAY)
    gray = cv2.cvtColor(frame[60:700, 300:1140], cv2.COLOR_BGR2GRAY)
    best = (0.0, 1.0, float(PAYLOAD_HOME[0]), float(PAYLOAD_HOME[1]))
    for scale in np.arange(0.40, 1.16, 0.05):
        tpl = cv2.resize(_payload_tpl, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, value, _, at = cv2.minMaxLoc(result)
        if value > best[0]:
            best = (float(value), float(scale), 300 + at[0] + tpl.shape[1] / 2, 60 + at[1] + tpl.shape[0] / 2)
    return best


def setup_camera(p, log=None) -> None:
    """Overhead, fully out, then in a notch at a time until the payload is the size it is in the
    placing view (a wheel notch is sometimes ignored, so counting notches isn't enough)."""
    maps.set_overhead_camera(p)
    for _ in range(ZOOM_IN_NOTCHES + 6):
        score_, scale, _, _ = find_payload(p.grab())
        if scale >= 0.95:
            break
        p.hover(720, 250)
        p.sleep(0.15)
        p.move_rel(2, 0)
        p.sleep(0.1)
        p.scroll(-maps.NOTCH)
        p.sleep(0.5)
    if log:
        log(f"placing view: payload at scale {find_payload(p.grab())[1]:.2f}")
    p.move_rel(1, 0)
    p.move_rel(-1, 0)


# ----------------------------------------------------------------------------- hotbar
SLOT_X = [328 + 87 * k for k in range(10)]  # the Expedition hotbar has ten slots (7-10: hires)
HOTBAR_PRICES = (280, 742, 1160, 774)


def read_hotbar_costs(frame: np.ndarray) -> dict[int, int]:
    """Each slot's price ("¥1,250"), read twice at two sizes; a price counts when both agree."""
    def once(scale: float) -> dict[int, int]:
        x0, y0, x1, y1 = HOTBAR_PRICES
        crop = frame[y0:y1, x0:x1]
        if scale != 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        result, _ = ocr._get_engine()(crop, use_cls=False)
        found = {}
        for corners, text, _ in result or []:
            middle = x0 + sum(c[0] for c in corners) / 4 / scale
            slot = min(range(10), key=lambda i: abs(SLOT_X[i] - middle))
            digits = re.sub(r"\D", "", text)
            if digits and abs(SLOT_X[slot] - middle) < 40:
                found[slot + 1] = int(digits)
        return found
    first, second = once(1.0), once(2.0)
    return {slot: value for slot, value in first.items() if second.get(slot) == value}


# ----------------------------------------------------------------------------- NPCs
CHARACTER = (720, 405)  # the camera follows the character: it stands about mid-frame
WALK_PX_PER_S = 190.0  # fully zoomed out, roughly (a 0.7 s hold moved ~130 px); re-aimed each leg
ENCOUNTER_CHOICES = {"discuss": (432, 699), "barter": (624, 699), "engage": (816, 699), "leave": (1008, 699)}
DIALOG_NEXT = (720, 645)
DIALOG_YES, DIALOG_NO = (575, 700), (863, 700)
HIRE_BUTTON, HIRE_LEAVE = (576, 699), (864, 699)
SHOP_TOMES = [(395, 255), (528, 255), (658, 255)]
SHOP_HAMMER, SHOP_ANVIL = (430, 405), (625, 405)
SHOP_BUY_ALL, SHOP_REFRESH, SHOP_BACK = (528, 554), (528, 609), (126, 739)
SHOP_YEN = (1265, 722, 1400, 760)  # the shop's own "¥ 650" (the HUD's is hidden)
PAYLOAD_HP = (650, 377, 790, 392)  # "960 / 1,000" over the payload
# What to say to each encounter (wiki + seen): The Hero's Barter is ¥500 for a fully upgraded unit.
DEFAULT_ENCOUNTERS = {"The Hero": "barter", "String Demon": "leave", "Elf Mage": "leave",
                      "Crow": "leave", "8th Sword": "leave", "The Drink": "leave"}


def wait_for(p, name: str, timeout: float = 4.0, gone: bool = False) -> bool:
    """Until a screen mark shows (or, with gone, until it's gone). Dialogs slide in and out, and a
    click during that is lost (seen at 30 fps)."""
    end = time.time() + timeout
    while time.time() < end:
        here = seen(p.grab(), name) > 0.85
        if here != gone:
            p.sleep(0.3)  # let the slide finish
            return True
        p.sleep(0.15)
    return False


def leave_dialog(p) -> bool:
    """Click an open dialog's Leave until it's gone."""
    for _ in range(3):
        score_, at = where(p.grab(), "leave")
        if score_ < 0.85:
            return True
        p.click(*at)
        if wait_for(p, "leave", 2.5, gone=True):
            return True
    return False


def find_label(frame: np.ndarray, words: tuple[str, ...]) -> list[tuple[str, int, int]]:
    """On-screen text lines containing one of words (lower case), as (text, x, y)."""
    found = []
    keys = [w.replace(" ", "") for w in words]
    for text, x, y in ocr.find_words(frame, (0, 60, 1260, 690)):
        low = text.lower().replace(" ", "")  # OCR runs words together: "HireableUnit"
        if any(k in low for k in keys):
            found.append((text, x, y))
    return found


def prompt_showing(frame: np.ndarray, word: str | None = None) -> bool:
    """Roblox's proximity prompt near the character: "E Speak" at Ramen Guy, "E Interact" at a
    hire or an encounter. With word, only that one (the shop stands among the hires)."""
    return bool(find_label(frame, (word,) if word else ("interact", "speak")))


WALK_DEBUG_FOLDER = [None]  # the run's picture folder, for a walk that didn't arrive


def zoom_out_for_npcs(p, log=None) -> None:
    """NPC labels sit beyond the placing view: look from fully zoomed out. Checked by the payload's
    size, as wheel notches get dropped (seen at 30 fps)."""
    for attempt in range(3):
        if attempt == 0:
            maps.set_overhead_camera(p)
        else:
            p.hover(720, 250)
            p.sleep(0.2)
            p.move_rel(3, 0)
            p.sleep(0.15)
            for _ in range(maps.ZOOM_OUT_NOTCHES):
                p.scroll(maps.NOTCH)
                p.sleep(0.08)
        p.sleep(0.5)
        scale = find_payload(p.grab())[1]
        if scale <= 0.6:
            return
        if log:
            log(f"zooming out for the NPCs: payload still at scale {scale:.2f}")


def walk_to(p, words: tuple[str, ...], first: tuple[int, int] | None = None, legs: int = 5, log=None,
            prompt: str | None = None) -> bool:
    """Walk the character to the NPC whose label has one of words, until its "E" prompt shows.
    The label is found again after every leg (the camera follows the character)."""
    target = first
    for _ in range(legs):
        frame = p.grab()
        if prompt_showing(frame, prompt):
            return True
        if target is None:
            found = find_label(frame, words)
            if not found:
                if log:
                    log(f"lost sight of {words[0]}")
                return False
            _, lx, ly = min(found, key=lambda f: abs(f[1] - CHARACTER[0]) + abs(f[2] - CHARACTER[1]))
            target = (lx, ly + 45)  # the label floats over the NPC's head
        dx, dy = target[0] - CHARACTER[0], target[1] - CHARACTER[1]
        if abs(dx) > 20:
            p.key("d" if dx > 0 else "a", hold=min(2.5, abs(dx) / WALK_PX_PER_S))
        if abs(dy) > 20:
            p.key("s" if dy > 0 else "w", hold=min(2.5, abs(dy) / WALK_PX_PER_S))
        p.sleep(0.5)
        target = None
    frame = p.grab()
    if prompt_showing(frame, prompt):
        return True
    if WALK_DEBUG_FOLDER[0]:
        cv2.imwrite(os.path.join(WALK_DEBUG_FOLDER[0], f"walk_{words[0].replace(' ', '')}_{int(time.time())}.jpg"),
                    cv2.resize(frame, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
        if log:
            log("walk failed; prompts read: " + ", ".join(t for t, _, _ in find_label(frame, ("interact", "speak", "e "))))
    return False


def walk_and_open(p, words: tuple[str, ...], opened, first: tuple[int, int] | None = None, legs: int = 8,
                  log=None, avoid=None) -> bool:
    """Walk to the NPC labelled with words and press E until opened() says its window is up.
    NPCs stand packed together, so the "E" prompt is often for a neighbour or not read at all:
    within ~70 px the key is simply pressed and what opened is looked at; avoid() closes a wrong
    one (a hire's dialog when the shop was wanted)."""
    target = first
    misses = 0
    for leg in range(legs):
        frame = p.grab()
        if leg and prompt_showing(frame):
            # Arrived: the prompt even covers the NPC's label.
            p.key("e")
            p.sleep(1.3)
            if opened():
                return True
            if avoid is not None:
                avoid()
        if target is None:
            found = find_label(frame, words)
            if not found:
                misses += 1  # OCR misses a label now and then, or another one covers it
                if misses >= 3:
                    if log:
                        log(f"lost sight of {words[0]}")
                    return False
                p.sleep(0.4)
                continue
            misses = 0
            _, lx, ly = min(found, key=lambda f: abs(f[1] - CHARACTER[0]) + abs(f[2] - CHARACTER[1]))
            target = (lx, ly + 45)
        dx, dy = target[0] - CHARACTER[0], target[1] - CHARACTER[1]
        if abs(dx) < 70 and abs(dy) < 70 or prompt_showing(frame):
            p.key("e")
            p.sleep(1.3)
            if opened():
                return True
            if avoid is not None:
                avoid()
        # Shorter legs as it closes in (the walk speed in pixels is only roughly known).
        share = 1.0 if max(abs(dx), abs(dy)) > 200 else 0.6
        if abs(dx) > 15:
            p.key("d" if dx > 0 else "a", hold=min(2.5, share * abs(dx) / WALK_PX_PER_S))
        if abs(dy) > 15:
            p.key("s" if dy > 0 else "w", hold=min(2.5, share * abs(dy) / WALK_PX_PER_S))
        p.sleep(0.5)
        target = None
    if WALK_DEBUG_FOLDER[0]:
        cv2.imwrite(os.path.join(WALK_DEBUG_FOLDER[0], f"walk_{words[0].replace(' ', '')}_{int(time.time())}.jpg"),
                    cv2.resize(p.grab(), None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
    return False


def talk_through(p, choice: str, log) -> None:
    """An open encounter dialog: pick the option, click through the lines, accept."""
    p.click(*ENCOUNTER_CHOICES[choice])
    p.sleep(1.2)
    if choice == "leave":
        return
    for _ in range(8):
        frame = p.grab()
        words = " ".join(t for t, _, _ in ocr.find_words(frame, (330, 640, 1110, 730))).lower()
        if "yes" in words:
            p.click(*DIALOG_YES)
            p.sleep(1.2)
            continue
        if not words and not ocr.read_text(frame, (450, 560, 990, 630)):
            return
        p.click(*DIALOG_NEXT)
        p.sleep(1.0)


# ----------------------------------------------------------------------------- getting in
REPEAT_STAGE = (400, 639)  # on the results


def read_difficulty(frame) -> int | None:
    found = re.search(r"(\d)", ocr.read_text(frame, DIFF_TEXT, scale=2.5))
    return int(found.group(1)) if found else None


def pick_stage(p, map_name: str, difficulty: int, log) -> None:
    """On the Expedition picker: the map, then - / + until the difficulty reads right (the
    picker remembers the last one, so it's read rather than assumed)."""
    p.click(*MAP_BUTTONS[map_name])
    p.sleep(0.8)
    for _ in range(6):
        now = read_difficulty(p.grab())
        if now == difficulty:
            log(f"Expedition picker: {map_name}, difficulty {difficulty}")
            return
        p.click(*(DIFF_PLUS if now is None or now < difficulty else DIFF_MINUS))
        p.sleep(0.6)
    raise RuntimeError(f"the Expedition difficulty never read {difficulty}")
