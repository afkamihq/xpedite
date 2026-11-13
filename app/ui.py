"""The pieces every window is built from: cards, pills, numbers, key rows, toasts, and the
animated sub-window."""
from __future__ import annotations

import os
import time

import cv2
import yaml
from PyQt6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRect, QRectF, Qt,
                          QTimer, QVariantAnimation, pyqtSignal)
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from glass import paint_glass, paint_shadow, rounded
from theme import ACCENT, ACCENT_SOFT, BAD, ICON_FONT, ICONS, MUTED, QSS, RIM, STATE_COLORS, WARN

SOFT_WHITE = "#e8ecf4"


def load_yaml(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, yaml.YAMLError):
        return default


def save_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def label(text, name=None, wrap=True) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def backdrop_of(widget):
    """The Backdrop of the main window this widget belongs to, if there is one."""
    window = widget.window()
    return getattr(window, "backdrop", None) or getattr(getattr(window, "main", None), "backdrop", None)


def icon(name: str, size: int = 16, color: str = SOFT_WHITE) -> QLabel:
    """A glyph from Windows' icon font."""
    widget = QLabel(ICONS.get(name, name))
    # In the stylesheet: the app-wide one would otherwise override a font set in code.
    widget.setStyleSheet(f"font-family: '{ICON_FONT}'; font-size: {round(size * 1.35)}px; color: {color}; background: transparent;")
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


def badge(name: str, size: int = 34, color: str = SOFT_WHITE) -> QLabel:
    """An icon on a small glass bead, for headers and navigation. White by default: the
    glass carries the colour of what is behind it, so icons need none of their own."""
    widget = icon(name, round(size * 0.42), color)
    widget.setFixedSize(size, size)
    widget.setStyleSheet(f"font-family: '{ICON_FONT}'; font-size: {round(size * 0.42)}px; color: {color}; "
                         f"background: rgba(255, 255, 255, 0.075); {RIM} border-radius: {size // 2}px;")
    return widget


def round_pixmap(pixmap: QPixmap, radius: float) -> QPixmap:
    """A picture with rounded corners and a hairline rim, to sit in glass."""
    out = QPixmap(pixmap.size())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(0, 0, pixmap.width(), pixmap.height())
    painter.setClipPath(rounded(rect, radius))
    painter.drawPixmap(0, 0, pixmap)
    painter.setClipping(False)
    painter.setPen(QPen(QColor(255, 255, 255, 46), 1))
    painter.drawPath(rounded(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius - 0.5))
    painter.end()
    return out


def to_pixmap(image) -> QPixmap:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())


class Card(QFrame):
    """A titled pane of glass. Add widgets or layouts with .add().

    On the main window it is real glass, bending the ground behind it. Inside a sub-window
    (itself a sheet of glass) it is a plate set into that sheet instead: glass on glass
    muddies both."""
    RADIUS = 18
    INSET_RADIUS = 14

    def __init__(self, title: str = "", spacing: int = 8, margins: int = 14, icon_name: str | None = None,
                 extra: QWidget | None = None):
        super().__init__()
        self.setObjectName("card")
        self._previous = None
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(margins, margins - 2, margins, margins)
        self.box.setSpacing(spacing)
        self.title = None
        if title:
            row = QHBoxLayout()
            row.setSpacing(8)
            if icon_name:
                row.addWidget(icon(icon_name, 11, MUTED))
            self.title = label(title.upper(), "head", wrap=False)
            row.addWidget(self.title)
            row.addStretch(1)
            if extra is not None:
                row.addWidget(extra)
            self.box.addLayout(row)

    def add(self, item, stretch=0):
        if isinstance(item, QWidget):
            self.box.addWidget(item, stretch)
        else:
            self.box.addLayout(item, stretch)
        return item

    def inset(self) -> bool:
        return isinstance(self.window(), SubWindow)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        if self.inset():
            path = rounded(rect.adjusted(0.5, 0.5, -0.5, -0.5), self.INSET_RADIUS)
            painter.fillPath(path, QColor(0, 0, 0, 46))
            painter.fillPath(path, QColor(255, 255, 255, 7))
            painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
            painter.drawPath(path)
            # The plate's lower lip catches the light; its top sits in the sheet's shadow.
            painter.setPen(QPen(QColor(255, 255, 255, 24), 1))
            y = rect.bottom() - 1
            painter.drawLine(int(rect.left() + self.INSET_RADIUS), int(y), int(rect.right() - self.INSET_RADIUS), int(y))
            return
        backdrop = backdrop_of(self)
        pixmap = previous = None
        fade = 1.0
        if backdrop is not None:
            where = QRect(self.mapTo(self.window(), QPoint(0, 0)), self.size())
            pixmap = backdrop.pane(where, self.RADIUS)
            fade = backdrop.fade
            if fade < 1.0 and self._previous is not None and self._previous.size() == pixmap.size():
                previous = self._previous
            elif fade >= 1.0:
                self._previous = pixmap
        paint_glass(painter, rect, self.RADIUS, pixmap, previous, fade)


class Pill(QLabel):
    """A state badge whose colour fades from one state to the next."""

    def __init__(self, text="Idle"):
        super().__init__()
        self._word = text.upper()
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(26)
        self._color = QColor(STATE_COLORS["Idle"])
        self._apply(self._color)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(260)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._apply)

    def _apply(self, color):
        self._color = QColor(color)
        c = self._color
        self.setStyleSheet(f"background: rgba({c.red()}, {c.green()}, {c.blue()}, 34); color: {c.lighter(112).name()}; "
                           f"border: 1px solid rgba({c.red()}, {c.green()}, {c.blue()}, 70); border-radius: 8px; "
                           "font-family: 'Bahnschrift'; font-weight: 600; font-size: 12px; padding: 0 14px; letter-spacing: 2.4px;")
        self.setText(self._word)

    def set_state(self, text):
        self._word = text.upper()
        self._apply(self._color)
        target = QColor(STATE_COLORS.get(text, "#3a4052"))
        if target != self._color:
            self.anim.stop()
            self.anim.setStartValue(self._color)
            self.anim.setEndValue(target)
            self.anim.start()


class Meter(QWidget):
    """A small picture of a number: ticks for progress (waves), pips for a count (health)."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.value, self.total = 0, 0
        self.setFixedHeight(8)

    def set(self, value: int, total: int):
        if (value, total) != (self.value, self.total):
            self.value, self.total = value, total
            self.update()

    def paintEvent(self, event):
        if self.total <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.kind == "pips":
            for k in range(self.total):
                x = 4 + k * 12
                on = k < self.value
                diamond = QPainterPath()
                diamond.moveTo(x, 0.5)
                diamond.lineTo(x + 3.5, 4)
                diamond.lineTo(x, 7.5)
                diamond.lineTo(x - 3.5, 4)
                diamond.closeSubpath()
                painter.setBrush(QColor(255, 255, 255, 235 if on else 40))
                painter.drawPath(diamond)
            return
        count = min(self.total, 30)
        gap = 2.0
        width = (self.width() - 6 - gap * (count - 1)) / count
        lit = self.value * count / self.total
        for k in range(count):
            on = k < lit
            painter.setBrush(QColor(255, 255, 255, 225 if on else 34))
            painter.drawRoundedRect(QRectF(2 + k * (width + gap), 2, width, 4), 1, 1)


class Stat(QWidget):
    """A small title over a number, which flashes the accent when its value changes; with a
    meter under it, if asked for."""

    def __init__(self, title, icon_name=None, meter: str | None = None):
        super().__init__()
        frame = QFrame()
        frame.setObjectName("tile")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        box = QVBoxLayout(frame)
        box.setContentsMargins(4, 3, 4, 3)
        box.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(5)
        if icon_name:
            top.addWidget(icon(icon_name, 9, MUTED))
        top.addWidget(label(title.upper(), "head", wrap=False))
        top.addStretch(1)
        box.addLayout(top)
        self.value = label("-", "value", wrap=False)
        box.addWidget(self.value)
        self.meter = None
        if meter:  # "none" keeps the room, so a row of stats lines up with its metered neighbours
            self.meter = Meter(meter)
            box.addWidget(self.meter)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(700)
        self.anim.setStartValue(QColor("#9fb8ff"))
        self.anim.setEndValue(QColor("#ffffff"))
        self.anim.valueChanged.connect(lambda c: self.value.setStyleSheet(f"color: {QColor(c).name()};"))

    def set(self, text):
        if text != self.value.text():
            self.value.setText(text)
            if text not in ("-", ""):
                self.anim.stop()
                self.anim.start()


def fade_in(widget, duration=220, rise=14):
    """Fade a window in while it rises a little into place."""
    end = widget.pos()
    widget.move(end + QPoint(0, rise))
    widget.setWindowOpacity(0.0)
    widget.show()
    group = QParallelAnimationGroup(widget)
    fade = QPropertyAnimation(widget, b"windowOpacity", widget)
    fade.setDuration(duration)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    slide = QPropertyAnimation(widget, b"pos", widget)
    slide.setDuration(duration + 60)
    slide.setStartValue(end + QPoint(0, rise))
    slide.setEndValue(end)
    slide.setEasingCurve(QEasingCurve.Type.OutCubic)
    group.addAnimation(fade)
    group.addAnimation(slide)
    group.start()
    widget._entrance = group


def fade_out(widget, then=None, duration=150):
    fade = QPropertyAnimation(widget, b"windowOpacity", widget)
    fade.setDuration(duration)
    fade.setStartValue(widget.windowOpacity())
    fade.setEndValue(0.0)
    fade.setEasingCurve(QEasingCurve.Type.InCubic)

    def done():
        widget.hide()
        widget.setWindowOpacity(1.0)
        if then:
            then()
    fade.finished.connect(done)
    fade.start()
    widget._exit = fade


class SubWindow(QWidget):
    """A frameless window owned by the main one: own title bar (drag it), kept above the main
    window, minimized with it, animated in and out. Esc closes it."""
    closed = pyqtSignal()
    MARGIN = 26  # room around the sheet for its shadow
    RADIUS = 24

    def __init__(self, main, title: str, subtitle: str, size: tuple[int, int], icon_name: str = "main"):
        super().__init__(main, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.main = main
        self.setObjectName("sub")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(QSS)
        m = self.MARGIN
        self.resize(size[0] + 2 * m, size[1] + 2 * m)
        self.fit = False
        self._drag = None
        self._previous = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(m + 1, m + 2, m + 1, m + 1)
        outer.setSpacing(0)
        bar = QWidget()
        bar.setFixedHeight(64)
        bar_box = QHBoxLayout(bar)
        bar_box.setContentsMargins(18, 0, 12, 0)
        bar_box.setSpacing(12)
        bar_box.addWidget(badge(icon_name, 38))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label(title.upper(), "head"))
        titles.addWidget(label(subtitle, "subtitle", wrap=False))
        bar_box.addLayout(titles)
        bar_box.addStretch(1)
        self.bar_box = bar_box
        close = QPushButton(ICONS["close"])
        close.setObjectName("close")
        close.setToolTip("Close (Esc)")
        close.clicked.connect(self.close_animated)
        bar_box.addWidget(close)
        outer.addWidget(bar)
        self.body = QWidget()
        self.body_box = QVBoxLayout(self.body)
        self.body_box.setContentsMargins(18, 6, 18, 18)
        self.body_box.setSpacing(12)
        outer.addWidget(self.body, 1)

    def sheet_rect(self) -> QRect:
        m = self.MARGIN
        return self.rect().adjusted(m, m, -m, -m)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        sheet = self.sheet_rect()
        rect = QRectF(sheet)
        paint_shadow(painter, rect, self.RADIUS, depth=1.6)
        backdrop = backdrop_of(self)
        pixmap = previous = None
        fade = 1.0
        if backdrop is not None:
            moving = time.perf_counter() - getattr(self, "_moved_at", 0.0) < 0.15
            last = getattr(self, "_last_pane", None)
            if moving and last is not None and last.size() == sheet.size() * last.devicePixelRatio():
                # Dragged or sliding in: the glass bent at the last spot, re-bent where it stops
                # (3.3 ms a frame while moving, 13 Nov 2026).
                pixmap = last
            else:
                where = QRect(self.mapToGlobal(sheet.topLeft()) - self.main.mapToGlobal(QPoint(0, 0)), sheet.size())
                pixmap = backdrop.pane(where, self.RADIUS, sheet=True, band=30.0, strength=16.0)
                self._last_pane = pixmap
            fade = backdrop.fade
            if fade < 1.0 and self._previous is not None and self._previous.size() == pixmap.size():
                previous = self._previous
            elif fade >= 1.0:
                self._previous = pixmap
        paint_glass(painter, rect, self.RADIUS, pixmap, previous, fade, strength=1.15)
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        y = sheet.top() + 66
        painter.drawLine(sheet.left() + 20, y, sheet.right() - 20, y)

    def moveEvent(self, event):
        self._moved_at = time.perf_counter()
        self.update()
        if not hasattr(self, "_settle"):
            self._settle = QTimer(self)
            self._settle.setSingleShot(True)
            self._settle.timeout.connect(self.update)  # the glass bent again where it stopped
        self._settle.start(180)
        super().moveEvent(event)

    def open(self):
        if self.isVisible():
            self.raise_()
            self.activateWindow()
            return
        self.on_open()
        if hasattr(self.main, "glass_behind_sheets"):
            self.main.glass_behind_sheets()
        if self.fit:  # as tall as the content, so nothing sits empty
            self.resize(self.width(), self.sizeHint().height())
        centre = self.main.geometry().center()
        self.move(centre.x() - self.width() // 2, max(10, centre.y() - self.height() // 2))
        fade_in(self)
        self.raise_()
        self.activateWindow()

    def on_open(self):
        """Refresh what's shown, each time the window opens."""

    def close_animated(self):
        fade_out(self, self.closed.emit)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_animated()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < self.MARGIN + 64:
            self._drag = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None


class Toast(QFrame):
    """A short message that slides in at the corner of an area and leaves by itself."""

    def __init__(self, parent, text, kind="info", area: QRect | None = None):
        super().__init__(parent)
        glyph, color = {"good": ("check", "#ffffff"), "warn": ("warn", WARN), "bad": ("warn", BAD)}.get(
            kind, ("info", "#ffffff"))
        self.setStyleSheet("QLabel { background: transparent; border: 0; }")
        box = QHBoxLayout(self)
        box.setContentsMargins(14, 11, 18, 13)
        box.setSpacing(11)
        box.addWidget(icon(glyph, 10, color), 0, Qt.AlignmentFlag.AlignTop)
        text_label = label(text)
        text_label.setStyleSheet("font-size: 13px; color: #eef1f6;")
        text_label.setMaximumWidth(340)
        box.addWidget(text_label)
        self.born = time.perf_counter()
        self.life = 3.2
        self.adjustSize()
        area = area or parent.rect()
        end = QPoint(area.right() - self.width() - 12, area.bottom() - self.height() - 12)
        self.move(end + QPoint(24, 0))
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.0)
        self.setGraphicsEffect(effect)
        self.show()
        self.raise_()
        self.group = QParallelAnimationGroup(self)
        slide = QPropertyAnimation(self, b"pos", self)
        slide.setDuration(260)
        slide.setStartValue(self.pos())
        slide.setEndValue(end)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(220)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        self.group.addAnimation(slide)
        self.group.addAnimation(fade)
        self.group.start()
        QTimer.singleShot(int(self.life * 1000), self.leave)
        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self.update)
        self.ticker.start(50)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 10.0
        painter.setClipPath(rounded(rect, radius))
        painter.fillRect(rect, QColor(13, 15, 20, 228))
        # How long it has left: a hairline along the bottom that runs out.
        left = max(0.0, 1.0 - (time.perf_counter() - self.born) / self.life)
        painter.fillRect(QRectF(rect.left(), rect.bottom() - 2, rect.width() * left, 2), QColor(255, 255, 255, 70))
        painter.setClipping(False)
        paint_glass(painter, rect, radius, None, strength=0.9)

    def leave(self):
        fade = QPropertyAnimation(self.graphicsEffect(), b"opacity", self)
        fade.setDuration(260)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.finished.connect(self.deleteLater)
        fade.start()
        self._leaving = fade


class KeyRow(QPushButton):
    """A hotkey: its key and what it does. Clicking it does the same as pressing it."""

    def __init__(self, key, text):
        super().__init__()
        self.setObjectName("hotkey")
        box = QHBoxLayout(self)
        box.setContentsMargins(4, 2, 4, 2)
        box.setSpacing(10)
        chip = QLabel(key)
        chip.setObjectName("key")
        chip.setFixedWidth(38)
        chip.setFixedHeight(24)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(chip)
        self.text_label = QLabel(text)
        self.text_label.setStyleSheet("background: transparent; font-size: 13px;")
        box.addWidget(self.text_label, 1)
        self.setFixedHeight(34)
        for child in (chip, self.text_label):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


class NavButton(QPushButton):
    """A window to open: icon badge, title, what it's for, and a chevron."""

    def __init__(self, icon_name, title, subtitle, color=ACCENT):
        super().__init__()
        self.setObjectName("nav")
        self.setFixedHeight(58)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        box = QHBoxLayout(self)
        box.setContentsMargins(10, 0, 12, 0)
        box.setSpacing(11)
        box.addWidget(badge(icon_name, 34))
        words = QVBoxLayout()
        words.setSpacing(0)
        words.addStretch(1)
        words.addWidget(label(title, "navtitle", wrap=False))
        words.addWidget(label(subtitle, "navsub", wrap=False))
        words.addStretch(1)
        box.addLayout(words, 1)
        arrow = icon("chevron", 9, "rgba(235, 240, 250, 0.45)")
        box.addWidget(arrow)
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


__all__ = ["ACCENT_SOFT"]


# ------------------------------------------------------------------ settings rows (12 Nov 2026)
# The user: no default checkboxes, far less text, easy to scan. A setting is one row: a short
# label left, its control right, hairlines between rows.
class Toggle(QPushButton):
    """A pill switch, near-white when on (colour only for state). Checkable: isChecked(),
    setChecked(), toggled(bool), like the checkbox it replaces."""
    W, H = 40, 22

    def __init__(self, checked: bool = False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._slide)

    def _slide(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get(self):
        return self._pos

    def _set(self, value):
        self._pos = value
        self.update()

    from PyQt6.QtCore import pyqtProperty as _prop
    knob = _prop(float, _get, _set)

    def setChecked(self, on: bool):
        super().setChecked(on)
        self._pos = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._pos
        track = QColor(255, 255, 255, int(26 + (235 - 26) * t))
        p.setPen(QPen(QColor(255, 255, 255, 60 if t < 0.5 else 0), 1))
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.W - 1, self.H - 1), self.H / 2, self.H / 2)
        d = self.H - 6
        x = 3 + t * (self.W - 6 - d)
        knob = QColor(17, 20, 27) if t >= 0.5 else QColor(214, 220, 232)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(knob)
        p.drawEllipse(QRectF(x, 3, d, d))
        p.end()


class SettingRow(QWidget):
    """One setting: a short label (and an optional dim note under it), the control on the right."""

    def __init__(self, title: str, control: QWidget | None = None, note: str = ""):
        super().__init__()
        box = QHBoxLayout(self)
        box.setContentsMargins(2, 5, 2, 5)
        box.setSpacing(12)
        words = QVBoxLayout()
        words.setSpacing(0)
        words.addWidget(label(title, "row", wrap=False))
        if note:
            words.addWidget(label(note, "dim", wrap=False))
        box.addLayout(words, 1)
        if control is not None:
            box.addWidget(control, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.control = control


class ToggleRow(SettingRow):
    """A SettingRow with a Toggle, standing in for a QCheckBox (isChecked/setChecked/toggled)."""

    def __init__(self, title: str, checked: bool = False, note: str = ""):
        self.switch = Toggle(checked)
        super().__init__(title, self.switch, note)
        self.toggled = self.switch.toggled

    def isChecked(self) -> bool:
        return self.switch.isChecked()

    def setChecked(self, on: bool):
        self.switch.setChecked(on)

    def mouseReleaseEvent(self, event):  # the whole row toggles, not only the pill
        self.switch.toggle()


def hairline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background: rgba(255, 255, 255, 0.07); border: none;")
    return line


def rows(card: "Card", *widgets):
    """Rows into a card, a hairline between each (kept on the row, so show_row hides both)."""
    for n, widget in enumerate(widgets):
        if n:
            widget.hairline = card.add(hairline())
        card.add(widget)


def show_row(widget, on: bool):
    widget.setVisible(on)
    line = getattr(widget, "hairline", None)
    if line is not None:
        line.setVisible(on)


def number(low, high, step=1, suffix="", special="", decimals=False, width=96):
    """A number box without arrows (type, or scroll over it), right-aligned."""
    from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox
    box = QDoubleSpinBox() if decimals else QSpinBox()
    box.setRange(low, high)
    box.setSingleStep(step)
    box.setSuffix(suffix)
    if special:
        box.setSpecialValueText(special)
    # Arrows hidden by the theme (::up-button width 0): setButtonSymbols(NoButtons) under a
    # stylesheet collapses the text to 1 px.
    box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    box.setFixedWidth(width)
    return box


def secret_field(placeholder: str):
    """A password-style line edit with an eye button that shows it. Returns (widget, edit)."""
    from PyQt6.QtWidgets import QLineEdit
    holder = QWidget()
    box = QHBoxLayout(holder)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(6)
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    eye = QPushButton(ICONS["view"])
    eye.setCheckable(True)
    eye.setFixedSize(30, 30)
    eye.setCursor(Qt.CursorShape.PointingHandCursor)
    eye.setStyleSheet(f"QPushButton {{ font-family: '{ICON_FONT}'; font-size: 14px; color: {MUTED};"
                      " background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);"
                      " border-radius: 9px; padding: 0; }"
                      " QPushButton:checked { color: #ffffff; background: rgba(255,255,255,0.14); }")
    eye.toggled.connect(lambda on: edit.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
    box.addWidget(edit, 1)
    box.addWidget(eye)
    return holder, edit
