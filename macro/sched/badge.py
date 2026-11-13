"""A small animated badge for a result's webhook embed (Discord plays GIFs in embeds): a ring
that sweeps round to how far the task has got, then the outcome's mark settles in the middle,
a check for a win, a cross for a loss. Colours match the app: near-black, white, one tint.
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw

SIZE = 160
SCALE = 4  # drawn large and shrunk, for smooth edges
FRAMES = 22
GOOD = (127, 224, 181)
BAD = (255, 140, 140)
GROUND = (13, 16, 22)
CORNER = (30, 31, 34)  # outside the rounded corners: Discord's dark embed


def _ease(t: float) -> float:
    return 1 - (1 - t) ** 3


def _mix(colour, alpha: float):
    """A colour laid over the badge's ground at that strength (GIFs have no soft transparency)."""
    return tuple(round(c * alpha + g * (1 - alpha)) for c, g in zip(colour, GROUND))


def _frame(progress: float, mark: float, colour, won: bool) -> Image.Image:
    s = SIZE * SCALE
    image = Image.new("RGB", (s, s), CORNER)
    draw = ImageDraw.Draw(image)
    r = s * 0.12
    draw.rounded_rectangle((0, 0, s - 1, s - 1), r, fill=GROUND)
    # Glass rim: a light line along the top edge.
    draw.rounded_rectangle((2, 2, s - 3, s - 3), r, outline=_mix((255, 255, 255), 0.16), width=SCALE * 2)
    pad = s * 0.17
    box = (pad, pad, s - pad, s - pad)
    width = int(s * 0.07)
    draw.arc(box, 0, 360, fill=_mix((255, 255, 255), 0.12), width=width)
    if progress > 0.001:
        draw.arc(box, -90, -90 + 360 * progress, fill=colour, width=width)
        # A bright head on the sweep.
        angle = math.radians(-90 + 360 * progress)
        cx, cy, rr = s / 2, s / 2, (s - 2 * pad) / 2 - width / 2
        hx, hy = cx + rr * math.cos(angle), cy + rr * math.sin(angle)
        head = width * 0.62
        draw.ellipse((hx - head, hy - head, hx + head, hy + head), fill=_mix((255, 255, 255), 0.92))
    if mark > 0:
        ink = _mix((255, 255, 255), mark)
        grow = 0.75 + 0.25 * mark
        c = s / 2
        u = s * 0.13 * grow
        line = int(s * 0.055)
        if won:
            points = [(c - u, c + u * 0.05), (c - u * 0.25, c + u * 0.8), (c + u * 1.05, c - u * 0.75)]
            draw.line(points, fill=ink, width=line, joint="curve")
        else:
            draw.line([(c - u * 0.8, c - u * 0.8), (c + u * 0.8, c + u * 0.8)], fill=ink, width=line)
            draw.line([(c - u * 0.8, c + u * 0.8), (c + u * 0.8, c - u * 0.8)], fill=ink, width=line)
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def result_badge(progress: float, won: bool) -> bytes:
    """GIF bytes: the sweep to `progress` (0..1), then the mark, holding on the last frame."""
    colour = GOOD if won else BAD
    progress = max(0.0, min(1.0, progress))
    frames, durations = [], []
    for i in range(FRAMES):
        t = i / (FRAMES - 1)
        sweep = _ease(min(1.0, t / 0.7)) * progress
        mark = _ease(max(0.0, (t - 0.55) / 0.45))
        frames.append(_frame(sweep, mark, colour, won).convert("P", palette=Image.Palette.ADAPTIVE))
        durations.append(40)
    durations[-1] = 60000  # then rest: a badge, not a spinner
    out = io.BytesIO()
    frames[0].save(out, format="GIF", save_all=True, append_images=frames[1:], duration=durations, loop=0,
                   disposal=2)
    return out.getvalue()


def bar(fraction: float, cells: int = 12) -> str:
    """A text progress bar for an embed: filled and empty blocks."""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * cells)
    return "▰" * filled + "▱" * (cells - filled)
