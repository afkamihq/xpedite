"""Challenges: the farm for Trait Crystals (trait rerolls).

Regular Challenges are three Story stages on Hard with extra stage effects, a fresh three
every 30 minutes, each clearable 10 times a day; some pay 3 Trait Crystals a clear. The
Daily Challenge is one stage for the day and pays 10 (seen 10 Nov 2026).

read_offers() reads a tab of the Challenges window: each row's map and act, how many clears
are left today, and whether Trait Crystals are among its rewards. choose() picks the offer
to play: one the macro has a plan for, with clears left, crystals first. enter() opens it
and starts it, landing in the match like a Story stage. Nothing here can spend: the rows
and Select Stage are the only things pressed, and Enter Matchmaking never is.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass

import numpy as np

from macro.nav.navigator import NavError, Navigator
from macro.nav.stages import STORY_MAPS, TRIP_TO_MATCH, _simple, _similarity
from macro.vision import ocr
from macro.vision.screens import SCALE

STEP_TIMEOUT = 12.0
# Rows of the Challenges window, at 1920x1080: the top edge of each row card.
ROW_TOPS = {"regular": (296, 508, 720), "daily": (296,)}
TITLE = (920, 27, 1335, 66)        # from a row's top: "East Town - Act 4"
REWARDS = (922, 100, 1527, 174)    # the reward strip, icons and their small names
LIMIT = (667, 153, 840, 187)       # "Daily Limit 10 / 10"
MIN_NAME_MATCH = 0.72
DETAIL_TITLE = (740, 284, 1200, 334)  # on the details page: "School Grounds - Act 1"
ROTATION_MARGIN = 25  # seconds either side of :00 and :30 when the regular three change
CRYSTAL = re.compile(r"tr[a-z]{0,2}[il1|]t")  # "Trait", read as "Tralt", "Trait", "Trat"


class Unavailable(NavError):
    """The offer can't be played now: cleared this rotation ("Available in 10:21"), or done
    for the day (its button goes grey)."""


SELECT_STAGE_BOX = (830, 820, 1195, 884)  # the green Select Stage button on the details page


def select_stage_ready(frame: np.ndarray) -> bool:
    x0, y0, x1, y1 = (round(v * SCALE) for v in SELECT_STAGE_BOX)
    crop = frame[y0:y1, x0:x1].astype(int)
    green = (crop[..., 1] > 170) & (crop[..., 2] < 160) & (crop[..., 0] < 120)
    return green.mean() > 0.35


@dataclass
class Offer:
    kind: str                # "regular" or "daily"
    row: int                 # 1-based, top to bottom
    map: str | None
    act: int | None
    crystals: bool
    left: int | None         # clears left today, when it could be read
    text: str = ""

    @property
    def key(self) -> tuple:
        return self.kind, self.map, self.act

    def describe(self) -> str:
        where = f"{self.map} Act {self.act}" if self.map else "an unreadable stage"
        left = f", {self.left} clears left" if self.left is not None else ""
        return f"{self.kind} #{self.row}: {where} Hard{', Trait Crystals' if self.crystals else ''}{left}"


def _box(row_top: int, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return tuple(round(v * SCALE) for v in (x0, row_top + y0, x1, row_top + y1))


def _whitened(frame: np.ndarray, box) -> np.ndarray:
    """The box with only its white letters kept, dark on light: the titles glow blue."""
    x0, y0, x1, y1 = box
    out = frame.copy()
    white = frame[y0:y1, x0:x1].min(axis=2) > 170
    out[y0:y1, x0:x1] = np.where(white[..., None], 0, 255).astype(np.uint8)
    return out


def _title(frame: np.ndarray, row_top: int) -> tuple[str | None, int | None, str]:
    """Map and act, voted on over a few readings: each misreads a different letter."""
    box = _box(row_top, TITLE)
    tight = (box[0], box[1] + 2, box[2], box[3] - 2)
    readings = []
    for picture in (frame, _whitened(frame, box)):
        for crop, scale in ((box, 3.0), (tight, 2.0)):
            readings.append(ocr.read_line(picture, crop, scale))
    maps = Counter()
    acts = Counter()
    for text in readings:
        simple = _simple(text)
        scores = {name: _similarity(_simple(name), simple) for name in STORY_MAPS}
        best = max(scores, key=scores.get)
        if scores[best] >= MIN_NAME_MATCH:
            maps[best] += 1
        found = re.search(r"act\s*([1-5])\b", text.lower().replace(" ", ""))
        if found:
            acts[int(found.group(1))] += 1
    map_name = maps.most_common(1)[0][0] if maps else None
    act = acts.most_common(1)[0][0] if acts else None
    return map_name, act, " / ".join(readings)


def _left(frame: np.ndarray, row_top: int) -> int | None:
    text = ocr.read_line(frame, _box(row_top, LIMIT), 3.0)
    found = re.search(r"(\d+)\s*/\s*(\d+)", text)
    return int(found.group(1)) if found else None


def read_offers(nav: Navigator, kind: str) -> list[Offer]:
    """Open a tab of the Challenges window (already showing) and read its rows."""
    nav.press("challenges", "tab_regular" if kind == "regular" else "tab_daily")
    nav.p.sleep(1.0)
    frame = nav.p.grab()
    offers = []
    for row, top in enumerate(ROW_TOPS[kind], start=1):
        map_name, act, text = _title(frame, top)
        if map_name is None and act is None:
            continue  # an empty row
        rewards = ocr.read_text(frame, _box(top, REWARDS), 3.0).lower()
        offers.append(Offer(kind, row, map_name, act, bool(CRYSTAL.search(rewards)), _left(frame, top), text))
    return offers


def choose(offers: list[Offer], can_play, crystals_only: bool = False, used=()) -> Offer | None:
    """The offer to play: known stage, a plan for its map, clears left, not already used
    this rotation; crystals first."""
    usable = [o for o in offers if o.map and o.act and can_play(o.map) and (o.left is None or o.left > 0)
              and o.key not in used]
    if crystals_only:
        usable = [o for o in usable if o.crystals]
    usable.sort(key=lambda o: (not o.crystals, o.row))
    return usable[0] if usable else None


def seconds_to_rotation(now: float | None = None) -> float:
    """Seconds until the regular three next change (every :00 and :30, local clock)."""
    t = time.localtime(now)
    into = (t.tm_min % 30) * 60 + t.tm_sec
    return 1800 - into


def near_rotation() -> bool:
    left = seconds_to_rotation()
    return left < ROTATION_MARGIN or left > 1800 - 5


def detail_title(frame: np.ndarray) -> tuple[str | None, int | None]:
    box = tuple(round(v * SCALE) for v in DETAIL_TITLE)
    maps, acts = Counter(), Counter()
    for picture in (frame, _whitened(frame, box)):
        for scale in (2.0, 3.0):
            text = ocr.read_line(picture, box, scale)
            scores = {name: _similarity(_simple(name), _simple(text)) for name in STORY_MAPS}
            best = max(scores, key=scores.get)
            if scores[best] >= MIN_NAME_MATCH:
                maps[best] += 1
            found = re.search(r"act\s*([1-5])\b", text.lower().replace(" ", ""))
            if found:
                acts[int(found.group(1))] += 1
    return (maps.most_common(1)[0][0] if maps else None), (acts.most_common(1)[0][0] if acts else None)


def enter(nav: Navigator, offer: Offer):
    """From the Challenges window on the offer's tab: open its row, check it is still the stage
    that was read (the regular three change every half hour), Select Stage, Start."""
    nav.press("challenges", f"row_{offer.row}")
    if nav.wait_for("challenge_detail", STEP_TIMEOUT) is None:
        raise NavError(f"the challenge row didn't open; on {nav.settle()}")
    nav.p.sleep(0.6)
    map_name, act = detail_title(nav.p.grab())
    if map_name is not None and (map_name != offer.map or (act is not None and act != offer.act)):
        nav.press("challenge_detail", "back")
        raise NavError(f"the row now holds {map_name} Act {act}, not {offer.map} Act {offer.act}: "
                       "the challenges changed")
    if not select_stage_ready(nav.p.grab()):
        box = tuple(round(v * SCALE) for v in SELECT_STAGE_BOX)
        words = ocr.read_line(nav.p.grab(), box, 2.0)
        nav.press("challenge_detail", "back")
        raise Unavailable(f"{offer.describe()} can't be played now ({words or 'its button is grey'})")
    nav.press("challenge_detail", "select_stage")
    if nav.wait_for("party_room", STEP_TIMEOUT) is None:
        raise NavError(f"Select Stage didn't reach the party room; on {nav.settle()}")
    nav.p.sleep(0.8)
    nav.press("party_room", "start_normal")
    if nav.wait_for("match", TRIP_TO_MATCH) is None:
        raise NavError(f"the challenge never started; on {nav.settle()}")
    nav.p.sleep(2.0)
