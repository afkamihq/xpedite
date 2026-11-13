"""Liquid glass: the one material every panel, button sheet and sub-window is made of.

What makes it read as glass rather than a grey box (after Apple's Liquid Glass and the web
recreations of it):
- The ground is the game itself. Its picture, spread across the whole window and blurred,
  lights the app, so the app takes its colour from what is playing and needs almost none
  of its own.
- Lensing. A pane is thick in the middle and curves away at its rim, so near the edge it
  bends what is behind it: the backdrop is resampled through a displacement field that is
  flat in the middle and strongest at the rim, with the colour channels bent a little
  differently (the faint fringe real glass has).
- Frost, a darker smoke tint so text stays readable over any game, and a specular rim:
  light from the top left catches the upper edge hard and the far corner softly.

Everything is computed on a picture a quarter or half the window's size and only when
the backdrop changes (every few seconds) or a pane moves, so the macro's frame budget is
left alone.
"""
from __future__ import annotations

import math
import os
import time

import cv2
import numpy as np
from PyQt6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FALLBACK = os.path.join(ROOT, "app", "assets", "ground.jpg")  # the lobby, small: glass only shows it blurred

GROUND_LIFT, GROUND_GAIN = 0.035, 0.24   # the window's own ground: dark, the game's colours just showing
GLASS_LIFT, GLASS_GAIN = 0.075, 0.30     # a pane: a step brighter than the ground, like smoked glass
SHEET_LIFT, SHEET_GAIN = 0.055, 0.22      # a sub-window over the game: same smoke, a touch darker
FADE_MS, FADE_FRAME_MS = 800, 90  # a cross-fade of light: 0.8 s at 11 frames a second
SAME_LIGHT = 7.0  # mean difference of a 32x18 thumbnail below which the game's light is unchanged
GLASS_SATURATION = 1.35                  # glass gathers colour (Apple's backdrop saturate)
GROUND_SATURATION = 0.8


def _to_pixmap(bgr: np.ndarray) -> QPixmap:
    bgr = np.ascontiguousarray(bgr)
    h, w = bgr.shape[:2]
    return QPixmap.fromImage(QImage(bgr.data, w, h, 3 * w, QImage.Format.Format_BGR888).copy())


def qimage_to_bgr(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h = image.width(), image.height()
    data = np.frombuffer(image.constBits().asstring(image.bytesPerLine() * h), np.uint8)
    rgb = data.reshape(h, image.bytesPerLine())[:, :w * 3].reshape(h, w, 3)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _tone(bgr: np.ndarray, lift: float, gain: float, saturation: float) -> np.ndarray:
    """Compress a picture into a dark band (lift + gain * value) and set its colourfulness."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * saturation, 0, 255)
    hsv[..., 2] = 255.0 * (lift + gain * hsv[..., 2] / 255.0)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def _cover(image: np.ndarray, width: int, height: int, zoom: float = 1.0) -> np.ndarray:
    """Scale to fill width x height, cropping the middle."""
    h, w = image.shape[:2]
    scale = max(width / w, height / h) * zoom
    resized = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    y = (resized.shape[0] - height) // 2
    x = (resized.shape[1] - width) // 2
    return resized[y:y + height, x:x + width]


def rounded_sdf(width: int, height: int, radius: float, hole: tuple | None = None) -> np.ndarray:
    """Distance inside a rounded rectangle to its nearest edge (negative outside). With a
    hole [x, y, w, h], the shape is a frame, and its inner edge counts too."""
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    xs += 0.5
    ys += 0.5
    half_w, half_h = width / 2.0, height / 2.0
    qx = np.abs(xs - half_w) - (half_w - radius)
    qy = np.abs(ys - half_h) - (half_h - radius)
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - radius
    distance = -outside
    if hole is not None:
        hx, hy, hw, hh = hole
        dx = np.maximum(hx - xs, xs - (hx + hw))
        dy = np.maximum(hy - ys, ys - (hy + hh))
        from_hole = np.where((dx > 0) | (dy > 0), np.hypot(np.maximum(dx, 0), np.maximum(dy, 0)), np.maximum(dx, dy))
        distance = np.minimum(distance, from_hole)
    return distance


class LensMap:
    """The displacement field of one pane shape, built once per size: where each pixel of
    the pane looks into the backdrop, per colour channel."""

    def __init__(self, width: int, height: int, radius: float, band: float, strength: float,
                 hole: tuple | None = None, pad: int = 0):
        distance = rounded_sdf(width, height, radius, hole)
        gy, gx = np.gradient(distance)
        norm = np.hypot(gx, gy) + 1e-6
        gx, gy = gx / norm, gy / norm  # points into the glass, away from the nearest edge
        inside = np.clip(distance / band, 0.0, 1.0)
        bend = strength * (1.0 - inside) ** 2.2  # flat in the middle, strongest at the rim
        ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
        # The whole pane magnifies a little, as a thick lens does.
        cx, cy = width / 2.0, height / 2.0
        mx = cx + (xs - cx) * 0.988
        my = cy + (ys - cy) * 0.988
        self.maps = []
        for spread in (1.12, 1.0, 0.88):  # B, G, R: the fringe
            self.maps.append(((mx + gx * bend * spread + pad).astype(np.float32),
                              (my + gy * bend * spread + pad).astype(np.float32)))
        self.pad = pad

    def apply(self, source: np.ndarray) -> np.ndarray:
        """source is the backdrop under the pane, `pad` pixels bigger on every side."""
        channels = []
        for index, (map_x, map_y) in enumerate(self.maps):
            channels.append(cv2.remap(source[..., index], map_x, map_y, cv2.INTER_LINEAR,
                                      borderMode=cv2.BORDER_REFLECT))
        return cv2.merge(channels)


class Backdrop(QObject):
    """The scene behind the glass, for one window size. feed() it the game's picture now and
    then; panes ask it for what they show with pane()."""
    changed = pyqtSignal()
    WORK = 2  # glass is computed at half size: frost hides the difference

    def __init__(self, width: int, height: int, hole: QRect):
        super().__init__()
        self.width, self.height = width, height
        self.hole = QRect(hole)
        self.version = 0
        self.ground = None        # QPixmap, the window's own ground
        self.previous_ground = None
        self.glass = None         # np, half size: what panes on the window see
        self.sheet = None         # np, half size: what sub-windows see (game and window behind)
        self.fade = 1.0
        self._lens_maps = {}
        self._panes = {}
        self._game = None
        self._shot = None
        # Film grain, so the dark ground never bands: added and taken away as two unsigned layers.
        noise = np.random.default_rng(7).normal(0, 2.2, (height, width)).round()
        self._grain = tuple(cv2.merge([np.clip(sign * noise, 0, 255).astype(np.uint8)] * 3) for sign in (1, -1))
        # The change of light is a slow cross-fade at a low frame rate: every frame of it
        # repaints the whole window, and the CPU belongs to the macro.
        self._thumb = None
        self._fade_step = QTimer(self)
        self._fade_step.setInterval(FADE_FRAME_MS)
        self._fade_step.timeout.connect(self._fading)
        fallback = cv2.imread(FALLBACK)
        self.feed(fallback if fallback is not None else np.full((810, 1440, 3), 40, np.uint8), animate=False)

    # ----------------------------------------------------------------------------- scene
    def feed(self, game: np.ndarray, animate: bool = True):
        """A new picture of the game. Dark frames (loading, a black screen) are ignored, so
        the app doesn't go dark with them."""
        if game is None or game.size == 0 or float(game.mean()) < 12:
            return
        thumb = cv2.resize(game, (32, 18), interpolation=cv2.INTER_AREA).astype(np.int16)
        if self._thumb is not None and float(np.abs(thumb - self._thumb).mean()) < SAME_LIGHT:
            return  # the light hasn't changed enough to be worth a repaint
        self._thumb = thumb
        self._game = game
        w4, h4 = self.width // 4, self.height // 4
        ambient = _cover(game, w4, h4, zoom=1.12)
        # The ground keeps the game's shapes, softly; glass blurs them further, so the
        # difference between the two is what reads as frost, and the rim has shapes to bend.
        ambient = cv2.GaussianBlur(ambient, (0, 0), 3.2)
        # The game itself sits in the hole: sub-windows over it see it, softened.
        hx, hy = self.hole.x() // 4, self.hole.y() // 4
        hw, hh = max(1, self.hole.width() // 4), max(1, self.hole.height() // 4)
        scene = ambient.copy()
        scene[hy:hy + hh, hx:hx + hw] = cv2.resize(game, (hw, hh), interpolation=cv2.INTER_AREA)[:scene.shape[0] - hy, :scene.shape[1] - hx]

        # Toning is per pixel, so it is done small and then scaled up: the same picture at a
        # sixteenth of the work.
        ground = _tone(ambient, GROUND_LIFT, GROUND_GAIN, GROUND_SATURATION).astype(np.float32)
        ground = np.clip(ground * self._vignette(w4, h4), 0, 255).astype(np.uint8)
        ground = cv2.resize(ground, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
        grain_up, grain_down = self._grain
        ground = cv2.subtract(cv2.add(ground, grain_up), grain_down)
        self.previous_ground = self.ground
        self.ground = _to_pixmap(ground)

        half = (self.width // self.WORK, self.height // self.WORK)
        glass = _tone(cv2.GaussianBlur(ambient, (0, 0), 6.5), GLASS_LIFT, GLASS_GAIN, GLASS_SATURATION)
        self.glass = cv2.resize(glass, half, interpolation=cv2.INTER_LINEAR)
        if self._shot is not None:
            self.sheet = self._sheet_from_shot()
        else:
            sheet = _tone(cv2.GaussianBlur(scene, (0, 0), 2.2), SHEET_LIFT, SHEET_GAIN, GLASS_SATURATION)
            self.sheet = cv2.resize(sheet, half, interpolation=cv2.INTER_LINEAR)
        self.version += 1
        self._panes = {k: v for k, v in self._panes.items() if k[-1] == self.version - 1}
        if animate and self.previous_ground is not None:
            self.fade = 0.0
            self._fade_started = time.perf_counter()
            self._fade_step.start()
            self.changed.emit()
        else:
            self.fade = 1.0
            self.changed.emit()

    def under_sheets(self, window_picture: QImage):
        """What sub-windows see: the window as it looks now, with the game in its hole.
        Called as one opens, so its glass bends the panels behind it. The picture may come at
        the working size already (half); the smoke and blur are done off the Qt thread, so the
        sheet opens at once and its glass catches up a moment later (13 Nov 2026: ~40 ms of
        every open was this)."""
        picture = qimage_to_bgr(window_picture)
        half = (self.width // self.WORK, self.height // self.WORK)
        if picture.shape[:2] != (half[1], half[0]):
            picture = cv2.resize(picture, half, interpolation=cv2.INTER_AREA)
        self._shot = picture

        def work():
            self.sheet = self._sheet_from_shot()
            self.version += 1
            self.changed.emit()  # queued to the Qt thread
        import threading
        threading.Thread(target=work, daemon=True, name="sheet-glass").start()

    def _sheet_from_shot(self) -> np.ndarray:
        """The window as last photographed, with the newest game picture in its hole: the
        window's own panels already are smoked glass, so they are only blurred, while the
        bright game gets the full smoke."""
        k = self.WORK
        shot = self._shot.copy()
        h = self.hole
        x, y, w, hh = h.x() // k, h.y() // k, max(1, h.width() // k), max(1, h.height() // k)
        if self._game is not None:
            game = _tone(cv2.resize(self._game, (w, hh), interpolation=cv2.INTER_AREA), SHEET_LIFT, SHEET_GAIN,
                         GLASS_SATURATION)
            shot[y:y + hh, x:x + w] = game[:shot.shape[0] - y, :shot.shape[1] - x]
        return cv2.GaussianBlur(shot, (0, 0), 6)

    def _vignette(self, width: int, height: int) -> np.ndarray:
        """Darker towards the window's edges, so the eye settles on the game."""
        if getattr(self, "_vig", None) is None or self._vig.shape[:2] != (height, width):
            ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
            dx = (xs - width / 2) / (width / 2)
            dy = (ys - height / 2) / (height / 2)
            self._vig = (1.0 - 0.32 * np.clip(dx * dx * 0.6 + dy * dy * 0.9, 0, 1) ** 1.3)[..., None]
        return self._vig

    def _fading(self):
        t = min(1.0, (time.perf_counter() - self._fade_started) * 1000.0 / FADE_MS)
        self.fade = 0.5 - 0.5 * math.cos(math.pi * t)  # ease in and out
        if t >= 1.0:
            self.fade = 1.0
            self._fade_step.stop()
        self.changed.emit()

    # ------------------------------------------------------------------------------ panes
    def pane(self, rect: QRect, radius: float, sheet: bool = False, lens: bool = True,
             hole: tuple | None = None, band: float = 18.0, strength: float = 9.0) -> QPixmap:
        """What a pane at rect (window coordinates) shows: the backdrop bent through it."""
        key = (rect.x(), rect.y(), rect.width(), rect.height(), radius, sheet, lens, hole, self.version)
        cached = self._panes.get(key)
        if cached is not None:
            return cached
        source = self.sheet if sheet else self.glass
        k = self.WORK
        w, h = max(2, rect.width() // k), max(2, rect.height() // k)
        pad = round(strength / k) + 2 if lens else 0
        x0, y0 = rect.x() // k - pad, rect.y() // k - pad
        crop = _crop(source, x0, y0, w + 2 * pad, h + 2 * pad)
        if lens:
            shape = (w, h, radius / k, band / k, strength / k,
                     tuple(round(v / k) for v in hole) if hole else None, pad)
            lens_map = self._lens_maps.get(shape)
            if lens_map is None:
                lens_map = self._lens_maps[shape] = LensMap(*shape[:5], hole=shape[5], pad=pad)
            out = lens_map.apply(crop)
        else:
            out = crop
        pixmap = _to_pixmap(cv2.resize(out, (rect.width(), rect.height()), interpolation=cv2.INTER_LINEAR))
        if len(self._panes) > 120:
            self._panes.clear()
        self._panes[key] = pixmap
        return pixmap


def _crop(image: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """A crop that may run off the picture: the edge is mirrored."""
    H, W = image.shape[:2]
    left, top = max(0, -x), max(0, -y)
    right, bottom = max(0, x + w - W), max(0, y + h - H)
    if left or top or right or bottom:
        image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_REFLECT)
        x += left
        y += top
    return image[y:y + h, x:x + w]


# ------------------------------------------------------------------------------- painting
def rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


_shadow_cache: dict = {}


def paint_shadow(painter: QPainter, rect: QRectF, radius: float, depth: float = 1.0):
    """A soft contact shadow under a pane: a few widening, fading outlines. Drawn once per size
    into a picture and reused: redrawn every frame it was 2.7 ms of a sub-window's 10 ms paint
    (13 Nov 2026)."""
    device = painter.device()
    dpr = device.devicePixelRatioF() if device is not None else 1.0
    margin = math.ceil(26 * depth) + 2
    w, h = rect.width(), rect.height()
    key = (round(w), round(h), round(radius, 1), round(depth, 2), round(dpr, 2))
    pixmap = _shadow_cache.get(key)
    if pixmap is None:
        pixmap = QPixmap(math.ceil((w + 2 * margin) * dpr), math.ceil((h + 2 * margin) * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        local = QRectF(margin, margin, w, h)
        for step in range(10, 0, -1):
            grow = step * 2.0 * depth
            alpha = int(9 * depth * (1 - step / 11) ** 1.6) + 1
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(local.adjusted(-grow, -grow + 4 * depth, grow, grow + 6 * depth),
                              radius + grow, radius + grow)
        p.end()
        if len(_shadow_cache) > 48:
            _shadow_cache.clear()
        _shadow_cache[key] = pixmap
    painter.drawPixmap(QPointF(rect.left() - margin, rect.top() - margin), pixmap)


_overlay_cache: dict = {}


def _glass_overlay(w: float, h: float, radius: float, tint: QColor | None, strength: float, hover: float,
                   dpr: float) -> QPixmap:
    """Everything of a pane that isn't the backdrop, as one picture for its size and look."""
    key = (round(w), round(h), round(radius, 1), tint.rgba() if tint is not None else None,
           round(strength, 2), round(hover, 2), round(dpr, 2))
    cached = _overlay_cache.get(key)
    if cached is not None:
        return cached
    pixmap = QPixmap(math.ceil(w * dpr) + 1, math.ceil(h * dpr) + 1)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(0, 0, w, h)
    path = rounded(rect, radius)
    painter.setClipPath(path)
    # The body: a breath of white, so even a black backdrop reads as a surface.
    painter.fillPath(path, QColor(255, 255, 255, int(9 + 10 * hover)))
    if tint is not None:
        painter.fillPath(path, tint)
    # Sheen: the light the upper surface catches, gone by a third of the way down.
    sheen = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + min(90.0, rect.height() * 0.45)))
    sheen.setColorAt(0.0, QColor(255, 255, 255, int(20 * strength)))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillPath(path, QBrush(sheen))
    # A caustic: the brightest spot where the light enters, top left.
    glow = QRadialGradient(QPointF(rect.left() + rect.width() * 0.12, rect.top()), max(60.0, rect.width() * 0.55))
    glow.setColorAt(0.0, QColor(255, 255, 255, int(16 * strength)))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillPath(path, QBrush(glow))
    painter.setClipping(False)
    # Depth: the lower inner edge is in the pane's own shadow.
    inner = rounded(rect.adjusted(1.5, 1.5, -1.5, -1.5), max(0.0, radius - 1.5))
    shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    shade.setColorAt(0.0, QColor(0, 0, 0, 0))
    shade.setColorAt(0.75, QColor(0, 0, 0, 0))
    shade.setColorAt(1.0, QColor(0, 0, 0, int(70 * strength)))
    painter.setPen(QPen(QBrush(shade), 2.0))
    painter.drawPath(inner)
    # The specular rim: hard where the light hits (top left), a soft bounce opposite.
    rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
    rim.setColorAt(0.0, QColor(255, 255, 255, int(170 * strength)))
    rim.setColorAt(0.22, QColor(255, 255, 255, int(48 * strength)))
    rim.setColorAt(0.55, QColor(255, 255, 255, int(14 * strength)))
    rim.setColorAt(0.85, QColor(255, 255, 255, int(34 * strength)))
    rim.setColorAt(1.0, QColor(255, 255, 255, int(90 * strength)))
    painter.setPen(QPen(QBrush(rim), 1.1))
    painter.drawPath(rounded(rect.adjusted(0.55, 0.55, -0.55, -0.55), radius - 0.55))
    painter.end()
    if len(_overlay_cache) > 256:
        _overlay_cache.clear()
    _overlay_cache[key] = pixmap
    return pixmap


def paint_glass(painter: QPainter, rect: QRectF, radius: float, backdrop_pixmap: QPixmap | None,
                previous: QPixmap | None = None, fade: float = 1.0, tint: QColor | None = None,
                strength: float = 1.0, hover: float = 0.0):
    """Backdrop, then body, tint, sheen and specular rim of one pane, in the painter's
    coordinates. The body is drawn once per size and look (_glass_overlay): drawn every frame
    it was ~2 ms of each sub-window paint (13 Nov 2026)."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if backdrop_pixmap is not None:
        painter.setClipPath(rounded(rect, radius))
        if previous is not None and fade < 1.0:
            painter.drawPixmap(rect.topLeft(), previous)
            painter.setOpacity(fade)
        painter.drawPixmap(rect.topLeft(), backdrop_pixmap)
        painter.setOpacity(1.0)
        painter.setClipping(False)
    device = painter.device()
    dpr = device.devicePixelRatioF() if device is not None else 1.0
    painter.drawPixmap(rect.topLeft(), _glass_overlay(rect.width(), rect.height(), radius, tint, strength,
                                                      round(hover * 20) / 20, dpr))
    painter.restore()
