"""The afkami brand from one drawing: the ghost cursor (a mouse pointer whose lower edge is a ghost's
hem, with sleepy eyes: it clicks while you're away). Writes app/assets/brand/:
- afkami_mark_light.svg / _dark.svg   the mark alone, for light text on dark or the reverse
- afkami_icon.svg, xpedite_icon.svg   on the dark tile; the hub's eyes are dark, a unit's are its colour
- afkami.ico, xpedite.ico             16-256 px (xpedite.ico is also copied to app/assets/macro.ico,
                                      which the desktop shortcuts point at)
- xpedite_avatar_512.png              the Discord bot's avatar (full bleed: Discord crops a circle)
- afkami_banner_960x540.png           a Discord server banner
- sticker_*.png                       320 px Discord stickers, outlined for light and dark themes

    .venv-win/Scripts/python.exe tools/make_brand.py
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "app", "assets", "brand")

TILE = "#15181e"
INK = "#f3f5f9"
MUTED = "#9aa3b5"
UNITS = {"afkami": TILE, "xpedite": "#ff9a3c"}  # eye colour: the hub's are the tile's, each unit has its own

# 512 x 512. The pointer: tip, the 45 degree right edge, the shoulder back in (what makes it read
# as a mouse pointer, not a triangle), then three hanging lobes
# back to the left edge. The same colour as a round-joined stroke rounds every corner.
BODY = ("M150 80 L390 320 L318 322 Q305.1 364.2 262 354.7 Q249.1 396.9 206 387.3 "
        "Q193.1 429.6 150 420 Z")
EYES = {
    "sleepy": "M180 250 Q200 268 220 250 M244 250 Q264 268 284 250",
    "happy": "M180 262 Q200 242 220 262 M244 262 Q264 242 284 262",
}
# Centred on its weight, not its box: like a play button, a pointer's mass sits along its straight
# left edge (weight centre (225, 270), box centre (270, 250)), so box-centred it hugged the left of
# the tile, plainly so in the taskbar (user, 13 Nov 2026).
CENTRE = "translate(31 -2)"
# At 32 px and below a little larger, so it still reads as a pointer at a glance.
CENTRE_SMALL = "translate(256 256) scale(1.16) translate(-225 -258)"


def pointer(body: str, eyes: str, eye_kind: str = "sleepy", outline: str | None = None, open_eyes=False,
            transform: str = CENTRE) -> str:
    parts = []
    if outline:  # a dark rim so a white pointer reads on light backgrounds too (stickers)
        parts.append(f'<path d="{BODY}" fill="{outline}" stroke="{outline}" stroke-width="58" stroke-linejoin="round"/>')
    parts.append(f'<path d="{BODY}" fill="{body}" stroke="{body}" stroke-width="18" stroke-linejoin="round"/>')
    if open_eyes:
        parts.append(f'<circle cx="200" cy="254" r="13" fill="{eyes}"/><circle cx="264" cy="254" r="13" fill="{eyes}"/>')
    else:
        parts.append(f'<path d="{EYES[eye_kind]}" fill="none" stroke="{eyes}" stroke-width="14" stroke-linecap="round"/>')
    return f'<g transform="{transform}">' + "".join(parts) + "</g>"


def svg(content: str, size: int = 512) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 512 512">'
            f"{content}</svg>")


def tile_icon(eye_colour: str, full_bleed: bool = False, small: bool = False) -> str:
    background = (f'<rect width="512" height="512" fill="{TILE}"/>' if full_bleed
                  else f'<rect width="512" height="512" rx="112" fill="{TILE}"/>')
    return svg(background + pointer(INK, eye_colour, transform=CENTRE_SMALL if small else CENTRE))


def zz(x: float, y: float, s: float, colour: str, outline: str) -> str:
    def one(cx, cy, k):
        pts = f"{cx},{cy} {cx + 34 * k},{cy} {cx},{cy + 38 * k} {cx + 34 * k},{cy + 38 * k}"
        return (f'<polyline points="{pts}" fill="none" stroke="{outline}" stroke-width="{30 * k}" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="{12 * k}" stroke-linecap="round" stroke-linejoin="round"/>')
    return one(x, y, s) + one(x + 44 * s, y - 52 * s, s * 0.7)


def render(svg_text: str, size: int):
    from PyQt6.QtCore import QByteArray, Qt
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(QByteArray(svg_text.encode()))
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    return image


def to_pil(image):
    from PIL import Image
    from PyQt6.QtCore import QBuffer, QIODevice
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    import io
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")


def write(name: str, text: str):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(text)


def banner(path: str):
    """960 x 540: the hub's icon, the wordmark, what it is, and the first unit."""
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QImage, QPainter
    image = QImage(960, 540, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#0f1115"))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.drawImage(QRectF(96, 150, 240, 240), render(tile_icon(UNITS["afkami"]), 480))
    title = QFont("Bahnschrift", 1)
    title.setPixelSize(118)
    title.setWeight(QFont.Weight.DemiBold)
    p.setFont(title)
    p.setPen(QColor(INK))
    p.drawText(QRectF(384, 150, 560, 140), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "afkami")
    line = QFont("Segoe UI", 1)
    line.setPixelSize(30)
    p.setFont(line)
    p.setPen(QColor(MUTED))
    p.drawText(QRectF(390, 286, 560, 44), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "macros that play while you're away")
    p.setBrush(QColor(UNITS["xpedite"]))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(392, 352, 14, 14))
    unit = QFont("Bahnschrift", 1)
    unit.setPixelSize(26)
    p.setFont(unit)
    p.setPen(QColor(INK))
    p.drawText(QRectF(418, 340, 540, 40), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "xpedite  ·  Anime Expeditions")
    p.end()
    image.save(path)


def main():
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841 - fonts need it
    os.makedirs(OUT, exist_ok=True)
    write("afkami_mark_light.svg", svg(pointer(INK, TILE)))
    write("afkami_mark_dark.svg", svg(pointer(TILE, INK)))
    for unit, eyes in UNITS.items():
        write(f"{unit}_icon.svg", tile_icon(eyes))
        sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
        big = to_pil(render(tile_icon(eyes), 256))
        frames = {s: to_pil(render(tile_icon(eyes, small=s <= 32), s)) for s in sizes}  # each size drawn, not shrunk
        big.save(os.path.join(OUT, f"{unit}.ico"), format="ICO", sizes=[(s, s) for s in sizes],
                 append_images=[frames[s] for s in sizes if s != 256])
        render(tile_icon(eyes), 1024).save(os.path.join(OUT, f"{unit}_icon_1024.png"))
    render(tile_icon(UNITS["xpedite"], full_bleed=True), 512).save(os.path.join(OUT, "xpedite_avatar_512.png"))
    render(tile_icon(UNITS["afkami"], full_bleed=True), 512).save(os.path.join(OUT, "afkami_avatar_512.png"))
    banner(os.path.join(OUT, "afkami_banner_960x540.png"))
    stickers = {
        "zz": pointer(INK, TILE, "sleepy", outline=TILE) + zz(404, 138, 1.0, INK, TILE),
        "on_it": pointer(INK, TILE, outline=TILE, open_eyes=True),
        "gg": pointer(INK, UNITS["xpedite"], "happy", outline=TILE),
    }
    for name, content in stickers.items():
        text = svg(content)
        write(f"sticker_{name}.svg", text)
        render(text, 320).save(os.path.join(OUT, f"sticker_{name}.png"))
    shutil.copyfile(os.path.join(OUT, "xpedite.ico"), os.path.join(ROOT, "app", "assets", "macro.ico"))
    print("wrote", len(os.listdir(OUT)), "files to", OUT)


if __name__ == "__main__":
    main()
