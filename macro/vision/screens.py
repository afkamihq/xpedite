"""Knowing which screen we're on: small template matches in fixed places.

Screens are data: data/screens.yaml lists them in checking order, and
data/anchors.yaml holds the marks that identify each one (made by
tools/find_anchors.py). Adjusting to a game update usually means re-cutting
anchors, not changing code.
"""

from __future__ import annotations

import glob
import os
import time
from dataclasses import dataclass

import cv2
import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAD = 24  # how far an anchor may sit from its spot: Windows fullscreen and framed differ by 18 px
UNKNOWN = "unknown"
BLACK = "black"
BLACK_BELOW = 6  # mean brightness
LOADING = {BLACK, "roblox_teleport", "game_loading"}  # normal during a trip, not lost


def _game_size() -> tuple[int, int]:
    """The game's picture size, from data/display.yaml. 1920x1080 if it has no frame."""
    path = os.path.join(ROOT, "data", "display.yaml")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            frame = (yaml.safe_load(f) or {}).get("frame")
        if frame:
            return frame[2], frame[3]
    return 1920, 1080


GAME_WIDTH, GAME_HEIGHT = _game_size()
# data/screens.yaml and data/nav.yaml keep positions at 1920x1080, which were all
# measured there. Roblox's UI scales evenly across, and to within about 18 px down.
SCALE = GAME_WIDTH / 1920


def scaled(x: float, y: float) -> tuple[int, int]:
    return round(x * SCALE), round(y * SCALE)


FOLDERS = {"native": "frames_native", "win": "frames_win", "linux": "frames"}


def frame_path(name: str) -> str:
    """native/lobby: at the current game size. win/lobby and linux/lobby: older 1920x1080."""
    folder, _, stem = name.partition("/")
    return os.path.join(ROOT, "refs", FOLDERS[folder], stem + ".png")


def load_frame(name: str) -> np.ndarray:
    """A saved picture at the game's current size."""
    image = cv2.imread(frame_path(name))
    if image is None:
        raise FileNotFoundError(frame_path(name))
    if image.shape[1] != GAME_WIDTH:
        image = cv2.resize(image, (GAME_WIDTH, GAME_HEIGHT), interpolation=cv2.INTER_AREA)
    return image


def load_gray(name: str) -> np.ndarray:
    return cv2.cvtColor(load_frame(name), cv2.COLOR_BGR2GRAY)


def match_near(gray: np.ndarray, template: np.ndarray, x0: int, y0: int, pad: int = PAD) -> float:
    """Best match of template around (x0, y0), from -1 to 1."""
    h, w = template.shape
    region = gray[max(y0 - pad, 0):y0 + h + pad, max(x0 - pad, 0):x0 + w + pad]
    if region.shape[0] < h or region.shape[1] < w:
        return -1.0
    return float(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED).max())


def load_definitions() -> dict:
    """The screens, each with any pictures of it taken at the game's current size added
    (refs/frames_native/<screen>__N.png). Screens with hand-picked boxes keep their first
    picture first, since their boxes were picked on it."""
    with open(os.path.join(ROOT, "data", "screens.yaml"), encoding="utf-8") as f:
        screens = yaml.safe_load(f)["screens"]
    native = glob.glob(os.path.join(ROOT, "refs", FOLDERS["native"], "*__*.png"))
    for path in sorted(native, reverse=True):
        stem = os.path.basename(path)[:-4]
        definition = screens.get(stem.split("__")[0])
        if definition is None:
            continue
        if "boxes" in definition:
            definition["frames"].append(f"native/{stem}")
        else:
            definition["frames"].insert(0, f"native/{stem}")
    return screens


@dataclass
class Anchor:
    template: np.ndarray
    x: int
    y: int
    threshold: float


@dataclass
class Detection:
    name: str
    score: float  # the weakest anchor's match
    ms: float


PATCHES = os.path.join(ROOT, "data", "anchor_patches.npz")


def patch_key(source: str, box) -> str:
    """The name of an anchor's patch in data/anchor_patches.npz."""
    return f"{source}@{'_'.join(str(int(v)) for v in box)}".replace("/", "~")


def load_patches() -> dict:
    """The anchors' patches baked by tools/build_anchors.py, if they were baked at this game size.
    With them the full screenshots in refs/ aren't needed to run (13 Nov 2026: ~0.6 MB instead of
    ~270 MB)."""
    if not os.path.exists(PATCHES):
        return {}
    with np.load(PATCHES) as data:
        if tuple(int(v) for v in data["size"]) != (GAME_WIDTH, GAME_HEIGHT):
            return {}
        return {k: data[k] for k in data.files if k != "size"}


class ScreenDetector:
    def __init__(self):
        self.definitions = load_definitions()
        with open(os.path.join(ROOT, "data", "anchors.yaml"), encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        baked = load_patches()
        sources: dict[str, np.ndarray] = {}
        self.anchors: dict[str, list[Anchor]] = {}
        for name in self.definitions:  # keeps the checking order
            built = []
            for a in saved.get(name) or []:
                x0, y0, x1, y1 = a["box"]
                patch = baked.get(patch_key(a["source"], a["box"]))
                if patch is None:  # not baked (a new anchor): cut it from its screenshot
                    source = sources.setdefault(a["source"], load_gray(a["source"]))
                    patch = source[y0:y1, x0:x1].copy()
                built.append(Anchor(patch, x0, y0, a["threshold"]))
            if built:
                self.anchors[name] = built

    def score(self, gray: np.ndarray, name: str) -> float | None:
        """The weakest passing anchor's match, or None if the screen isn't showing.

        A screen with three anchors may miss one: an anchor can sit on content that
        looked fixed in the sample pictures but isn't, such as today's challenge.
        That's safe because anchors score far below their thresholds elsewhere."""
        anchors = self.anchors[name]
        misses_allowed = 1 if len(anchors) >= 3 else 0
        weakest, misses = 1.0, 0
        for anchor in anchors:
            value = match_near(gray, anchor.template, anchor.x, anchor.y)
            if value < anchor.threshold:
                misses += 1
                if misses > misses_allowed:
                    return None
            else:
                weakest = min(weakest, value)
        return weakest

    def classify(self, frame: np.ndarray) -> Detection:
        """Which screen this frame shows. First match in checking order wins."""
        start = time.perf_counter()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        for name in self.anchors:
            value = self.score(gray, name)
            if value is not None:
                return Detection(name, value, (time.perf_counter() - start) * 1000)
        # Nearly black, allowing for the small notices Roblox shows during a trip.
        name = BLACK if gray[::8, ::8].mean() < BLACK_BELOW else UNKNOWN
        return Detection(name, 0.0, (time.perf_counter() - start) * 1000)

    def button(self, screen: str, name: str) -> tuple[int, int]:
        """A button's position. Raises for anything not on the allow-list."""
        where = self.definitions[screen]["buttons"][name]
        return tuple(where["native"]) if isinstance(where, dict) else scaled(*where)
