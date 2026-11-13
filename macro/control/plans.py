"""A plan: everything a player can set for a map, as plain data.

  data/maps/<map>/layouts/<name>.yaml
    units:   per hotbar slot: priority, how many to place, where (in reference.png's pixels),
             how far to upgrade, targeting, and from which wave
    steps:   the build order: each is "place" or "upgrade" for one unit's spot. Generated from
             the units, and can be reordered by hand.

A plan can hold anything a person typed, so loading NEVER fails on a bad value. normalize() turns
each into the nearest thing that makes sense and notes it in Plan.notes. So "upgrade to 9" stays
9 here, and the engine stops when the game says it's maxed. Only the game knows the real limits.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

from macro.control.placing import on_hud
from macro.vision.screens import ROOT

MAPS = os.path.join(ROOT, "data", "maps")
SLOTS = (1, 2, 3, 4, 5, 6)
TARGETING = ("First", "Last", "Closest", "Strongest", "Boss", "Weakest", "Shielded", "Fastest")
DEFAULT_UPGRADE_ROUNDS = 3  # in a generated order; anything more comes from the finishing pass


def _number(value, default=None):
    """Whatever was typed as a whole number, or default. "9", 9.0, " 9 lvl" all give 9."""
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else default


@dataclass
class UnitPlan:
    slot: int
    priority: int = 50  # lower goes first
    count: int | None = None  # how many of its spots to use; None means all of them
    upgrade_to: int | None = None  # None means as far as the game allows
    targeting: str | None = None  # None leaves the game's setting alone
    from_wave: int = 1
    enabled: bool = True
    spots: list[list[int]] = field(default_factory=list)
    # The game's own Auto Upgrade for this unit, switched on as each one is placed: for farms,
    # which should go to max as soon as the Yen allows without the plan spelling it out.
    auto_upgrade: bool = False
    # Whether that happens as each one is placed (True) or at an "auto" step in the order
    # (False): auto upgrade is greedy, and farms on it from the start starve the defence.
    auto_on_place: bool = True
    auto_priority: int = 1  # the game's auto-upgrade priority: 1 first, up to 6
    farm: bool = False  # makes Yen: may be slipped in early while a bigger move waits

    @property
    def used_spots(self) -> list[list[int]]:
        return self.spots if self.count is None else self.spots[:self.count]


@dataclass
class Plan:
    map: str
    name: str
    units: list[UnitPlan] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)  # {do: place|upgrade, slot, spot}
    custom_order: bool = False  # the player arranged steps; regenerate only when asked
    notes: list[str] = field(default_factory=list)

    def unit(self, slot: int) -> UnitPlan | None:
        return next((u for u in self.units if u.slot == slot), None)

    def by_priority(self) -> list[UnitPlan]:
        return sorted((u for u in self.units if u.enabled), key=lambda u: (u.priority, u.slot))

    def point(self, step: dict) -> list[int] | None:
        unit = self.unit(step["slot"])
        if unit and 0 <= step["spot"] < len(unit.spots):
            return unit.spots[step["spot"]]
        return None


def _clean_spots(raw, slot: int, notes: list[str], width: int, height: int) -> list[list[int]]:
    spots = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            notes.append(f"slot {slot}: ignored a spot that isn't a point: {item!r}")
            continue
        x, y = _number(item[0]), _number(item[1])
        if x is None or y is None:
            notes.append(f"slot {slot}: ignored a spot without numbers: {item!r}")
        elif not (0 <= x < width and 0 <= y < height):
            notes.append(f"slot {slot}: ignored ({x}, {y}), which is off the picture")
        elif on_hud(x, y):
            notes.append(f"slot {slot}: ignored ({x}, {y}), which is over the game's buttons")
        else:
            spots.append([x, y])
    return spots


def normalize(raw: dict | None, map_name: str, name: str, width: int = 1440, height: int = 810) -> Plan:
    """Anything in, a runnable plan out. Each change made is explained in plan.notes."""
    plan = Plan(map_name, name)
    notes = plan.notes
    raw = raw if isinstance(raw, dict) else {}
    seen: dict[int, UnitPlan] = {}
    for entry in raw.get("units") if isinstance(raw.get("units"), list) else []:
        if not isinstance(entry, dict):
            notes.append(f"ignored a unit entry that isn't settings: {entry!r}")
            continue
        slot = _number(entry.get("slot"))
        if slot not in SLOTS:
            notes.append(f"ignored a unit in slot {entry.get('slot')!r}: slots are 1 to 6")
            continue
        if slot in seen:
            notes.append(f"slot {slot} was listed twice, so its spots were combined")
            seen[slot].spots += _clean_spots(entry.get("spots"), slot, notes, width, height)
            continue
        unit = UnitPlan(slot)
        priority = _number(entry.get("priority"))
        if priority is None and entry.get("priority") is not None:
            notes.append(f"slot {slot}: priority {entry['priority']!r} isn't a number, so it's last")
        unit.priority = priority if priority is not None else 50
        count = entry.get("count")
        if count is not None:
            unit.count = _number(count)
            if unit.count is None:
                notes.append(f"slot {slot}: placements {count!r} isn't a number, so all its spots are used")
        upgrade = entry.get("upgrade_to")
        if upgrade not in (None, "", "max", "Max", "MAX"):
            unit.upgrade_to = _number(upgrade)
            if unit.upgrade_to is None:
                notes.append(f"slot {slot}: upgrade {upgrade!r} isn't a number, so it goes to max")
        targeting = entry.get("targeting")
        if targeting not in (None, "", "Leave"):
            match = next((t for t in TARGETING if t.lower() == str(targeting).strip().lower()), None)
            if match is None:
                notes.append(f"slot {slot}: targeting {targeting!r} isn't known, so it's left alone")
            unit.targeting = match
        from_wave = _number(entry.get("from_wave"), 1)
        unit.from_wave = max(1, from_wave)
        unit.enabled = entry.get("enabled", True) is not False
        unit.auto_upgrade = entry.get("auto_upgrade") in (True, "true", "yes", 1, "later")
        unit.auto_on_place = entry.get("auto_upgrade") != "later"
        unit.spots = _clean_spots(entry.get("spots"), slot, notes, width, height)
        if unit.count is not None and unit.count > len(unit.spots):
            notes.append(f"slot {slot}: asked for {unit.count} placements but only {len(unit.spots)} are "
                         "marked, so only those are used")
        seen[slot] = unit
    plan.units = [seen[s] for s in sorted(seen)]
    plan.custom_order = bool(raw.get("custom_order"))

    steps = []
    for step in raw.get("steps") if isinstance(raw.get("steps"), list) else []:
        if not isinstance(step, dict) or step.get("do") not in ("place", "upgrade", "auto"):
            notes.append(f"ignored a step that isn't place, upgrade or auto: {step!r}")
            continue
        slot, spot = _number(step.get("slot")), _number(step.get("spot"))
        unit = seen.get(slot)
        if unit is None or spot is None or spot >= len(unit.spots):
            notes.append(f"ignored a step for a unit or spot that doesn't exist: {step!r}")
            continue
        if step["do"] == "upgrade" and unit.auto_upgrade:
            continue  # it upgrades itself
        steps.append({"do": step["do"], "slot": slot, "spot": spot})
    plan.steps = steps
    reconcile(plan)
    return plan


def generate_steps(plan: Plan) -> list[dict]:
    """A sensible order from the units: everyone's first placement by priority, then a round of
    upgrades and the next placements. The finishing pass in the engine takes it to the end."""
    units = plan.by_priority()
    steps = [{"do": "place", "slot": u.slot, "spot": 0} for u in units if u.used_spots]
    deepest = max((len(u.used_spots) for u in units), default=0)
    for level in range(1, max(DEFAULT_UPGRADE_ROUNDS, deepest) + 1):
        for unit in units:
            spots = unit.used_spots
            limit = DEFAULT_UPGRADE_ROUNDS if unit.upgrade_to is None else unit.upgrade_to
            for spot in range(min(level, len(spots))):
                if level - spot <= limit and level - spot >= 1:
                    steps.append({"do": "upgrade", "slot": unit.slot, "spot": spot})
            if level < len(spots):
                steps.append({"do": "place", "slot": unit.slot, "spot": level})
    return steps


def reconcile(plan: Plan):
    """Keep steps in line with the units after edits: drop steps for removed or disabled spots,
    add a placement for new ones, and place before upgrading."""
    if not plan.steps:
        plan.steps = generate_steps(plan)
        return
    valid = {(u.slot, i) for u in plan.by_priority() for i in range(len(u.used_spots))}
    kept, placed = [], set()
    for step in plan.steps:
        key = (step["slot"], step["spot"])
        if key not in valid:
            continue
        if step["do"] == "place":
            if key in placed:
                continue
            placed.add(key)
        elif key not in placed:
            kept.append({"do": "place", "slot": key[0], "spot": key[1]})
            placed.add(key)
        kept.append(step)
    for unit in plan.by_priority():
        for i in range(len(unit.used_spots)):
            if (unit.slot, i) not in placed:
                kept.append({"do": "place", "slot": unit.slot, "spot": i})
    plan.steps = kept


def path(map_name: str, name: str) -> str:
    return os.path.join(MAPS, map_name, "layouts", name + ".yaml")


def from_old_steps(raw: dict) -> dict:
    """The earlier format, a flat list of {place: slot, at} and {upgrade: point, cost}."""
    units: dict[int, dict] = {}
    where: dict[tuple, tuple] = {}
    steps = []
    order = 1
    for step in raw.get("steps") or []:
        if "place" in step:
            slot = int(step["place"])
            unit = units.setdefault(slot, {"slot": slot, "priority": order, "spots": []})
            if len(unit["spots"]) == 0:
                order += 1
            if step.get("auto"):
                unit["auto_upgrade"] = True
            where[tuple(step["at"])] = (slot, len(unit["spots"]))
            unit["spots"].append(list(step["at"]))
            steps.append({"do": "place", "slot": slot, "spot": where[tuple(step["at"])][1]})
        elif "upgrade" in step and tuple(step["upgrade"]) in where:
            slot, spot = where[tuple(step["upgrade"])]
            steps.append({"do": "upgrade", "slot": slot, "spot": spot})
        elif "auto" in step and isinstance(step["auto"], list) and tuple(step["auto"]) in where:
            # Switch the game's Auto Upgrade on for the unit there, at this point in the order.
            slot, spot = where[tuple(step["auto"])]
            units[slot]["auto_upgrade"] = "later"
            steps.append({"do": "auto", "slot": slot, "spot": spot})
    return {"units": list(units.values()), "steps": steps, "custom_order": True}


def load(map_name: str, name: str) -> Plan:
    raw = None
    try:
        with open(path(map_name, name), encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as error:
        plan = Plan(map_name, name)
        plan.notes.append(f"couldn't read the plan, so it starts empty: {error}")
        return plan
    if isinstance(raw, dict) and "units" not in raw and "steps" in raw:
        raw = from_old_steps(raw)
    return normalize(raw, map_name, name)


def save(plan: Plan):
    os.makedirs(os.path.dirname(path(plan.map, plan.name)), exist_ok=True)
    data = {"custom_order": plan.custom_order,
            "units": [{"slot": u.slot, "priority": u.priority, "count": u.count, "upgrade_to": u.upgrade_to,
                       "targeting": u.targeting, "from_wave": u.from_wave, "enabled": u.enabled,
                       "auto_upgrade": (u.auto_upgrade if u.auto_on_place or not u.auto_upgrade else "later"),
                       "spots": u.spots}
                      for u in plan.units],
            "steps": plan.steps}
    with open(path(plan.map, plan.name), "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def names(map_name: str) -> list[str]:
    folder = os.path.join(MAPS, map_name, "layouts")
    if not os.path.isdir(folder):
        return []
    return sorted(n[:-5] for n in os.listdir(folder) if n.endswith(".yaml") and not n.endswith(("test.yaml", "_test.yaml")))
