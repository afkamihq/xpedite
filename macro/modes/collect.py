"""Collecting finished quests and battlepass rewards, which build up as the macro plays.

The Battlepass screens have paid buttons right beside the free one (+10 Levels, Buy Premium
Pass, Buy 25 Levels). So a click needs all of these: the lobby's red "!" badge says there's
something to get, the detector confirms the screen, the button is on that screen's
allow-list, it reads exactly "Claim All", and it's green. Grey means nothing to claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import cv2
import numpy as np

from macro.nav.navigator import NavError, Navigator
from macro.vision import ocr
from macro.vision.screens import scaled


@dataclass
class Place:
    name: str
    lobby_button: str
    screen: str
    badge: tuple[int, int]  # the "!" on its lobby icon, in game pixels
    claim_box: tuple[int, int, int, int]  # where its Claim All is, in game pixels


PLACES = (
    Place("quests", "quests", "quests", (80, 407), (302, 610, 794, 650)),
    Place("season battlepass", "pass_season", "battlepass", (1423, 297), (956, 610, 1136, 650)),
    Place("event battlepass", "pass_event", "event_pass", (1423, 375), (1218, 745, 1428, 795)),
)
BADGE_HALF = 12
BADGE_MIN_RED = 30  # pixels
OPEN_WAIT = 5.0


def has_badge(frame: np.ndarray, place: Place) -> bool:
    """Whether a lobby icon shows the bright red "!" circle."""
    x, y = place.badge
    crop = frame[y - BADGE_HALF:y + BADGE_HALF, x - BADGE_HALF:x + BADGE_HALF].astype(int)
    red = (crop[:, :, 2] > 190) & (crop[:, :, 1] < 70) & (crop[:, :, 0] < 70)
    return int(red.sum()) >= BADGE_MIN_RED


def is_green(frame: np.ndarray, box: tuple[int, int, int, int]) -> bool:
    x0, y0, x1, y1 = box
    b, g, r = cv2.mean(frame[y0:y1, x0:x1])[:3]
    return g > 120 and g > r * 1.3 and g > b * 1.5


def says_claim_all(frame: np.ndarray, box: tuple[int, int, int, int]) -> bool:
    return re.sub(r"[^a-z]", "", ocr.read_text(frame, box, scale=2.0).lower()) == "claimall"


def collect_rewards(nav: Navigator, on_lost=None, log=None) -> list[str]:
    """From anywhere: collect whatever's waiting. Returns a line for each thing it did."""
    log = log or (lambda text: None)
    report = []
    p = nav.p
    nav.go("lobby", on_lost=on_lost)
    looked = False  # one look serves every badge until something is opened (was 0.5 s each)
    for place in PLACES:
        if not looked:
            p.hover(*scaled(960, 300))
            p.sleep(0.5)
            nav.see()
            looked = True
        if not has_badge(nav.last_frame, place):
            continue
        looked = False
        log(f"{place.name}: something to collect")
        nav.press("lobby", place.lobby_button)
        if nav.wait_for(place.screen, OPEN_WAIT * 2) is None:
            raise NavError(f"{place.name} didn't open; on {nav.settle()}")
        p.sleep(1.0)
        nav.see()
        frame = nav.last_frame
        if not says_claim_all(frame, place.claim_box) or not is_green(frame, place.claim_box):
            report.append(f"{place.name}: badge showed, but no green Claim All, so nothing clicked")
        else:
            nav.press(place.screen, "claim_all")
            if nav.wait_for("obtained_rewards", OPEN_WAIT) is None:
                report.append(f"{place.name}: pressed Claim All, but no rewards appeared")
            else:
                report.append(f"{place.name}: collected")
                p.sleep(0.5)
                nav.press("obtained_rewards", "dismiss")
                nav.wait_for(place.screen, OPEN_WAIT)
                p.sleep(0.6)
        nav.go("lobby", on_lost=on_lost)
    return report
