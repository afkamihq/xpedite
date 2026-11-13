"""Reading match numbers fast: Yen, wave, health, enemies and time.

OCR takes about 0.6 s and misses things, so this does the job in a few milliseconds.
The text is bold with a dark outline, which separates each character into its own blob.
Blobs are compared with saved shapes in data/digits/ (made by tools/build_digits.py).

The top pills shift sideways as their contents change width, so each is found by its
fixed label ("wave", "time", ...), and the number is read from just left of it. The
Yen row is centred, so it's found by its tall yen icon.

Every reading comes with a confidence. Trust it: below MIN_CONFIDENCE, the value is
None, not a guess, and the caller can look again on the next frame.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass

import cv2
import numpy as np

from macro.vision.screens import SCALE

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHAPES = os.path.join(ROOT, "data", "digits")
GLYPH = (16, 24)  # width, height of a normalised shape
MIN_CONFIDENCE = 0.72
MIN_MARGIN = 0.04  # ahead of the best different character by at least this

S = SCALE
# The pills sit lower than scaling alone says, because Roblox's own top bar doesn't shrink.
# In a real match the pills can wrap: with "1 / 15" and "16" the clock drops to a second row.
TOP_ROW = (20, 60) if S == 1 else (18, 100)  # where to look for the pills' labels
TOP_X = (round(620 * S), round(1320 * S))
PILL_NUMBER_WIDTH = round(96 * S)  # the widest number, "15 / 15" or "00:38", left of its label
YEN_BOX = (round(800 * S), round(858 * S), round(1180 * S), round(916 * S) + 8)
# Sizes below are for numbers enlarged back to their 1920x1080 size, which is what keeps
# the dark outlines between digits. See _enlarge.
PILL_HEIGHT = (12, 26)  # a digit's height; a colon's dots are shorter
PILL_MAX_WIDTH = 24
YEN_ICON_HEIGHT = (33, 42)  # measured 36-38
YEN_ICON_WIDTH = (24, 34)  # measured 28-29
YEN_HEIGHT = (16, 31)
YEN_COMMA_BELOW = 16
YEN_DIGIT_TOP = (18, 24)  # in the enlarged crop of YEN_BOX; measured 20-22
YEN_DIGIT_BOTTOM = (38, 43)  # measured 40
YEN_MAX_WIDTH = 26
YEN_MAX_GAP = 18
YEN_ROW_CENTRE = 157.25  # in the enlarged crop of YEN_BOX; see _row_is_whole
YEN_ROW_TOLERANCE = 2.5
YEN_ICON_GAP = 18.5  # from the icon's right edge when not pulsing
YEN_MIDDLE_TO_FIRST_DIGIT = 32.5
DIGIT_GAP = 6  # measured 2
DIGIT_GAP_WITH_COMMA = 14  # measured 9
RUN_MAX_GAP = 16
PILL_ABOVE_LABEL = round(12 * S)
PILL_BELOW_LABEL = round(28 * S)
LABELS = ("health", "wave", "enemies", "time")
# Event matches (Soul Furnace, 11 Nov 2026) put Candy Corn and Souls left of the Yen in one
# centred row: crown icon, count, soul icon, count, yen icon, count. Measured in the enlarged
# crop of EVENT_BOX: the row (crown's left to the last Yen digit) centres at 226, and each
# count's first digit sits a fixed distance from its icon's middle.
EVENT_BOX = (round(720 * S), YEN_BOX[1], round(1200 * S), YEN_BOX[3])
EVENT_ROW_CENTRE = 226.0
EVENT_ROW_TOLERANCE = 3.5
CROWN_SIZE = ((34, 46), (20, 32))  # width, height
SOUL_ICON_SIZE = ((18, 26), (32, 42))
EVENT_FIRST_DIGIT = {"candy": 27.0, "souls": 26.0, "yen": YEN_MIDDLE_TO_FIRST_DIGIT}
LABEL_MIN = 0.55  # 1.00 on Windows, about 0.6 on Linux, which draws them slightly differently


@dataclass
class Reading:
    text: str
    confidence: float
    x: int = 0  # where the reading was found on screen

    @property
    def number(self) -> int | None:
        return int(self.text) if self.text.isdigit() else None


def _enlarge(crop: np.ndarray) -> np.ndarray:
    """At smaller sizes digits touch. Enlarged first, the outlines still separate them."""
    return crop if S == 1 else cv2.resize(crop, None, fx=1 / S, fy=1 / S, interpolation=cv2.INTER_CUBIC)


def _white_mask(crop: np.ndarray) -> np.ndarray:
    """Pill numbers are near-white with a tint; icons are saturated, so their weakest
    colour channel is low."""
    return (crop.min(axis=2) > 150).astype(np.uint8)


def _gold_mask(crop: np.ndarray) -> np.ndarray:
    return ((crop[:, :, 2] > 170) & (crop[:, :, 1] > 110)).astype(np.uint8)


def _blobs(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Boxes (x, y, w, h) of connected blobs, left to right."""
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    boxes = [tuple(int(v) for v in stats[i][:4]) for i in range(1, count)]
    return sorted(boxes)


def _normalise(mask: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = box
    return cv2.resize(mask[y:y + h, x:x + w].astype(np.float32), GLYPH, interpolation=cv2.INTER_AREA)


def pill_glyph_boxes(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    # Digits and the slash are tall; a colon's dots are short and get dropped.
    return [b for b in _blobs(mask) if PILL_HEIGHT[0] <= b[3] <= PILL_HEIGHT[1] and 2 <= b[2] <= PILL_MAX_WIDTH]


def yen_glyph_boxes(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """The digit blobs following the tall yen icon, stopping at the first wide gap so
    a "+¥N next wave" pill beyond it isn't read.

    Returns nothing rather than risk a wrong number. A wrong Yen is far worse than a
    missing one, so the row must be whole: centred, and fitting its commas (1,000,000)."""
    blobs = _blobs(mask)
    # By its size: orange ground beside it can be just as tall, but it's narrower.
    icon = next((b for b in blobs if YEN_ICON_HEIGHT[0] <= b[3] <= YEN_ICON_HEIGHT[1]
                 and YEN_ICON_WIDTH[0] <= b[2] <= YEN_ICON_WIDTH[1]), None)
    if icon is None:
        return []
    # The number is level with the icon. Blank everything above and below that first:
    # ground that touches a digit would otherwise join it into one tall blob, and the
    # digit would be lost. That read 951,650 as 95,650.
    band = mask.copy()
    band[:icon[1] - 1] = 0
    band[icon[1] + icon[3] + 1:] = 0
    mask[:] = band
    icon_right = icon[0] + icon[2]
    digits, commas, right = [], [], icon[0] + icon[2] / 2 + YEN_MIDDLE_TO_FIRST_DIGIT
    for box in _blobs(mask):
        if box[0] < icon_right:  # part of the icon
            continue
        if box[3] < YEN_COMMA_BELOW:  # a comma or a speck: only digits move the position
            commas.append(box)
            continue
        # Digits sit at a fixed height and size. Anything else is ground, which on orange
        # maps passes the colour filter in huge blobs, or a digit something has touched. It's
        # safe to skip either: _row_is_whole and _fits_commas catch a lost digit.
        if not (YEN_DIGIT_TOP[0] <= box[1] <= YEN_DIGIT_TOP[1]
                and YEN_DIGIT_BOTTOM[0] <= box[1] + box[3] <= YEN_DIGIT_BOTTOM[1]
                and box[2] <= YEN_MAX_WIDTH):
            continue
        if box[0] - right > YEN_MAX_GAP:
            break
        digits.append(box)
        right = box[0] + box[2]
    if not digits or not _row_is_whole(icon, digits) or not _fits_commas(digits, commas):
        return []
    return digits


def event_row_boxes(mask: np.ndarray) -> dict | None:
    """The digit boxes of Candy Corn, Souls and Yen in an event match's currency row, or None
    when this isn't that row or any part of it can't be trusted (same rules as the Yen alone)."""
    def fits(box, size):
        return size[0][0] <= box[2] <= size[0][1] and size[1][0] <= box[3] <= size[1][1]
    blobs = _blobs(mask)
    crown = next((b for b in blobs if fits(b, CROWN_SIZE) and b[0] < 150), None)
    if crown is None:
        return None
    soul = next((b for b in blobs if b[0] > crown[0] + crown[2] and fits(b, SOUL_ICON_SIZE)), None)
    if soul is None:
        return None
    yen = next((b for b in blobs if b[0] > soul[0] + soul[2]
                and fits(b, (YEN_ICON_WIDTH, YEN_ICON_HEIGHT))), None)
    if yen is None:
        return None
    band = mask.copy()
    band[:yen[1] - 1] = 0
    band[yen[1] + yen[3] + 1:] = 0
    mask[:] = band
    icons = {"candy": crown, "souls": soul, "yen": yen}
    order = ["candy", "souls", "yen"]
    runs = {name: ([], []) for name in order}
    for box in _blobs(mask):
        owner = None
        for name in order:
            icon = icons[name]
            if box[0] >= icon[0] + icon[2]:
                owner = name
        if owner is None or any(box[0] < icons[n][0] + icons[n][2] and box[0] + box[2] > icons[n][0] for n in order):
            continue  # left of the row, or part of an icon
        digits, commas = runs[owner]
        if box[3] < YEN_COMMA_BELOW:
            commas.append(box)
            continue
        if not (YEN_DIGIT_TOP[0] <= box[1] <= YEN_DIGIT_TOP[1]
                and YEN_DIGIT_BOTTOM[0] <= box[1] + box[3] <= YEN_DIGIT_BOTTOM[1]
                and box[2] <= YEN_MAX_WIDTH):
            continue
        last = digits[-1][0] + digits[-1][2] if digits else None
        if last is not None and box[0] - last > YEN_MAX_GAP:
            continue  # past the end of this count
        digits.append(box)
    out = {}
    for name in order:
        digits, commas = runs[name]
        icon = icons[name]
        if not digits or abs(digits[0][0] - icon[0] - icon[2] / 2 - EVENT_FIRST_DIGIT[name]) > 4:
            return None
        if not _fits_commas(digits, commas):
            return None
        out[name] = digits
    last = out["yen"][-1]
    if abs((crown[0] + last[0] + last[2]) / 2 - EVENT_ROW_CENTRE) > EVENT_ROW_TOLERANCE:
        return None
    return out


def _row_is_whole(icon, digits) -> bool:
    """The row of icon and digits is centred on screen, measured at 150.0 to 150.5 for
    every length of number. So a digit missing from either end throws it off-centre, which
    gaps and commas can't show. The first digit also sits a fixed distance from the icon."""
    icon_middle = icon[0] + icon[2] / 2
    centre = (icon_middle + digits[-1][0] + digits[-1][2]) / 2
    return (abs(centre - YEN_ROW_CENTRE) <= YEN_ROW_TOLERANCE
            and abs(digits[0][0] - icon_middle - YEN_MIDDLE_TO_FIRST_DIGIT) <= 4)


def _fits_commas(digits, commas) -> bool:
    """Three digits between and after commas, one to three before the first."""
    if not digits:
        return False
    bottom = max(d[1] + d[3] for d in digits)
    top = min(d[1] for d in digits)
    # Digits in a row are all the same height. One that isn't has something touching it:
    # a bar across the top of a 0 read as 8.
    if bottom - top > max(d[3] for d in digits) or max(d[3] for d in digits) - min(d[3] for d in digits) > 1:
        return False
    middle = (top + bottom) / 2
    # A comma hangs at the baseline, between digits. Specks elsewhere don't count.
    # Measured commas: 4-5 wide, 8-9 tall, top a little below the digits' middle, bottom
    # just under theirs. It has to be this tight, as orange ground leaves specks that pass
    # for a comma, and a false one after the last digit would refuse a good reading.
    hanging = [c for c in commas if 3 <= c[2] <= 7 and 6 <= c[3] <= 12
               and middle <= c[1] <= middle + 9 and bottom - 2 <= c[1] + c[3] <= bottom + 7]
    real = [c for c in hanging if digits[0][0] < c[0] < digits[-1][0]]
    # A comma just after the last digit means the number carried on and was cut short.
    last_right = digits[-1][0] + digits[-1][2]
    if any(0 <= c[0] - last_right <= YEN_MAX_GAP for c in hanging):
        return False
    # Neighbouring digits sit close together, closer without a comma between them. A wider
    # gap is where a digit has gone missing, even if what's left still looks like a number.
    for left, next_digit in zip(digits, digits[1:]):
        gap = next_digit[0] - (left[0] + left[2])
        comma_between = any(left[0] < c[0] < next_digit[0] for c in real)
        if gap > (DIGIT_GAP_WITH_COMMA if comma_between else DIGIT_GAP):
            return False
    groups, count = [], 0
    marks = sorted(c[0] for c in real)
    for digit in digits:
        while marks and marks[0] < digit[0]:
            groups.append(count)
            count = 0
            marks.pop(0)
        count += 1
    groups.append(count)
    if len(groups) == 1:
        return groups[0] <= 3
    return 1 <= groups[0] <= 3 and all(g == 3 for g in groups[1:])


class DigitReader:
    def __init__(self, shapes_dir: str = SHAPES, skip_source: str | None = None):
        """skip_source leaves out shapes taken from one picture, for fair testing."""
        self.shapes: list[tuple[str, np.ndarray]] = []
        for path in glob.glob(os.path.join(shapes_dir, "glyph_*.png")):
            stem = os.path.basename(path)[:-4]
            _, char, source, _ = stem.split("__") if "__" in stem else (None, None, None, None)
            if skip_source and source == skip_source:
                continue
            image = cv2.imread(path, cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
            self.shapes.append((_char_from_name(char), image))
        self._stack = np.stack([s[1].ravel() - s[1].mean() for s in self.shapes]) if self.shapes else None
        if self._stack is not None:
            self._stack /= np.linalg.norm(self._stack, axis=1, keepdims=True) + 1e-6
        self.labels = {}
        for name in LABELS:
            path = os.path.join(shapes_dir, f"label_{name}.png")
            if os.path.exists(path):
                self.labels[name] = cv2.imread(path, cv2.IMREAD_GRAYSCALE)

    def _classify(self, glyph: np.ndarray) -> tuple[str, float]:
        vector = glyph.ravel() - glyph.mean()
        vector /= np.linalg.norm(vector) + 1e-6
        scores = self._stack @ vector
        best = int(np.argmax(scores))
        char = self.shapes[best][0]
        # Barely ahead of a different character is a guess: a bar across a 0 read as 8.
        runner_up = max(float(s) for s, shape in zip(scores, self.shapes) if shape[0] != char)
        if float(scores[best]) - runner_up < MIN_MARGIN:
            return char, 0.0
        return char, float(scores[best])

    def _read(self, mask: np.ndarray, boxes, offset_x: int) -> Reading:
        chars, weakest = [], 1.0
        for box in boxes:
            char, score = self._classify(_normalise(mask, box))
            chars.append(char)
            weakest = min(weakest, score)
        if not chars:
            return Reading("", 0.0, offset_x)
        return Reading("".join(chars), weakest, offset_x + boxes[0][0])

    def read_yen(self, frame: np.ndarray) -> int | None:
        reading = self.yen_reading(frame)
        if reading.confidence < MIN_CONFIDENCE:
            return None
        if len(reading.text) > 1 and reading.text[0] == "0":  # no number starts with 0
            return None
        return reading.number

    def event_row(self, frame: np.ndarray) -> dict | None:
        """{candy, souls, yen} in an event match's currency row (a value None if unsure), or
        None if this frame has no such row."""
        x0, y0, x1, y1 = EVENT_BOX
        mask = _gold_mask(_enlarge(frame[y0:y1, x0:x1]))
        boxes = event_row_boxes(mask)
        if boxes is None:
            # A path line behind the HUD can cross the digits and cut each in two (Soul Furnace's
            # bottom path, 11 Nov 2026): close thin horizontal gaps and look again. The row's
            # checks (heights, gaps, commas, centring) still have to pass.
            # Rows inside the digits' band with no gold but blue across them are such a line (one
            # or two rows when enlarged): fill each from the rows either side, where both are gold.
            crop = _enlarge(frame[y0:y1, x0:x1])
            mask = _gold_mask(crop)
            blue = (crop[:, :, 0].astype(int) > crop[:, :, 2].astype(int) + 20)
            top, bottom = YEN_DIGIT_TOP[0], YEN_DIGIT_BOTTOM[0]
            for r in range(top + 1, bottom):
                one = blue[r] & (mask[r] == 0) & (mask[r - 1] > 0) & (mask[r + 1] > 0)
                two = blue[r] & blue[r + 1] & (mask[r] == 0) & (mask[r + 1] == 0) & (mask[r - 1] > 0) & (mask[r + 2] > 0)
                mask[r][one] = 1
                mask[r][two] = 1
                mask[r + 1][two] = 1
            boxes = event_row_boxes(mask)
        if boxes is None:
            return None
        out = {}
        for name, digits in boxes.items():
            reading = self._read(mask, digits, x0)
            ok = reading.confidence >= MIN_CONFIDENCE and not (len(reading.text) > 1 and reading.text[0] == "0")
            out[name] = reading.number if ok else None
        return out

    def yen_reading(self, frame: np.ndarray) -> Reading:
        x0, y0, x1, y1 = YEN_BOX
        mask = _gold_mask(_enlarge(frame[y0:y1, x0:x1]))
        return self._read(mask, yen_glyph_boxes(mask), x0)

    def pill_region(self, frame: np.ndarray, name: str) -> tuple[int, int, int, int] | None:
        """Where a pill's number is, as x0, y0, x1, y1: left of its label, at the label's
        own height, as a wrapped pill sits on another row and the first row's digits
        mustn't get mixed in. None if the label isn't found."""
        y0, y1 = TOP_ROW
        x_lo, x_hi = TOP_X
        row = cv2.cvtColor(frame[y0:y1, x_lo:x_hi], cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(row, self.labels[name], cv2.TM_CCOEFF_NORMED)
        _, score, _, (at_x, at_y) = cv2.minMaxLoc(result)
        if score < LABEL_MIN:
            return None
        right = x_lo + at_x
        label_y = y0 + at_y
        return max(right - PILL_NUMBER_WIDTH, 0), max(label_y - PILL_ABOVE_LABEL, 0), right, label_y + PILL_BELOW_LABEL

    def pill_reading(self, frame: np.ndarray, name: str) -> Reading:
        """The text in one top pill, found through its label."""
        region = self.pill_region(frame, name)
        if region is None:
            return Reading("", 0.0)
        left, top, right, bottom = region
        mask = _white_mask(_enlarge(frame[top:bottom, left:right]))
        boxes = pill_glyph_boxes(mask)
        # Too wide to be one digit means digits have merged. A wrong number is worse than none.
        if any(PILL_HEIGHT[0] <= b[3] <= PILL_HEIGHT[1] and b[2] > PILL_MAX_WIDTH for b in _blobs(mask)):
            return Reading("", 0.0)
        # The number ends just before the label, and an icon can sit further left: read
        # the run of glyphs nearest the label, stopping at a wide gap.
        run = []
        for box in reversed(boxes):
            if run and run[0][0] - (box[0] + box[2]) > RUN_MAX_GAP:
                break
            run.insert(0, box)
        return self._read(mask, run, left)

    def read_hud(self, frame: np.ndarray) -> dict:
        """Yen, wave, wave_total, health, enemies, seconds. A value it can't read
        confidently is None."""
        def number(name):
            reading = self.pill_reading(frame, name)
            return reading.number if reading.confidence >= MIN_CONFIDENCE else None

        wave_reading = self.pill_reading(frame, "wave")
        wave, total = None, None
        if wave_reading.confidence >= MIN_CONFIDENCE:
            parts = wave_reading.text.split("/")
            if all(part.isdigit() for part in parts) and len(parts) <= 2:
                wave = int(parts[0])
                total = int(parts[1]) if len(parts) == 2 else None
        time_reading = self.pill_reading(frame, "time")
        seconds = None
        if time_reading.confidence >= MIN_CONFIDENCE and time_reading.text.isdigit() and len(time_reading.text) == 4:
            seconds = int(time_reading.text[:2]) * 60 + int(time_reading.text[2:])
        yen = self.read_yen(frame)
        event = self.event_row(frame) if yen is None else None
        if event is not None:
            yen = event["yen"]
        return {"yen": yen, "wave": wave, "wave_total": total, "souls": event["souls"] if event else None,
                "candy": event["candy"] if event else None,
                "health": number("health"), "enemies": number("enemies"), "seconds": seconds}


def _char_from_name(name: str) -> str:
    return "/" if name == "slash" else name
