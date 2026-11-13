"""Reading text and numbers from small parts of the screen with RapidOCR.

Slow compared to template matching, so it only ever runs on small crops and only
when needed. The model loads the first time it's used.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

_engine = None
THREADS = 4


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        # A few threads: twice as fast as all 24 here (0.6 s against 1.2 s a read),
        # and the game needs the CPU.
        _engine = RapidOCR(intra_op_num_threads=THREADS, inter_op_num_threads=1)
    return _engine


def read_text(frame: np.ndarray, box: tuple[int, int, int, int], scale: float = 2.0) -> str:
    """All the text inside box [x0, y0, x1, y1], joined with spaces."""
    x0, y0, x1, y1 = box
    crop = cv2.resize(frame[y0:y1, x0:x1], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    # A crop with little around the text reads poorly, so add a margin.
    crop = cv2.copyMakeBorder(crop, 12, 12, 12, 12, cv2.BORDER_REPLICATE)
    result, _ = _get_engine()(crop, use_cls=False)
    return " ".join(line[1] for line in result) if result else ""


def read_line(frame: np.ndarray, box: tuple[int, int, int, int], scale: float = 2.0) -> str:
    """One line of text filling box. Skips looking for where the text is, so about 50 ms against
    600 ms. Needs a tight box around a single line."""
    x0, y0, x1, y1 = box
    crop = cv2.resize(frame[y0:y1, x0:x1], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    result, _ = _get_engine()(crop, use_det=False, use_cls=False)
    return result[0][0].strip() if result else ""


def read_number(frame: np.ndarray, box: tuple[int, int, int, int]) -> int | None:
    """The digits in box as one number, ignoring commas and symbols, or None."""
    digits = re.sub(r"\D", "", read_text(frame, box))
    return int(digits) if digits else None


def find_words(frame: np.ndarray, box: tuple[int, int, int, int] | None = None) -> list[tuple[str, int, int]]:
    """Text found in box (default: the whole screen), as (text, x, y) of each line's
    centre, in full-screen pixels."""
    x0, y0, x1, y1 = box or (0, 0, frame.shape[1], frame.shape[0])
    crop = frame[y0:y1, x0:x1]
    scale = min(1.0, 1600 / crop.shape[1])  # the game is 1440 wide, and its text is small
    if scale < 1.0:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    result, _ = _get_engine()(crop, use_cls=False)
    found = []
    for corners, text, _ in result or []:
        xs, ys = zip(*corners)
        found.append((text, int(x0 + sum(xs) / 4 / scale), int(y0 + sum(ys) / 4 / scale)))
    return found


def read_screen_words(frame: np.ndarray) -> str:
    """Everything on a downsized copy of the screen: for an unknown screen, to look
    for words like Reconnect or Close. Slow, so only when lost."""
    small = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)
    result, _ = _get_engine()(small, use_cls=False)
    return " ".join(line[1] for line in result) if result else ""
