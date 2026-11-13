"""Getting unstuck: the ladder from docs/ARCHITECTURE.md.

1. A purchase prompt: cancel it and stop the run. Nothing is worth a chance of spending.
2. Roblox gone or frozen: restart it, if the run allows that.
3. A disconnect dialog: Reconnect.
4. A popup: click its Close/OK-style button, found by reading the screen.
5. Still lost: Escape once, in case a menu is open.
6. Give up: save what's on screen and say why.

On an unknown screen, the only things it may click are the exact safe words below,
and text naming money overrides them all.
"""

from __future__ import annotations

import os
import re
import time

import cv2

from macro.platform import Platform
from macro.vision.screens import ROOT

# Seeing any of these on an unknown screen means a spending prompt may be up.
MONEY_WORDS = ("robux", "purchase", "buy", "premium", "gamepass", "subscribe")
CANCEL_WORDS = ("cancel", "not now", "no thanks")
RECONNECT_WORDS = ("reconnect",)
DISCONNECT_WORDS = ("disconnected", "connection lost", "lost connection", "error code", "reconnect")
# Only ever clicked when the whole line of text is exactly one of these.
SAFE_CLOSE_WORDS = ("close", "ok", "okay", "continue", "x", "done", "got it", "skip")
MAX_POPUPS = 5
# Roblox's own "Joining server" screen has an X that cancels the join: wait, never click.
JOINING_WORDS = ("joining server", "expeditions entertainment")
# The second is Roblox's place card while it joins a teleport (a Trick's match, 10 Nov 2026): the
# game's name over a blurred background, its creator below.
# Roblox's home page: the client is open but not in the game (a cancelled or failed join).
# Compared with spaces removed, as the reader often drops them. Any two are enough.
HOME_WORDS = ("recommendedforyou", "addfriends", "moments", "charts")
JOIN_TIMEOUT = 150.0


class RunStopped(RuntimeError):
    """The run must stop for a person to look. The message says why, and a frame is
    saved in logs/."""


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def plan_for_words(words: list[tuple[str, int, int]]) -> tuple[str, tuple[int, int] | None]:
    """What to do given the text on an unknown screen: (action, where). The action is
    one of money_stop, reconnect, joining, home, close, none. Pure logic, so it can be tested."""
    lines = [(_normal(text), x, y) for text, x, y in words]
    if any(word in text for text, _, _ in lines for word in JOINING_WORDS):
        return "joining", None
    packed = [text.replace(" ", "") for text, _, _ in lines]
    if sum(any(word in text for text in packed) for word in HOME_WORDS) >= 2:
        return "home", None
    if any(word in text for text, _, _ in lines for word in MONEY_WORDS):
        cancel = next(((x, y) for text, x, y in lines if text in CANCEL_WORDS), None)
        return "money_stop", cancel
    if any(word in text for text, _, _ in lines for word in DISCONNECT_WORDS):
        reconnect = next(((x, y) for text, x, y in lines if text in RECONNECT_WORDS), None)
        if reconnect:
            return "reconnect", reconnect
    for text, x, y in lines:
        if text in SAFE_CLOSE_WORDS:
            return "close", (x, y)
    return "none", None


class Recovery:
    def __init__(self, platform: Platform, navigator, may_restart: bool = True, read_words=None, log=None):
        self.p = platform
        self.nav = navigator
        self.may_restart = may_restart
        self.log = log or (lambda text: None)
        self.popups_closed = 0
        self.escaped = False
        self._read_words = read_words  # the OCR is replaced in tests

    def read_words(self, frame):
        if self._read_words:
            return self._read_words(frame)
        from macro.vision import ocr

        return ocr.find_words(frame)

    def stop(self, why: str):
        folder = os.path.join(ROOT, "logs")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"stopped-{time.strftime('%Y%m%d-%H%M%S')}.png")
        if self.nav.last_frame is not None:
            cv2.imwrite(path, self.nav.last_frame)
        raise RunStopped(f"{why} (screen saved to {path})")

    def game_problem(self) -> str | None:
        """Roblox gone or frozen, if the platform can tell."""
        if not self.p.game_running():
            return "Roblox isn't running"
        check = getattr(self.p, "game_frozen", None)
        if check and check():
            return "Roblox has stopped responding"
        return None

    def restart_game(self, why: str, wait: bool = True) -> bool:
        if not self.may_restart:
            self.stop(f"{why}, and this run isn't allowed to restart it")
        self.log(f"{why}: restarting it")
        kill = getattr(self.p, "close_game", None)
        if kill:
            kill()
        problem = self.p.make_game_ready()
        if problem:
            self.stop(f"couldn't restart Roblox: {problem}")
        self.p.guard.arm()
        if wait:
            self.wait_until_in_game()
        return True

    def wait_until_in_game(self, timeout: float = JOIN_TIMEOUT) -> bool:
        """After a start: sit through Roblox's joining and the game's loading, clicking nothing."""
        from macro.vision.screens import LOADING, UNKNOWN

        known = set(self.nav.detector.anchors) - set(LOADING) - {UNKNOWN}
        end = self.p.now() + timeout
        relaunched = False
        while self.p.now() < end:
            if self.nav.wait_for(known, 10.0) is not None:
                return True
            # Roblox open on its home page will never load the game: start the game again, once.
            if not relaunched and self.nav.last_frame is not None                     and plan_for_words(self.read_words(self.nav.last_frame))[0] == "home":
                relaunched = True
                self.restart_game("Roblox is on its home page, not in the game", wait=False)
                end = self.p.now() + timeout
        self.log(f"the game still hadn't loaded after {timeout:.0f} s")
        return False

    def __call__(self, screen: str) -> bool:
        """Navigator's on_lost. True if it did something worth trying again after."""
        problem = self.game_problem()
        if problem:
            return self.restart_game(problem)

        action, where = plan_for_words(self.read_words(self.nav.last_frame))
        if action == "joining":
            self.log("Roblox is joining the server: waiting")
            self.wait_until_in_game()
            return True
        if action == "home":
            return self.restart_game("Roblox is on its home page, not in the game")
        if action == "money_stop":
            if where:
                self.p.click(*where)
            self.stop("a purchase prompt appeared on an unknown screen, so the run stopped"
                      + (" after cancelling it" if where else ", with no Cancel to press"))
        if action == "reconnect":
            self.log("disconnected: pressing Reconnect")
            self.p.click(*where)
            self.p.sleep(3)
            return True
        if action == "close" and self.popups_closed < MAX_POPUPS:
            self.popups_closed += 1
            self.log(f"closing a popup at {where}")
            self.p.click(*where)
            self.p.sleep(0.8)
            return True
        if not self.escaped:
            # If no menu was open this opens Roblox's own, which the navigator closes.
            self.escaped = True
            self.log("unknown screen, nothing safe to click: pressing Escape once")
            self.p.key("escape")
            self.p.sleep(1.0)
            return True
        self.stop(f"lost on {screen}, with nothing safe to click")
        return False
