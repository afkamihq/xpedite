"""Comparing the live overhead view with a map's reference picture.

Features on the ground are matched between the two, which says how far the view has
shifted. That is how the macro knows the character reached the map's set position, and
where a point marked on the picture is on screen right now. The HUD and the avatar's
area are left out, since they don't belong to the map.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from macro.vision.screens import GAME_HEIGHT, GAME_WIDTH, SCALE

MIN_INLIERS = 40  # fewer agreeing features than this isn't a trustworthy match
ORB_FEATURES = 3000


def _mask() -> np.ndarray:
    mask = np.full((GAME_HEIGHT, GAME_WIDTH), 255, np.uint8)
    for x0, y0, x1, y1 in ((0, 0, 1920, 120),  # top bar and pills
                           (0, 850, 1920, 1080),  # Yen, hotbar, level bar
                           (1600, 0, 1920, 1080),  # right-hand buttons
                           (0, 0, 180, 1080),  # left-hand icons and objectives
                           (760, 400, 1160, 680),  # the avatar
                           # Event matches (Soul Furnace, 11 Nov 2026): Heat bars, the Forge
                           # button and the Start Game window. Unmasked, ~200 HUD features
                           # agreed with the reference while the ground had moved.
                           (640, 107, 1280, 227),
                           (853, 795, 1067, 860),
                           (753, 147, 1167, 367)):
        mask[round(y0 * SCALE):round(y1 * SCALE), round(x0 * SCALE):round(x1 * SCALE)] = 0
    return mask


_MASK = _mask()
cv2.ocl.setUseOpenCL(False)  # see macro/vision/__init__.py
_ORB = cv2.ORB_create(ORB_FEATURES)
_MATCHER = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


@dataclass
class Alignment:
    """How the live view relates to the reference: live = matrix * reference."""
    matrix: np.ndarray
    inliers: int
    dx: float  # the scene's shift, in game pixels, at the middle of the screen
    dy: float
    roll: float  # degrees
    scale: float

    def to_live(self, x: float, y: float) -> tuple[int, int]:
        """Where a point marked on the reference picture is on screen now."""
        px, py = self.matrix @ np.array([x, y, 1.0])
        return round(float(px)), round(float(py))


def features(frame: np.ndarray):
    return _ORB.detectAndCompute(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), _MASK)


def align(reference, live) -> Alignment | None:
    """reference and live are from features(). None if they can't be matched with confidence."""
    (kr, dr), (kl, dl) = reference, live
    if dr is None or dl is None:
        return None
    matches = _MATCHER.match(dr, dl)
    if len(matches) < MIN_INLIERS:
        return None
    pr = np.float32([kr[m.queryIdx].pt for m in matches])
    pl = np.float32([kl[m.trainIdx].pt for m in matches])
    matrix, inliers = cv2.estimateAffinePartial2D(pr, pl, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if matrix is None or int(inliers.sum()) < MIN_INLIERS:
        return None
    centre = np.array([GAME_WIDTH / 2, GAME_HEIGHT / 2, 1.0])
    shift = matrix @ centre - centre[:2]
    return Alignment(matrix, int(inliers.sum()), float(shift[0]), float(shift[1]),
                     float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0]))),
                     float(np.hypot(matrix[0, 0], matrix[1, 0])))
