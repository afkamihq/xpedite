"""What a match paid, read off the results window's "Gained Rewards" strip: each tile has its
count ("1x", "300x") at its top left and its name under it. Only items worth keeping a tally
of are named here: Crumbling Fragments are a one-use key for a raid's last stage (user,
10 Nov 2026; Hollow Desert Act 3 drops them), and Trait Crystals are trait rerolls.
"""
from __future__ import annotations

import re

import numpy as np

from macro.vision import ocr
from macro.vision.screens import SCALE

STRIP = (380, 627, 1173, 747)  # 1920x1080 scale
TRACKED = {
    "Crumbling Fragment": ("crumbl", "fragmen"),
    "Trait Crystal": ("traitcr", "traltcr", "trait", "tralt"),
    "Candy Corn": ("candycorn", "candyc", "candy"),
}
COUNT = re.compile(r"^(\d[\d,]*)\s*[xX]$")
MAX_GAP = 75  # px at 1440 wide: a name sits at most this far right of its tile's count


def read_rewards(frame: np.ndarray) -> dict[str, int]:
    """Tracked items and how many, from a results window that is showing."""
    box = tuple(round(v * SCALE) for v in STRIP)
    words = ocr.find_words(frame, box)
    counts = [(x, int(m.group(1).replace(",", ""))) for text, x, _ in words
              if (m := COUNT.match(text.strip()))]
    found: dict[str, int] = {}
    for text, x, _ in words:
        simple = re.sub(r"[^a-z]", "", text.lower())
        name = next((item for item, keys in TRACKED.items() if any(simple.startswith(k) for k in keys)), None)
        if name is None or name in found:
            continue
        left = [(cx, n) for cx, n in counts if 0 <= x - cx <= MAX_GAP * SCALE / 0.75]
        if left:
            found[name] = max(left)[1]  # the nearest count to its left
    return found


def describe(loot: dict[str, int]) -> str:
    return ", ".join(f"{n} {name}{'s' if n != 1 else ''}" for name, n in loot.items()) or "nothing tracked"
