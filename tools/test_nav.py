"""Navigation and recovery against a simulated game, using the real detector on real
pictures. Doesn't touch Roblox, so bad things can be arranged on purpose: lost clicks,
wrong screens, popups, disconnects, a crash, a freeze, a purchase prompt.

It proves the logic, not that the game behaves as data/nav.yaml says.
Run from the project root:  .venv-win/Scripts/python.exe tools/test_nav.py
"""
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
LOGS = os.path.join(ROOT, "logs")
LOGS_BEFORE = set(os.listdir(LOGS)) if os.path.isdir(LOGS) else set()  # a real run's pictures are kept
from macro.nav import navigator as navigator_module
from macro.nav.navigator import NavError, Navigator, find_route, load_edges
from macro.nav.recovery import Recovery, RunStopped, plan_for_words
from macro.platform.base import Platform
from macro.vision.screens import ScreenDetector, load_frame

# A simulated game answers at once, so there's no need to wait as long as for a real one.
navigator_module.STEP_TIMEOUT = 0.6
navigator_module.TRIP_TIMEOUT = 2.0
navigator_module.AFTER_ARRIVAL = 0.0

failures = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {name}{'  ' + str(detail) if detail != '' else ''}", flush=True)
    if not ok:
        failures.append(name)


class FakeGuard:
    tripped = False
    stopped = False
    pausable = False
    paused_total = 0.0

    def wait_if_paused(self):
        pass

    def check(self):
        pass

    def arm(self):
        pass


class FakeGame(Platform):
    """Shows saved pictures, and moves between them as data/nav.yaml says clicks do."""

    def __init__(self, detector, start="lobby"):
        super().__init__()
        self.guard = FakeGuard()
        self.detector = detector
        self.screen = start
        self.clicks = []
        self.keys = []
        self.lose_next_clicks = 0
        self.next_click_goes_to = None
        self.running = True
        self.frozen = False
        self.restarts = 0
        self.overlay = None  # a blank "popup" hiding the screen; words come from read_words
        self.pictures = {name: load_frame(d["frames"][0]) for name, d in detector.definitions.items()}
        self.edges, _ = load_edges()
        self.trip_until = 0.0
        self.trip_target = None

    def grab(self):
        if self.overlay is not None:
            return self.overlay
        if time.perf_counter() < self.trip_until:
            return self.pictures["game_loading"]
        if self.trip_target:
            self.screen, self.trip_target = self.trip_target, None
        return self.pictures[self.screen]

    def sleep(self, seconds):
        time.sleep(min(seconds, 0.02))

    def _move(self, x, y): pass
    def _rel(self, dx, dy): pass
    def _button(self, button, down): pass
    def _key(self, name, down): pass
    def _text(self, text): pass
    def game_running(self): return self.running
    def game_frozen(self): return self.frozen
    def close_game(self): self.running = False

    def make_game_ready(self):
        self.running, self.frozen, self.overlay = True, False, None
        self.screen = "lobby"
        self.restarts += 1
        return None

    def click(self, x, y, button="left", hold=0.06):
        self.clicks.append((x, y))
        if self.overlay is not None:
            return
        if self.lose_next_clicks:
            self.lose_next_clicks -= 1
            return
        if self.next_click_goes_to:
            self.screen, self.next_click_goes_to = self.next_click_goes_to, None
            return
        buttons = {n: self.detector.button(self.screen, n) for n in (self.detector.definitions[self.screen].get("buttons") or {})}
        pressed = next((name for name, at in buttons.items() if tuple(at) == (x, y)), None)
        # The last click of the two-click steps in Navigator._perform.
        finishing = {"event_gamemode": "soul_furnace_picker", "select_map": "party_room"}
        if pressed in finishing:
            self.screen = finishing[pressed]
            return
        for edge in self.edges:
            if edge.source == self.screen and edge.do == pressed:
                if edge.trip:
                    self.trip_until, self.trip_target = time.perf_counter() + 0.5, edge.target
                else:
                    self.screen = edge.target
                return

    def key(self, name, hold=0.05):
        self.keys.append(name)

    def scroll(self, amount):
        self.screen = {"play_menu_top": "play_menu_bottom", "play_menu_bottom": "play_menu_top"}.get(self.screen, self.screen)


detector = ScreenDetector()
edges, _ = load_edges()

# ------------------------------------------------------------- the graph itself
screens = set(detector.definitions)
bad_buttons = [f"{e.source}.{e.do}" for e in edges if e.do and e.do not in ("open_soul_furnace", "select_school_grounds")
               and e.do not in (detector.definitions[e.source].get("buttons") or {})]
check("every edge's button is on the allow-list", not bad_buttons, bad_buttons)
check("every edge joins real screens", all(e.source in screens and (e.target in screens or e.target == "any") for e in edges))
results_only = {"game_loading", "roblox_teleport", "match", "party_room", "unit_panel", "unit_manager", "obtained_rewards",
                "autoplay_settings", "sandbox_controls", "esc_menu", "story_gate",
                "match_party"}  # match_party: only from inside a finished match (the ship button)
stranded = [s for s in screens if s not in {"game_loading", "roblox_teleport", "esc_menu", "obtained_rewards"} and find_route(edges, s, "lobby") is None]
check("every screen has a way back to the lobby", not stranded, stranded)
unreachable = [s for s in screens if s not in results_only | {"exit_confirm", "victory", "defeat"} and find_route(edges, "lobby", s) is None]
check("every menu can be reached from the lobby", not unreachable, unreachable)
route = find_route(edges, "lobby", "sandbox_picker")
check("Sandbox route is lobby, top, bottom, picker", [e.target for e in route] == ["play_menu_top", "play_menu_bottom", "sandbox_picker"])
route = find_route(edges, "party_room", "lobby")
check("tested edges are preferred, untested used if needed", route is not None and route[0].untested, [e.target for e in route])

# --------------------------------------------------------------- normal travel
game = FakeGame(detector)
nav = Navigator(game, detector)
for goal in ("story_mastery", "raid_act_picker", "tower", "soul_furnace_picker", "lobby", "sandbox_picker", "party_room"):
    try:
        check(f"reaches {goal} and is confirmed there", nav.go(goal) == goal and game.screen == goal, game.screen)
    except NavError as e:
        check(f"reaches {goal}", False, e)

game = FakeGame(detector, start="match")
nav = Navigator(game, detector)
check("leaves a match through the confirm and the trip", nav.go("lobby") == "lobby" and game.screen == "lobby")

# ---------------------------------------------------------------- things going wrong
game = FakeGame(detector)
nav = Navigator(game, detector)
game.lose_next_clicks = 2
check("a lost click is retried", nav.go("story_maps") == "story_maps", f"{len(game.clicks)} clicks")

game = FakeGame(detector, start="play_menu_top")
nav = Navigator(game, detector)
game.next_click_goes_to = "raid_maps"
check("a click landing on the wrong screen re-routes", nav.go("story_maps") == "story_maps" and game.screen == "story_maps", game.screen)

game = FakeGame(detector, start="quests")
nav = Navigator(game, detector)
check("starting mid-way through a panel still gets home", nav.go("lobby") == "lobby")

game = FakeGame(detector)
nav = Navigator(game, detector)
game.lose_next_clicks = 10_000
try:
    nav.go("story_maps", max_steps=4)
    check("a dead button ends in an error, not forever", False)
except NavError as e:
    check("a dead button ends in an error, not forever", True, e)

black = np.zeros((1080, 1920, 3), np.uint8)
game = FakeGame(detector)
game.overlay = black


def clear_after():
    time.sleep(0.2)
    game.overlay = None


import threading

nav = Navigator(game, detector)
threading.Thread(target=clear_after, daemon=True).start()
check("black screens are waited out, not treated as lost", nav.go("lobby", on_lost=lambda s: False) == "lobby")

game = FakeGame(detector, start="esc_menu")
game_key = game.key
game.key = lambda name, hold=0.05: (game_key(name, hold), setattr(game, "screen", "lobby"))[0]
nav = Navigator(game, detector)
check("Roblox's own menu is closed, not a dead end", nav.go("story_maps") == "story_maps" and game.keys == ["escape"], game.keys)

# ---------------------------------------------------------- reading stage names
from macro.nav.stages import _names_map, header_matches

check("a misread map name still matches", header_matches("storycrimsonsshoreact1nnormalmode", "Crimson Shore", 1, "Normal"))
check("a misread name can't match a different map", not header_matches("storycrimsonsshoreact1nnormalmode", "East Town", 1, "Normal"))
check("similar names stay apart", not _names_map("fairykingforest", "Flower Forest") and not _names_map("flowerforest", "Fairy King Forest"))
check("the wrong act is refused", not header_matches("storyschoolgroundsact2normalmode", "School Grounds", 1, "Normal"))
check("the wrong difficulty is refused", not header_matches("storyschoolgroundsact1hardmode", "School Grounds", 1, "Normal"))

# --------------------------------------------------------------- recovery
noise = np.random.default_rng(2).integers(0, 255, (1080, 1920, 3), dtype=np.uint8)
check("word plan: money beats everything",
      plan_for_words([("Close", 1, 1), ("Buy for 100 Robux", 2, 2), ("Cancel", 3, 3)]) == ("money_stop", (3, 3)))
check("word plan: Reconnect", plan_for_words([("Disconnected", 1, 1), ("Reconnect", 5, 6), ("Leave", 9, 9)]) == ("reconnect", (5, 6)))
check("word plan: close needs the exact word", plan_for_words([("Close the store and buy", 1, 1)])[0] == "money_stop"
      and plan_for_words([("Closed for now", 1, 1)]) == ("none", None) and plan_for_words([("Okay", 7, 8)]) == ("close", (7, 8)))
check("word plan: Roblox's joining screen is waited out, its X never clicked",
      plan_for_words([("X", 50, 50), ("Anime Expeditions", 5, 5), ("Joining server", 9, 9)]) == ("joining", None))
check("word plan: Roblox's home page means relaunch",
      plan_for_words([("Add Friends", 1, 1), ("Recommended ForYou", 2, 2), ("Home", 3, 3)]) == ("home", None)
      and plan_for_words([("Charts", 1, 1), ("Close", 5, 5)]) == ("close", (5, 5)))
check("word plan: never clicks Leave", plan_for_words([("Leave", 1, 1)]) == ("none", None))


def scenario(words, setup=None, may_restart=True, goal="lobby"):
    game = FakeGame(detector)
    game.overlay = noise
    if setup:
        setup(game)
    nav = Navigator(game, detector)

    def read_words(frame):
        return words(game) if callable(words) else words

    recovery = Recovery(game, nav, may_restart=may_restart, read_words=read_words)
    return game, nav, recovery


def popup_words(game):
    return [("You leveled up!", 500, 300), ("Close", 960, 700)]


class ClosablePopup(FakeGame):
    pass


game, nav, recovery = scenario(popup_words)
original = game.click
game.click = lambda x, y, *a, **k: (original(x, y), setattr(game, "overlay", None))[0]
check("a popup is closed with its own button", nav.go("lobby", on_lost=recovery) == "lobby" and (960, 700) in game.clicks)

game, nav, recovery = scenario([("Disconnected", 900, 400), ("Reconnect", 800, 700), ("Leave", 1100, 700)])
original_dis = game.click
game.click = lambda x, y, *a, **k: (original_dis(x, y), setattr(game, "overlay", None))[0]
check("a disconnect presses Reconnect, not Leave",
      nav.go("lobby", on_lost=recovery) == "lobby" and (800, 700) in game.clicks and (1100, 700) not in game.clicks)

game, nav, recovery = scenario([("Buy Gems", 900, 400), ("100 Robux", 900, 500), ("Cancel", 800, 700), ("Buy", 1100, 700)])
try:
    nav.go("lobby", on_lost=recovery)
    check("a purchase prompt stops the run", False)
except RunStopped as e:
    check("a purchase prompt stops the run", True)
    check("  it pressed Cancel and never Buy", (800, 700) in game.clicks and (1100, 700) not in game.clicks, game.clicks)

game, nav, recovery = scenario([("Buy Gems", 900, 400)])
try:
    nav.go("lobby", on_lost=recovery)
    check("a purchase prompt with no Cancel clicks nothing and stops", False)
except RunStopped:
    check("a purchase prompt with no Cancel clicks nothing and stops", game.clicks == [], game.clicks)

game, nav, recovery = scenario([("Strange text", 900, 400), ("Leave", 1100, 700)])
try:
    nav.go("lobby", on_lost=recovery)
    check("an unknown screen with nothing safe stops the run", False)
except RunStopped as e:
    check("an unknown screen with nothing safe stops the run", game.clicks == [] and game.keys == ["escape"],
          f"clicks {game.clicks}, keys {game.keys}")

game, nav, recovery = scenario([], setup=lambda g: setattr(g, "running", False))
check("a crash restarts Roblox and carries on", nav.go("lobby", on_lost=recovery) == "lobby" and game.restarts == 1)

game, nav, recovery = scenario([], setup=lambda g: setattr(g, "frozen", True))
check("a freeze restarts Roblox and carries on", nav.go("lobby", on_lost=recovery) == "lobby" and game.restarts == 1)

game, nav, recovery = scenario([], setup=lambda g: setattr(g, "running", False), may_restart=False)
try:
    nav.go("lobby", on_lost=recovery)
    check("a crash stops the run if restarting isn't allowed", False)
except RunStopped:
    check("a crash stops the run if restarting isn't allowed", game.restarts == 0)

for path in (set(os.listdir(LOGS)) - LOGS_BEFORE) if os.path.isdir(LOGS) else []:
    if path.startswith(("stopped-", "lost-")):
        os.remove(os.path.join(ROOT, "logs", path))

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
