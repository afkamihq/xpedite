"""Trick or Treat (Halloween event): go round the lobby's Ethereal Doors and knock on each.

Measured 10 Nov 2026 (docs/WINDOWS.md, "Trick or Treat"):
- A door floats "Trick or Treat! / Knock for rewards!" when it's ready and "Trick or Treat! / Ready
  in MM:SS" while it cools down (about 10 minutes, per door). Close up the game shows
  "E  Ethereal Door / Open".
- E knocks. **Treat**: a banner "Treat! +10 Candy Corn" and an Obtained Rewards popup, closed by
  any click; hovering the candy tile shows "NNx Owned". **Trick**: a teleport into a match,
  "Halloween Trick <Map> - Act N", Hard Mode, 10 waves, with a loaner team and a "Team: Preset"
  button above the Yen that switches to your own team.
- Doors are found from lobby areas reached through Areas. Never AFK Chamber (starts AFK mode), never
  Showcase (a testing zone with no way back but a restart).
- The camera turns from the top of the picture: a right-drag that starts on an interact prompt
  doesn't turn (user).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import math

import cv2
import numpy as np

from macro.control.walker import CENTRE_X, FOCAL_PX, Walker, find, turn_degrees
from macro.nav import stages
from macro.vision.ocr import find_words, read_text
from macro.vision.screens import LOADING

LABEL = ["knock for rewards"]          # a ready door
PROMPT = ["ethereal door"]
WORLD = (200, 60, 1300, 640)           # the 3D view, without the side HUD
# The six doors (user, 10 Nov 2026), each by the lobby area it is reached from, in round order.
# The Story door is reached from Rift Shop: the Story teleport lands inside the portal ring,
# which hides the door's label.
# Doors come and go (10 Nov 2026, 21:40: the Story one was gone while ten other spots showed one),
# so the user's six come first and the other spots a door was seen from are fallbacks. A spot with no
# door in sight is looked at again after NO_DOOR_RETRY.
DOORS = ["spawn", "tournament", "shiny converter", "guilds", "story", "raid shop",
         "gold shop", "index", "summon", "tower", "upgrades", "unit ascension", "rift shop"]
NO_DOOR_RETRY = 5 * 60
AREAS = DOORS
AREAS_BUTTON = (52, 510)               # lobby, game coordinates (1440x810)
AREAS_SEARCH = (845, 157)
AREAS_FIRST = (567, 285)
AREAS_CLOSE = (1162, 150)
TEAM_BUTTON = (720, 623)               # in a Trick match, above the Yen
AUTO_PLAY = (1352, 519)                # the game's own Auto Play button, in a match
TEAM_TEXT = (620, 605, 820, 642)
STAGE_LABEL = (1120, 345, 1440, 372)
POPUP_CLOSE = (720, 120)               # "click anywhere to close": an empty spot at the top
CANDY_TILE = (718, 400)                # the Obtained Rewards tile, hovered for its "NNx Owned"
INVITE_DECLINE = (877, 207)
TILT_UP = 900                          # counts up from fully down: the lobby ahead, a little down
ZOOM_IN = 7                            # notches in from fully out (spawn's own is 10)


class NoDoor(RuntimeError):
    pass


@dataclass
class Knock:
    kind: str                  # "treat", "trick" or "nothing"
    candy: int | None = None   # Candy Corn from a Treat's banner
    owned: int | None = None   # Candy Corn owned, from the reward tile's tooltip
    frame: object = None       # the Treat popup, for the webhook


def _words(frame, box=WORLD) -> str:
    return " ".join(w for w, _, _ in find_words(frame, box)).lower().replace(" ", "")


def decline_invite(p, frame=None) -> bool:
    """Party invites cover the top of the screen in public lobbies: decline one if it shows."""
    frame = p.grab() if frame is None else frame
    if "partyinvite" in _words(frame, (300, 80, 1140, 120)):
        p.click(*INVITE_DECLINE); p.sleep(0.6)
        return True
    return False


# Spots to start a tilt drag from, tried in turn: a right-drag that starts on an interact prompt or a
# floating label doesn't turn the camera, so a drag that changed nothing is tried again elsewhere.
DRAG_SPOTS = [(720, 95), (300, 700), (1150, 720), (400, 95), (1040, 95), (720, 560)]


def _small(frame):
    return cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY).astype(np.int16)


def _tilt(p, dy: int) -> bool:
    """Tilt by dy counts (positive: down) with a right-drag, from a spot where it takes."""
    for spot in DRAG_SPOTS:
        before = _small(p.grab())
        p.hover(*spot); p.turn(0, dy, steps=20); p.sleep(0.35)
        p.move_rel(3, 0); p.move_rel(-3, 0)  # a turn holds the pointer until a nudge
        p.sleep(0.15)
        if np.abs(_small(p.grab()) - before).mean() > 4:
            return True
    return False


def set_camera(p):
    """The same view every time, whatever came before: tilt clamped fully down then raised a
    fixed amount, zoom fully out then a fixed number of notches in. Roblox takes each wheel event
    as one notch, so one event per notch. Relative nudges used to add up until the camera sat
    inside the crowd at spawn."""
    _tilt(p, 3000)           # may change nothing if it was already fully down: that's fine
    _tilt(p, -TILT_UP)
    p.hover(720, 95)
    for _ in range(25):
        p.scroll(15); p.sleep(0.03)
    p.sleep(0.3)
    for _ in range(ZOOM_IN):
        p.scroll(-15); p.sleep(0.05)
    p.sleep(0.4)


def to_area(p, name: str, log=print):
    """Teleport to a lobby area through Areas: search its name, click the first result."""
    if name in ("afk chamber", "showcase"):
        raise NoDoor(f"never {name}")
    for _ in range(3):
        p.click(*AREAS_BUTTON); p.sleep(1.5)
        if "areas" not in _words(p.grab(), (220, 120, 600, 180)):
            decline_invite(p)
            p.click(*POPUP_CLOSE); p.sleep(1.0)  # something was in the way
            continue
        p.click(*AREAS_SEARCH); p.sleep(0.3)
        for _ in range(20):
            p.key("backspace")
        p.type_text(name); p.sleep(1.0)
        words = _words(p.grab(), (290, 190, 800, 340))
        if name.replace(" ", "") in words and "afk" not in words and "showcase" not in words:
            p.click(*AREAS_FIRST); p.sleep(3.0)
            return
        p.click(*AREAS_CLOSE); p.sleep(0.8)
    raise NoDoor(f"couldn't teleport to {name} through Areas")


def soonest_ready(frame) -> int | None:
    """Seconds until the soonest cooling door in view is ready, from its "Ready in MM:SS"."""
    best = None
    for text, _, _ in find_words(frame, WORLD):
        found = re.search(r"ready\s*in\s*(\d+)\s*[:.]\s*(\d\d)", text, re.I)
        if found:
            secs = int(found.group(1)) * 60 + int(found.group(2))
            best = secs if best is None else min(best, secs)
    return best


def look_round(p, walker, log, soonest, first: int | None = None) -> tuple[bool, int | None, bool, int | None]:
    """Turn round where we stand; walk to the first ready door seen. `first` is how many 30 degree
    turns found the door here last time: a teleport lands facing the same way, so that view is
    tried first. Returns (reached, soonest "Ready in" seen, any door label seen, turns it took)."""
    seen = False
    order = list(range(12))
    if first is not None:
        order = [first] + [k for k in order if k != first]
    at = 0
    for k in order:
        if k != at:
            turn_degrees(p, 30 * ((k - at) % 12 if (k - at) % 12 <= 6 else (k - at) % 12 - 12))
            at = k
        frame = p.grab()
        if find(frame, PROMPT, WORLD):
            return True, soonest, True, k
        if find(frame, ["trick or treat"], WORLD):
            seen = True
        wait = soonest_ready(frame)
        if wait is not None:
            soonest = wait if soonest is None else min(soonest, wait)
        if find(frame, LABEL, WORLD):
            return walker.approach(LABEL, PROMPT), soonest, True, k
    return False, soonest, seen, None


COOLDOWN = 10 * 60   # a knocked door's wait, when its own "Ready in" couldn't be read


class DoorRound:
    """Goes round the six doors in order. Each door's ready time is remembered (from its "Ready in"
    when seen, else ten minutes after a knock), so a cooling door is skipped without a trip."""

    def __init__(self):
        self.ready_at = {door: 0.0 for door in DOORS}
        self.turns = {}      # door -> 30 degree turns from its arrival that showed it
        self.next = 0
        self.current = None

    def knocked(self):
        if self.current:
            self.ready_at[self.current] = time.time() + COOLDOWN

    def wait(self) -> float:
        """Seconds until the soonest door is ready (0 if one is)."""
        return max(0.0, min(self.ready_at.values()) - time.time())

    def go(self, p, log=print) -> bool:
        """To the next ready door, its prompt showing. False if none was reachable this round."""
        walker = Walker(p, log)
        for k in range(len(DOORS)):
            door = DOORS[(self.next + k) % len(DOORS)]
            if self.ready_at[door] > time.time():
                continue
            try:
                to_area(p, door, log)
            except NoDoor as why:
                log(f"  {why}")
                continue
            set_camera(p)
            if door in LEAD_OUT:
                reached = walk_out_to_door(p, walker, LEAD_OUT[door], log)
            else:
                reached, soonest, self._label_seen, turns = look_round(p, walker, log, None,
                                                                       self.turns.get(door))
                if turns is not None:
                    self.turns[door] = turns
                if not reached and soonest is not None:
                    self.ready_at[door] = time.time() + soonest + 3
                    log(f"  {door}'s door is ready in {soonest} s")
                    continue
                if not reached and soonest is None and not self._label_seen:
                    self.ready_at[door] = time.time() + NO_DOOR_RETRY
                    log(f"  no door at {door} now")
                    continue
            if reached:
                self.current = door
                self.next = (DOORS.index(door) + 1) % len(DOORS)
                log(f"  at the {door} door")
                return True
            log(f"  couldn't reach the {door} door")
            self.ready_at[door] = time.time() + 60  # try it again in a minute
        return False


def knock(nav, log=print) -> Knock:
    """Press E at the door and see what came of it. A Treat's popup over a close camera can
    classify as unknown, so a Treat is known by its words, and a Trick only by the teleport."""
    p = nav.p
    # E opens the nearest prompt, and Summon's ("Summon / Open Menu") is a spending menu: knock
    # only when the door's is the one on screen.
    prompts = _words(p.grab())
    if "etherealdoor" not in prompts or any(bad in prompts for bad in ("openmenu", "purchase", "buy")):
        log(f"not knocking: the prompt on screen isn't only the door's ({prompts[:80]!r})")
        return Knock("nothing")
    p.key("e")
    end = time.time() + 12
    while time.time() < end:
        p.sleep(0.5)
        frame = p.grab()
        screen = nav.detector.classify(frame).name
        if screen in LOADING or screen not in ("lobby", "obtained_rewards", "unknown"):
            return Knock("trick")
        words = _words(frame, (0, 0, 1440, 810))
        if "expeditionsentertainment" in words or "joiningserver" in words:
            return Knock("trick")  # Roblox's place card while the Trick's teleport joins
        # A Treat is its popup's words, read twice to be sure: never click on a guess, a click
        # during a Trick's teleport can cancel it.
        if screen == "obtained_rewards" or "obtainedrewards" in words:
            p.sleep(0.4)
            again = _words(p.grab(), (300, 20, 1140, 560))
            if "obtainedrewards" not in again and nav.detector.classify(p.grab()).name != "obtained_rewards":
                continue
            found = re.search(r"\+(\d+)candycorn", words + again)
            candy = int(found.group(1)) if found else None
            if candy is None:  # the banner fades quickly: the tile's own count, "10x", stays
                tile = [t for t, _, _ in find_words(p.grab(), (600, 330, 840, 400))]
                count = next((re.match(r"^(\d+)\s*x$", t.strip(), re.I) for t in tile
                              if re.match(r"^(\d+)\s*x$", t.strip(), re.I)), None)
                candy = int(count.group(1)) if count else None
            p.hover(*CANDY_TILE); p.sleep(0.8)
            shot = p.grab()
            owned = re.search(r"(\d[\d,]*)x?owned", _words(shot, (600, 300, 1100, 600)))
            result = Knock("treat", candy, int(owned.group(1).replace(",", "")) if owned else None, shot)
            p.click(*POPUP_CLOSE); p.sleep(0.8)
            return result
    return Knock("nothing")


def stage_of_trick(frame) -> tuple[str | None, int | None]:
    """The map and act from the match's label: "Halloween Trick Crimson Shore - Act 5"."""
    text = read_text(frame, STAGE_LABEL, 2.5)
    found = re.search(r"trick\s*(.+?)\s*-\s*act\s*(\d)", text, re.I)
    if not found:
        return None, None
    squash = lambda t: re.sub(r"[^a-z]", "", t.lower())  # noqa: E731
    for name in stages.STORY_MAPS:
        if squash(name) == squash(found.group(1)):
            return name, int(found.group(2))
    return None, int(found.group(2))


def use_own_team(p, log=print) -> bool:
    """Press the Team button until it no longer reads Preset. True once it doesn't."""
    for _ in range(3):
        before = read_text(p.grab(), TEAM_TEXT, 2.0)
        if before and "preset" not in before.lower():
            log(f"  team button reads {before!r}")
            return True
        p.click(*TEAM_BUTTON); p.sleep(1.5)
        p.hover(*POPUP_CLOSE); p.sleep(0.4)
        after = read_text(p.grab(), TEAM_TEXT, 2.0)
        log(f"  team button: {before!r} -> {after!r}")
        if after and "preset" not in after.lower():
            return True
    return False


def wait_for_match(nav, timeout: float = 90.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if nav.detector.classify(nav.p.grab()).name == "match":
            nav.p.sleep(1.0)
            if nav.detector.classify(nav.p.grab()).name == "match":
                return True
        nav.p.sleep(1.0)
    return False


# Doors not in sight from an area's arrival point, and how to bring them into view. Guilds lands
# inside the hall at The Hero; the hall's exit, with the door beside it, is straight behind him down
# the carpet (10 Nov 2026). So: face him, turn half a circle, walk out.
LEAD_OUT = {"guilds": {"face": ["the hero", "guild management"], "turn_degrees": 180}}


def walk_out_to_door(p, walker, route, log=print, hops: int = 14) -> bool:
    """Face the route's landmark, turn by its amount, then walk forward until a ready door's label
    shows, and on to the door."""
    mark = walker.search(route["face"])
    if mark is None:
        log("  couldn't see the landmark to walk out from")
        return False
    turn_degrees(p, math.degrees(math.atan((mark.x - CENTRE_X) / FOCAL_PX)) + route["turn_degrees"])
    for attempt in range(2):
        for _ in range(hops):
            frame = p.grab()
            if find(frame, PROMPT, WORLD):
                return True
            if find(frame, LABEL, WORLD):
                return walker.approach(LABEL, PROMPT)
            p.key("w", 0.6)
            p.sleep(0.2)
        log("  no door that way: turning round")  # a turn that didn't take walks the wrong way
        turn_degrees(p, 180)
    return False
