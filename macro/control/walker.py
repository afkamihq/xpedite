"""Walking to things in the lobby by how they look: a Trick-or-Treat door's floating label, a
rift, an NPC. Look for the target's words on screen, turn the camera so they sit in the middle,
take a short walk, look again; stop when the game shows the target's "E" prompt.

Short hops with a look between each, because one long walk overshoots (10 Nov 2026: a 1.5 s
walk went straight past a door 3 m away). Everything is read off the screen with OCR, so it
works for any lobby layout the game ships, at the cost of about a second a look.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from macro.vision.ocr import find_words
from macro.vision.screens import ROOT  # noqa: F401  (the game's frame size comes with it)

YAW_DEG_PER_COUNT = 0.080      # data/calibration/win32.yaml
FOCAL_PX = 502.0               # measured: 200 counts (16 deg) moved the lobby view 144 px
CENTRE_X = 720
# Where the pointer sits for a camera turn: over the game (never the app), and high up, where no
# interact prompt sits: a right-drag that starts on a prompt doesn't turn the camera (user, 10 Nov).
# From here a full circle came back to the same pixels.
LOOK_FROM = (720, 95)


def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


@dataclass
class Seen:
    text: str
    x: int
    y: int


def find(frame, words: list[str], box=None) -> list[Seen]:
    """Every line of on-screen text containing one of `words` (spaces and case ignored)."""
    wanted = [_norm(w) for w in words]
    return [Seen(t, x, y) for t, x, y in find_words(frame, box) if any(w in _norm(t) for w in wanted)]


def counts_to_face(x: float) -> int:
    """Camera counts that bring screen column x to the middle."""
    return round(math.degrees(math.atan((x - CENTRE_X) / FOCAL_PX)) / YAW_DEG_PER_COUNT)


# Arrow-key turning, measured 10 Nov 2026 in the lobby: 12 taps of 0.25 s on Right came back to
# the very same view (and again at 24 and 36), so a 0.25 s tap is 30 degrees. Right turns the
# view right. Holds shorter than about 0.2 s barely turn (the key needs a moment to start).
TAP = 0.25
TAP_DEGREES = 30.0
FINE_TAP = 0.125
FINE_DEGREES = 15.0   # 24 taps of 0.125 s made a full circle (and 20 of 0.15 s): 120 deg a second
DEADBAND = 8.0        # a target this close to straight ahead needs no turn: the walk corrects it


def turn_degrees(p, degrees: float):
    """Turn right by `degrees` (negative: left) in arrow-key taps."""
    key = "right" if degrees > 0 else "left"
    left = abs(degrees)
    while left >= TAP_DEGREES - FINE_DEGREES / 2:
        p.key(key, TAP); p.sleep(0.12)
        left -= TAP_DEGREES
    while left >= max(DEADBAND, FINE_DEGREES / 2):
        p.key(key, FINE_TAP); p.sleep(0.12)
        left -= FINE_DEGREES
    p.sleep(0.15)


class Walker:
    """p: a Platform with the guard armed. log: a function taking a line of text."""

    def __init__(self, p, log=print):
        self.p, self.log = p, log

    def turn(self, counts: int):
        """Turn the camera by `counts` (the mouse's yaw unit, 0.080 deg each) with the arrow keys:
        no pointer is involved, so an interact prompt under the pointer can't swallow the turn
        (a right-drag that starts on one doesn't turn, user 10 Nov 2026)."""
        turn_degrees(self.p, counts * YAW_DEG_PER_COUNT)

    def look(self, words, avoid=None) -> list[Seen]:
        frame = self.p.grab()
        seen = find(frame, words, (0, 90, 1440, 640))  # below the top bar, above the hotbar
        if avoid:
            seen = [s for s in seen if not avoid(s)]
        return seen

    def search(self, words, steps: int = 12, avoid=None) -> Seen | None:
        """Turn round in `steps` until the words show. None after a full circle."""
        for i in range(steps):
            seen = self.look(words, avoid)
            if seen:
                return min(seen, key=lambda s: abs(s.x - CENTRE_X))
            self.turn(round(4501 / steps))
        return None

    def approach(self, target_words, prompt_words, max_hops: int = 25, hop: float = 0.45,
                 avoid=None) -> bool:
        """Walk until the prompt shows (True), or give up (False). The target must be in view
        at the start, or found by a search."""
        lost = 0
        for n in range(max_hops):
            frame = self.p.grab()
            prompt = find(frame, prompt_words, (0, 90, 1440, 640))
            if prompt:
                self.log(f"  prompt in view after {n} hops: {prompt[0].text!r}")
                return True
            seen = [s for s in find(frame, target_words, (0, 90, 1440, 640)) if not (avoid and avoid(s))]
            if not seen:
                lost += 1
                if lost > 2:
                    found = self.search(target_words, avoid=avoid)
                    if found is None:
                        self.log("  lost the target")
                        return False
                    lost = 0
                    continue
                self.p.key("w", hop / 2)  # it may be right behind the character
                continue
            lost = 0
            target = min(seen, key=lambda s: abs(s.x - CENTRE_X))
            angle = math.degrees(math.atan((target.x - CENTRE_X) / FOCAL_PX))
            if abs(angle) > DEADBAND:
                turn_degrees(self.p, angle)
            # Labels low on screen are close: shorter hops so the prompt isn't overshot.
            near = target.y > 380
            self.p.key("w", hop * (0.5 if near else 1.0))
            self.p.sleep(0.15)
        self.log(f"  no prompt after {max_hops} hops")
        return False
