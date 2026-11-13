"""Bake the screen detector's anchors into data/anchor_patches.npz: the small grey patches it matches,
cropped from the reference screenshots exactly as the detector would crop them at start.

The detector needs ~0.6 MB of patches but used to load ~270 MB of full screenshots to cut them
from (39 frames, some at three resolutions). With this file the macro runs without refs/ at all;
the screenshots stay a development tool for picking anchors (tools/find_anchors.py). Run this
after changing data/anchors.yaml or the game size (data/display.yaml).

    .venv-win/Scripts/python.exe tools/build_anchors.py
"""
import os
import sys

import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.vision import screens  # noqa: E402


def main():
    with open(os.path.join(ROOT, "data", "anchors.yaml"), encoding="utf-8") as f:
        saved = yaml.safe_load(f)
    patches, sources = {}, {}
    for name, anchors in saved.items():
        for a in anchors or []:
            source = sources.setdefault(a["source"], screens.load_gray(a["source"]))
            x0, y0, x1, y1 = a["box"]
            patches[screens.patch_key(a["source"], a["box"])] = source[y0:y1, x0:x1].copy()
    out = screens.PATCHES
    np.savez_compressed(out, size=np.array([screens.GAME_WIDTH, screens.GAME_HEIGHT]), **patches)
    print(f"{len(patches)} patches from {len(sources)} screenshots -> {os.path.relpath(out, ROOT)} "
          f"({os.path.getsize(out) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
