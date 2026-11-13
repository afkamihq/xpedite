"""Getting anywhere in the game: find a route through the screen graph, take one step,
confirm the screen it led to, and look again.

Nothing here is "click and hope". Every step says which screen it expects, and if a
different one appears the route is worked out afresh from where the game really is.
Only allow-listed buttons (data/screens.yaml) can be clicked.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass

import cv2
import yaml

from macro.platform import GuardTripped, Platform
from macro.vision.screens import LOADING, ROOT, UNKNOWN, ScreenDetector, scaled

STABLE_FOR = 0.3  # a screen counts once it has held this long; animations flicker
STEP_TIMEOUT = 12.0
TRIP_TIMEOUT = 120.0
AFTER_ARRIVAL = 0.8  # menus keep animating, and clicks made during that get lost
POLL = 0.03
MAX_SAME_STEP = 3


class NavError(RuntimeError):
    """Couldn't get there, and it needs recovery or a person. The message says why."""


@dataclass
class Edge:
    source: str
    target: str
    do: str | None = None
    scroll: str | None = None
    key: str | None = None
    trip: bool = False
    untested: bool = False


def load_edges() -> tuple[list[Edge], dict]:
    with open(os.path.join(ROOT, "data", "nav.yaml"), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    edges = [Edge(source=e["from"], target=e["to"], do=e.get("do"), scroll=e.get("scroll"), key=e.get("key"),
                  trip=e.get("trip", False), untested=e.get("untested", False)) for e in data["edges"]]
    return edges, data["scrolls"]


def find_route(edges: list[Edge], start: str, goal: str) -> list[Edge] | None:
    """Fewest steps from start to goal, or None. Untested edges are used only when
    there's no other way."""
    for allow_untested in (False, True):
        queue, seen = deque([(start, [])]), {start}
        while queue:
            screen, path = queue.popleft()
            if screen == goal:
                return path
            for edge in edges:
                if edge.source == screen and edge.target not in seen and edge.target != "any"\
                        and (allow_untested or not edge.untested):
                    seen.add(edge.target)
                    queue.append((edge.target, path + [edge]))
    return None


# A party invite from another player (seen 10 Nov 2026): a banner at the top with a green
# Accept and a red Decline side by side. Only Decline is ever pressed.
INVITE_ACCEPT = (977, 277)
INVITE_DECLINE = (1171, 277)


def invite_showing(frame) -> bool:
    def patch(point):
        # The band above the button's word: pure button colour.
        x, y = scaled(*point)
        return frame[y - 14:y - 10, x - 30:x + 30].reshape(-1, 3).mean(axis=0)
    b, g, r = patch(INVITE_ACCEPT)
    accept_green = g > 200 and r < 180 and b < 90
    b, g, r = patch(INVITE_DECLINE)
    decline_red = r > 200 and g < 100 and b < 100
    return accept_green and decline_red


class Navigator:
    def __init__(self, platform: Platform, detector: ScreenDetector | None = None, log=None):
        self.p = platform
        self.detector = detector or ScreenDetector()
        self.edges, self.scrolls = load_edges()
        self.log = log or (lambda text: None)
        self._last_frame = None

    # ------------------------------------------------------------------ seeing
    def see(self) -> str:
        self._last_frame = self.p.grab()
        if invite_showing(self._last_frame):
            # Another player's party invite sits over the top of the screen: always Decline.
            self.log("declined a party invite")
            self.p.click(*scaled(*INVITE_DECLINE))
            self.p.sleep(0.4)
            self._last_frame = self.p.grab()
        return self.detector.classify(self._last_frame).name

    @property
    def last_frame(self):
        return self._last_frame

    def settle(self, timeout: float = 5.0) -> str:
        """The screen once it has held still, or whatever it was last if it won't."""
        start = self.p.now()
        current, since = self.see(), self.p.now()
        while self.p.now() - start < timeout:
            self.p.sleep(POLL)
            name = self.see()
            if name != current:
                current, since = name, self.p.now()
            elif self.p.now() - since >= STABLE_FOR:
                break
        return current

    def wait_for(self, expected: str | set[str], timeout: float = STEP_TIMEOUT) -> str | None:
        """Wait until the expected screen has held. Returns it, or None on timeout."""
        wanted = {expected} if isinstance(expected, str) else expected
        start = self.p.now()
        current, since = None, start
        while self.p.now() - start < timeout:
            name = self.see()
            if name != current:
                current, since = name, self.p.now()
            if name in wanted and self.p.now() - since >= STABLE_FOR:
                return name
            self.p.sleep(POLL)
        return None

    # ------------------------------------------------------------------- acting
    def press(self, screen: str, button: str):
        """Click an allow-listed button. Asking for anything else raises KeyError."""
        where = self.detector.button(screen, button)
        if button == "back_to_lobby":
            where = self._find_exit_icon() or where
        self.p.click(*where)

    _EXIT_ICON = None

    def _find_exit_icon(self):
        """The exit door in Roblox's top bar, found by its picture: its place depends on which
        icons Roblox shows before it (12 Nov 2026: with no voice chat, as in the Remote Desktop
        account, there's no microphone and the door sits 55 px further left)."""
        import os

        import cv2
        if Navigator._EXIT_ICON is None:
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                "data", "icons", "topbar_exit.png")
            Navigator._EXIT_ICON = cv2.imread(path)
        icon = Navigator._EXIT_ICON
        if icon is None:
            return None
        region = self.p.grab()[10:75, 200:470]
        result = cv2.matchTemplate(region, icon, cv2.TM_CCOEFF_NORMED)
        _, value, _, at = cv2.minMaxLoc(result)
        if value < 0.8:
            return None
        return 200 + at[0] + icon.shape[1] // 2, 10 + at[1] + icon.shape[0] // 2

    def scroll_at(self, x: int, y: int, amount: float):
        self.p.hover(x, y)
        self.p.scroll(amount)

    def _perform(self, edge: Edge):
        if edge.scroll:
            spec = self.scrolls[edge.scroll]
            self.scroll_at(*scaled(*spec["at"]), spec["amount"])
        elif edge.key:
            self.p.key(edge.key)
        elif edge.do == "open_soul_furnace":
            self.press("events", "halloween")
            self.p.sleep(1.2)
            self.press("events", "event_gamemode")
        elif edge.do == "select_school_grounds":
            self.press("sandbox_picker", "school_grounds")
            self.p.sleep(0.6)
            self.press("sandbox_picker", "select_map")
        else:
            self.press(edge.source, edge.do)

    def step(self, edge: Edge) -> str | None:
        """Take one edge. Returns the screen it led to, which might not be the expected
        one (the caller replans), or None if nothing recognisable came of it."""
        self.log(f"{edge.source} -> {edge.target}" + (" (untested)" if edge.untested else ""))
        self._perform(edge)
        timeout = TRIP_TIMEOUT if edge.trip else STEP_TIMEOUT
        wanted = {edge.target} if edge.target != "any" else set(self.detector.anchors) - {edge.source}
        arrived = self.wait_for(wanted, timeout)
        if arrived is None:
            arrived = self.settle(2.0)
            arrived = None if arrived in (UNKNOWN, *LOADING) else arrived
        else:
            self.p.sleep(AFTER_ARRIVAL)
        return arrived

    def _save_lost(self) -> str:
        """Keep the frame: a screen that wasn't recognised is how new ones get learned."""
        folder = os.path.join(ROOT, "logs")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"lost-{time.strftime('%Y%m%d-%H%M%S')}.png")
        if self._last_frame is not None:
            cv2.imwrite(path, self._last_frame)
        return path

    def go(self, goal: str, max_steps: int = 25, on_lost=None) -> str:
        """Go to a screen from wherever the game is now. on_lost(screen) is called when
        the screen is unknown or has no route, and should return True if it did
        something worth trying again after. Raises NavError if it can't get there."""
        lost_count = 0
        tries: dict[tuple[str, str], int] = {}
        for _ in range(max_steps):
            current = self.settle()
            if current == goal:
                return current
            route = find_route(self.edges, current, goal) if current not in (UNKNOWN, *LOADING) else None
            if route:
                # The same step from the same screen, over and over, isn't working. It may
                # mean the screen isn't what it looks like, so don't keep clicking.
                attempt = (current, route[0].target)
                tries[attempt] = tries.get(attempt, 0) + 1
                if tries[attempt] > MAX_SAME_STEP:
                    raise NavError(f"{current} -> {route[0].target} failed {MAX_SAME_STEP} times; "
                                   f"screen saved as {self._save_lost()}")
                self.step(route[0])
                continue
            # A menu like Roblox's own closes back to whatever is underneath.
            closes = next((e for e in self.edges if e.source == current and e.target == "any"), None)
            if closes:
                self.step(closes)
                continue
            if current in LOADING:
                # A trip in progress: wait for it to finish rather than call it lost.
                arrived = self.wait_for(set(self.detector.anchors) - LOADING, TRIP_TIMEOUT)
                if arrived is not None:
                    continue
                current = self.settle(1.0)
            lost_count += 1
            if lost_count > 5:
                break
            self.log(f"lost on {current} (going to {goal}); screen saved as {self._save_lost()}")
            if on_lost is None or not on_lost(current):
                raise NavError(f"on {current} with no way to {goal}")
        raise NavError(f"gave up going to {goal}; last screen {self.see()}")


__all__ = ["Edge", "GuardTripped", "NavError", "Navigator", "find_route", "load_edges"]
