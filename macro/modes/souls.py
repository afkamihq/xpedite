"""Where the Soul Furnace's Souls go: the user's plan (11 Nov 2026), in this order.

1. SPA Boost until it's maxed (+50%). Its auto forge is on from the start and spends every 20
   Souls, so Souls only pile up once the Forge stops selling it.
2. An Unbound Tome (250) for each of OUR placed units the plan lists (`souls: unbound:`, default
   the three Atoms), found on their Unit Manager cards (a card's panel shows the unit's trait).
   Fallback: the unit is clicked on the map where it was placed.
3. Random Units (100 each): bought one at a time, each placed at once on the next free spot of
   `extra_spots` (home view), again and again. More important than DMG/RNG (user).
4. A good new unit (`unbound_new`: Wolf = Starrk, Atom = Cid, Impaler = Alucard, Reaper = Ichigo)
   gets an Unbound Tome too, before the next Random Unit.
5. From wave `bin_after_wave` (20), a hotbar slot whose units are all placed is dragged into the
   hotbar's bin when a purchase needs the room, counting Random Units still on their countdown
   (only the hotbar entry goes; placed units stay). Ours first. Binning every finished slot at
   once cost ~13 drags a run, 2 in 3 missed over Remote Desktop (13 Nov 2026).
6. DMG and RNG Boost (auto forge) once nothing above can be bought, or from wave
   `boosts_from_wave` (45) once the Random Units are done: then they take the Souls ahead of the
   remaining "more Unbound" tomes. Before that rule they were never bought: runs used 4-6 of the
   9+ tomes queued and died at wave 55-65 with the boosts untouched (13 Nov 2026).

Everything is checked on the screen after it's done: a purchase by the slot it lit, a placement by
the toast and the Unit Manager's newest card, a tome by the hotbar and the unit's panel.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from macro.vision import ocr

# After Start the hotbar has ten slots and a bin (11 Nov 2026 pictures).
SLOT_X = {n: 328 + 87 * (n - 1) for n in range(1, 11)}
HOTBAR_Y = 730
HOTBAR_ROW = (285, 688, 1160, 776)
BIN = (1193, 732)
SLOT_LIT = 40  # an empty slot is dark (V ~17); one holding something is bright (68+)
RANDOM_PRICE = 100
# The Forge's Random Unit counter read "2/5" after two purchases (11 Nov 2026, 16:04): at most
# five a match, it seems. Bought ones arrive after a short countdown.
RANDOM_CAP = 5
FINAL_BOSS_PRICE = 500
TOME_PRICE = 250

# The furnace end of the three paths (home view), where every enemy the others miss walks past.
# The first four are from tools/path_cover.py; the rest ring the cage, clear of our own units
# (Stone Alchemists at (590, 510), (540, 610), (590, 610); the 8th Sword at (740, 460)).
DEFAULT_SPOTS = [(640, 360), (790, 510), (840, 360), (690, 410), (950, 440),
                 (880, 510), (700, 520), (930, 300), (760, 320), (1040, 330), (620, 440),
                 (880, 560), (980, 500), (680, 290), (1060, 420)]


def slot_of_x(x: float) -> int:
    return min(SLOT_X, key=lambda s: abs(SLOT_X[s] - x))


def lit_slots(frame) -> set[int]:
    out = set()
    for slot, x in SLOT_X.items():
        patch = cv2.cvtColor(frame[700:765, x - 38:x + 38], cv2.COLOR_BGR2HSV)
        if np.median(patch[:, :, 2]) > SLOT_LIT:
            out.add(slot)
    return out


def tome_slots(frame) -> set[int]:
    """Slots holding a tome, by their "Tome" label."""
    return {slot_of_x(x) for text, x, y in ocr.find_words(frame, HOTBAR_ROW) if "tome" in text.lower()}


@dataclass
class SoulConfig:
    unbound: dict = field(default_factory=lambda: {"atom": 3})  # our placed units: name part -> how many
    unbound_new: list = field(default_factory=lambda: ["wolf", "atom", "impaler", "reaper"])
    extra_units: bool = True
    extra_spots: list = field(default_factory=lambda: list(DEFAULT_SPOTS))
    extra_priority: int = 3  # Auto Upgrade priority for a placed Random Unit
    bin_after_wave: int = 20  # 0 = never use the bin
    boosts: list = field(default_factory=lambda: ["dmg", "rng"])
    # Final Boss (Global, 500 Souls, 5 Heat Bars): "ends the run and earn +20% Candy Corn and 100
    # bonus Candy Corn" (wiki). An Infinite run always ends in Defeat, so it's bought the moment
    # the furnace's health drops to final_boss_health; 500 Souls are kept for it once the tomes
    # and Random Units are done (boosts get only what's above that).
    final_boss: bool = False
    final_boss_health: int = 2
    # User, 12 Nov 2026: from final_boss_save_from nothing more is bought and the Souls are saved
    # for the Final Boss, which is bought from final_boss_wave on as soon as 500 are there.
    # Earlier only in an emergency with 500 on hand: health down to final_boss_health, or
    # final_boss_enemies on the field after wave 40 (the end comes fast: 3 -> 0 health in one
    # wave at 55; 255-312 enemies in the last 1-3 waves of every run that night).
    final_boss_save_from: int = 44
    final_boss_wave: int = 60
    final_boss_enemies: int = 255
    # Once the Random Units are done, Unbound Tomes for more of our placed units (user: "focus on
    # extra units and unbound tomes"); DMG/RNG only once the run's Candy Corn is past this.
    unbound_more: dict = field(default_factory=lambda: {"blade": 3, "sovereign": 3})
    boosts_from_candy: int = 2000
    # From this wave (once the Random Units are done) DMG/RNG come before more Unbound: a damage
    # boost helps every unit, a tome only one (13 Nov 2026). 0 = only by Candy Corn / when idle.
    boosts_from_wave: int = 45

    @classmethod
    def from_plan(cls, plan) -> "SoulConfig":
        raw = (plan.get("souls") if isinstance(plan, dict) else None) or {}
        config = cls()
        if "unbound" in raw:
            value = raw["unbound"] or {}
            if isinstance(value, list):  # [atom, atom, atom] is the same as {atom: 3}
                counted: dict = {}
                for name in value:
                    counted[_key(name)] = counted.get(_key(name), 0) + 1
                value = counted
            config.unbound = {_key(k): int(v) for k, v in value.items()}
        if "unbound_new" in raw:
            config.unbound_new = [_key(n) for n in raw["unbound_new"] or []]
        if "extra_units" in raw:
            config.extra_units = bool(raw["extra_units"])
        if raw.get("extra_spots"):
            config.extra_spots = [tuple(int(v) for v in s) for s in raw["extra_spots"]]
        if "extra_priority" in raw:
            config.extra_priority = int(raw["extra_priority"])
        if "bin_after_wave" in raw:
            config.bin_after_wave = int(raw["bin_after_wave"] or 0)
        if "boosts" in raw:
            config.boosts = [str(b).lower() for b in raw["boosts"] or []]
        if "final_boss" in raw:
            config.final_boss = bool(raw["final_boss"])
        if "final_boss_health" in raw:
            config.final_boss_health = int(raw["final_boss_health"])
        if "final_boss_save_from" in raw:
            config.final_boss_save_from = int(raw["final_boss_save_from"])
        if "final_boss_wave" in raw:
            config.final_boss_wave = int(raw["final_boss_wave"])
        if "final_boss_enemies" in raw:
            config.final_boss_enemies = int(raw["final_boss_enemies"])
        if "unbound_more" in raw:
            value = raw["unbound_more"] or {}
            if isinstance(value, list):
                counted: dict = {}
                for name in value:
                    counted[_key(name)] = counted.get(_key(name), 0) + 1
                value = counted
            config.unbound_more = {_key(k): int(v) for k, v in value.items()}
        if "boosts_from_candy" in raw:
            config.boosts_from_candy = int(raw["boosts_from_candy"])
        if "boosts_from_wave" in raw:
            config.boosts_from_wave = int(raw["boosts_from_wave"] or 0)
        return config

    def describe(self) -> str:
        ours = ", ".join(f"{v} {k}" for k, v in self.unbound.items()) or "none"
        return (f"SPA to max, Unbound on ours ({ours}), "
                + (f"Random Units placed again and again, Unbound on new {'/'.join(self.unbound_new)}, "
                   if self.extra_units else "")
                + (f"bin from wave {self.bin_after_wave}, " if self.bin_after_wave else "")
                + f"then {'/'.join(self.boosts) or 'nothing'}"
                + (f" from wave {self.boosts_from_wave}" if self.boosts_from_wave else "")
                + (f" or past {self.boosts_from_candy} Candy Corn" if self.boosts_from_candy else "")
                + (f"; more Unbound for {', '.join(f'{v} {k}' for k, v in self.unbound_more.items())} after the Random Units"
                   if self.unbound_more else "")
                + (f"; saving for the Final Boss from wave {self.final_boss_save_from}, bought from wave "
                   f"{self.final_boss_wave} (earlier at {self.final_boss_health} health or "
                   f"{self.final_boss_enemies}+ enemies)" if self.final_boss else ""))


def _key(name) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


_UNIT_NAMES: list = []


def is_unit_name(card_name: str) -> bool:
    """A card's simplified name is a unit's (data/unit_names.txt), not a summon's or a misread."""
    import os
    if not _UNIT_NAMES:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "data", "unit_names.txt")
        with open(path, encoding="utf-8") as f:
            _UNIT_NAMES.extend(_key(line) for line in f if line.strip() and not line.startswith("#"))
    return bool(card_name) and any(card_name.startswith(u[:7]) or u.startswith(card_name[:7])
                                   for u in _UNIT_NAMES if u)


def name_matches(card_name: str, key: str) -> bool:
    """A card's simplified name against a list entry: the name must START with it, so "wolf"
    is Starrk's Wolf (Revived) and not Iron Wolf (Struggler)."""
    return bool(key) and card_name.startswith(key)


@dataclass
class Slot:
    kind: str  # "ours", "extra" or "tome"
    name: str = ""
    placed: bool = False
    tries: int = 0
    spot: tuple | None = None
    bin_fails: int = 0


@dataclass
class Placement:
    """Where a unit went, for clicking it on the map (the tome fallback)."""
    name: str
    view: str
    point: tuple


class SoulSpender:
    """The Souls side of one Soul Furnace run. `tick` is called from the match loop with each
    frame read; it does at most one thing and returns True when it did (the loop then reads a
    fresh frame)."""

    def __init__(self, p, nav, forge, profile, config: SoulConfig, log, order: dict | None = None,
                 placements: list | None = None, views: dict | None = None):
        self.p, self.nav, self.forge, self.profile = p, nav, forge, profile
        self.config, self.log, self.order = config, log, order
        self.placements: list[Placement] = list(placements or [])
        self.views = views or {}
        self.slots: dict[int, Slot] = {n: Slot("ours") for n in range(1, 7)}
        self.spa_done = False
        self._rich_since = None
        self.tomed: dict = {}  # name key -> tomes used on it this run
        # One entry per tome still wanted, in order: ours first ({atom: 3} -> atom, atom, atom).
        self.tome_targets: list = [k for k, n in self.config.unbound.items() for _ in range(n)]
        self.tome_waiting: tuple | None = None  # (slot, card or None, key) of a tome bought, not used
        self.tome_fails = 0
        self.spot_index = 0
        self.boosting = False
        self.blocked_until = 0.0
        self.extras_placed = 0
        self.tomes_used = 0
        self.binned: list = []
        self.bin_tries = 0
        self.random_arrived = 0  # Random Units that have shown up in the hotbar
        self.wave = 0
        self.boosts_started_wave: int | None = None
        self.last_buy_fail = 0.0
        self.random_bought = 0
        self.final_boss_bought = False
        self.final_boss_tries = 0
        self.candy: int | None = None
        self._more_added = False
        self._saving_logged = False
        self.known: list | None = None  # our cards from one Unit Manager read (survey)
        self.prefound: dict = {}  # a new unit's key -> its card, found before the Souls are in
        self._adopted = False

    def adopt(self, frame):
        """Hotbar slots 7-10 holding something the run didn't buy (a resumed match): a tome is
        used on the next target, a unit is placed (or found already placed: "limit")."""
        tomes = tome_slots(frame)
        for slot in sorted(lit_slots(frame)):
            if slot in self.slots:
                continue
            if slot in tomes:
                self.slots[slot] = Slot("tome")
                if self.tome_waiting is None:
                    self.tome_waiting = (slot, None, self._next_tome_key() or "atom")
                self.log(f"hotbar slot {slot} holds a tome already")
            else:
                self.slots[slot] = Slot("extra")
                self.random_arrived += 1
                self.log(f"hotbar slot {slot} holds a unit already: placing it")

    # ------------------------------------------------------------------ the loop's entry
    def tick(self, frame, wave: int, souls: int | None, collected: int | None = None,
             health: int | None = None, heat_bars: int | None = None, enemies: int | None = None,
             candy: int | None = None) -> bool:
        now = self.p.now()
        if health == 0:
            return False  # the run is over: any click now would close its results
        self.candy = candy if candy is not None else self.candy
        hurt = health is not None and 0 < health <= self.config.final_boss_health
        swamped = enemies is not None and wave >= 40 and enemies >= self.config.final_boss_enemies
        due = wave >= self.config.final_boss_wave
        if (self.config.final_boss and not self.final_boss_bought and self.final_boss_tries < 3
                and (due or hurt or swamped) and (souls or 0) >= FINAL_BOSS_PRICE
                and (heat_bars is None or heat_bars >= 5)):
            why = (f"wave {wave}" if due else f"down to {health} health at wave {wave}" if hurt
                   else f"{enemies} enemies on the field at wave {wave}")
            self.log(f"{why}: Final Boss for +20% Candy Corn and +100 (Candy Corn now {self.candy})")
            self.final_boss_tries += 1
            self.final_boss_bought = self.buy_final_boss()
            return True
        self.wave = wave
        if now < self.blocked_until:
            return False
        # The bin is used only when a purchase needs the room (_make_room): binning every finished
        # slot from bin_after_wave cost ~13 drags a run, 2 in 3 missed over RDP (13 Nov 2026).
        if not self.spa_done:
            # SPA's auto forge takes every 20 Souls until it's maxed: Souls staying at 100 or
            # more for 6 s mean it's done, if the Heat bar's count says ~50 boosts were bought
            # (a wave's burst of Souls can sit a moment before the auto forge takes it).
            if souls is not None and souls >= RANDOM_PRICE:
                if self._rich_since is None:
                    self._rich_since = now
                boosts = (collected - souls) // 20 if collected else None
                waited = now - self._rich_since
                if (waited > 6 and (boosts is None or boosts >= 45)) or waited > 30:
                    self.spa_done = True
                    self.log(f"SPA Boost is maxed (Souls stay at {souls}, ~{boosts} boosts bought): "
                             f"Souls go to the plan now")
            else:
                self._rich_since = None
            if not self.spa_done:
                return False
        if not self._adopted:
            self._adopted = True
            self.adopt(frame)
        try:
            return self._step(frame, wave, souls)
        except Exception as error:  # noqa: BLE001 - a failed step must never end the match
            self.log(f"Soul step failed: {error}")
            self.blocked_until = self.p.now() + 10
            return True

    def _in_match(self) -> bool:
        """The match is on screen (not its results): no Soul step acts otherwise (22:40: the
        Defeat came mid-step and 72 s went on turning the camera round the results)."""
        return self.nav.detector.classify(self.p.grab()).name == "match"

    def _step(self, frame, wave, souls) -> bool:
        from macro.modes import furnace
        if not self._in_match():
            return False
        # Anything that turned up in the hotbar since the last look: a Random Unit arrives after
        # the Forge's countdown ("Random Unit 0:08  2/5" beside the Forge button), not at once.
        self.p.hover(720, 82)
        new = lit_slots(self.p.grab()) - set(self.slots)
        if new:
            self.adopt(self.p.grab())
        # 1. a tome bought but not used yet is used first
        if self.tome_waiting:
            return self._use_waiting_tome()
        # 2. a Random Unit in the hotbar that isn't placed yet
        if self.config.extra_units:
            unplaced = [s for s, v in self.slots.items() if v.kind == "extra" and not v.placed and v.tries < 3]
            if unplaced:
                return self._place_extra(unplaced[0])
        souls = souls or 0
        if self.config.final_boss and not self.final_boss_bought and wave >= self.config.final_boss_save_from:
            if not self._saving_logged:
                self._saving_logged = True
                self.log(f"wave {wave}: nothing more is bought, Souls are saved for the Final Boss")
            return False
        wants_unit = (self.config.extra_units and self.spot_index < len(self.config.extra_spots)
                      and self.random_bought < RANDOM_CAP)
        if not wants_unit and not self._more_added and self.config.unbound_more:
            # The Random Units are done: Unbound for more of our units (user, 12 Nov 2026).
            self._more_added = True
            self.tome_targets += [k for k, n in self.config.unbound_more.items() for _ in range(n)]
            self.log(f"Random Units done: Unbound Tomes next for {', '.join(self.tome_targets) or 'nobody'}")
        if (not wants_unit and self.config.boosts and self.config.boosts_from_wave
                and wave >= self.config.boosts_from_wave and not self.config.final_boss):
            # Late game: DMG/RNG for every unit before one more Unbound (13 Nov 2026).
            return self._boosts(True) if not self.boosting else False
        target = self._next_tome_key()  # 3. a tome for one of ours, or for a good new unit
        if target is not None and target in self.config.unbound and self.known is None:
            # One read of the Unit Manager, before the Souls reach a tome: where each of ours
            # is and whether it has Unbound. Every tome after that goes straight to its card.
            self.survey(target)
            return True
        if (target is not None and target not in self.config.unbound and target not in self.prefound
                and souls >= TOME_PRICE - 100):
            # A new unit's card is looked for while the last 100 Souls come in.
            self.prefound[target] = furnace.tome_target(self.p, self.nav, target, self.log)
            if self.prefound[target] is None:
                self.prefound.pop(target)
                self._mark_all_tomed(target)
            return True
        if target is None and not wants_unit:
            return self._boosts(True)  # 6. nothing else to buy, ever
        if not self._room_possible(frame, wave):
            # Room comes back with the bin's wave: until then the Souls aren't left idle.
            return self._boosts(True)
        if self.boosting:
            return self._boosts(False)  # Souls are saved for the next thing again
        price = TOME_PRICE if target is not None else RANDOM_PRICE
        if souls < price:
            return False
        if not self._make_room(wave):
            self.blocked_until = self.p.now() + 10
            return True
        if target is not None:
            card = self._known_target(target)
            spare = tome_slots(self.p.grab())
            if spare:  # a tome already in the hotbar (bought earlier, nobody took it): that one
                if card is not None:
                    return self._fast_tome(card, target, min(spare))
                self.tome_waiting = (min(spare), None, target)
                return self._use_waiting_tome()
            if card is None:
                card = furnace.tome_target(self.p, self.nav, target, self.log)
            if card is None:
                self._mark_all_tomed(target)
                return True
            return self._buy_and_use_tome(card, target)
        return self._buy_random()

    # ------------------------------------------------------------------ hotbar room
    def _free_slots(self, frame) -> set[int]:
        return set(SLOT_X) - lit_slots(frame)

    def _bin_allowed(self, wave) -> bool:
        return bool(self.config.bin_after_wave) and wave >= self.config.bin_after_wave

    def _room_possible(self, frame, wave) -> bool:
        return bool(self._free_slots(frame)) or (self._bin_allowed(wave) and bool(self._binnable()))

    def _make_room(self, wave) -> bool:
        """A free hotbar slot for the next purchase, beyond the ones Random Units still on the
        Forge's countdown will take; made with the bin from bin_after_wave on."""
        self.p.hover(720, 82)
        self.p.sleep(0.2)
        pending = max(0, self.random_bought - self.random_arrived)
        need = 1 + pending
        free = len(self._free_slots(self.p.grab()))
        if free >= need:
            return True
        if not self._bin_allowed(wave):
            return False
        for slot in self._binnable():
            if self.bin_slot(slot):
                free += 1
                if free >= need:
                    return True
        return False

    def _binnable(self) -> list[int]:
        ours = [s for s, v in sorted(self.slots.items()) if v.kind == "ours" and v.bin_fails < 3]
        extras = [s for s, v in sorted(self.slots.items()) if v.kind == "extra" and v.placed and v.bin_fails < 3]
        return ours + extras

    def bin_slot(self, slot: int) -> bool:
        """Drag a hotbar slot onto the bin right of slot 10. Only the hotbar entry goes: the
        units already placed stay (user, 11 Nov 2026). True once the slot is dark."""
        from macro.modes import furnace
        p = self.p
        furnace.close_unit_manager(p, self.nav)
        x = SLOT_X[slot]
        before = lit_slots(p.grab())
        if slot not in before:
            self.slots.pop(slot, None)
            return True
        self.bin_tries += 1
        p.hover(x, HOTBAR_Y)
        p.sleep(0.3)
        p.button_down("left")
        try:
            # Held a moment, moved in many small steps, rested over the bin: a quicker drag
            # was missed ~1 time in 3 (11 Nov 2026, 22:21). Over Remote Desktop 2 in 3 still
            # missed (13 Nov 2026): slower steps, then a small wiggle over the bin so the game
            # sees the pointer move onto it, not only arrive.
            p.sleep(0.35)
            for k in range(1, 21):
                p.move(x + (BIN[0] - x) * k / 20, HOTBAR_Y + (BIN[1] - HOTBAR_Y) * k / 20)
                p.sleep(0.05)
            for dx, dy in ((6, 0), (0, 6), (-6, 0), (0, -6), (0, 0)):
                p.move(BIN[0] + dx, BIN[1] + dy)
                p.sleep(0.06)
            p.sleep(0.35)
        finally:
            p.button_up("left")
        p.sleep(0.6)
        p.hover(720, 82)
        p.sleep(0.3)
        frame = p.grab()
        gone = slot not in lit_slots(frame)
        name = self.slots.get(slot, Slot("?")).kind
        self.log(f"hotbar slot {slot} ({name}) {'binned' if gone else 'NOT binned'}")
        if gone:
            self.slots.pop(slot, None)
            self.binned.append(slot)
        else:
            self._picture(f"bin_fail_{slot}")
            if slot in self.slots:
                self.slots[slot].bin_fails += 1
        p.key("z")
        return gone

    # ------------------------------------------------------------------ Random Units
    def _buy_random(self) -> bool:
        from macro.modes import furnace
        p = self.p
        furnace.close_unit_manager(p, self.nav)
        p.hover(720, 82)
        p.sleep(0.2)
        before = lit_slots(p.grab())
        if not self.forge.buy("random_unit"):
            self.blocked_until = p.now() + 5
            return True
        p.hover(720, 82)
        p.sleep(0.5)
        frame = p.grab()
        new = sorted(lit_slots(frame) - before)
        if not new:
            # It comes after the Forge's countdown: the next looks at the hotbar adopt it.
            self.random_bought += 1
            self.log(f"Random Unit bought ({self.random_bought} this run): it arrives after the Forge's countdown")
            self.blocked_until = p.now() + 3
            return True
        slot = new[0]
        if slot in tome_slots(frame):
            self.log(f"slot {slot} lit after the Random Unit, but it holds a tome")
            self.slots[slot] = Slot("tome")
            return True
        self.random_bought += 1
        self.random_arrived += 1
        self.slots[slot] = Slot("extra")
        self.log(f"Random Unit bought: hotbar slot {slot}")
        return self._place_extra(slot)

    def _place_extra(self, slot: int) -> bool:
        """Place the Random Unit in `slot` on the next spot that takes it. A refused spot is
        skipped for good (something stands there); "limit" means it's already placed."""
        from macro.modes import furnace
        p = self.p
        entry = self.slots[slot]
        alignment = self._home_alignment()
        if alignment is None:
            entry.tries += 1
            self.blocked_until = p.now() + 8
            return True
        if slot in tome_slots(p.grab()):  # never press a tome's key with a click to follow
            self.slots[slot] = Slot("tome")
            return True
        last_before = self._last_card_name()
        while self.spot_index < len(self.config.extra_spots):
            spot = self.config.extra_spots[self.spot_index]
            outcome = place_at(p, alignment, slot, spot, self.log)
            if outcome == "limit":
                entry.placed = True
                self.log(f"slot {slot}: already placed")
                return True
            if outcome == "refused":
                self.spot_index += 1
                continue
            if outcome.startswith("blocked"):
                # The game said something else at every nudge (not "cannot place here"): not
                # the spot's fault, so the spot is kept and this unit tries again later.
                entry.tries += 1
                self.blocked_until = p.now() + 20
                self._picture(f"place_blocked_{slot}")
                return True
            entry.placed, entry.spot = True, spot
            self.spot_index += 1
            self.extras_placed += 1
            self.placements.append(Placement("", "home", spot))
            name = self._after_placing(last_before)
            entry.name = name
            self.placements[-1].name = name
            self.log(f"extra unit {self.extras_placed}: {name or '?'} placed at {spot}")
            if any(name_matches(name, k) for k in self.config.unbound_new):
                # One entry per tome wanted; the key is the unit's own name, so the card search
                # finds every unit of that kind and gives the tome to the one without Unbound.
                self.tome_targets.append(name[:8])
                self.log(f"  {name} is on the Unbound list: the next 250 Souls are its tome")
            return True
        entry.tries = 3
        self.log("no extra spot left that takes a unit")
        return True

    def _home_alignment(self):
        from macro.control import maps
        from macro.modes import furnace
        from macro.vision import align
        p = self.p
        furnace.close_unit_manager(p, self.nav)
        reference = align.features(cv2.imread(self.profile.reference_path))
        result = align.align(reference, align.features(p.grab()))
        if result is not None and result.inliers >= 150 and abs(result.scale - 1) <= 0.08:
            return result
        if not self._in_match():
            return None
        self.log(f"the home view isn't on screen ({result and result.inliers} features): finding it")
        try:
            return furnace._home(p, self.profile, self.log)
        except maps.PositionError as error:
            self.log(f"couldn't get home: {error}")
            return None

    def _last_card_name(self) -> str:
        """The name on the Unit Manager's last card (built units move to the end)."""
        from macro.modes import furnace
        cards = [c for c in self._bottom_cards() if is_unit_name(c.name)]
        furnace.close_unit_manager(self.p, self.nav)
        return cards[-1].name if cards else ""

    def _bottom_cards(self) -> list:
        from macro.modes import furnace
        p = self.p
        if not furnace.open_unit_manager(p, self.nav, self.log):
            return []
        p.hover(*furnace.UM_SCROLL_AT)
        p.scroll(2000)
        p.sleep(0.5)
        p.hover(*furnace.UM_OFF_CARDS)
        p.sleep(0.25)
        frame = p.grab()
        cards = [c for c in furnace.read_cards(frame, ocr.find_words(frame, furnace.UM_PANEL)) if c.name]
        cards.sort(key=lambda c: (c.y // 40, c.x))
        return cards

    def _after_placing(self, last_before: str) -> str:
        """Auto Upgrade on for the new unit (the last card), at extra_priority. Its name back."""
        from macro.modes import furnace
        p = self.p
        p.sleep(0.6)
        cards = [c for c in self._bottom_cards() if is_unit_name(c.name)]
        name = cards[-1].name if cards else ""
        if cards and name == last_before:
            self.log(f"  the last card is still {name}: the new unit may be a phantom further up")
        for card in cards:
            if card.maxed or card.on:
                continue
            target = self.order_priority(card.name)
            furnace._step_box(p, card.box, target, was_on=False)
            self.log(f"  Auto Upgrade on for {card.name}, priority {target}")
        furnace.close_unit_manager(p, self.nav)
        return name

    def order_priority(self, name: str) -> int:
        from macro.modes import furnace
        order = self.order or furnace.UPGRADE_ORDER
        for k, v in order.items():
            if k in name:
                return v
        return self.config.extra_priority

    # ------------------------------------------------------------------ tomes
    def _next_tome_key(self) -> str | None:
        for key in self.tome_targets:
            return key
        return None

    def _mark_all_tomed(self, key: str):
        self.tome_targets = [k for k in self.tome_targets if k != key]
        self.log(f"every {key} has Unbound already")

    def _buy_and_use_tome(self, card, key: str) -> bool:
        from macro.modes import furnace
        p = self.p
        p.hover(720, 82)
        p.sleep(0.2)
        before = tome_slots(p.grab())
        lit_before = lit_slots(p.grab())
        if not furnace.buy_tome(self.forge, "unbound"):
            self.log("the Unbound Tome didn't show in the hotbar")
            self._picture("tome_not_seen")
            self.tome_fails += 1
            self.blocked_until = p.now() + 10
            if self.tome_fails >= 4:
                self._give_up_tomes()
            return True
        frame = p.grab()
        slot = next(iter(sorted(tome_slots(frame) - before)), None) or next(iter(sorted(lit_slots(frame) - lit_before)), None)
        if slot is not None:
            self.slots[slot] = Slot("tome")
            return self._fast_tome(card, key, slot)
        self.tome_waiting = (slot, card, key)
        return self._use_waiting_tome()

    # ------------------------------------------------------------------ remembered cards
    def survey(self, key: str):
        """Read the Unit Manager once: every card of `key`, where it is (scroll step and place)
        and whether its unit has Unbound (its panel, opened as the card shows)."""
        from macro.modes import furnace
        p = self.p
        started = p.now()
        known = []
        expected = max(1, self.config.unbound.get(key, 1))

        def visit(card):
            p.click(*furnace._portrait(card))
            p.sleep(0.8)
            tags = ocr.read_text(p.grab(), furnace.UNIT_PANEL_TAGS, scale=1.5).lower()
            p.click(*furnace.UNIT_PANEL_CLOSE)
            p.sleep(0.35)
            p.hover(*furnace.UM_OFF_CARDS)
            p.sleep(0.15)
            if tags.strip():
                card.unbound = "unbound" in tags
                known.append(card)
            # All of ours found: the rest of the list doesn't matter (22:26: reading on to the
            # end took 65 s for 3 Atoms found in the first two steps).
            return len(known) >= expected

        furnace.unit_cards(p, self.nav, key, self.log, visit=visit)
        furnace.close_unit_manager(p, self.nav)
        self.known = known
        lacking = [c for c in known if not c.unbound]
        self.log(f"Unit Manager read in {p.now() - started:.0f} s: {len(known)} {key} cards, "
                 f"{len(lacking)} without Unbound (steps {[c.page for c in lacking]})")
        # Tomes wanted for ours: no more than the cards that lack one.
        wanted = min(self.config.unbound.get(key, 0), len(lacking))
        others = [k for k in self.tome_targets if k != key]
        self.tome_targets = [key] * wanted + others

    def _known_target(self, key: str):
        if key in self.prefound:
            return self.prefound.get(key)
        if self.known is None:
            return None
        return next((c for c in self.known if key in c.name and not getattr(c, "unbound", True)), None)

    def _fast_tome(self, card, key: str, slot: int) -> bool:
        """The tome in `slot` onto `card`: open the Unit Manager at the card's step, press the
        tome's key there (no closing and reopening), click the card's portrait. Falls back to
        the old way (furnace.use_tome) if the key didn't take with the Unit Manager open."""
        from macro.modes import furnace
        p, nav = self.p, self.nav
        started = p.now()
        if not furnace.open_unit_manager(p, nav, self.log):
            self.tome_waiting = (slot, card, key)
            return True
        furnace._go_to_page(p, getattr(card, "page", 0))
        frame = p.grab()

        def grey(c):
            return c.x if not c.on else c.x - furnace.TEAL_FROM_GREY

        seen = furnace.read_cards(frame, ocr.find_words(frame, furnace.UM_PANEL))
        here = [c for c in seen if c.name == card.name and abs(c.y - card.y) < 40 and abs(grey(c) - grey(card)) < 40]
        if not here:
            same = [(grey(c), c.y) for c in seen if c.name == card.name]
            self.log(f"{card.name} isn't at its remembered place ({grey(card)}, {card.y}) at step {card.page}; "
                     f"there: {same or [c.name for c in seen]}: reading the list again")
            self._picture("card_moved")
            self.known = None
            furnace.close_unit_manager(p, nav)
            self.tome_waiting = (slot, None, key)
            return True
        target = here[0]
        p.hover(*furnace.UM_OFF_CARDS)
        p.key("0" if slot == 10 else str(slot))
        p.sleep(0.35)
        p.click(*furnace._portrait(target))
        p.sleep(0.9)
        tags = ocr.read_text(p.grab(), furnace.UNIT_PANEL_TAGS, scale=1.5).lower()
        p.click(*furnace.UNIT_PANEL_CLOSE)
        p.sleep(0.3)
        furnace.close_unit_manager(p, nav)
        p.hover(720, 82)
        p.sleep(0.3)
        gone = slot not in tome_slots(p.grab())
        self.log(f"tome on {target.name} (step {card.page}): "
                 f"{'applied' if gone and 'unbound' in tags else 'not applied'} in {p.now() - started:.1f} s "
                 f"(panel reads {tags!r})")
        if gone:
            card.unbound = True
            self.prefound.pop(key, None)
            self._tome_done(slot, key)
            return True
        # The key didn't take with the Unit Manager open: the tome is still there, used the old way.
        self.tome_waiting = (slot, card, key)
        return self._use_waiting_tome()

    def _use_waiting_tome(self) -> bool:
        from macro.modes import furnace
        p = self.p
        slot, card, key = self.tome_waiting
        if not tome_slots(p.grab()):
            # Used already (a click that "missed" did apply it): look at the units again.
            self.log("the tome isn't in the hotbar any more")
            self.tome_waiting = None
            if slot in self.slots and self.slots[slot].kind == "tome":
                self.slots.pop(slot)
            return True
        if card is None:
            card = furnace.tome_target(p, self.nav, key, self.log)
            if card is None:
                self._mark_all_tomed(key)
                # A tome nobody here needs: the next key on the list takes it.
                nxt = self._next_tome_key()
                if nxt is None:
                    self.log("a tome is left in the hotbar with nobody to take it")
                    self.tome_waiting = None
                    return True
                self.tome_waiting = (slot, None, nxt)
                return True
            self.tome_waiting = (slot, card, key)
        if furnace.use_tome(p, self.nav, card, self.log):
            self._tome_done(slot, key)
            return True
        if not tome_slots(p.grab()):
            # Gone from the hotbar though the panel didn't say: it went on SOME unit.
            self.log("the tome went, but the panel didn't confirm where")
            self._tome_done(slot, key)
            return True
        self.tome_fails += 1
        if self.tome_fails >= 2 and self._tome_on_map(key):
            self._tome_done(slot, key)
            return True
        self.tome_waiting = (slot, None, key)  # read the cards again next time
        self.blocked_until = p.now() + 5
        if self.tome_fails >= 5:
            self._give_up_tomes()
        return True

    def _tome_done(self, slot, key):
        self.tome_waiting = None
        self.tome_fails = 0
        self.tomes_used += 1
        self.tomed[key] = self.tomed.get(key, 0) + 1
        if slot in self.slots and self.slots[slot].kind == "tome":
            self.slots.pop(slot)
        if key in self.tome_targets:  # one entry is one tome
            self.tome_targets.remove(key)
        self.log(f"Unbound Tome {self.tomes_used} used ({key}: {self.tomed[key]}); "
                 f"still wanted: {', '.join(self.tome_targets) or 'none'}")

    def _give_up_tomes(self):
        # Never leave Souls piling up behind a step that keeps failing (user, 11 Nov 2026).
        self.log("the tome step keeps failing: Souls go to Random Units instead")
        self.tome_targets = []
        self.tome_waiting = None

    def _tome_on_map(self, key: str) -> bool:
        """Fallback: click each remembered unit of `key` on the map (outside apply mode its
        panel opens and shows its trait); the first without Unbound gets the tome, clicked
        again in apply mode. Units placed from other views are walked to."""
        from macro.modes import furnace
        p = self.p
        for place in [pl for pl in self.placements if name_matches(pl.name, key)]:
            alignment = self._view_alignment(place.view)
            if alignment is None:
                continue
            try:
                x, y = alignment.to_live(*place.point)
                p.key("z")
                p.hover(x, y)
                p.sleep(0.15)
                p.click(x, y)
                p.sleep(0.9)
                tags = ocr.read_text(p.grab(), furnace.UNIT_PANEL_TAGS, scale=1.5).lower()
                p.click(*furnace.UNIT_PANEL_CLOSE)
                p.sleep(0.4)
                if not tags.strip() or "unbound" in tags:
                    continue
                slot = next(iter(tome_slots(p.grab())), None)
                if slot is None:
                    return True
                p.hover(720, 82)
                p.key("0" if slot == 10 else str(slot))
                p.sleep(0.8)
                p.hover(x, y)
                p.sleep(0.15)
                p.click(x, y)
                p.sleep(1.0)
                tags = ocr.read_text(p.grab(), furnace.UNIT_PANEL_TAGS, scale=1.5).lower()
                p.click(*furnace.UNIT_PANEL_CLOSE)
                p.sleep(0.4)
                p.hover(720, 82)
                p.sleep(0.3)
                done = not tome_slots(p.grab())
                self.log(f"tome by the map on {key} at {place.point} ({place.view}): "
                         f"{'applied' if done else 'not applied'} (panel reads {tags!r})")
                if done:
                    return True
            finally:
                self._back_home(place.view)
        return False

    def _view_alignment(self, view: str):
        from macro.control import maps
        if view == "home":
            return self._home_alignment()
        profile = self.views.get(view)
        if profile is None:
            return None
        if self._home_alignment() is None:
            return None
        maps.walk_route(self.p, profile)
        try:
            return maps.correct_position(self.p, profile, self.log, search=False)
        except maps.PositionError as error:
            self.log(f"couldn't confirm the {view} view: {error}")
            return None

    def _back_home(self, view: str):
        from macro.modes import furnace
        if view == "home" or view not in self.views:
            return
        for key, seconds in reversed(self.views[view].route):
            self.p.key(furnace.BACK[key], hold=seconds)
            self.p.sleep(0.2)
        self._home_alignment()

    # ------------------------------------------------------------------ DMG / RNG
    def _boosts(self, on: bool) -> bool:
        """DMG/RNG auto forge on only while nothing else can be bought; off again as soon as
        something can (else they'd keep the Souls under 100 for good). With the Final Boss on,
        the auto forge stays off and boosts are bought by hand with what's above its 500."""
        if self.config.final_boss:
            return self._boosts_above_reserve() if on else False
        if on and not self._boosts_allowed():
            return False
        if on == self.boosting or not self.config.boosts:
            return False
        wanted = {r: (n + 1 if on else 0) for n, r in enumerate(self.config.boosts)}
        self.forge.set_autos(wanted)
        self.boosting = on
        if on and self.boosts_started_wave is None:
            self.boosts_started_wave = self.wave
        late = bool(self.config.boosts_from_wave) and self.wave >= self.config.boosts_from_wave
        if on:
            why = f"from wave {self.wave}: late game, every unit hits harder" if late else "nothing else can be bought now"
            self.log(f"DMG/RNG boosts on {why}")
        else:
            self.log("DMG/RNG boosts off: Souls are saved again")
        return True

    def _boosts_allowed(self) -> bool:
        """By wave (boosts_from_wave) or by the run's Candy Corn (boosts_from_candy), whichever
        comes first; with neither set, whenever nothing else can be bought."""
        c = self.config
        if not c.boosts_from_wave and not c.boosts_from_candy:
            return True
        if c.boosts_from_wave and self.wave >= c.boosts_from_wave:
            return True
        return bool(c.boosts_from_candy) and self.candy is not None and self.candy >= c.boosts_from_candy

    def _boosts_above_reserve(self) -> bool:
        if not self.config.boosts:
            return False
        if not self._boosts_allowed():
            return False  # by wave or Candy Corn (user, 12-13 Nov 2026)
        self.p.hover(720, 82)
        self.p.sleep(0.2)
        from macro.vision.digits import DigitReader
        souls = getattr(self, "_reader", None) or DigitReader()
        self._reader = souls
        have = souls.read_hud(self.p.grab()).get("souls")
        spare = (have or 0) - FINAL_BOSS_PRICE
        if spare < 100:
            return False
        clicks = min(spare // 20, 20)
        from macro.modes import furnace
        if not self.forge.open():
            return False
        for n in range(clicks):
            recipe = self.config.boosts[n % len(self.config.boosts)]
            if recipe in furnace.RECIPES:
                self.p.click(*furnace.RECIPES[recipe][0])
                self.p.sleep(0.25)
        self.forge.close()
        self.log(f"{clicks} boosts ({'/'.join(self.config.boosts)}) bought, 500 Souls kept for the Final Boss")
        return True

    def buy_final_boss(self) -> bool:
        """Forge, down to the Global recipes, Buy under "Final Boss" (found by its title: Buy
        sits ~93 px under a title and ~27 px left of its centre, as in the Self row)."""
        p = self.p
        if not self.forge.open():
            return False
        found = None
        seen_log = []
        for step in range(24):
            frame = p.grab()
            words = ocr.find_words(frame, (300, 190, 1130, 655))
            seen_log.append(f"{step}: " + ", ".join(t for t, x, y in words if len(t) > 4 and not t.lower().startswith("buy"))[:160])
            for text, x, y in words:
                low = text.lower().replace(" ", "")
                if low.startswith("finalboss") or (low.startswith("final") and len(low) <= 10):
                    found = (x, y)
                    break
            if found and found[1] + 93 < 640:
                break
            if found:  # its Buy is under the panel's edge: a little more
                found = None
                p.hover(720, 450)
                p.scroll(20)
                p.sleep(0.4)
                continue
            # Small steps: 120 jumped over the whole Global section (11 Nov 2026, 23:26).
            p.hover(720, 450)
            p.scroll(40)
            p.sleep(0.4)
        if not found:
            import os
            from macro.control import maps
            with open(os.path.join(maps.ROOT, "cap", "furnace", "souls", "final_boss_scan.txt"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S") + chr(10) + chr(10).join(seen_log) + chr(10) * 2)
        if not found:
            self.log("couldn't find the Final Boss in the Forge")
            self._picture("final_boss_missing")
            self.forge.close()
            return False
        buy = (found[0] - 27, found[1] + 93)
        self._picture("final_boss_before")
        p.click(*buy)
        p.sleep(1.0)
        self._picture("final_boss_after")
        self.log(f"Final Boss bought (Buy at {buy})")
        self.forge.close()
        return True

    def _picture(self, name: str):
        import os
        from macro.control import maps
        folder = os.path.join(maps.ROOT, "cap", "furnace", "souls")
        os.makedirs(folder, exist_ok=True)
        cv2.imwrite(os.path.join(folder, f"{time.strftime('%H%M%S')}_{name}.png"), self.p.grab())


GHOST_VALID = 8.0  # blue minus red gain where the held unit's ghost is (tools/scan_spots.py)


def ghost_gain(base, frame, x: int, y: int, half: int = 34) -> float | None:
    """How much bluer than redder the spot got once the unit's ghost is over it: the game draws
    the ghost blue where it may go, red where not."""
    h, w = frame.shape[:2]
    if not (half <= x < w - half and half <= y < h - half):
        return None
    a = base[y - half:y + half, x - half:x + half].astype(float)
    b = frame[y - half:y + half, x - half:x + half].astype(float)
    return float((b[:, :, 0] - a[:, :, 0]).mean() - (b[:, :, 2] - a[:, :, 2]).mean())


def place_at(p, alignment, slot: int, point, log) -> str:
    """Hold the unit in `slot` and click a point of the home picture, nudged a little if the game
    refuses the exact spot. "placed" (built, or a phantom when the Yen is short), "limit" (that
    unit is all placed), or "refused" (no spot near it takes it)."""
    from macro.control import placing
    from macro.control.engine import toast_text
    from macro.modes import furnace
    placing.EXTRA_AREAS[:] = placing.EVENT_AREAS
    x0, y0 = alignment.to_live(*point)
    p.hover(720, 82)
    p.sleep(0.15)
    base = p.grab()  # the map without the unit's ghost, to see the ghost's colour against
    p.key("0" if slot == 10 else str(slot))
    p.sleep(0.25)
    other = None
    refused = 0
    clicked = False
    try:
        for ox, oy in furnace.NUDGES:
            x, y = int(x0 + ox), int(y0 + oy)
            if placing.on_hud(x, y):
                continue
            p.hover(x, y)
            p.sleep(0.16)
            gain = ghost_gain(base, p.grab(), x, y)
            if gain is not None and gain < GHOST_VALID:
                # Red ghost: not allowed here. Seen without a click (a refused click and its
                # toast cost ~3 s each: 30 s a spot on 11 Nov 2026, 22:32).
                refused += 1
                continue
            clicked = True
            p.click(x, y)
            p.sleep(0.2)
            words = toast_text(p.grab())
            if "limit" in words:
                return "limit"
            if words:
                end = p.now() + 3.0
                while p.now() < end and toast_text(p.grab()):
                    p.sleep(0.2)
                if "cannot" in words or "can't" in words or "invalid" in words or "here" in words:
                    refused += 1
                else:
                    other = words
                    log(f"slot {slot}: the game said {words!r} at ({x}, {y})")
                continue
            log(f"slot {slot} placed at ({x}, {y})" + (" (nudged)" if (ox, oy) != (0, 0) else ""))
            return "placed"
        if other is not None and not refused:
            return f"blocked: {other}"
        if not clicked:
            # Every nudge looked red without a click. A unit already at its placement limit (a
            # duplicate Random Unit) shows no ghost at all, which reads the same: one real click
            # tells them apart, so a good spot isn't thrown away (12 Nov 2026, 00:45).
            x, y = int(x0), int(y0)
            p.hover(x, y)
            p.sleep(0.12)
            p.click(x, y)
            p.sleep(0.25)
            words = toast_text(p.grab())
            if "limit" in words:
                return "limit"
            if not words:
                log(f"slot {slot} placed at ({x}, {y}) (the ghost read wrong)")
                return "placed"
        log(f"slot {slot}: no spot near {tuple(point)} was allowed")
        return "refused"
    finally:
        p.hover(720, 82)
        p.key("z")
        p.sleep(0.2)
        placing.EXTRA_AREAS[:] = []


# ------------------------------------------------------------------ settings in the layout file
def layout_path(plan_name: str = "paths") -> str:
    import os
    from macro.control import maps
    return os.path.join(maps.MAPS, "soul_furnace", "layouts", f"{plan_name}.yaml")


def load_config(plan_name: str = "paths") -> SoulConfig:
    import yaml
    try:
        with open(layout_path(plan_name), encoding="utf-8") as f:
            return SoulConfig.from_plan(yaml.safe_load(f) or {})
    except OSError:
        return SoulConfig()


def save_config(config: SoulConfig, plan_name: str = "paths"):
    """Write the `souls:` section at the end of the layout file, keeping everything above it
    (comments included) as it is."""
    path = layout_path(plan_name)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    at = text.find("\nsouls:\n")
    head = text if at < 0 else text[:at + 1]
    if at < 0 and not head.endswith("\n"):
        head += "\n"
    spots = ", ".join(f"[{x}, {y}]" for x, y in config.extra_spots)
    block = ("souls:\n"
             f"  unbound: {{{', '.join(f'{k}: {v}' for k, v in config.unbound.items())}}}\n"
             f"  unbound_new: [{', '.join(config.unbound_new)}]\n"
             f"  extra_units: {'true' if config.extra_units else 'false'}\n"
             f"  extra_priority: {config.extra_priority}\n"
             f"  bin_after_wave: {config.bin_after_wave}\n"
             f"  boosts: [{', '.join(config.boosts)}]\n"
             f"  final_boss: {'true' if config.final_boss else 'false'}\n"
             f"  final_boss_health: {config.final_boss_health}\n"
             f"  final_boss_save_from: {config.final_boss_save_from}\n"
             f"  final_boss_wave: {config.final_boss_wave}\n"
             f"  final_boss_enemies: {config.final_boss_enemies}\n"
             f"  unbound_more: {{{', '.join(f'{k}: {v}' for k, v in config.unbound_more.items())}}}\n"
             f"  boosts_from_candy: {config.boosts_from_candy}\n"
             f"  boosts_from_wave: {config.boosts_from_wave}\n")
    if config.extra_spots != DEFAULT_SPOTS:
        block += f"  extra_spots: [{spots}]\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + block)


def parse_counts(text: str) -> dict:
    """ "atom x3, 8th sword" -> {"atom": 3, "8thsword": 1} """
    out: dict = {}
    for part in re.split(r"[,;]", text):
        found = re.fullmatch(r"\s*(.*?)\s*(?:[x×*]\s*(\d+))?\s*", part)
        name = _key(found.group(1)) if found else ""
        if name:
            out[name] = out.get(name, 0) + int(found.group(2) or 1)
    return out


def show_counts(counts: dict) -> str:
    return ", ".join(f"{k} x{v}" if v != 1 else k for k, v in counts.items())
