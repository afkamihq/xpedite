"""Find the marks that identify each screen, and save them to data/anchors.yaml.

A good anchor looks the same in all of a screen's frames, across platforms and
graphics levels, which rules out the 3D world and anything that changes. It must
also be absent from every screen checked later. Screens checked earlier don't
count: they get their chance first.

Doesn't touch the game. Runs at low priority.
Run from the project root:  .venv-win/Scripts/python.exe tools/find_anchors.py
"""
import os
import sys
import time

import cv2
import psutil
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.vision.screens import GAME_HEIGHT, GAME_WIDTH, SCALE, load_definitions, load_gray, match_near

SIZES = [(104, 20), (76, 22), (46, 20), (30, 30)]  # half-resolution pixels at 1440x810
STEP = 8
MIN_POSITIVE = 0.82
MAX_NEGATIVE = 0.60
MIN_DETAIL = 14  # flat areas match anything
WANT = 3
# Full-screen areas showing the player's team and currencies. Any team has to work,
# so nothing that depends on them may identify a screen.
AVOID = [tuple(round(v * SCALE) for v in area) for area in (
    (600, 860, 1320, 1080),  # currencies, Yen, hotbar, level bar
    (620, 0, 1300, 70),  # match pills: health, wave, enemies, time
)]


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def threshold_for(positive, negative):
    """Halfway between how it scores here and elsewhere, but never so high that its own
    screen could fail: a hand-picked mark like Back also appears on other screens, and
    it's the screen's other mark that tells them apart."""
    # Just below its worst score on its own screen, not halfway: at 0.70, locked act tabs
    # on a stage picker passed for marks that belonged to Sandbox Controls.
    return round(max(0.70, positive - 0.12), 3)


def search(names, group, later, half):
    """Candidates as (margin, positive, negative, box in half-res), best first."""
    source = half[group[0]]
    others = [half[n] for n in group[1:]]
    negatives = [half[n] for n in later]
    found = []
    for tw, th in SIZES:
        for y in range(0, source.shape[0] - th, STEP):
            for x in range(0, source.shape[1] - tw, STEP):
                full_box = (x * 2, y * 2, (x + tw) * 2, (y + th) * 2)
                if any(overlaps(full_box, area) for area in AVOID):
                    continue
                template = source[y:y + th, x:x + tw]
                if template.std() < MIN_DETAIL:
                    continue
                positive = 1.0
                for frame in others:
                    positive = min(positive, match_near(frame, template, x, y, pad=12))
                    if positive < MIN_POSITIVE:
                        break
                if positive < MIN_POSITIVE:
                    continue
                negative = -1.0
                for frame in negatives:
                    negative = max(negative, match_near(frame, template, x, y, pad=12))
                    if negative > MAX_NEGATIVE:
                        break
                if negative > MAX_NEGATIVE:
                    continue
                found.append((positive - negative, positive, negative, (x, y, x + tw, y + th)))
    found.sort(reverse=True)
    return found


def main():
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == "win32" else 10)
    cv2.setNumThreads(1)
    definitions = load_definitions()
    names = list(definitions)
    all_frames = {f for d in definitions.values() for f in d["frames"]}
    full = {f: load_gray(f) for f in all_frames}
    half = {f: cv2.resize(g, (GAME_WIDTH // 2, GAME_HEIGHT // 2), interpolation=cv2.INTER_AREA) for f, g in full.items()}

    # find_anchors.py SCREEN...: redo only those, keeping the rest of the saved file.
    only = sys.argv[1:]
    output, problems = {}, []
    if only:
        with open(os.path.join(ROOT, "data", "anchors.yaml"), encoding="utf-8") as f:
            output = yaml.safe_load(f)
    for i, name in enumerate(names):
        if only and name not in only:
            continue
        started = time.perf_counter()
        d = definitions[name]
        group = d["frames"]
        later = [f for later_name in names[i + 1:] for f in definitions[later_name]["frames"]]
        chosen = []
        if "boxes" in d:
            for box in d["boxes"]:  # given at 1920x1080, like all positions in that file
                box = [round(v * SCALE) for v in box]
                x0, y0, x1, y1 = box
                template = full[group[0]][y0:y1, x0:x1]
                negative = max((match_near(full[f], template, x0, y0) for f in later), default=-1.0)
                positive = min((match_near(full[f], template, x0, y0) for f in group[1:]), default=1.0)
                chosen.append((positive, negative, tuple(box)))
        else:
            for _, positive, negative, box in search(names, group, later, half):
                if all(not overlaps(box, c[2]) for c in chosen):
                    chosen.append((positive, negative, box))
                    if len(chosen) == WANT:
                        break
            # Re-score at full resolution: that's what runs in the game.
            rescored = []
            for positive, negative, box in chosen:
                x0, y0, x1, y1 = (v * 2 for v in box)
                template = full[group[0]][y0:y1, x0:x1]
                positive = min((match_near(full[f], template, x0, y0) for f in group[1:]), default=1.0)
                negative = max((match_near(full[f], template, x0, y0) for f in later), default=-1.0)
                rescored.append((positive, negative, (x0, y0, x1, y1)))
            chosen = rescored
        # A single picture says nothing about how much a screen can vary, so don't
        # set the bar halfway up to its perfect match with itself.
        output[name] = [{"source": group[0], "box": list(box),
                         "threshold": threshold_for(p, n) if len(group) > 1 else round(max(0.70, n + 0.1), 3),
                         "seen_at_least": round(p, 3), "elsewhere_at_most": round(n, 3)} for p, n, box in chosen]
        note = ", ".join(f"{p:.2f}/{n:.2f}" for p, n, _ in chosen) or "NONE"
        print(f"{name:22s} {len(group)} frames, {time.perf_counter() - started:5.1f} s: {note}", flush=True)
        if not chosen:
            problems.append(name)

    path = os.path.join(ROOT, "data", "anchors.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Made by tools/find_anchors.py. seen_at_least / elsewhere_at_most: how this mark\n"
                "# scored on its own screen's frames and on screens checked later.\n")
        yaml.safe_dump({n: output[n] for n in names if n in output}, f, sort_keys=False)
    print(f"saved {path}")
    print("NO ANCHORS FOR: " + ", ".join(problems) if problems else "every screen has anchors")


if __name__ == "__main__":
    main()
