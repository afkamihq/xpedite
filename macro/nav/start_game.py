"""The "Start Game?" window a match waits under while Auto Vote Start is off, and the results
window's banner. Used by Story, Sandbox and challenges alike."""
from __future__ import annotations

import cv2

from macro.vision.screens import SCALE, scaled

# With the game's Auto Vote Start off (the user's choice, 10 Nov 2026: a slow PC can load a
# match at wave 5 otherwise), a match waits at wave 0 under a "Start Game?" window until its
# green Start Game button is pressed. The macro sets the camera and makes its first move
# first, with the clock stopped, then presses it.
START_GAME = (960, 331)  # 1920x1080 scale
BANNER = (360, 176, 666, 224)  # the results window's title banner, 1920x1080 scale


def banner_outcome(frame) -> str | None:
    """Victory or Defeat by the results window's title banner: blue or red. The layout alone
    can't tell them apart on a map's last act, whose Victory has no Next Stage button
    (Hollow Desert Act 3 was logged a defeat, 10 Nov 2026)."""
    x0, y0, x1, y1 = (round(v * SCALE) for v in BANNER)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    strong = hsv[..., 1] > 120
    hue = hsv[..., 0]
    blue = ((hue > 85) & (hue < 125) & strong).mean()
    red = (((hue < 10) | (hue > 165)) & strong).mean()
    if blue > 0.5 and red < 0.1:
        return "victory"
    if red > 0.5 and blue < 0.1:
        return "defeat"
    return None


def start_window_showing(frame) -> bool:
    """The Start Game button, sampled on its plain band above the words at three points: green,
    or purple while the pointer is over it."""
    x, y = scaled(*START_GAME)
    for dx in (-100, 0, 100):
        b, g, r = frame[y - 13:y - 9, x + dx - 3:x + dx + 3].reshape(-1, 3).mean(axis=0)
        green = g > 200 and b < 90 and 100 < r < 180
        purple = b > 90 and g < 40 and 50 < r < 160
        if not (green or purple):
            return False
    return True


def press_start(nav, log=None, tries: int = 3) -> bool:
    """Press Start Game if its window is up, again if a click comes too early to take (seen in
    Sandbox, 10 Nov 2026). True once the window has gone."""
    p = nav.p
    for attempt in range(tries):
        if not start_window_showing(p.grab()):
            return attempt > 0
        p.hover(*scaled(*START_GAME))
        p.sleep(0.15)
        p.click(*scaled(*START_GAME))
        end = p.now() + 3.0
        while p.now() < end:
            p.sleep(0.25)
            if not start_window_showing(p.grab()):
                if log:
                    log("  pressed Start Game")
                return True
    return False
