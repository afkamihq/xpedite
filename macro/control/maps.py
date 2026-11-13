"""A map's set position, its reference picture, and its unit layouts.

All of it is plain data in data/maps/<map>/, which anyone can edit:
  profile.yaml      how to reach the set position from spawn (the "map adjustment")
  reference.png     the view from there, which placements are marked against
  layouts/NAME.yaml which hotbar slot goes where, in the picture's pixels

A layout says "slot 3", never a unit's name, so any team works with it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import cv2
import yaml

from macro.platform import Platform
from macro.vision import align
from macro.vision.screens import GAME_HEIGHT, GAME_WIDTH, ROOT, scaled

MAPS = os.path.join(ROOT, "data", "maps")
TILT_DOWN = 3500  # counts: tilt clamps by 3000, so any start ends at the same pitch
ZOOM_OUT_NOTCHES = 16  # zoom clamps by 10 from spawn
NOTCH = 15
POSITION_TOLERANCE = 8.0  # game pixels: close enough that placements land where marked
MAX_CORRECTIONS = 5
MIN_HOLD = 0.03  # shorter key holds don't move the avatar reliably
ROLL_PER_COUNT = 0.077  # degrees the picture turns per count of yaw, measured from overhead
ROLL_TOLERANCE = 0.3  # degrees: straighter than this isn't worth a turn
# Over Remote Desktop the yaw turns with arrow keys (WindowsPlatform.turn): 15 deg taps, then a
# shorter hold for the rest. Aim within REMOTE_ROLL_AIM: the walk keys follow the camera, so 5 deg
# off sent the walk to the north view astray (12 Nov 2026, 20:06, 8 of 16 phantoms). If the short
# holds don't move it, accept up to REMOTE_ROLL_OK as before: placements go through the
# alignment, which takes the rotation out.
REMOTE_ROLL_OK = 8.0
REMOTE_ROLL_AIM = 2.0


def _roll_ok(p) -> float:
    return REMOTE_ROLL_OK if getattr(p, "remote", False) else ROLL_TOLERANCE


def _roll_aim(p) -> float:
    return REMOTE_ROLL_AIM if getattr(p, "remote", False) else ROLL_TOLERANCE


ROLL_FIXABLE = 30.0  # degrees: more than this and the picture match itself is in doubt
QUARTER_TURN = round(90 / ROLL_PER_COUNT)  # counts
MIN_TRUSTED = 120  # features in agreement below which a match is a guess (a wrong one had 54)


class PositionError(RuntimeError):
    """Couldn't confirm being at the map's set position."""


@dataclass
class MapProfile:
    name: str
    route: list = field(default_factory=list)  # [[key, seconds], ...] from spawn
    walk_px_per_s: float = 191.0
    yaw_counts: int = 0  # straightens the view, so this map's lane runs up the screen
    zoom_in_notches: int = 0  # from fully out: show the lane, not the whole map

    @property
    def folder(self) -> str:
        return os.path.join(MAPS, self.name)

    @property
    def reference_path(self) -> str:
        return os.path.join(self.folder, "reference.png")

    def save(self):
        os.makedirs(os.path.join(self.folder, "layouts"), exist_ok=True)
        with open(os.path.join(self.folder, "profile.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump({"route": self.route, "walk_px_per_s": self.walk_px_per_s,
                            "yaw_counts": self.yaw_counts, "zoom_in_notches": self.zoom_in_notches,
                            "game_size": [GAME_WIDTH, GAME_HEIGHT]}, f, sort_keys=False)


def load_profile(name: str) -> MapProfile:
    with open(os.path.join(MAPS, name, "profile.yaml"), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return MapProfile(name, data.get("route") or [], data.get("walk_px_per_s", 191.0),
                      data.get("yaw_counts", 0), data.get("zoom_in_notches", 0))


def load_layout(map_name: str, layout: str) -> list[dict]:
    """The steps of a layout, in order: {slot, at: [x, y]} and anything added later."""
    with open(os.path.join(MAPS, map_name, "layouts", layout + ".yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)["steps"]


def set_overhead_camera(p: Platform, profile: MapProfile | None = None, yaw: int | None = None):
    """The view to place from. Tilt and zoom-out both clamp, so going to those limits and
    then a fixed amount back gives the same view every time. The turn doesn't clamp: it's
    the map's own from a fresh spawn, or `yaw` counts when the camera was left turned by an
    earlier match (a match started from inside another keeps the camera as it was)."""
    p.hover(*scaled(960, 300))
    p.turn(0, TILT_DOWN, steps=30)
    p.sleep(0.2)
    # Roblox ignores the wheel until the pointer has really moved over the world.
    p.hover(*scaled(960, 300))
    for _ in range(ZOOM_OUT_NOTCHES):
        p.scroll(NOTCH)
        p.sleep(0.03)
    p.sleep(0.5)
    if profile:
        for _ in range(profile.zoom_in_notches):
            p.scroll(-NOTCH)
            p.sleep(0.2)
        counts = profile.yaw_counts if yaw is None else yaw
        if counts:
            p.turn(counts, 0)
            p.sleep(0.2)
    # A turn can leave the pointer held by the game until it moves.
    p.move_rel(1, 0)
    p.move_rel(-1, 0)


def walk_route(p: Platform, profile: MapProfile):
    for key, seconds in profile.route:
        p.key(key, hold=seconds)
        p.sleep(0.25)


def _search_quarter_turns(p: Platform, reference, first, log) -> align.Alignment | None:
    """Turn a quarter at a time, all the way round, and stop at the view that matches best."""
    def score(result):
        return result.inliers if result is not None and abs(result.scale - 1) <= 0.05 else 0
    best, best_turn = first, 0
    for quarter in range(1, 4):
        p.turn(QUARTER_TURN, 0)
        p.move_rel(1, 0)
        p.move_rel(-1, 0)
        p.sleep(0.5)
        result = align.align(reference, align.features(p.grab()))
        log(f"looking round: a quarter turn x{quarter}, {score(result)} features agree")
        if score(result) > score(best):
            best, best_turn = result, quarter
    # Back to the best of the four (a full turn brings it home).
    p.turn(QUARTER_TURN * ((best_turn - 3) % 4), 0)
    p.move_rel(1, 0)
    p.move_rel(-1, 0)
    p.sleep(0.5)
    return align.align(reference, align.features(p.grab()))


def correct_position(p: Platform, profile: MapProfile, log=None, search: bool = True) -> align.Alignment:
    """Walk until the view matches the reference picture. Raises PositionError if it can't."""
    log = log or (lambda text: None)
    reference_image = cv2.imread(profile.reference_path)
    if reference_image is None:
        raise PositionError(f"{profile.name} has no reference picture yet")
    reference = align.features(reference_image)
    result = None
    searched = False
    turns_work, turned_from = True, None
    for attempt in range(MAX_CORRECTIONS + 1):
        p.sleep(0.5)
        result = align.align(reference, align.features(p.grab()))
        lost = result is None or abs(result.scale - 1) > 0.05 or abs(result.roll) > ROLL_FIXABLE \
            or result.inliers < MIN_TRUSTED
        if lost and not searched and search:
            # Some maps don't always start the camera facing the same way (Hollow Desert came
            # out half a turn round between two entries, 10 Nov 2026), so look all four ways.
            searched = True
            result = _search_quarter_turns(p, reference, result, log)
        if result is not None and result.inliers < MIN_TRUSTED:
            raise PositionError(f"only {result.inliers} features agree with the reference picture")
        if result is None:
            raise PositionError("the view doesn't match the reference picture")
        off = max(abs(result.dx), abs(result.dy))
        log(f"position check {attempt + 1}: off by ({result.dx:.1f}, {result.dy:.1f}) px, "
            f"turned {result.roll:.1f} deg, {result.inliers} features agree")
        if abs(result.scale - 1) > 0.05 or abs(result.roll) > ROLL_FIXABLE:
            raise PositionError(f"the camera isn't right: rotated {result.roll:.1f} deg, scale {result.scale:.3f}")
        if turned_from is not None:
            if abs(turned_from - result.roll) < 0.3 * abs(turned_from):
                turns_work = False  # a short hold that didn't register: don't spend the corrections
                log(f"turning {turned_from:.1f} deg moved the view {turned_from - result.roll:.1f} deg: "
                    f"leaving it at {result.roll:.1f} deg")
            turned_from = None
        if abs(result.roll) > (_roll_aim(p) if turns_work else _roll_ok(p)):
            # Slanted: turn by what the picture says. This is what makes a camera carried
            # over from another match come out the same as one set from spawn.
            if attempt == MAX_CORRECTIONS:
                break
            turned_from = result.roll
            p.turn(round(result.roll / ROLL_PER_COUNT), 0)
            p.move_rel(1, 0)
            p.move_rel(-1, 0)
            continue
        if off <= POSITION_TOLERANCE:
            return result
        # W moves the scene down and D moves it left, so walk against the offset.
        for amount, positive_key, negative_key in ((result.dy, "s", "w"), (result.dx, "d", "a")):
            hold = abs(amount) / profile.walk_px_per_s
            if abs(amount) > POSITION_TOLERANCE / 2 and hold >= MIN_HOLD:
                p.key(positive_key if amount > 0 else negative_key, hold=hold)
                p.sleep(0.2)
    # Close enough after every correction (a few px, under a degree: the ground on some views
    # shimmers) is better than giving up on the run.
    # Placements go through the alignment, which takes the rotation out, so up to 2 deg is fine
    # (11 Nov 2026: 1.1 deg on the down view skipped four placements), and the offset too: 17 px
    # off skipped the bottom path's Atom (11 Nov 2026, 16:49) though the alignment places it right.
    if result is not None and max(abs(result.dx), abs(result.dy)) <= 5 * POSITION_TOLERANCE and abs(result.roll) <= max(2.0, _roll_ok(p) + 0.5) and result.inliers >= MIN_TRUSTED:
        log(f"near enough: {max(abs(result.dx), abs(result.dy)):.0f} px off, {result.roll:.1f} deg")
        return result
    raise PositionError(f"still {max(abs(result.dx), abs(result.dy)):.0f} px off and rotated {result.roll:.1f} deg "
                        f"after {MAX_CORRECTIONS} corrections")


def _turn(p: Platform, counts: int):
    p.hover(*scaled(960, 300))
    p.turn(counts, 0)
    p.move_rel(1, 0)
    p.move_rel(-1, 0)
    p.sleep(0.45)


def find_position(p: Platform, profile: MapProfile, log=None, step_degrees: float = 15.0,
                  tries: int = 3) -> align.Alignment:
    """For maps whose spawn camera doesn't face the same way every join and whose spawn isn't
    one spot (Soul Furnace, 11 Nov 2026: 90 and 113 deg off, the character somewhere by the
    furnace). Look all the way round in small turns, face the way that matches the reference
    best, straighten it, walk by what the picture says, then the usual position check. A sweep
    that loses the picture is done again (11 Nov 2026, 15:08: one miss threw a whole run away)."""
    log = log or (lambda text: None)
    for attempt in range(tries):
        try:
            return _find_position_once(p, profile, log, step_degrees)
        except PositionError as error:
            if attempt == tries - 1:
                raise
            log(f"finding the position failed ({error}); looking round again")
    raise PositionError("no way round matched the reference picture")


def _find_position_once(p: Platform, profile: MapProfile, log, step_degrees: float) -> align.Alignment:
    set_overhead_camera(p, profile)
    reference = align.features(cv2.imread(profile.reference_path))
    step = round(step_degrees / ROLL_PER_COUNT)
    turns = round(360 / step_degrees)
    best, best_turn = None, 0
    for k in range(turns):
        result = align.align(reference, align.features(p.grab()))
        if result is not None and abs(result.scale - 1) <= 0.15 and abs(result.roll) <= 25 and                 (best is None or result.inliers > best.inliers):
            best, best_turn = result, k
        _turn(p, step)
    if best is None:
        raise PositionError("no way round matched the reference picture")
    log(f"facing the reference best {best_turn * step_degrees:.0f} deg round ({best.inliers} features agree, "
        f"{best.roll:.0f} deg off)")
    # A full circle brings it home, so the best direction is best_turn steps on. Turned the short
    # way, one step at a time: one 300-330 deg turn lost the picture three times running (11 Nov
    # 2026, 16:14-16:15) and threw the whole setup away.
    back = best_turn if best_turn <= turns // 2 else best_turn - turns
    for _ in range(abs(back)):
        _turn(p, step if back > 0 else -step)
    lost = 0
    for _ in range(16):
        result = align.align(reference, align.features(p.grab()))
        if result is None or abs(result.scale - 1) > 0.15:
            # Look a little either side before giving up (half a step right, a step left, ...).
            lost += 1
            if lost > 4:
                raise PositionError("lost the reference picture while walking toward it")
            _turn(p, (step // 2) * (lost if lost % 2 else -lost))
            continue
        if abs(result.roll) > max(1.0, _roll_ok(p)):
            _turn(p, round(result.roll / ROLL_PER_COUNT))
            continue
        if max(abs(result.dx), abs(result.dy)) <= POSITION_TOLERANCE * 2 and result.inliers >= MIN_TRUSTED:
            break
        for amount, positive_key, negative_key in ((result.dy, "s", "w"), (result.dx, "d", "a")):
            hold = min(1.2, 0.8 * abs(amount) / profile.walk_px_per_s)
            if hold >= MIN_HOLD:
                p.key(positive_key if amount > 0 else negative_key, hold=hold)
                p.sleep(0.2)
        p.sleep(0.3)
    return correct_position(p, profile, log)


def go_to_position(p: Platform, profile: MapProfile, log=None, yaw: int | None = None) -> align.Alignment:
    """The whole "map adjustment": set the camera, walk the route, confirm. `yaw` as in
    set_overhead_camera, for a match started without leaving the last one."""
    set_overhead_camera(p, profile, yaw)
    walk_route(p, profile)
    return correct_position(p, profile, log)
