"""The plan, drawn as a route: one waypoint per task in the queue, strung along a line that
winds across the card the way a route does on a map, coming in from the left and running
on off the right edge.

- Every game mode has its own emblem, an engraved seal of a shape (a circle for Story, a
  hexagon for Raid, a diamond for Challenge ...), so a plan reads at a glance without colour.
- Real chain runs between them: links laid along the route, face-on and edge-on in turn
  so they interlock. Travelled links are polished, links ahead are dim, and the stretch into
  the task being played carries a slow surge of light from link to link.
- That waypoint wears a dial whose ticks light up as it gets done: whole runs, plus the
  waves of the match in progress. Nothing breathes or pulses.

It only animates during a run, at a modest frame rate, and only repaints itself. Clicking
it opens Tasks.
"""
from __future__ import annotations

import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from theme import WARN

FPS = 30
R = 15.0             # emblem radius
MIN_GAP = 112.0      # waypoint to waypoint, at the tightest
MAX_GAP = 200.0
LINK_LENGTH = 13.0   # a chain link, end to end
LINK_PITCH = 9.6     # link to link: less than a link's length, so they overlap and interlock
EDGE = 100.0         # room at each end: the road comes in and runs on, and end names fit
WHITE = QColor(255, 255, 255)
INK = QColor("#0c0e13")
TITLE_FONT = "Bahnschrift"

SHAPES = {
    "story": "circle", "sandbox": "square", "raid": "hexagon", "challenge": "diamond", "boss_rush": "triangle",
    "expedition": "pentagon", "tower": "tower", "soul_furnace": "octagon", "furnace": "octagon", "rift": "star", "ancient_one": "star",
    "infinite": "circle", "mastery": "hexagon",
}
MODE_NAMES = {"story": "Story", "sandbox": "Sandbox", "raid": "Raid", "challenge": "Challenge", "boss_rush": "Boss Rush",
              "expedition": "Expedition", "tower": "Tower", "soul_furnace": "Soul Furnace", "furnace": "Soul Furnace", "rift": "Demonic Rift"}


def _a(color: QColor, alpha: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def shape_path(kind: str, centre: QPointF, r: float) -> QPainterPath:
    path = QPainterPath()
    x, y = centre.x(), centre.y()
    if kind == "square":
        path.addRoundedRect(QRectF(x - r * 0.84, y - r * 0.84, r * 1.68, r * 1.68), r * 0.3, r * 0.3)
    elif kind == "tower":
        path.addRoundedRect(QRectF(x - r * 0.62, y - r, r * 1.24, r * 2.0), r * 0.22, r * 0.22)
    elif kind == "star":
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = r * (1.12 if i % 2 == 0 else 0.52)
            point = QPointF(x + radius * math.cos(angle), y + radius * math.sin(angle))
            path.moveTo(point) if i == 0 else path.lineTo(point)
        path.closeSubpath()
    elif kind in ("hexagon", "pentagon", "octagon", "triangle", "diamond"):
        sides = {"hexagon": 6, "pentagon": 5, "octagon": 8, "triangle": 3, "diamond": 4}[kind]
        start = {"hexagon": math.pi / 6, "octagon": math.pi / 8}.get(kind, -math.pi / 2)
        grow = {"triangle": 1.25, "diamond": 1.14}.get(kind, 1.05)
        lift = r * 0.22 if kind == "triangle" else 0.0
        for i in range(sides):
            angle = start + i * 2 * math.pi / sides
            point = QPointF(x + r * grow * math.cos(angle), y + lift + r * grow * math.sin(angle))
            path.moveTo(point) if i == 0 else path.lineTo(point)
        path.closeSubpath()
    else:
        path.addEllipse(centre, r, r)
    return path


def entry_mode(entry: dict) -> str:
    return str(entry.get("mode") or "story")


def entry_title(entry: dict) -> str:
    return str(entry.get("map") or MODE_NAMES.get(entry_mode(entry), "Task"))


def entry_detail(entry: dict) -> str:
    mode = entry_mode(entry)
    times = entry.get("times")
    count = "forever" if not times else f"×{times}"
    act = entry.get("act")
    if mode == "sandbox":
        return f"Sandbox · {count}"
    if act:
        hard = " Hard" if str(entry.get("difficulty")) == "Hard" else ""
        return f"Act {act}{hard} · {count}"
    return f"{MODE_NAMES.get(mode, mode)} · {count}"


def _catmull(points: list[QPointF], steps: int = 22) -> list[QPointF]:
    """A smooth curve through every point."""
    if len(points) < 2:
        return list(points)
    out = []
    padded = [points[0]] + points + [points[-1]]
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * (2 * p1.x() + (-p0.x() + p2.x()) * t + (2 * p0.x() - 5 * p1.x() + 4 * p2.x() - p3.x()) * t2
                       + (-p0.x() + 3 * p1.x() - 3 * p2.x() + p3.x()) * t3)
            y = 0.5 * (2 * p1.y() + (-p0.y() + p2.y()) * t + (2 * p0.y() - 5 * p1.y() + 4 * p2.y() - p3.y()) * t2
                       + (-p0.y() + 3 * p1.y() - 3 * p2.y() + p3.y()) * t3)
            out.append(QPointF(x, y))
    out.append(points[-1])
    return out


class TaskChain(QWidget):
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("The plan. Click to change it in Tasks.")
        self.entries: list[dict] = []
        self.index = -1
        self.done = 0
        self.wave = 0.0
        self.state = "Idle"
        self.finished = False
        self._flow = 0.0
        self._shown = 0.0
        self._scroll = 0.0
        self._gap = MIN_GAP
        self._last = time.perf_counter()
        self._waypoints = []
        self.timer = QTimer(self)
        self.timer.setInterval(1000 // FPS)
        self.timer.timeout.connect(self._tick)

    # --------------------------------------------------------------------------- state
    def set_plan(self, entries: list[dict]):
        self.entries = [dict(e) for e in entries]
        self._update_timer()
        self.update()

    def set_progress(self, index: int, done: int, wave: float, state: str):
        if index != self.index:
            self._shown = 0.0
        self.index, self.done, self.wave, self.state = index, done, max(0.0, min(1.0, wave)), state
        self.finished = False
        self._update_timer()
        self.update()

    def set_finished(self, reached_end: bool):
        self.state = "Idle"
        self.finished = reached_end
        if not reached_end:
            self.index = -1
        self._update_timer()
        self.update()

    def _running(self) -> bool:
        return self.state in ("Running", "Starting", "Paused") and 0 <= self.index < len(self.entries)

    def _update_timer(self):
        if self._running() and self.isVisible():
            if not self.timer.isActive():
                self._last = time.perf_counter()
                self.timer.start()
        else:
            self.timer.stop()

    def showEvent(self, event):
        self._update_timer()
        super().showEvent(event)

    def _target(self) -> float:
        if not (0 <= self.index < len(self.entries)):
            return 0.0
        times = self.entries[self.index].get("times")
        if not times:
            return self.wave
        return min(1.0, (self.done + self.wave) / max(1, int(times)))

    def _tick(self):
        now = time.perf_counter()
        dt, self._last = now - self._last, now
        if self.state != "Paused":
            self._flow = (self._flow + dt) % 10000.0
        self._shown += (self._target() - self._shown) * min(1.0, dt * 3.0)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    # --------------------------------------------------------------------------- layout
    def _points(self) -> list[QPointF]:
        n = len(self.entries)
        width, height = self.width(), self.height()
        mid = height * 0.34
        swing = min(13.0, height * 0.09)
        gap = max(MIN_GAP, min(MAX_GAP, (width - 2 * EDGE) / max(1, n - 1))) if n > 1 else MAX_GAP
        self._gap = gap
        total = gap * (n - 1)
        if total <= width - 2 * EDGE:
            start = (width - total) / 2
            self._scroll = 0.0
        else:
            focus = max(0, self.index)
            wanted = max(0.0, min(total - (width - 2 * EDGE), EDGE + focus * gap - width / 3))
            self._scroll += (wanted - self._scroll) * 0.2
            start = EDGE - self._scroll
        # The road rises and falls: each waypoint sits on a gentle swell of its own.
        return [QPointF(start + i * gap, mid + swing * math.sin(i * 1.9 + 0.6)) for i in range(n)]

    # ------------------------------------------------------------------------- painting
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.entries:
            painter.setPen(_a(WHITE, 0.5))
            painter.setFont(QFont("Segoe UI Variable Text", 10))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "No route yet.  Click here, or open Tasks, to plan what to play.")
            return
        points = self._points()
        # The road comes in from beyond the left edge and runs on past the right one.
        lead_in = QPointF(points[0].x() - 90, points[0].y() + 14)
        lead_out = QPointF(points[-1].x() + 90, points[-1].y() - 14)
        road = [lead_in] + points + [lead_out]
        curve = _catmull(road)
        steps = 22
        # Where each waypoint falls in the curve: waypoint i is road point i + 1.
        at = [(i + 1) * steps for i in range(len(points))]
        self._waypoints = points
        reached = self._reached()
        ink_end = at[reached] if reached >= 0 else 0
        if self.finished:
            ink_end = len(curve) - 1
        self._paint_road(painter, curve, ink_end, at)
        for i, centre in enumerate(points):
            self._paint_waypoint(painter, i, centre, self._status(i))
        if points[-1].x() > self.width() - 10 or points[0].x() < 10:
            for left in (True, False):
                x0 = 0 if left else self.width() - 40
                fade = QLinearGradient(0 if left else self.width(), 0, 40 if left else self.width() - 40, 0)
                fade.setColorAt(0.0, QColor(14, 16, 21, 210))
                fade.setColorAt(1.0, QColor(14, 16, 21, 0))
                painter.fillRect(QRectF(x0, 0, 40, self.height()), fade)

    def _reached(self) -> int:
        """The last waypoint the inked road has got to."""
        if self.finished:
            return len(self.entries) - 1
        return self.index

    def _status(self, i: int) -> str:
        if self.finished:
            return "done"
        if self.index < 0:
            return "next" if i == 0 else "ahead"
        if i < self.index:
            return "done"
        return "current" if i == self.index else "ahead"

    def _paint_road(self, painter: QPainter, curve: list[QPointF], ink_end: int, at: list[int]):
        """Real chain between the waypoints: links laid at even steps along the route, each
        turned to it, face-on and edge-on in turn so they interlock. Links already travelled
        are polished steel; links ahead are dim; the stretch into the task being played
        carries a slow surge of light from link to link."""
        points = self._waypoints
        # Arc length along the curve, so links sit at even steps on bends as on straights.
        lengths = [0.0]
        for a, b in zip(curve, curve[1:]):
            lengths.append(lengths[-1] + math.hypot(b.x() - a.x(), b.y() - a.y()))
        total = lengths[-1]
        pitch = LINK_PITCH
        links = []
        position = 0.0
        k = 0
        index = 0
        while position <= total:
            while index < len(lengths) - 2 and lengths[index + 1] < position:
                index += 1
            a, b = curve[index], curve[index + 1]
            span = lengths[index + 1] - lengths[index] or 1.0
            t = (position - lengths[index]) / span
            p = QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)
            angle = math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x()))
            # Leave room around each emblem: the chain is fastened to it, not through it.
            if all(math.hypot(p.x() - c.x(), p.y() - c.y()) > R + 7 for c in points):
                links.append((k, index, position, p, angle))
            position += pitch
            k += 1
        live = self._running()
        start = at[self.index - 1] if live and self.index > 0 else 0
        end = at[self.index] if live else -1
        surge = (self._flow * 0.16) % 1.0 if live and self.state != "Paused" else None
        span_start, span_end = lengths[start], lengths[end] if end >= 0 else 0.0
        # Face-on links first, then the edge-on ones threaded through them.
        for face_on in (True, False):
            for k, index, position, p, angle in links:
                if (k % 2 == 0) != face_on:
                    continue
                travelled = index < ink_end or self.finished
                energised = live and start <= index < end
                fade = min(1.0, position / 70.0, (total - position) / 70.0)  # runs in and out of view
                light = 0.0
                if energised and surge is not None:
                    along = (position - span_start) / max(1.0, span_end - span_start)
                    light = math.exp(-((along - surge) / 0.09) ** 2)
                if travelled and not energised:
                    metal = 0.82
                elif energised:
                    metal = 0.5 + 0.45 * light
                else:
                    metal = 0.26
                self._link(painter, p, angle, face_on, metal * fade, light * fade)

    @staticmethod
    def _link(painter: QPainter, p: QPointF, angle: float, face_on: bool, metal: float, light: float):
        painter.save()
        painter.translate(p)
        painter.rotate(angle)
        length = LINK_LENGTH
        if face_on:
            ring = QRectF(-length / 2, -3.7, length, 7.4)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_a(INK, 0.55 * min(1.0, metal * 1.6)), 3.4))
            painter.drawRoundedRect(ring, 3.7, 3.7)
            steel = QLinearGradient(0, -3.7, 0, 3.7)
            steel.setColorAt(0.0, _a(WHITE, metal))
            steel.setColorAt(1.0, _a(WHITE, metal * 0.45))
            painter.setPen(QPen(steel, 1.45))
            painter.drawRoundedRect(ring, 3.7, 3.7)
        else:
            bar = QRectF(-length / 2 + 0.5, -1.35, length - 1, 2.7)
            painter.setPen(QPen(_a(INK, 0.6 * min(1.0, metal * 1.6)), 1.0))
            steel = QLinearGradient(0, -1.35, 0, 1.35)
            steel.setColorAt(0.0, _a(WHITE, min(1.0, metal * 1.1)))
            steel.setColorAt(1.0, _a(WHITE, metal * 0.5))
            painter.setBrush(steel)
            painter.drawRoundedRect(bar, 1.35, 1.35)
        if light > 0.05:
            # The surge: a little light caught inside the link, no bigger than the link.
            glow = QRadialGradient(QPointF(0, 0), length * 0.7)
            glow.setColorAt(0.0, _a(QColor("#dfe8ff"), 0.35 * light))
            glow.setColorAt(1.0, _a(QColor("#dfe8ff"), 0.0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(0, 0), length * 0.7, length * 0.7)
        painter.restore()

    def _paint_waypoint(self, painter: QPainter, i: int, centre: QPointF, status: str):
        entry = self.entries[i]
        kind = SHAPES.get(entry_mode(entry), "circle")
        painter.save()
        if status == "current":
            paused = self.state == "Paused"
            tone = QColor(WARN) if paused else WHITE
            halo = QRadialGradient(centre, R * 2.2)
            halo.setColorAt(0.0, _a(tone, 0.10))
            halo.setColorAt(1.0, _a(tone, 0.0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(centre, R * 2.2, R * 2.2)
            # The dial: 40 ticks around the emblem, lit as the task gets done.
            ticks, inner, outer = 40, R + 7.5, R + 11.5
            lit = self._shown * ticks
            for k in range(ticks):
                angle = -math.pi / 2 + k * 2 * math.pi / ticks
                on = k < lit
                long = k % 10 == 0
                c, s = math.cos(angle), math.sin(angle)
                painter.setPen(QPen(_a(tone, 0.95 if on else 0.18), 1.5 if on else 1.0, cap=Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(centre.x() + c * inner, centre.y() + s * inner),
                                 QPointF(centre.x() + c * (outer + (2.5 if long else 0)), centre.y() + s * (outer + (2.5 if long else 0))))
            # A marker riding the dial at the progress so far.
            angle = -math.pi / 2 + self._shown * 2 * math.pi
            tip = QPointF(centre.x() + math.cos(angle) * (outer + 6), centre.y() + math.sin(angle) * (outer + 6))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_a(tone, 1.0))
            painter.drawEllipse(tip, 2.1, 2.1)
            # The emblem: a dark seal with a bright rim and a beating heart.
            path = shape_path(kind, centre, R)
            painter.setBrush(_a(INK, 0.85))
            painter.setPen(QPen(_a(tone, 0.95), 1.6))
            painter.drawPath(path)
            core = shape_path(kind, centre, R * 0.42)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_a(tone, 0.95))
            painter.drawPath(core)
        elif status == "done":
            path = shape_path(kind, centre, R)
            body = QLinearGradient(centre.x(), centre.y() - R, centre.x(), centre.y() + R)
            body.setColorAt(0.0, QColor("#ffffff"))
            body.setColorAt(1.0, QColor("#c9d1df"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(body)
            painter.drawPath(path)
            # Stamped: the inner seal pressed in, dark.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_a(INK, 0.55), 1.1))
            painter.drawPath(shape_path(kind, centre, R * 0.58))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_a(INK, 0.85))
            painter.drawPath(shape_path(kind, centre, R * 0.24))
        else:
            near = status == "next"
            path = shape_path(kind, centre, R)
            painter.setBrush(_a(INK, 0.55))
            painter.setPen(QPen(_a(WHITE, 0.85 if near else 0.5), 1.3))
            painter.drawPath(path)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_a(WHITE, 0.4 if near else 0.18), 1.0))
            painter.drawPath(shape_path(kind, centre, R * 0.55))
        # Words: the map in the display face, what and how many under it.
        strength = {"current": 1.0, "done": 0.7, "next": 0.9}.get(status, 0.5)
        title = QFont(TITLE_FONT, 10)
        title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.3)
        title.setWeight(QFont.Weight.DemiBold if status == "current" else QFont.Weight.Normal)
        painter.setFont(title)
        painter.setPen(_a(WHITE, strength))
        room = max(MIN_GAP, min(self._gap, 190.0)) - 10
        box = QRectF(centre.x() - room / 2, centre.y() + R + 19, room, 18)
        painter.drawText(box, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         painter.fontMetrics().elidedText(entry_title(entry), Qt.TextElideMode.ElideRight, int(box.width())))
        detail = QFont("Segoe UI Variable Text", 8)
        painter.setFont(detail)
        painter.setPen(_a(WHITE, strength * 0.55))
        text = entry_detail(entry)
        if status == "current":
            times = entry.get("times")
            run = min(self.done + 1, int(times)) if times else self.done + 1
            text = f"run {run} of {times}" if times else f"run {run}"
        painter.drawText(box.translated(0, 17), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, text)
        painter.restore()
