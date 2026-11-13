"""The interface both backends share, and the input logic they have in common.

Units match what docs/GAME.md measured, so its numbers carry over: pixels at
1920x1080, scroll 15 = one notch (positive = down / zoom out), camera counts for
relative motion.

Every input goes through the guard. Presses are recorded under a lock, so a guard
trip can always release what is held and nothing can be pressed after it.
"""

from __future__ import annotations

import threading
import time

import numpy as np

LEFT, RIGHT, MIDDLE = "left", "right", "middle"


class GuardTripped(RuntimeError):
    """Input was refused or interrupted: the user took over, the game isn't in
    front, or the stop hotkey was pressed. str(error) says which."""


class PointerLocked(RuntimeError):
    """A click was refused because the pointer isn't where it was sent, so the game
    has locked it (see docs/GAME.md). Nothing was pressed."""


class Platform:
    width = 1920
    height = 1080
    nudge_to_hover = False  # the pointer must move over a button for it to click
    pointer_tries = 2  # hovers before a click is refused because the pointer isn't there

    def __init__(self):
        self.guard = None  # set by the backend: arm(), check(), tripped, reason
        self._io = threading.Lock()
        self._held_buttons: set[str] = set()
        self._held_keys: set[str] = set()

    # ------------------------------------------------- backends provide these
    def grab(self) -> np.ndarray:
        """The whole screen now, as a BGR image (height x width x 3)."""
        raise NotImplementedError

    def _move(self, x: float, y: float): raise NotImplementedError
    def _rel(self, dx: float, dy: float): raise NotImplementedError
    def _button(self, button: str, down: bool): raise NotImplementedError
    def _wheel(self, amount: float): raise NotImplementedError
    def _key(self, name: str, down: bool): raise NotImplementedError
    def _text(self, text: str): raise NotImplementedError
    def game_running(self) -> bool: raise NotImplementedError

    def _pointer_at(self, x: float, y: float) -> bool:
        """Whether the pointer is really there. Backends that can't tell say yes."""
        return True

    def launch_game(self):
        """Start Roblox into the game. This ends any other session on the
        account, so the caller must have permission to do that."""
        raise NotImplementedError

    def close(self):
        self.release_all()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ guarded input
    def now(self) -> float:
        """A clock that stops during pauses, so a pause can't make a wait time out."""
        return time.perf_counter() - self.guard.paused_total

    def _do(self, action, *args):
        """Run an input once input is allowed. With a pausing guard this waits through a pause
        and carries on. It can't wait while holding the lock, as releasing keys needs it."""
        while True:
            self.guard.wait_if_paused()
            with self._io:
                try:
                    self.guard.check()
                except GuardTripped:
                    if self.guard.pausable and not self.guard.stopped:
                        continue
                    raise
                action(*args)
                return

    def sleep(self, seconds: float):
        """Wait, but stop at once if the guard trips. Slices of 5 ms keep the
        hold times used for walking accurate."""
        end = time.perf_counter() + seconds
        while (left := end - time.perf_counter()) > 0:
            time.sleep(min(left, 0.005))
            before = self.guard.paused_total
            self.guard.wait_if_paused()
            end += self.guard.paused_total - before
            if not self.guard.pausable:
                self.guard.check()

    def move(self, x: float, y: float):
        self._do(self._move, x, y)

    def move_rel(self, dx: float, dy: float):
        """Relative motion: what Roblox reads while it has the pointer locked."""
        self._do(self._rel, dx, dy)

    def scroll(self, amount: float):
        self._do(self._wheel, amount)

    def type_text(self, text: str):
        self._do(self._text, text)

    def button_down(self, button: str):
        def press():
            self._button(button, True)
            self._held_buttons.add(button)
        self._do(press)

    def button_up(self, button: str):
        """Always allowed: releasing is the safe direction."""
        with self._io:
            if button in self._held_buttons:
                self._button(button, False)
                self._held_buttons.discard(button)

    def key_down(self, name: str):
        def press():
            self._key(name, True)
            self._held_keys.add(name)
        self._do(press)

    def key_up(self, name: str):
        """Always allowed: releasing is the safe direction."""
        with self._io:
            if name in self._held_keys:
                self._key(name, False)
                self._held_keys.discard(name)

    def release_all(self):
        with self._io:
            for name in list(self._held_keys):
                self._key(name, False)
            self._held_keys.clear()
            for button in list(self._held_buttons):
                self._button(button, False)
            self._held_buttons.clear()

    # --------------------------------------------------------------- gestures
    def hover(self, x: float, y: float):
        """Put the pointer somewhere so that Roblox notices. On Windows it ignores a plain
        jump: a button under the new spot won't click, and a tooltip under the old spot
        stays up."""
        self.move(x, y)
        self.sleep(0.05)
        if self.nudge_to_hover:
            self.move_rel(2, 0)
            self.sleep(0.05)
            self.move(x, y)
            self.sleep(0.15)

    def click(self, x: float, y: float, button: str = LEFT, hold: float = 0.06):
        # Roblox reads hover first: arrive, settle, press, release.
        self.hover(x, y)
        for _ in range(self.pointer_tries - 1):  # moved in between? look again before refusing
            if self._pointer_at(x, y):
                break
            self.sleep(0.25)
            self.hover(x, y)
        if not self._pointer_at(x, y):
            raise PointerLocked(f"asked for ({x}, {y}) but the game is holding the pointer")
        self.button_down(button)
        try:
            self.sleep(hold)
        finally:
            self.button_up(button)

    def key(self, name: str, hold: float = 0.05):
        self.key_down(name)
        try:
            self.sleep(hold)
        finally:
            self.key_up(name)

    def turn(self, dx: float, dy: float = 0.0, steps: int = 10, step_s: float = 0.01):
        """Hold the right button and push the mouse by (dx, dy) counts."""
        self.button_down(RIGHT)
        try:
            self.sleep(0.03)
            for _ in range(steps):
                self.move_rel(dx / steps, dy / steps)
                self.sleep(step_s)
            self.sleep(0.03)
        finally:
            self.button_up(RIGHT)
