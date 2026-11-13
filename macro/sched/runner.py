"""Playing a queue: what to play, how many times, what happens between, and pausing.

No window code here: the app passes in callbacks. A queue is a list of entries:
  {mode: story|sandbox, map: "Flaming Monastery", act: 1, difficulty: Normal, plan: story, times: 5}
times 0 means forever. Bad entries are skipped with a reason, not fatal.

Touching the mouse or keyboard pauses the run where it is, and Resume carries on from there. F8
ends it. A drop in gems or gold ends it, with a message saying so.
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field

import cv2
import yaml

from macro import brand
from macro.control import maps, plans
from macro.control.engine import read_hotbar_costs
from macro.modes import challenge, furnace, rewards, story, trick
from macro.modes.collect import collect_rewards
from macro.nav import stages
from macro.nav.currency import SpendingDetected, SpendingWatch
from macro.nav.navigator import NavError, Navigator
from macro.nav.recovery import Recovery, RunStopped
from macro.platform import GuardTripped, PointerLocked
from macro.platform.windows import WindowsPlatform, idle_seconds
from macro.sched import badge, webhook
from macro.vision.digits import DigitReader
from macro.vision.screens import ROOT, scaled

MAX_FAILURES = 3  # in a row, on one entry, before moving to the next
LOBBY_EVERY = 10  # matches in a row without the lobby, before a visit to check gems and collect rewards
RESUME_IDLE = 2.0  # hands off this long after Resume
AUTO_RESUME = 3.0  # a pause ends by itself once mouse and keyboard have been still this long (0: never)
ACCEPTED_MODES = ("story", "sandbox", "challenge", "trick", "furnace")
SANDBOX_BUTTONS = {"School Grounds": "school_grounds", "Flower Forest": "flower_forest", "Rose Kingdom": "rose_kingdom",
                   "Fairy King Forest": "fairy_king_forest", "King's Tomb": "kings_tomb", "East Town": "east_town",
                   "Crimson Shore": "crimson_shore", "Flaming Monastery": "flaming_monastery"}


def folder_of(map_name: str) -> str:
    return map_name.lower().replace("'", "").replace(" ", "_")


def clean_entry(entry) -> tuple[dict | None, str]:
    """A queue entry made safe to run, or None and why not. Values that merely look odd are
    fixed: times of -3 or "abc" run once."""
    if not isinstance(entry, dict):
        return None, f"not a queue entry: {entry!r}"
    mode = str(entry.get("mode", "story")).lower()
    if mode not in ACCEPTED_MODES:
        return None, f"{mode} isn't built yet"
    times = plans._number(entry.get("times"), 1)
    times = 0 if entry.get("times") in (0, "0", "inf", "infinite") else max(1, times)
    if mode == "trick":
        # One run is one knock. The map of a Trick is read when it happens.
        return {"mode": mode, "map": "Trick or Treat", "act": None, "difficulty": "Hard",
                "plan": str(entry.get("plan") or "story"), "times": times}, ""
    if mode == "furnace":
        # The Halloween event's Soul Furnace, Infinite Hard: one map, runs until it's lost.
        spa = plans._number(entry.get("spa_boosts"), furnace.SPA_TARGET)
        after = str(entry.get("after_spa") or "random_unit")
        return {"mode": mode, "map": "Soul Furnace", "act": None, "difficulty": "Hard",
                "plan": str(entry.get("plan") or "paths"), "times": times,
                "spa_boosts": max(0, spa), "after_spa": after if after in furnace.RECIPES or after == "none" else "random_unit"}, ""
    if mode == "challenge":
        # Which stage is only known once the Challenges window is read, at play time.
        kind = "daily" if str(entry.get("map", "")).lower().startswith("daily") else "regular"
        return {"mode": mode, "map": f"{kind.capitalize()} challenge", "kind": kind, "act": None,
                "difficulty": "Hard", "plan": str(entry.get("plan") or "story"), "times": times,
                "crystals_only": bool(entry.get("crystals_only", False))}, ""
    map_name = entry.get("map")
    if map_name not in stages.STORY_MAPS:
        return None, f"{map_name!r} isn't a known map"
    if not os.path.exists(os.path.join(plans.MAPS, folder_of(map_name), "reference.png")):
        return None, f"{map_name} has no reference picture yet"
    if mode == "sandbox" and map_name not in SANDBOX_BUTTONS:
        return None, f"{map_name} can't be opened in Sandbox yet"
    act = plans._number(entry.get("act"), 1)
    act = max(1, min(5, act))
    difficulty = "Hard" if str(entry.get("difficulty", "")).lower() == "hard" else "Normal"
    times = plans._number(entry.get("times"), 1)
    times = 0 if entry.get("times") in (0, "0", "inf", "infinite") else max(1, times)
    return {"mode": mode, "map": map_name, "act": act, "difficulty": difficulty,
            "plan": str(entry.get("plan") or "story"), "times": times}, ""


def stage_of(entry: dict) -> tuple:
    return entry["mode"], entry["map"], entry.get("act"), entry.get("difficulty")


ROLE_PRIORITY = {"dps": 1, "farm": 2, "support": 3}  # the game's 1 upgrades first


def slot_roles() -> dict[int, str]:
    """Each hotbar slot's role (dps, support, farm), from the team preset and data/units.yaml."""
    try:
        with open(os.path.join(ROOT, "data", "presets", "current_team.yaml"), encoding="utf-8") as f:
            slots = (yaml.safe_load(f) or {}).get("slots") or {}
        with open(os.path.join(ROOT, "data", "units.yaml"), encoding="utf-8") as f:
            units = (yaml.safe_load(f) or {}).get("units") or {}
    except OSError:
        return {}
    return {int(slot): ("farm" if info.get("farm") else units.get(str(info.get("unit")), {}).get("role"))
            for slot, info in slots.items()}


def auto_priorities() -> dict[int, int]:
    """Each hotbar slot's auto-upgrade priority, from its unit's role: the main damage dealer
    first, then farms, then support; a unit's own `auto_priority` in data/units.yaml wins."""
    try:
        with open(os.path.join(ROOT, "data", "presets", "current_team.yaml"), encoding="utf-8") as f:
            slots = (yaml.safe_load(f) or {}).get("slots") or {}
        with open(os.path.join(ROOT, "data", "units.yaml"), encoding="utf-8") as f:
            units = (yaml.safe_load(f) or {}).get("units") or {}
    except OSError:
        return {}
    out = {}
    for slot, info in slots.items():
        unit = units.get(str(info.get("unit")), {})
        out[int(slot)] = int(unit.get("auto_priority") or ROLE_PRIORITY.get(unit.get("role"), 4))
    return out


def playable(map_name: str) -> bool:
    """Whether the macro can play a map: a reference picture and a plan with moves in it."""
    folder = os.path.join(plans.MAPS, folder_of(map_name))
    return os.path.exists(os.path.join(folder, "reference.png")) and \
        os.path.exists(os.path.join(folder, "layouts", "story.yaml"))


class NothingToPlay(Exception):
    """A task with nothing it can play right now: move on to the next one, or for a task set
    to run forever, wait until `retry_at` (time.time()) and look again."""

    def __init__(self, text: str, retry_at: float | None = None):
        super().__init__(text)
        self.retry_at = retry_at


def describe(entry: dict) -> str:
    times = "forever" if not entry.get("times") else f"x{entry['times']}"
    if str(entry.get("mode")) == "challenge":
        only = ", Trait Crystal ones only" if entry.get("crystals_only") else ", crystals first"
        return f"{str(entry.get('map') or 'Regular challenge')}{only}, {times}"
    if str(entry.get("mode")) == "sandbox":
        return f"Sandbox: {entry.get('map')}, plan {entry.get('plan')}, {times}"
    if str(entry.get("mode")) == "furnace":
        return (f"Soul Furnace Infinite: plan {entry.get('plan', 'paths')}, Souls to SPA, Unbound Tomes, "
                f"Random Units, more Unbound, then the Final Boss, {times}")
    if str(entry.get("mode")) == "trick":
        knocks = "forever" if not entry.get("times") else f"{entry['times']} knocks"
        return f"Trick or Treat: the lobby's doors, {knocks}"
    return f"{entry.get('map')} Act {entry.get('act')} {entry.get('difficulty')}, plan {entry.get('plan')}, {times}"


@dataclass
class Stats:
    state: str = "Idle"
    task: str = ""
    run: str = ""
    wave: str = "-"
    yen: str = "-"
    health: str = "-"
    enemies: str = "-"
    clock: str = "-"
    wins: int = 0
    losses: int = 0
    gems_start: int | None = None
    gems_now: int | None = None
    notes: list = field(default_factory=list)
    loot: dict = field(default_factory=dict)  # tracked rewards this session: name -> count
    index: int = -1      # the queue item being played
    done: int = 0        # runs of it finished
    finished: bool = False  # the queue went to its end


class QueueRunner(threading.Thread):
    def __init__(self, queue: list[dict], settings: dict, on_log, on_stats, on_paused, on_result, on_finished):
        super().__init__(daemon=True, name="queue-runner")
        self.queue_entries = queue
        self._used = {}  # challenge offers that can't be played again yet: key -> time.time() it can
        self._inside = None  # the finished Story match the game is still in: {stage, yaw, matches}
        self.settings = settings
        self.on_log, self.on_stats, self.on_paused = on_log, on_stats, on_paused
        self.on_result, self.on_finished = on_result, on_finished
        self.stats = Stats()
        self.stop_requested = threading.Event()
        self.resume_requested = threading.Event()
        self.p: WindowsPlatform | None = None

    # ------------------------------------------------------------------ the app's controls
    def request_stop(self):
        self.stop_requested.set()
        self.resume_requested.set()

    def request_resume(self):
        self.resume_requested.set()

    # ------------------------------------------------------------------------------ pausing
    def _on_pause(self, reason: str):
        """Runs on the macro's thread, with everything frozen, until it's fine to go on."""
        self.resume_requested.clear()
        auto_note = float(self.settings.get("auto_resume", AUTO_RESUME) or 0)
        self._log(f"PAUSED: {reason}. " + (f"It goes on by itself after {auto_note:.0f} s of no touch; "
                                            if auto_note > 0 else "Press Resume, ") + "F8 ends the run.")
        self.stats.state = "Paused"
        self.on_paused(reason)
        self._send_stats()
        guard = self.p.guard
        auto = float(self.settings.get("auto_resume", AUTO_RESUME) or 0)
        paused_at = time.time()
        while True:
            self.resume_requested.wait(0.2)
            if guard.stopped or self.stop_requested.is_set():
                raise GuardTripped("stopped")
            if self.resume_requested.is_set():
                break
            # A small accidental touch shouldn't stop a run (user, 11 Nov 2026): once nobody has
            # touched anything for `auto` seconds, carry on as if Resume had been pressed.
            if auto > 0 and time.time() - paused_at >= auto and idle_seconds() >= auto:
                self._log(f"nothing touched for {auto:.0f} s: resuming by itself")
                break
        self._log("resuming once the mouse and keyboard are still")
        wanted = float(self.settings.get("resume_idle", RESUME_IDLE) or RESUME_IDLE)
        while idle_seconds() < wanted:
            if guard.stopped or self.stop_requested.is_set():
                raise GuardTripped("stopped")
            time.sleep(0.1)
        stuck_since = None
        while True:
            self.p.focus_game()
            guard.start()
            time.sleep(0.3)
            try:
                problem = self.p.make_game_ready(timeout=20)
                if problem:
                    raise GuardTripped(problem)
                guard.arm()
                break
            except GuardTripped as still:
                self._log(f"can't resume yet: {still}")
                self.resume_requested.clear()
                self.on_paused(str(still))
                # Unattended (auto-resume on), it tries again by itself every 15 s instead of
                # waiting for Resume (11 Nov 2026: hours lost on "Roblox never opened a window").
                # A Roblox that stays hung or gone for 2 minutes is closed, so the next try
                # starts it afresh; the run then carries on from the lobby.
                stuck_since = stuck_since or time.time()
                text = str(still).lower()
                if auto > 0 and time.time() - stuck_since > 120 and (
                        "stopped responding" in text or "frozen" in text or "never opened" in text
                        or "not in front" in text):
                    self._log("Roblox has been stuck for 2 minutes: closing it to start it again")
                    try:
                        self.p.close_game()
                    except Exception as error:  # noqa: BLE001 - the next try relaunches anyway
                        self._log(f"closing Roblox: {error}")
                    stuck_since = time.time()
                end = time.time() + (15 if auto > 0 else 1e9)
                while not self.resume_requested.wait(0.2) and time.time() < end:
                    if guard.stopped or self.stop_requested.is_set():
                        raise GuardTripped("stopped")
        self.stats.state = "Running"
        self.on_paused("")
        self._send_stats()

    # ------------------------------------------------------------------------------ helpers
    def _log(self, text: str):
        self.on_log(text)

    def _send_stats(self):
        self.on_stats(self.stats)

    def _hud_seen(self, screen, frame, hud):
        if hud:
            s = self.stats
            s.wave = f"{hud['wave']}/{hud['wave_total']}" if hud["wave_total"] else str(hud["wave"] or "-")
            s.yen = f"{hud['yen']:,}" if hud["yen"] is not None else s.yen
            s.health = str(hud["health"]) if hud["health"] is not None else s.health
            s.enemies = str(hud["enemies"]) if hud["enemies"] is not None else s.enemies
            if hud["seconds"] is not None:
                s.clock = f"{hud['seconds'] // 60}:{hud['seconds'] % 60:02d}"
            now = time.perf_counter()
            if now - getattr(self, "_last_stats", 0) > 0.5:
                self._last_stats = now
                self._send_stats()

    def _balance(self, nav, watch, recovery):
        nav.go("lobby", on_lost=recovery)
        # Read once per lobby visit: _to_lobby has usually just done it (an OCR read and a 0.8 s
        # wait for the hotbar's tooltip to go, saved twice per visit).
        if time.time() - getattr(self, "_balance_at", 0) < 20:
            return nav.p.grab()
        self.p.hover(*scaled(960, 300))  # hotbar tooltips cover the row
        self.p.sleep(0.8)
        frame = self.p.grab()
        balance = watch.check(frame)
        self._balance_at = time.time()
        if balance.gems is not None:
            self.stats.gems_now = balance.gems
            if self.stats.gems_start is None:
                self.stats.gems_start = balance.gems
        self._send_stats()
        return frame

    def _load(self, entry: dict):
        folder = folder_of(entry["map"])
        plan = plans.load(folder, entry["plan"])
        for note in plan.notes:
            self._log(f"plan {entry['plan']}: {note}")
        if not plan.by_priority() or not plan.steps:
            raise NavError(f"plan {entry['plan']} for {entry['map']} has no units placed on it yet")
        roles = slot_roles()
        for unit in plan.units:
            unit.farm = roles.get(unit.slot) == "farm"
        if self.settings.get("upgrades") == "auto":
            # The game upgrades everything itself, by priority: the macro places in the plan's
            # order, farms go on Auto Upgrade where the plan says, and every other unit once all
            # are placed (switched on as they land, it spent the Yen before Atom was down).
            priorities = auto_priorities()
            steps = [st for st in plan.steps if st["do"] != "upgrade"]
            on = {(st["slot"], st["spot"]) for st in steps if st["do"] == "auto"}
            rest = [(u.slot, i) for u in plan.units for i in range(len(u.used_spots)) if (u.slot, i) not in on]
            rest.sort(key=lambda key: priorities.get(key[0], 6))
            plan.steps = steps + [{"do": "auto", "slot": slot, "spot": i} for slot, i in rest]
            for unit in plan.units:
                unit.auto_upgrade, unit.auto_on_place = True, False
                unit.auto_priority = priorities.get(unit.slot, 6)
        return maps.load_profile(folder), plan

    def _play_challenge(self, entry, nav, reader, recovery, watch, costs) -> dict:
        """Read the Challenges window, pick the best offer this macro can play, play it."""
        if self._inside:
            self._to_lobby(nav, recovery, watch)
        self._balance(nav, watch, recovery)
        if not costs:
            costs.update(read_hotbar_costs(nav.p.grab()))
            self._log("unit prices: " + ", ".join(f"slot {k} {v}" for k, v in sorted(costs.items())))
        if entry["kind"] == "regular" and challenge.near_rotation():
            wait = challenge.seconds_to_rotation() + 8 if challenge.seconds_to_rotation() < 60 else 8
            self._log(f"the regular challenges change in a moment; waiting {wait:.0f} s for the new ones")
            self.p.sleep(wait)
        nav.go("challenges", on_lost=recovery)
        offers = challenge.read_offers(nav, entry["kind"])
        for offer in offers:
            self._log(f"  offer {offer.describe()}{'' if not offer.map or playable(offer.map) else ' (no plan for this map yet)'}")
        now = time.time()
        self._used = {k: t for k, t in self._used.items() if t > now}
        while True:
            offer = challenge.choose(offers, playable, entry.get("crystals_only", False), used=self._used)
            if offer is None:
                nav.go("lobby", on_lost=recovery)
                again = now + challenge.seconds_to_rotation() + 15 if entry["kind"] == "regular" else now + 3600
                raise NothingToPlay(f"no {entry['kind']} challenge it can play right now", again)
            self._log(f"playing {offer.describe()}")
            try:
                challenge.enter(nav, offer)
                break
            except challenge.Unavailable as why:
                self._log(f"  {why}")
                self._used[offer.key] = now + (challenge.seconds_to_rotation() + 15 if offer.kind == "regular"
                                               else 6 * 3600)
                if nav.wait_for("challenges", 6.0) is None:
                    nav.go("challenges", on_lost=recovery)
        played = {**entry, "map": offer.map, "act": offer.act}
        self.stats.task = f"{offer.map} Act {offer.act} Hard, {entry['kind']} challenge"
        self._send_stats()
        profile, plan = self._load(played)
        self._log("match started")
        result = story.play_match(nav, reader, profile, plan, costs, on_lost=recovery, log=self._log,
                                  on_frame=self._hud_seen, should_stop=self.stop_requested.is_set)
        self._log(f"{result.moves_made} moves made")
        frame = None
        if result.outcome in story.RESULT_SCREENS:
            self.p.sleep(3.0)
            frame = self.p.grab()
        self._report(played, result.outcome, result.seconds, frame, result)
        if result.outcome in story.RESULT_SCREENS:
            self._to_lobby(nav, recovery, watch)
        elif result.outcome != "stopped":
            nav.go("lobby", on_lost=recovery)
        return {"outcome": result.outcome}

    def _report(self, entry: dict, outcome: str, seconds: float, frame, result=None):
        if outcome == "victory":
            self.stats.wins += 1
        elif outcome == "defeat":
            self.stats.losses += 1
        self._log(f"RESULT: {outcome} after {seconds:.0f} s")
        self._send_stats()
        if frame is None:
            return
        self._last_loot = {}
        if outcome == "victory":
            try:
                self._last_loot = rewards.read_rewards(frame)
            except Exception as error:  # a tally is a nicety: never let it stop the run
                self._log(f"couldn't read the rewards: {error}")
            for name, count in self._last_loot.items():
                self.stats.loot[name] = self.stats.loot.get(name, 0) + count
            if self._last_loot:
                self._log(f"rewards: {rewards.describe(self._last_loot)} "
                          f"(this session: {rewards.describe(self.stats.loot)})")
                self._send_stats()
        folder = os.path.join(ROOT, "logs")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "last-result.png")
        cv2.imwrite(path, frame)
        self.on_result(path, outcome)
        url = webhook.target(self.settings)
        wanted = {"victory": self.settings.get("send_victory", True), "defeat": self.settings.get("send_defeat", True)}
        if url and wanted.get(outcome, True):
            ping = self.settings.get("ping", "")
            text = f"<@{ping}> lost a match" if ping and outcome == "defeat" else ""
            embed, progress = self._result_embed(entry, outcome, seconds, result)
            try:
                gif = [("badge.gif", badge.result_badge(progress, outcome in ("victory", "built")), "image/gif")]
            except Exception:  # a badge is decoration: never let it stop the report
                gif = []
                embed.pop("thumbnail", None)
            error = webhook.send(url, text, frame, embed=embed, files=gif)
            if error:
                self._log(f"webhook didn't send: {error}")

    def _result_embed(self, entry: dict, outcome: str, seconds: float, result) -> dict:
        s = self.stats
        mode = str(entry.get("mode"))
        if mode == "challenge":
            stage = f"{entry['map']} \u00b7 Act {entry['act']} \u00b7 Hard"
            kind = f"{entry.get('kind', 'regular').capitalize()} challenge"
        elif mode == "sandbox":
            stage, kind = f"{entry['map']} \u00b7 Sandbox", "Sandbox test"
        elif mode == "trick":
            stage = f"{entry['map']} \u00b7 Act {entry.get('act') or '?'} \u00b7 Hard"
            kind = "Halloween Trick"
        else:
            stage = f"{entry['map']} \u00b7 Act {entry['act']} \u00b7 {entry['difficulty']}"
            kind = "Story"
        title = f"{outcome.capitalize()} \u00b7 {stage}"
        lines = [f"**{kind}** cleared in **{webhook.clock(seconds)}**" if outcome == "victory"
                 else f"**{kind}**, {outcome} after **{webhook.clock(seconds)}**", ""]
        if result is not None and result.waves_seen:
            wave, total = result.waves_seen[-1]
            if total:
                lines.append(f"`WAVES ` {badge.bar(wave / total)}  **{wave}/{total}**")
        # How far this task has got, counting the match just played.
        progress = 1.0
        found = re.match(r"(\d+) of (\d+)", s.run or "")
        if found:
            run, times = int(found.group(1)), int(found.group(2))
            progress = run / times
            lines.append(f"`TASK  ` {badge.bar(progress)}  run **{run}** of {times}")
        elif s.run:
            lines.append(f"`TASK  ` run **{s.run.split(' of ')[0]}**, forever")
        tasks = len(self.queue_entries)
        if tasks > 1 and s.index >= 0:
            lines.append(f"`QUEUE ` {badge.bar((s.index + progress) / tasks)}  task **{s.index + 1}** of {tasks}")
        if result is not None and result.moves_made:
            lines.append(f"-# {result.moves_made} moves made")
        played = s.wins + s.losses
        fields = [("Session", f"**{s.wins}** won \u00b7 **{s.losses}** lost"
                              + (f"\n{badge.bar(s.wins / played, 8)} {round(100 * s.wins / played)}%" if played else ""))]
        loot = getattr(self, "_last_loot", {})
        if loot or s.loot:
            fields.append(("Loot", "\n".join(
                f"{'**+' + str(loot[name]) + '**' if loot.get(name) else '+0'} {name}"
                f" \u00b7 {s.loot.get(name, 0)} this session" for name in rewards.TRACKED if name in s.loot or name in loot)))
        if s.gems_now is not None:
            gained = s.gems_now - s.gems_start if s.gems_start is not None else 0
            fields.append(("Gems", f"**{s.gems_now:,}**\n{gained:+,} this session"))
        if getattr(self, "run_started_at", None):
            elapsed = time.time() - self.run_started_at
            pace = f"\n{3600 * played / elapsed:.1f} matches an hour" if played and elapsed > 60 else ""
            fields.append(("Running for", f"**{webhook.clock(elapsed)}**{pace}"))
        return webhook.result_embed(title, outcome, lines, fields, brand.NAME, True), progress

    # ------------------------------------------------------------------------- one play
    def _to_lobby(self, nav, recovery, watch):
        """Out of a finished match, then what only the lobby can do: the spending check and
        collecting rewards."""
        self._inside = None
        screen = nav.settle()
        if screen in story.RESULT_SCREENS:
            story.leave_results(nav, screen, on_lost=recovery)
        self._balance(nav, watch, recovery)
        if self.settings.get("collect", True):
            report = collect_rewards(nav, on_lost=recovery, log=self._log)
            for line in report:
                self._log(line)
            if report:  # the balance only needs reading again if something was claimed (~1.5 s)
                self._balance_at = 0
                self._balance(nav, watch, recovery)

    # ----------------------------------------------------------------------- Trick or Treat
    def _play_trick(self, entry, nav, reader, recovery, watch, costs) -> dict:
        """One knock: find a ready Ethereal Door, knock, and take what comes. A Treat is closed and
        reported with its picture; a Trick is a match, played with our team and our plan for its
        map (the game's Auto Play if there's none)."""
        if self._inside:
            self._to_lobby(nav, recovery, watch)
        p = self.p
        if nav.settle() != "lobby":
            nav.go("lobby", on_lost=recovery)
        if not costs:
            p.hover(*scaled(960, 300)); p.sleep(0.5)
            costs.update(read_hotbar_costs(p.grab()))
        if getattr(self, "_doors", None) is None:
            self._doors = trick.DoorRound()
        doors = self._doors
        if not doors.go(p, log=self._log):
            wait = max(10.0, doors.wait() + 3)
            raise NothingToPlay(f"every door is cooling down (the soonest in {doors.wait():.0f} s)", time.time() + wait)
        result = trick.knock(nav, log=self._log)
        if result.kind != "nothing":
            doors.knocked()
        tally = self.stats.loot
        if result.kind == "treat":
            self._treats = getattr(self, "_treats", 0) + 1
            before = getattr(self, "_candy_owned", None)
            if result.candy is None and result.owned is not None and before is not None and result.owned > before:
                result.candy = result.owned - before  # no count read: what the owned total gained
            if result.candy:
                tally["Candy Corn"] = tally.get("Candy Corn", 0) + result.candy
            if result.owned is not None:
                self._candy_owned = result.owned
            self._log(f"TREAT: +{result.candy or '?'} Candy Corn "
                      f"({tally.get('Candy Corn', 0)} this session, {result.owned or '?'} owned)")
            self._send_stats()
            self._treat_webhook(result)
            return {"outcome": "treat"}
        if result.kind != "trick":
            raise NavError("the knock did nothing")
        self._tricks = getattr(self, "_tricks", 0) + 1
        self._log("TRICK: off to a match")
        if not trick.wait_for_match(nav, 90):
            raise NavError("no match after the Trick's teleport")
        map_name, act = trick.stage_of_trick(p.grab())
        self._log(f"  the Trick's stage: {map_name or '?'} Act {act or '?'} Hard")
        own = trick.use_own_team(p, log=self._log)
        played = {**entry, "mode": "trick", "map": map_name or "Trick", "act": act, "difficulty": "Hard"}
        self.stats.task = f"Trick: {map_name or '?'} Act {act or '?'} Hard"
        self._send_stats()
        match = None
        if own and map_name and playable(map_name):
            profile, plan = self._load({**played, "plan": entry.get("plan") or "story"})
            match = story.play_match(nav, reader, profile, plan, costs, on_lost=recovery, log=self._log,
                                     on_frame=self._hud_seen, should_stop=self.stop_requested.is_set)
            seconds, outcome = match.seconds, match.outcome
        else:
            self._log(f"  no plan for it here (own team: {own}): the game's Auto Play plays it")
            started = time.time()
            p.click(*trick.AUTO_PLAY); p.sleep(1.0)
            if story.start_window_showing(p.grab()):
                story.press_start(nav, self._log)
            outcome = "unfinished"
            while time.time() - started < 900 and not self.stop_requested.is_set():
                frame = p.grab()
                if nav.detector.classify(frame).name in story.RESULT_SCREENS:
                    outcome = story.banner_outcome(frame) or "defeat"
                    break
                p.sleep(2.0)
            seconds = time.time() - started
        frame = None
        if outcome in ("victory", "defeat"):
            p.sleep(3.0)
            frame = p.grab()
        self._report(played, outcome, seconds, frame, match)
        if outcome != "stopped":
            self._to_lobby(nav, recovery, watch)
        return {"outcome": outcome}

    def _treat_webhook(self, result):
        url = webhook.target(self.settings)
        if not url or result.frame is None:
            return
        candy = self.stats.loot.get("Candy Corn", 0)
        owned = getattr(self, "_candy_owned", None)
        dot = "\u00b7"
        lines = [f"**Treat** from an Ethereal Door: **+{result.candy or '?'} Candy Corn**", "",
                 f"`KNOCKS` treats **{getattr(self, '_treats', 0)}** {dot} tricks **{getattr(self, '_tricks', 0)}**"]
        fields = [("Candy Corn", f"**+{candy:,}** this session" + (f"\n**{owned:,}** owned" if owned else ""))]
        if getattr(self, "run_started_at", None):
            fields.append(("Running for", f"**{webhook.clock(time.time() - self.run_started_at)}**"))
        embed = webhook.result_embed(f"Treat {dot} +{result.candy or '?'} Candy Corn", "victory", lines, fields,
                                     f"{brand.NAME} {dot} Trick or Treat", True)
        embed.pop("thumbnail", None)
        error = webhook.send(url, "", result.frame, embed=embed)
        if error:
            self._log(f"webhook didn't send: {error}")

    def _at_results(self) -> bool:
        """Roblox is showing a match's results (Victory/Defeat): a Soul Furnace run goes on from
        there with Retry, so a fresh start must not close it (user, 11 Nov 2026)."""
        try:
            from macro.vision.screens import ScreenDetector
            name = ScreenDetector().classify(self.p.grab()).name
        except Exception:  # noqa: BLE001 - no picture yet: start afresh as usual
            return False
        if name in story.RESULT_SCREENS:
            self._log("Roblox is on a results screen: carrying on from it, no fresh start")
            return True
        if name == "match" and story.start_window_showing(self.p.grab()):
            self._log("Roblox has a match waiting at Start Game: carrying on from it, no fresh start")
            return True
        return False

    # ------------------------------------------------------------------------- Soul Furnace
    def _play_furnace(self, entry, nav, reader, recovery, watch, costs) -> dict:
        """One Soul Furnace run: Repeat Stage from the last run's results when it can (the
        character stays where it was), else from the lobby through Events. The whole layout goes
        down as phantoms before Start; the rest is the Forge and the Unit Manager."""
        p = self.p
        profile = maps.load_profile("soul_furnace")
        # A plan with views (layouts/paths.yaml: units over all three paths, placed from several
        # spots) is its own kind; any other is an ordinary one-view plan.
        try:
            plan = furnace.load_paths_plan(entry["plan"])
        except OSError:
            plan = {}
        if not plan.get("views"):
            plan = plans.load("soul_furnace", entry["plan"])
        inside = self._inside if self._inside and self._inside.get("stage") == ("furnace",) else None
        screen = nav.settle()
        fresh = True
        if screen in story.RESULT_SCREENS and (inside is None or inside["matches"] < LOBBY_EVERY):
            # Retry from any results screen (user, 11 Nov 2026: "there was a literal retry button")
            self._log("repeating the Soul Furnace from the results")
            nav.press(screen, "repeat_stage")
            fresh = False
            matches = (inside["matches"] if inside else 0) + 1
        elif screen == "match" and story.start_window_showing(p.grab()):
            # A match already waiting at "Start Game?" (the app was restarted just after Retry):
            # played from where it is. Phantoms already queued answer "limit".
            self._log("a Soul Furnace match is waiting at Start Game: playing it")
            fresh = False
            matches = 1
        else:
            if self._inside:
                self._to_lobby(nav, recovery, watch)
            self._balance(nav, watch, recovery)
            nav.go("soul_furnace_picker", on_lost=recovery)
            stages.start_from_picker(nav, "soul_furnace_picker")
            matches = 1
        self._inside = None
        end = time.time() + 40
        while time.time() < end and not story.start_window_showing(p.grab()):
            p.sleep(0.3)
        if not story.start_window_showing(p.grab()):
            raise NavError("the Soul Furnace match never showed Start Game")
        self.stats.task = "Soul Furnace Infinite Hard"
        self._send_stats()
        self._log("match started")
        result = furnace.play_furnace(nav, reader, profile, plan, fresh=fresh, spa_target=entry["spa_boosts"],
                                      after_spa=entry["after_spa"], log=self._log, on_frame=self._hud_seen,
                                      should_stop=self.stop_requested.is_set)
        self._log(f"Soul Furnace: {result.outcome} at wave {result.wave}, {result.souls} Souls collected, "
                  f"{result.tomes} Unbound Tomes, {result.extras} extra units, {result.heat_bars} Heat bars, {result.seconds:.0f} s, "
                  f"bin {result.bins[0]}/{result.bins[1]}, "
                  + (f"DMG/RNG from wave {result.boosts_from}" if result.boosts_from else "no DMG/RNG"))
        frame = None
        if result.outcome in story.RESULT_SCREENS:
            p.sleep(3.0)
            frame = p.grab()
            self._inside = {"stage": ("furnace",), "yaw": 0, "matches": matches}
        self._furnace_report(entry, result, frame)
        if result.outcome not in story.RESULT_SCREENS and result.outcome != "stopped":
            nav.go("lobby", on_lost=recovery)
        return {"outcome": result.outcome}

    def _furnace_report(self, entry, result, frame):
        """Log, tally and webhook for a Soul Furnace run: always a Defeat in Infinite, so the
        wave reached and the Candy Corn are what count."""
        s = self.stats
        s.losses += 0  # an Infinite run always ends in Defeat: not a loss to count
        candy = None
        if frame is not None:
            try:
                loot = rewards.read_rewards(frame)
            except Exception as error:  # a tally is a nicety
                loot, _ = {}, self._log(f"couldn't read the rewards: {error}")
            candy = next((v for k, v in loot.items() if "candy" in k.lower()), None)
        # The results never show less than the HUD's last reading: a misread there dropped a digit
        # (12 Nov 2026, 08:46: "+133" for a run with 1,311 on the HUD).
        if candy is not None and result.candy is not None and candy < result.candy:
            self._log(f"the results read {candy} Candy Corn, under the HUD's {result.candy}: using the HUD's")
            candy = result.candy
        candy = candy if candy is not None else result.candy
        if candy:
            s.loot["Candy Corn"] = s.loot.get("Candy Corn", 0) + candy
        runs = getattr(self, "_furnace_runs", [])
        runs.append((result.wave or 0, candy or 0, result.seconds))
        self._furnace_runs = runs
        best = max(w for w, _, _ in runs)
        self._log(f"RESULT: Soul Furnace wave {result.wave}, +{candy or '?'} Candy Corn "
                  f"({s.loot.get('Candy Corn', 0)} this session, best wave {best})")
        self._send_stats()
        if frame is None:
            return
        folder = os.path.join(ROOT, "logs")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "last-result.png")
        cv2.imwrite(path, frame)
        self.on_result(path, "defeat")
        url = webhook.target(self.settings)
        if not url:
            return
        dot = "·"
        hours = sum(t for _, _, t in runs) / 3600
        lines = [f"**Soul Furnace** Infinite Hard reached **wave {result.wave or '?'}** in **{webhook.clock(result.seconds)}**", "",
                 f"`SOULS ` **{result.souls if result.souls is not None else '?'}** collected {dot} "
                 f"**{result.tomes}** Unbound Tomes {dot} **{result.extras}** extra units {dot} "
                 f"**{result.heat_bars}** Heat bars",
                 f"`RUNS  ` **{len(runs)}** this session {dot} best wave **{best}**"]
        fields = [("Candy Corn", f"**+{candy if candy is not None else '?'}** this run\n"
                                 f"**{s.loot.get('Candy Corn', 0):,}** this session"
                                 + (f"\n{s.loot.get('Candy Corn', 0) / hours:,.0f} an hour" if hours > 0.2 else ""))]
        if getattr(self, "run_started_at", None):
            fields.append(("Running for", f"**{webhook.clock(time.time() - self.run_started_at)}**"))
        embed = webhook.result_embed(f"Soul Furnace {dot} wave {result.wave or '?'}", "victory", lines, fields,
                                     f"{brand.NAME} {dot} Halloween", True)
        embed.pop("thumbnail", None)
        error = webhook.send(url, "", frame, embed=embed)
        if error:
            self._log(f"webhook didn't send: {error}")

    def _play_once(self, entry, nav, reader, recovery, watch, costs) -> dict:
        if entry["mode"] == "furnace":
            return self._play_furnace(entry, nav, reader, recovery, watch, costs)
        if entry["mode"] == "trick":
            return self._play_trick(entry, nav, reader, recovery, watch, costs)
        if entry["mode"] == "challenge":
            return self._play_challenge(entry, nav, reader, recovery, watch, costs)
        profile, plan = self._load(entry)
        p = self.p
        # A Story match that has just ended is the quickest way into the next one: Repeat
        # Stage for the same stage, the ship button's party for any other. The camera stays
        # as that match left it, so only the difference in the maps' turns is applied.
        inside, yaw = self._inside, None
        if inside and (entry["mode"] != "story" or inside["matches"] >= LOBBY_EVERY
                       or nav.settle() not in story.RESULT_SCREENS):
            self._to_lobby(nav, recovery, watch)
            inside = None
        if inside:
            screen = nav.settle()
            yaw = profile.yaw_counts - inside["yaw"]
            mode, map_name, act, difficulty = inside["stage"]
            if inside["stage"] == stage_of(entry):
                self._log("repeating the stage from the results")
                story.repeat_stage(nav, reader, screen)
            elif (screen == "victory" and (mode, map_name, difficulty) == (entry["mode"], entry["map"], entry.get("difficulty"))
                  and act is not None and entry.get("act") == act + 1):
                self._log("on to the next act from the results")
                story.next_stage(nav, reader)
            else:
                self._log("going to the stage from inside the match")
                story.enter_story_from_match(nav, reader, entry["map"], entry["act"], entry["difficulty"],
                                             on_lost=recovery)
        else:
            self._balance(nav, watch, recovery)
            if not costs:
                costs.update(read_hotbar_costs(nav.p.grab()))
                self._log("unit prices: " + ", ".join(f"slot {k} {v}" for k, v in sorted(costs.items())))
            if entry["mode"] == "story":
                story.enter_story(nav, entry["map"], entry["act"], entry["difficulty"], on_lost=recovery)
            else:
                stages.start_sandbox(nav, on_lost=recovery, map_button=SANDBOX_BUTTONS[entry["map"]])
                p.sleep(2.0)
        matches = inside["matches"] + 1 if inside else 1
        self._inside = None  # until this match ends well, the lobby is the way on
        self._log("match started")
        result = story.play_match(nav, reader, profile, plan, costs, on_lost=recovery, log=self._log,
                                  on_frame=self._hud_seen, should_stop=self.stop_requested.is_set,
                                  stop_when_built=entry["mode"] == "sandbox", yaw=yaw)
        self._log(f"{result.moves_made} moves made")
        frame = None
        if result.outcome in story.RESULT_SCREENS:
            p.sleep(3.0)
            frame = p.grab()
        elif result.outcome == "built":
            p.sleep(1.0)
            p.hover(*scaled(960, 110))
            p.sleep(0.5)
            frame = p.grab()
        self._report(entry, result.outcome, result.seconds, frame, result)
        if result.outcome in story.RESULT_SCREENS and entry["mode"] == "story"                 and self.settings.get("stay_in_match", True):
            self._inside = {"stage": stage_of(entry), "yaw": profile.yaw_counts, "matches": matches}
        elif result.outcome in story.RESULT_SCREENS:
            self._to_lobby(nav, recovery, watch)
        elif result.outcome != "stopped":
            nav.go("lobby", on_lost=recovery)
        return {"outcome": result.outcome}


    def _session_goal_reached(self) -> str | None:
        """The session's own end (Config): a clock time, or this much Candy Corn this session."""
        import datetime
        stop_at = str(self.settings.get("stop_at_time") or "").strip()
        if stop_at:
            try:
                hour, minute = (int(v) for v in stop_at.split(":"))
                started = datetime.datetime.fromtimestamp(self.run_started_at)
                target = started.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target <= started:
                    target += datetime.timedelta(days=1)  # "07:00" set at 01:00 means this morning
                if datetime.datetime.now() >= target:
                    return f"it's {stop_at}"
            except ValueError:
                pass
        candy_goal = int(self.settings.get("stop_at_candy") or 0)
        candy = self.stats.loot.get("Candy Corn", 0)
        if candy_goal and candy >= candy_goal:
            return f"{candy:,} Candy Corn this session (goal {candy_goal:,})"
        return None

    def _maybe_refresh(self, nav, recovery, watch):
        """Every few hours, between matches, close Roblox and start it again: a long session
        slows it down (user, 10 Nov 2026). Off when the setting is 0."""
        hours = float(self.settings.get("refresh_hours", 3) or 0)
        if hours <= 0 or time.time() - getattr(self, "_refreshed_at", time.time()) < hours * 3600:
            return
        self._log(f"refreshing Roblox after {hours:g} h, so it stays quick")
        self._inside = None  # a finished match needs no leaving: Roblox is closed outright
        self.p.guard.disarm()  # its own restart mustn't read as a problem with the window
        self.p.close_game()
        problem = self.p.make_game_ready(timeout=120)
        if problem:
            raise RunStopped(f"Roblox didn't come back after the refresh: {problem}")
        self.p.guard.arm()
        recovery.wait_until_in_game()
        nav.go("lobby", on_lost=recovery)
        self._refreshed_at = time.time()
        self._log("Roblox refreshed")

    def _play_queue(self, nav, reader, recovery, watch, costs) -> str:
        """The queue once, top to bottom. "stopped" if a stop was asked for."""
        for index, raw in enumerate(self.queue_entries):
            entry, why = clean_entry(raw)
            if entry is None:
                self._log(f"skipped queue item {index + 1}: {why}")
                continue
            failures, count = 0, 0
            try:
                self._maybe_refresh(nav, recovery, watch)
            except NavError as problem:
                self._log(f"the refresh had trouble ({problem}); carrying on")
                self.p.guard.arm()
            self.stats.task = describe(entry)
            self.stats.index, self.stats.done = index, 0
            while not self.stop_requested.is_set() and (not entry["times"] or count < entry["times"]):
                if count:
                    # Between runs too, not only between tasks: a forever task never reached it
                    # (11-12 Nov 2026: Roblox froze or crashed about an hour into each session).
                    try:
                        self._maybe_refresh(nav, recovery, watch)
                    except NavError as problem:
                        self._log(f"the refresh had trouble ({problem}); carrying on")
                        self.p.guard.arm()
                goal = self._session_goal_reached()
                if goal:
                    self._log(f"session goal reached: {goal}")
                    self.goal_reached = goal
                    self.stop_requested.set()
                    break
                count += 1
                self.stats.run = f"{count} of {entry['times']}" if entry["times"] else f"{count} of forever"
                self.stats.wave = self.stats.yen = self.stats.enemies = self.stats.clock = "-"
                self._send_stats()
                self._log(f"--- {describe({**entry, 'times': 1})}, run {self.stats.run}")
                try:
                    self._play_once(entry, nav, reader, recovery, watch, costs)
                    failures = 0
                    self._failed_streak = 0
                    self.stats.done = count
                    self._send_stats()
                except NothingToPlay as nothing:
                    if entry["times"] or nothing.retry_at is None:
                        self._log(f"{nothing}, so on to the next task")
                        break
                    wait = max(10.0, nothing.retry_at - time.time())
                    self._log(f"{nothing}; looking again in {wait / 60:.0f} min")
                    count -= 1  # waiting isn't a run
                    end = time.time() + wait
                    while time.time() < end and not self.stop_requested.is_set():
                        self.p.sleep(min(5.0, end - time.time()))
                    continue
                except (NavError, maps.PositionError, PointerLocked) as problem:
                    failures += 1
                    self._failed_streak = getattr(self, "_failed_streak", 0) + 1
                    self._log(f"that run failed: {problem}")
                    if isinstance(problem, PointerLocked) and getattr(self.p, "remote", False)                             and not getattr(self, "_told_pointer", False):
                        self._told_pointer = True
                        self._log("  over Remote Desktop a mouse resting on its window moves this pointer too: "
                                  "keep yours off the window while it plays")
                    # A moment before trying again: 15 runs failed in 40 s on a held pointer (13 Nov
                    # 2026, 08:13), each one straight after the last.
                    self.p.sleep(min(20.0, 4.0 * failures))
                    if failures >= MAX_FAILURES:
                        self._log(f"{MAX_FAILURES} failures in a row, so moving to the next queue item")
                        break
                    self._inside = None
                    nav.go("lobby", on_lost=recovery)
            if self.stop_requested.is_set():
                return "stopped"
        self.stats.finished = True
        return "finished"

    # -------------------------------------------------------------------------- the queue
    def run(self):
        self.run_started_at = time.time()
        self.stats.state = "Starting"
        self._send_stats()
        ending = "finished"
        try:
            import comtypes

            comtypes.CoInitialize()
        except Exception:
            pass
        try:
            self.p = WindowsPlatform()
            self.p.guard.pausable = True
            self.p.guard.pause_callback = self._on_pause
            if self.settings.get("fresh_start", True) and self.p.game_running() and not self._at_results():
                # A fresh Roblox for every run (user, 10 Nov 2026): no menus left open, no held
                # pointer, a clean camera, and straight into the private server if one is set.
                self._log("starting Roblox afresh")
                self.p.close_game()
            self._log("bringing Roblox into the frame")
            self.p.guard.start()
            problem = self.p.make_game_ready(timeout=120)
            if problem:
                raise GuardTripped(problem)
            self.p.guard.arm()
            self.stats.state = "Running"
            self._send_stats()
            nav = Navigator(self.p, log=lambda t: self._log(f"  {t}"))
            recovery = Recovery(self.p, nav, may_restart=bool(self.settings.get("may_restart", True)),
                                log=lambda t: self._log(f"  RECOVERY: {t}"))
            watch = SpendingWatch(log=self._log)
            reader = DigitReader()
            costs: dict[int, int] = {}
            recovery.wait_until_in_game()  # a cold start takes a while to join and load
            screen = nav.settle()
            first = str((self.queue_entries or [{}])[0].get("mode", "")).lower()
            if screen in story.RESULT_SCREENS and first != "furnace":
                # A Soul Furnace queue goes on from the results with Retry (11 Nov 2026, 23:50:
                # leaving them here sent a restarted app round the lobby instead).
                story.leave_results(nav, screen, on_lost=recovery)
            loops = 0
            self._refreshed_at = time.time()
            while True:
                if loops:
                    self._log(f"--- the queue again, round {loops + 1}")
                if self._play_queue(nav, reader, recovery, watch, costs) == "stopped":
                    ending = "stopped"
                    break
                loops += 1
                if not self.settings.get("repeat_queue") or self.stop_requested.is_set():
                    break
                if getattr(self, "_failed_streak", 0) >= MAX_FAILURES:
                    # The round ended on failures alone: a fresh Roblox before the next one, not
                    # another round straight away.
                    self._failed_streak = 0
                    recovery.restart_game("every run in that round failed")
            if self._inside and not self.stop_requested.is_set():
                self._to_lobby(nav, recovery, watch)
        except SpendingDetected as spent:
            ending = f"STOPPED BECAUSE {spent}"
            self._log(ending)
        except RunStopped as stopped:
            ending = f"stopped: {stopped}"
            self._log(ending)
        except GuardTripped as stopped:
            ending = "stopped" if self.p.guard.stopped or self.stop_requested.is_set() else f"stopped: {stopped}"
            self._log(f"run ended: {stopped}")
        except Exception as error:  # the window must always hear that the run ended
            ending = f"stopped by an error: {error!r}"
            self._log(ending)
        finally:
            if self.p:
                self.p.close()
            self.stats.state = "Idle"
            self._send_stats()
            url = webhook.target(self.settings)
            if url and self.settings.get("send_end", True):
                ping = self.settings.get("ping", "")
                text = (f"<@{ping}> " if ping else "") + (
                    f"Run {ending}. Wins {self.stats.wins}, losses {self.stats.losses}"
                    + (f", gems {self.stats.gems_now - self.stats.gems_start:+,}"
                       if self.stats.gems_now is not None and self.stats.gems_start is not None else "") + ".")
                error = webhook.send(url, text)
                if error:
                    self._log(f"webhook didn't send: {error}")
            if getattr(self, "goal_reached", None):
                ending = f"finished: {self.goal_reached}"
            self.on_finished(ending)
            user_stopped = ending == "stopped" and not getattr(self, "goal_reached", None)
            if self.settings.get("shutdown_when_done") and not user_stopped:
                # Opt-in (Config): the laptop needn't sit idle after a night's farming. A minute's
                # notice; "shutdown /a" in a terminal cancels it.
                self._log("the session is over: shutting the computer down in 60 s (shutdown /a cancels)")
                url = webhook.target(self.settings)
                if url:
                    webhook.send(url, "Session over: shutting the computer down in 60 s.")
                import subprocess
                subprocess.run(["shutdown", "/s", "/t", "60", "/c", f"{brand.ASCII_NAME}: the session is over"],
                               check=False)
