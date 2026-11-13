"""Build the digit shapes in data/digits/ from hand-labelled pictures, then test them.

The test reads each picture using only shapes from the other pictures, because a
picture recognising its own digits would prove nothing. Doesn't touch the game.
Run from the project root:  .venv-win/Scripts/python.exe tools/build_digits.py
"""
import glob
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.vision import digits as d
from macro.vision.screens import GAME_HEIGHT, GAME_WIDTH, frame_path, load_frame

# Read by eye. Format: yen, health, wave text, enemies, time digits.
TRUTH = {
    "win/match_hud": ("1000000", "3", "1", "0", "0009"),
    "win/match_hud_sandbox": ("1000000", "3", "1", "0", "0021"),
    "win/match_hud_unit": ("991650", "3", "1", "0", "0116"),
    "win/overhead_view": ("1000000", "3", "1", "0", "0343"),
    "win/unit_manager": ("1000000", "3", "1", "0", "0011"),
    "linux/match_hud": ("1220", "3", "3/15", "45", "0038"),
    "linux/match_autoplaying": ("60", "3", "4/15", "58", "0051"),
    "linux/overhead_view": ("1000000", "3", "1", "0", "0238"),
    "linux/sandbox_spawn": ("1000000", "3", "1", "0", "0007"),
    "linux/place_invalid_toast": ("983300", "3", "1", "0", "0522"),
    # A real Story match in the frame. Read by eye from the pictures.
    "native/match__4": ("600", "3", "1/15", "16", "0010"),
    "native/match__5": ("945", "3", "3/15", "33", "0032"),
    "native/match__7": ("558", "3", "5/15", "67", "0103"),
    "native/match__8": ("558", "3", "6/15", "85", "0118"),
    "native/match__9": ("2148", "3", "7/15", "72", "0134"),
    "native/match__10": ("1499", "3", "8/15", "64", "0151"),
    # Orange ground that passes the colour filter, where the Yen was once refused all match.
    "native/match__20": ("1000000", "3", "1", "0", "0010"),
}
LABEL_BOXES = {"health": (548, 37, 582, 48), "wave": (656, 37, 684, 48),
               "enemies": (760, 37, 804, 48), "time": (908, 37, 934, 48)}  # in LABEL_SOURCE
LABEL_SOURCE = "native/match__1"


def save_glyph(mask, box, char, source, n):
    name = "slash" if char == "/" else char
    glyph = d._normalise(mask, box)
    path = os.path.join(d.SHAPES, f"glyph__{name}__{source.replace('/', '-').replace('__', '_')}__{n}.png")
    cv2.imwrite(path, (glyph * 255).astype(np.uint8))


def build():
    os.makedirs(d.SHAPES, exist_ok=True)
    for old in glob.glob(os.path.join(d.SHAPES, "glyph_*.png")):
        os.remove(old)
    source = cv2.cvtColor(load_frame(LABEL_SOURCE), cv2.COLOR_BGR2GRAY)
    for name, (x0, y0, x1, y1) in LABEL_BOXES.items():
        cv2.imwrite(os.path.join(d.SHAPES, f"label_{name}.png"), source[y0:y1, x0:x1])

    reader = d.DigitReader()  # labels are all it has at this point
    counts, skipped = {}, []
    for picture, (yen, health, wave, enemies, clock) in TRUTH.items():
        frame = load_frame(picture)
        x0, y0, x1, y1 = d.YEN_BOX
        mask = d._gold_mask(d._enlarge(frame[y0:y1, x0:x1]))
        groups = [(mask, d.yen_glyph_boxes(mask), yen, "yen")]
        for name, text in (("health", health), ("wave", wave), ("enemies", enemies), ("time", clock)):
            left, top, right, bottom = reader.pill_region(frame, name)
            pill_mask = d._white_mask(d._enlarge(frame[top:bottom, left:right]))
            boxes = d.pill_glyph_boxes(pill_mask)
            run = []
            for box in reversed(boxes):
                if run and run[0][0] - (box[0] + box[2]) > d.RUN_MAX_GAP:
                    break
                run.insert(0, box)
            groups.append((pill_mask, run, text, name))
        for mask_used, boxes, text, label in groups:
            if len(boxes) != len(text):
                skipped.append(f"{picture} {label}: found {len(boxes)} blobs for {text!r}")
                continue
            for i, (box, char) in enumerate(zip(boxes, text)):
                save_glyph(mask_used, box, char, f"{picture}", f"{label}{i}")
                counts[char] = counts.get(char, 0) + 1
    # The clock frames from tools/live_nav.py, each named with its known true time. They
    # hold only the top of the screen. One sample per digit per position is plenty.
    kept = set()
    native = sorted(glob.glob(os.path.join(ROOT, "refs", "clock_native", "*.png")))
    for path in native + sorted(glob.glob(os.path.join(ROOT, "refs", "clock", "*.png"))):
        text = os.path.basename(path)[:-4].split("_")[1]
        top = cv2.imread(path)
        if path in native:  # the top of the game's picture, at its current size
            canvas = np.zeros((GAME_HEIGHT, GAME_WIDTH, 3), np.uint8)
            canvas[:top.shape[0]] = top
        else:  # a piece of a 1920x1080 screen
            canvas = np.zeros((1080, 1920, 3), np.uint8)
            canvas[:top.shape[0], 600:600 + top.shape[1]] = top
            canvas = cv2.resize(canvas, (GAME_WIDTH, GAME_HEIGHT), interpolation=cv2.INTER_AREA)
        left, top, right, bottom = reader.pill_region(canvas, "time")
        pill = d._white_mask(d._enlarge(canvas[top:bottom, left:right]))
        run = []
        for box in reversed(d.pill_glyph_boxes(pill)):
            if run and run[0][0] - (box[0] + box[2]) > d.RUN_MAX_GAP:
                break
            run.insert(0, box)
        if len(run) != 4:
            continue
        for i, (box, char) in enumerate(zip(run, text)):
            if (char, i) not in kept:
                kept.add((char, i))
                save_glyph(pill, box, char, "clock", f"{i}{os.path.basename(path)[:3]}")
                counts[char] = counts.get(char, 0) + 1
    print("shapes per character:", dict(sorted(counts.items())))
    missing = [c for c in "0123456789/" if c not in counts]
    print("characters with no shape:", missing or "none")
    for line in skipped:
        print("  skipped", line)


def test():
    total = correct = 0
    wrong, times = [], []
    for picture, truth in TRUTH.items():
        reader = d.DigitReader(skip_source=picture.replace("/", "-").replace("__", "_"))
        frame = load_frame(picture)
        start = time.perf_counter()
        readings = {"yen": reader.yen_reading(frame), "health": reader.pill_reading(frame, "health"),
                    "wave": reader.pill_reading(frame, "wave"), "enemies": reader.pill_reading(frame, "enemies"),
                    "time": reader.pill_reading(frame, "time")}
        times.append((time.perf_counter() - start) * 1000)
        for (name, reading), expected in zip(readings.items(), truth):
            total += 1
            if reading.text == expected:
                correct += 1
            else:
                wrong.append(f"{picture} {name}: read {reading.text!r} ({reading.confidence:.2f}), truth {expected!r}")
    print(f"\nreading each picture with shapes from the others: {correct} of {total} right")
    for line in wrong:
        print("  WRONG", line)
    print(f"time per frame, all five values: median {np.median(times):.1f} ms, worst {max(times):.1f} ms")


def stress_test():
    """A wrong Yen is worse than no Yen. So interfere with the number on purpose, as ground
    and tooltips do, and require the true value or nothing, never a different number."""
    reader = d.DigitReader()
    gold = (0, 200, 255)
    plate = (60, 60, 60)
    x0, y0, x1, y1 = d.YEN_BOX
    outcomes = {"bars touching it": [0, 0, []], "a digit or comma covered": [0, 0, []]}

    def judge(kind, frame, truth, what):
        got = reader.read_yen(frame)
        tally = outcomes[kind]
        if got == truth:
            tally[0] += 1
        elif got is None:
            tally[1] += 1
        else:
            tally[2].append(f"{what}: read {got}, truth {truth}")

    for picture, expected in TRUTH.items():
        frame = load_frame(picture)
        truth = int(expected[0])
        mask = d._gold_mask(d._enlarge(frame[y0:y1, x0:x1]))
        boxes = d.yen_glyph_boxes(mask)
        if not boxes:
            continue
        s = d.SCALE
        tops = y0 + round(boxes[0][1] * s)
        bottoms = y0 + round((boxes[0][1] + boxes[0][3]) * s)
        left, right = x0 + round(boxes[0][0] * s) - 8, x0 + round((boxes[-1][0] + boxes[-1][2]) * s) + 14
        for x in range(left, right, 2):
            for name, (a, b) in (("below", (bottoms - 1, bottoms + 22)), ("above", (tops - 22, tops + 1))):
                painted = frame.copy()
                cv2.rectangle(painted, (x, a), (x + 5, b), gold, -1)
                judge("bars touching it", painted, truth, f"{picture} bar {name} at x={x}")
        for i, box in enumerate(boxes):
            painted = frame.copy()
            ax, ay = x0 + round(box[0] * s), y0 + round(box[1] * s)
            cv2.rectangle(painted, (ax - 1, ay - 1), (ax + round(box[2] * s) + 1, ay + round(box[3] * s) + 1), plate, -1)
            judge("a digit or comma covered", painted, truth, f"{picture} digit {i} covered")
        for x in range(left, right, 3):  # blanking a thin strip takes out any comma too
            painted = frame.copy()
            cv2.rectangle(painted, (x, bottoms - 6), (x + 3, bottoms + 6), plate, -1)
            judge("a digit or comma covered", painted, truth, f"{picture} strip at x={x}")
    wrong_total = 0
    print("\nstress test, interfering with the Yen number:")
    for kind, (same, refused, wrong) in outcomes.items():
        print(f"  {kind}: {same} still right, {refused} refused, {len(wrong)} WRONG")
        for line in wrong[:8]:
            print("    WRONG", line)
        wrong_total += len(wrong)
    print("  never a wrong number" if not wrong_total else f"  {wrong_total} WRONG NUMBERS")
    return wrong_total


if __name__ == "__main__":
    build()
    test()
    sys.exit(1 if stress_test() else 0)
