"""The README's art, in docs/art/, from the same drawing as the brand (tools/make_brand.py):
- hero_dark.png / hero_light.png   the ghost cursor, "xpedite", "by afkami" and the tagline, on a
                                   transparent ground so GitHub's light or dark page shows through
- divider_dark.png / _light.png    a candy-corn stripe between sections
- how_dark.png / how_light.png     sees, reads, decides, clicks
- app.png                          the app with a Soul Furnace run docked in it (names blurred)

    .venv-win/Scripts/python.exe tools/make_readme_art.py [path of an in-game frame for app.png]
"""
import os
import sys

# As the app itself does (app/main.py): one Qt pixel is one screen pixel. Set before Qt starts, or
# the app's window is laid out at 125% while the game is pasted at 100%.
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "release"))

import make_brand as mb  # noqa: E402
from macro import brand  # noqa: E402

OUT = os.path.join(ROOT, "docs", "art")
THEMES = {"dark": {"ink": "#f3f5f9", "muted": "#8b93a5", "line": "#2a2f3a", "card": "#161a21"},
          "light": {"ink": "#15181e", "muted": "#5c6474", "line": "#d5d9e0", "card": "#f2f4f7"}}
CANDY = ["#f8c33a", "#ff9a3c", "#f3f5f9"]  # a candy corn: yellow base, orange middle, white tip


_APP = None


def qt():
    """The Qt application, kept alive here: dropped, every later Qt call crashed the process."""
    global _APP
    from macro.platform import windows  # noqa: F401 - sets the DPI awareness first, as the app does
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])
    return _APP


def font(family, px, weight=None):
    from PyQt6.QtGui import QFont
    f = QFont(family, 1)
    f.setPixelSize(px)
    if weight is not None:
        f.setWeight(weight)
    return f


def hero(theme: str, path: str):
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen
    t = THEMES[theme]
    w, h = 1280, 400
    icon = mb.render(mb.tile_icon(brand.UNIT_COLOUR), 520)  # before any painter is open (Qt's SVG crashed inside one)
    image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.drawImage(QRectF(250, 70, 260, 260), icon)
    p.setPen(QColor(t["ink"]))
    p.setFont(font("Bahnschrift", 132, QFont.Weight.DemiBold))
    p.drawText(QRectF(560, 64, 700, 170), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, brand.UNIT)
    p.setPen(QColor(t["muted"]))
    p.setFont(font("Segoe UI", 30))
    p.drawText(QRectF(566, 222, 700, 44), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "plays Anime Expeditions while you're away")
    # "by afkami" with a little candy corn before it
    x, y = 568, 290
    for n, colour in enumerate(CANDY):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(colour))
        p.drawRoundedRect(QRectF(x + n * 15, y, 13, 22), 4, 4)
    if theme == "light":  # the white tip needs an edge on a light page
        p.setPen(QPen(QColor(t["line"]), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x + 30, y, 13, 22), 4, 4)
    p.setPen(QColor(t["ink"]))
    p.setFont(font("Bahnschrift", 24))
    p.drawText(QRectF(x + 60, y - 6, 400, 34), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               f"by {brand.HUB}")
    p.end()
    image.save(path)


def divider(theme: str, path: str):
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QImage, QPainter, QPen
    t = THEMES[theme]
    w, h = 900, 24
    image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(t["line"]), 2))
    p.drawLine(0, h // 2, w // 2 - 46, h // 2)
    p.drawLine(w // 2 + 46, h // 2, w, h // 2)
    for n, colour in enumerate(CANDY):
        p.setPen(QPen(QColor(t["line"]), 1.2) if theme == "light" and n == 2 else Qt.PenStyle.NoPen)
        p.setBrush(QColor(colour))
        p.drawRoundedRect(QRectF(w // 2 - 34 + n * 24, 2, 20, 20), 6, 6)
    p.end()
    image.save(path)


def how(theme: str, path: str):
    """Sees the screen, reads it, decides, clicks: four tiles and dotted arrows."""
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QImage, QPainter, QPen
    from theme import ICON_FONT, ICONS
    t = THEMES[theme]
    w, h = 1200, 300
    ghost = mb.render(mb.tile_icon(brand.UNIT_COLOUR), 264)  # before the painter (see hero)
    image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    steps = [("view", "sees", "the game's picture,\n30 times a second"),
             ("notes", "reads", "the wave, Yen, Souls\nand every screen"),
             ("map", "decides", "your plan: where,\nwhat and when"),
             (None, "clicks", "like a player,\nmouse and keys")]
    tile = 132
    gap = (w - 4 * tile) / 4
    for n, (glyph, title, line) in enumerate(steps):
        cx = gap / 2 + n * (tile + gap) + tile / 2
        box = QRectF(cx - tile / 2, 26, tile, tile)
        if glyph is None:
            p.drawImage(box, ghost)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(mb.TILE))
            p.drawRoundedRect(box, 29, 29)
            p.setPen(QColor(mb.INK))
            p.setFont(font(ICON_FONT, 56))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, ICONS[glyph])
        p.setPen(QColor(t["ink"]))
        from PyQt6.QtGui import QFont
        p.setFont(font("Bahnschrift", 30, QFont.Weight.DemiBold))
        p.drawText(QRectF(cx - 140, 172, 280, 40), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, title)
        p.setPen(QColor(t["muted"]))
        p.setFont(font("Segoe UI", 19))
        p.drawText(QRectF(cx - 150, 214, 300, 60), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, line)
        if n < 3:  # a dotted arrow to the next tile
            x0, x1, y = cx + tile / 2 + 18, cx + tile / 2 + gap - 18, 26 + tile / 2
            pen = QPen(QColor(brand.UNIT_COLOUR), 4, Qt.PenStyle.DotLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x0, y), QPointF(x1 - 6, y))
            p.setPen(QPen(QColor(brand.UNIT_COLOUR), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.drawLine(QPointF(x1 - 14, y - 9), QPointF(x1 - 4, y))
            p.drawLine(QPointF(x1 - 14, y + 9), QPointF(x1 - 4, y))
    p.end()
    image.save(path)


def app_shot(frame_path: str, path: str):
    """The app as it looks mid-run: the look-only preview with sample numbers, a real furnace frame
    (names and level blurred) in the hole, then rounded and scaled for the page."""
    import builtins
    import cv2
    import numpy as np
    import privacy
    from PyQt6.QtCore import QPoint, QRectF, Qt
    from PyQt6.QtGui import QImage, QPainter, QPainterPath
    _open = builtins.open

    def guarded(file, mode="r", *a, **k):  # look only: nothing in the project is written
        if any(m in mode for m in "wax+") and os.path.abspath(os.fsdecode(file)).lower().startswith(ROOT.lower()) \
                and not os.path.abspath(os.fsdecode(file)).lower().startswith(OUT.lower()):
            return _open(os.devnull, mode, *a, **k)
        return _open(file, mode, *a, **k)
    builtins.open = guarded
    from macro.platform import windows
    windows.WindowsPlatform.launch_game = lambda self: (_ for _ in ()).throw(RuntimeError("art"))
    windows.WindowsPlatform._send = lambda self, *a: None
    import main as app_main
    from macro.sched.runner import Stats
    W = app_main.MainWindow
    W.register_hotkeys = W.first_attach = lambda self: None
    W.start_bot = lambda self, announce=True: None
    from PyQt6.QtTest import QTest
    w = W()
    w.show()
    QTest.qWait(1500)
    w.chain.set_plan(w.tasks.entries())
    w.chain.timer.stop()
    w.show_stats(Stats(state="Running", task="Soul Furnace Infinite Hard", run="7 of forever", wave="58",
                       yen="186,420", health="3", enemies="231", clock="27:41", wins=0, losses=6,
                       loot={"Candy Corn": 11585}, index=0, done=6))
    w.chain._shown = w.chain._target()
    w.chain._flow = 0.4
    w.chain.update()
    w.attach_state.setText("Roblox: attached")  # as during a real run
    w.start_button.setEnabled(False)
    w.pause_button.setEnabled(True)
    w.stop_button.setEnabled(True)
    import time
    w.run_started = time.time() - 3 * 3600 - 1060
    w.tick_clock()
    for line in ("wave 56, Yen 160,914, Souls 92, Candy Corn 1,815, enemies 214, health 3",
                 "Random Units done: Unbound Tomes next for blackheart, blade",
                 "DMG/RNG boosts on from wave 45: late game, every unit hits harder",
                 "tome on blackheartrevived: applied in 8.7 s",
                 "wave 57, Yen 172,301, Souls 40, Candy Corn 1,902, enemies 226, health 3",
                 "wave 58, Yen 186,420, Souls 61, Candy Corn 1,988, enemies 231, health 3"):
        w.log(line)
    QTest.qWait(600)
    shot = w.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
    game = cv2.imread(frame_path)
    with _open(frame_path, "rb") as f:
        game = cv2.imdecode(np.frombuffer(privacy.filter_file("data/maps/x.png", f.read()), np.uint8), cv2.IMREAD_COLOR)
    hole = w.hole
    game = cv2.resize(game, (hole.width(), hole.height()), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(game, cv2.COLOR_BGR2RGB)
    qgame = QImage(rgb.data, rgb.shape[1], rgb.shape[0], 3 * rgb.shape[1], QImage.Format.Format_RGB888).copy()
    p = QPainter(shot)
    p.drawImage(QPoint(hole.x(), hole.y()), qgame)
    p.end()
    # rounded corners and a size for the page
    scaled = shot.scaledToWidth(1600, Qt.TransformationMode.SmoothTransformation)
    out = QImage(scaled.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, out.width(), out.height()), 22, 22)
    p.setClipPath(clip)
    p.drawImage(0, 0, scaled)
    p.end()
    out.save(path)
    w.close()


def main():
    qt()
    os.makedirs(OUT, exist_ok=True)
    for theme in THEMES:
        hero(theme, os.path.join(OUT, f"hero_{theme}.png"))
        divider(theme, os.path.join(OUT, f"divider_{theme}.png"))
        how(theme, os.path.join(OUT, f"how_{theme}.png"))
    if len(sys.argv) > 1:
        app_shot(sys.argv[1], os.path.join(OUT, "app.png"))
    print("wrote", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
