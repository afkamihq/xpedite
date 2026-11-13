"""Choosing a particular stage, and starting it.

Islands are found by reading their names rather than from saved positions, because
the row scrolls. The stage picker's header is read back before anything starts, so a
wrong map, act or difficulty is caught and not played.
"""

from __future__ import annotations

import re
import time
from difflib import SequenceMatcher

import cv2

from macro.nav.navigator import NavError, Navigator, STEP_TIMEOUT
from macro.vision import ocr
from macro.vision.screens import SCALE, scaled

STORY_MAPS = ["School Grounds", "Flower Forest", "Rose Kingdom", "Fairy King Forest", "King's Tomb", "East Town",
              "Crimson Shore", "Flaming Monastery", "Hollow Desert"]
ISLAND_NAME_ROW = tuple(round(v * SCALE) for v in (0, 585, 1920, 650 + 24))  # the names under the islands
ISLAND_CLICK_Y = round(450 * SCALE)
ROW_CENTRE = scaled(960, 450)
# Map, act and difficulty in the stage picker. Taller at this size, as it sits lower.
HEADER_BOX = (400, 215, 700, 270) if SCALE != 1 else (440, 270, 1000, 360)
# The small green "Normal Mode" comes and goes with the enlargement, so try several.
HEADER_OCR_SCALES = (3.0, 2.0, 4.0, 2.67)
SCROLL_ALL_LEFT = -2000
SCROLL_STEP = 100  # about 660 px, so less than a screen
MAX_SCROLLS = 6
TRIP_TO_MATCH = 150.0  # a slow load once took over 90 s (Hollow Desert, 10 Nov)
MIN_NAME_MATCH = 0.8
ROW_MOVED_PX = 1


def _simple(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _similarity(name: str, text: str) -> float:
    """How well name appears somewhere in text, from 0 to 1."""
    best = 0.0
    width = len(name)
    for start in range(max(1, len(text) - width + 1)):
        for size in (width - 1, width, width + 1):
            best = max(best, SequenceMatcher(None, name, text[start:start + size]).ratio())
    return best


def _names_map(text: str, map_name: str) -> bool:
    """Whether text names this map. OCR misreads a letter now and then ("crimsonsshore"),
    so it needn't be exact, but no other map may fit better."""
    scores = {name: _similarity(_simple(name), text) for name in STORY_MAPS}
    return scores[map_name] >= MIN_NAME_MATCH and scores[map_name] == max(scores.values())


def find_island(frame, map_name: str) -> int | None:
    """The screen x of a map's island, or None if its name isn't showing."""
    for text, x, _ in ocr.find_words(frame, ISLAND_NAME_ROW):
        if _names_map(_simple(text), map_name):
            return x
    return None


def read_header(frame) -> str:
    """The stage picker's header, simplified: "storyschoolgroundsact1normalmode". At
    scale 2 this read all the test pictures; other scales lost the small green text."""
    return _simple(ocr.read_text(frame, HEADER_BOX, scale=HEADER_OCR_SCALES[0]))


def header_says(frame, map_name: str, act: int, difficulty: str) -> tuple[bool, str]:
    """Whether the picker's header names this stage, trying each enlargement. A wrong
    stage can't pass by this: each attempt must still read the right words."""
    header = ""
    for scale in HEADER_OCR_SCALES:
        header = _simple(ocr.read_text(frame, HEADER_BOX, scale=scale))
        if header_matches(header, map_name, act, difficulty):
            return True, header
    return False, header


def header_matches(header: str, map_name: str, act: int, difficulty: str) -> bool:
    """Act and difficulty must be exact: one wrong character there is a different stage."""
    return (_names_map(header, map_name) and re.search(rf"act{act}(?!\d)", header) is not None
            and _simple(difficulty) in header)


def _row_shift(before, after) -> int:
    """How many pixels the island row moved between two frames. Compared by position, not
    brightness, because the row shimmers even when it's still."""
    x0, y0, x1, y1 = ISLAND_NAME_ROW
    a = cv2.cvtColor(before[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(after[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    width = a.shape[1]
    start = width // 3
    piece = a[:, start:2 * start]
    _, _, _, (found, _) = cv2.minMaxLoc(cv2.matchTemplate(b, piece, cv2.TM_CCOEFF_NORMED))
    return abs(found - start)


def _wait_row_still(nav: Navigator, timeout: float = 5.0):
    """The row glides after a scroll, and a click during that lands on the wrong island.
    Wait until it has stopped. Leaves the still frame in nav.last_frame."""
    nav.see()
    previous = nav.last_frame
    end = time.perf_counter() + timeout
    still_since = time.perf_counter()
    while time.perf_counter() < end:
        nav.p.sleep(0.1)
        nav.see()
        if _row_shift(previous, nav.last_frame) > ROW_MOVED_PX:
            still_since = time.perf_counter()
        elif time.perf_counter() - still_since >= 0.4:
            return
        previous = nav.last_frame


def choose_story_stage(nav: Navigator, map_name: str, act: int, difficulty: str = "Normal", on_lost=None):
    """Go to a Story stage's picker and confirm it's showing that stage. Raises NavError
    otherwise. Doesn't start anything."""
    if map_name not in STORY_MAPS:
        raise NavError(f"{map_name!r} isn't a known Story map")
    if not 1 <= act <= 5 or difficulty not in ("Normal", "Hard"):
        raise NavError(f"no such stage: act {act}, {difficulty}")
    nav.go("story_maps", on_lost=on_lost)
    nav.scroll_at(*ROW_CENTRE, SCROLL_ALL_LEFT)
    _wait_row_still(nav)
    x = None
    for _ in range(MAX_SCROLLS + 4):
        read_from = nav.last_frame
        x = find_island(read_from, map_name)
        if x is not None:
            # Reading takes 0.6 s, and a long scroll can still be gliding slowly. The
            # position is only good if the row hasn't moved since that frame.
            nav.see()
            if _row_shift(read_from, nav.last_frame) <= ROW_MOVED_PX:
                break
            x = None
            _wait_row_still(nav)
            continue
        nav.scroll_at(*ROW_CENTRE, SCROLL_STEP)
        _wait_row_still(nav)
    if x is None:
        raise NavError(f"couldn't find the {map_name} island")
    nav.p.click(x, ISLAND_CLICK_Y)
    # Hollow Desert's picker opens on its "4th Gate" tab (a mode of its own, never played here).
    if nav.wait_for({"story_act", "story_gate"}, STEP_TIMEOUT) is None:
        raise NavError(f"clicking {map_name} didn't open its stage picker; on {nav.settle()}")
    nav.p.sleep(0.8)
    if map_name == "Hollow Desert":
        if act > 3:
            raise NavError("Hollow Desert has acts 1 to 3")
        nav.press("story_act", f"hd_tab_{act}")
        if nav.wait_for("story_act", STEP_TIMEOUT) is None:
            raise NavError(f"Hollow Desert's act {act} tab didn't open; on {nav.settle()}")
    else:
        nav.press("story_act", f"tab_{act}")
    nav.p.sleep(0.6)
    nav.press("story_act", difficulty.lower())
    nav.p.sleep(0.8)
    # OCR can drop a word on one frame, so look a few times before calling it wrong.
    header = ""
    for _ in range(2):
        nav.see()
        matched, header = header_says(nav.last_frame, map_name, act, difficulty)
        if matched:
            return
        nav.p.sleep(0.4)
    raise NavError(f"wanted {map_name} act {act} {difficulty}, but the picker says {header!r}")


def start_sandbox(nav: Navigator, on_lost=None, map_button: str = "school_grounds") -> None:
    """Go into a free Sandbox match on a map in the picker, until the match shows."""
    # Through the Sandbox picker by name: asking for "party_room" would find the shorter
    # way, through Story, and that room's Start is somewhere else.
    nav.go("sandbox_picker", on_lost=on_lost)
    nav.press("sandbox_picker", map_button)
    nav.p.sleep(0.6)
    nav.press("sandbox_picker", "select_map")
    if nav.wait_for("party_room", STEP_TIMEOUT) is None:
        raise NavError(f"Select Map didn't reach the party room; on {nav.settle()}")
    nav.p.sleep(0.8)
    nav.press("party_room", "start_sandbox")
    if nav.wait_for("match", TRIP_TO_MATCH) is None:
        raise NavError(f"the Sandbox match never started; on {nav.settle()}")
    # Sandbox has no stakes: start at once, so the "Start Game?" window isn't in the way.
    from macro.nav.start_game import press_start, start_window_showing
    end = nav.p.now() + 10.0
    while nav.p.now() < end and not start_window_showing(nav.p.grab()):
        nav.p.sleep(0.3)
    press_start(nav)


def start_from_picker(nav: Navigator, picker: str = "story_act") -> None:
    """From a confirmed stage picker: private party, then Start, until the match shows."""
    nav.press(picker, "select_stage")
    if nav.wait_for("party_room", STEP_TIMEOUT) is None:
        raise NavError(f"Select Stage didn't reach the party room; on {nav.settle()}")
    nav.p.sleep(0.8)
    nav.press("party_room", "start_normal")
    if nav.wait_for("match", TRIP_TO_MATCH) is None:
        raise NavError(f"the match never started; on {nav.settle()}")
