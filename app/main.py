"""The macro's main window. Roblox sits in the middle; the left rail shows the session, rewards and
logs; the right rail lists the hotkeys and opens the sub-windows (Main, Tasks, Config, Extras, About).

The middle is a real hole, so Roblox stays its own window, kept right behind or in front of this
one. Minimizing this minimizes Roblox too, and restoring brings both back.
Run from the project root:  xpedite.bat
"""
import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
# Real pixels: Qt would otherwise scale by Windows' 125%, and the hole wouldn't fit the game.
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

from macro.platform import windows as win  # noqa: E402  (first: it sets DPI awareness)

import cv2  # noqa: E402
from PyQt6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QRegion  # noqa: E402
from PyQt6.QtWidgets import QApplication, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget  # noqa: E402

from macro import brand  # noqa: E402
from macro.sched import runner as queue_runner, webhook  # noqa: E402
from chain import TaskChain  # noqa: E402
from logview import LogView  # noqa: E402
from panels import (AboutWindow, ConfigWindow, ExtrasWindow, TasksWindow, load_settings)  # noqa: E402
from setup_window import SetupWindow  # noqa: E402
from strategy import StrategyWindow  # noqa: E402
from glass import Backdrop, paint_glass, paint_shadow, qimage_to_bgr  # noqa: E402
from theme import BAD, ICON_FONT, ICONS, MUTED, QSS, WARN  # noqa: E402
from ui import Card, KeyRow, NavButton, Pill, Stat, SubWindow, Toast, icon, label, load_yaml  # noqa: E402

from macro.version import VERSION  # noqa: E402
WM_HOTKEY = 0x0312
VK = {"F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75, "F7": 0x76}
AMBIENT_EVERY = 3000  # ms between pictures of the game for the glass to take its light from
BEZEL = 6  # px of glass rim around the game
SAME_PRESS = 0.6  # s: a hotkey within this of a guard trip is the press that caused it
user32 = ctypes.WinDLL("user32", use_last_error=True)
# The taskbar shows this app's own icon (the afkami ghost cursor, app/assets/brand) under its own
# entry, not Python's: Windows groups windows by this id.
APP_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "brand", "xpedite.ico")
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("afkami.xpedite")
except (AttributeError, OSError):
    pass
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


class Bridge(QObject):
    """Everything the macro's threads tell the window goes through here."""
    log = pyqtSignal(str)
    stats = pyqtSignal(object)
    paused = pyqtSignal(str)
    result = pyqtSignal(str, str)
    finished = pyqtSignal(str)
    attached = pyqtSignal(str)
    picture = pyqtSignal(str)
    toast = pyqtSignal(str, str)
    hotkey = pyqtSignal(str)
    setup = pyqtSignal(object)
    update = pyqtSignal(str, object, str)  # state, release, detail


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(brand.NAME)
        from PyQt6.QtGui import QIcon
        if os.path.exists(APP_ICON):
            QApplication.instance().setWindowIcon(QIcon(APP_ICON))
            self.setWindowIcon(QIcon(APP_ICON))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowMinimizeButtonHint)
        self.setStyleSheet(QSS)
        self.setGeometry(QApplication.primaryScreen().availableGeometry())
        self.hole = QRect(*(win.FRAME or (240, 40, 1440, 810)))
        self.bridge = Bridge()
        self.platform = win.WindowsPlatform()
        self.runner = None
        self.job = None
        self.attached = False
        self.attaching = False
        self.was_minimized = False
        self.paused = False
        self.log_file = None
        self.hotkeys = {}
        self.run_started = None
        self.backdrop = Backdrop(self.width(), self.height(), self.hole)
        self.backdrop.changed.connect(self._backdrop_changed)
        self._bezel_previous = None
        self._shadow_key = None
        self._shadows = None

        self._build_bar()
        self._build_left()
        self._build_right()
        self._build_bottom()
        self.setMask(QRegion(self.rect()).subtracted(QRegion(self.hole)))

        self.strategy = StrategyWindow(self)
        self.tasks = TasksWindow(self)
        self.config = ConfigWindow(self)
        self.extras = ExtrasWindow(self)
        self.about = AboutWindow(self, VERSION)
        self.setup_window = SetupWindow(self)

        b = self.bridge
        b.log.connect(self.log)
        b.stats.connect(self.show_stats)
        b.paused.connect(self.show_paused)
        b.result.connect(self.show_result)
        b.finished.connect(self.run_finished)
        b.attached.connect(self.attach_done)
        b.picture.connect(self.picture_done)
        b.toast.connect(self.toast)
        b.hotkey.connect(self.hotkey_pressed)
        b.update.connect(self.update_state)

        self.keeper = QTimer(self)
        self.keeper.timeout.connect(self.keep_together)
        self.keeper.start(400)
        self.ambient = QTimer(self)
        self.ambient.timeout.connect(self.sample_game)
        self.ambient.start(AMBIENT_EVERY)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.tick_clock)
        self.clock.start(1000)
        self.queue_changed()
        self.log(f"{brand.NAME} {VERSION} opened")
        QTimer.singleShot(300, self.register_hotkeys)
        QTimer.singleShot(500, self.first_attach)
        QTimer.singleShot(1500, lambda: self.start_bot(announce=False))
        # Discord reports (macro/remote/reports.py): a summary every few hours, an alert when the
        # farm looks stuck, a notice that the app opened.
        self._opened_at = self._last_summary = time.time()
        self._stuck_alerted = False
        self.reports = QTimer(self)
        self.reports.timeout.connect(self.report_tick)
        self.reports.start(60_000)
        QTimer.singleShot(8000, self.opened_notice)
        QTimer.singleShot(3000, self.prewarm_sheets)
        # The bot's own status line shows what the farm is doing (user, 13 Nov 2026: "online"
        # alone didn't say it was working).
        self._presence = None
        self.presence_timer = QTimer(self)
        self.presence_timer.timeout.connect(self.presence_tick)
        self.presence_timer.start(30_000)
        # Updates (macro/update.py): a look at the newest release soon after opening and every 6 h;
        # one is installed by itself when nothing is running (Config: Update by itself).
        self.update_waiting = None
        self.updating = False
        QTimer.singleShot(6000, self.check_updates)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.check_updates)
        self.update_timer.start(6 * 3600 * 1000)
        if not os.path.exists(os.path.join(ROOT, "data", "setup_done")):
            QTimer.singleShot(1500, self.setup_window.open)  # a new user starts with Setup

    # ------------------------------------------------------------------------------- layout
    @staticmethod
    def _brand_mark(size: int) -> QLabel:
        """The afkami ghost cursor, drawn from its SVG at this screen's pixel density."""
        from PyQt6.QtCore import QByteArray
        from PyQt6.QtGui import QImage
        from PyQt6.QtSvg import QSvgRenderer
        mark = QLabel()
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "brand", "afkami_mark_light.svg")
        try:
            with open(path, encoding="utf-8") as f:
                renderer = QSvgRenderer(QByteArray(f.read().encode()))
        except OSError:
            return mark
        dpr = max(1.0, QApplication.primaryScreen().devicePixelRatio())
        image = QImage(int(size * dpr), int(size * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(dpr)
        mark.setPixmap(pixmap)
        mark.setFixedSize(size, size)
        return mark

    def _build_bar(self):
        bar = QWidget(self)
        bar.setGeometry(0, 0, self.width(), self.hole.top() - BEZEL)
        box = QHBoxLayout(bar)
        box.setContentsMargins(16, 0, 8, 0)
        box.setSpacing(9)
        box.addWidget(self._brand_mark(20))
        name = QLabel(f'{brand.HUB}<span style="color: rgba(235, 240, 250, 0.45); font-weight: 400;">'
                      f'&nbsp;&nbsp;·&nbsp;&nbsp;{brand.UNIT}</span>')
        name.setObjectName("brand")
        name.setTextFormat(Qt.TextFormat.RichText)
        box.addWidget(name)
        version = label(f"v{VERSION}", "dim", wrap=False)
        box.addWidget(version)
        box.addStretch(1)
        self.attach_dot = icon("link", 9, MUTED)
        box.addWidget(self.attach_dot)
        self.attach_state = label("Roblox: looking", "muted", wrap=False)
        box.addWidget(self.attach_state)
        box.addSpacing(10)
        minimize = QPushButton(ICONS["minimize"])
        minimize.setObjectName("chrome")
        minimize.setToolTip("Minimize, together with Roblox")
        minimize.clicked.connect(self.showMinimized)
        close = QPushButton(ICONS["close"])
        close.setObjectName("close")
        close.setToolTip("Close")
        close.clicked.connect(self.close)
        box.addWidget(minimize)
        box.addWidget(close)

    def _rail(self, x, width):
        rail = QWidget(self)
        rail.setGeometry(x, self.hole.top() - BEZEL, width, self.hole.height() + 2 * BEZEL)
        box = QVBoxLayout(rail)
        left = 12 if x == 0 else BEZEL + 8
        right = BEZEL + 8 if x == 0 else 12
        box.setContentsMargins(left, 0, right, 0)
        box.setSpacing(12)
        return box

    def _build_left(self):
        box = self._rail(0, self.hole.left())
        session = Card("Session", icon_name="session")
        self.pill = Pill("Idle")
        session.add(self.pill)
        self.task_text = label("Nothing running", "big")
        session.add(self.task_text)
        self.run_text = label("Pick what to play in Tasks, then Start.", "muted")
        session.add(self.run_text)
        box.addWidget(session)

        live = Card("Match", icon_name="match")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.stats = {}
        for index, (key, title) in enumerate((("wave", "Wave"), ("yen", "Yen"), ("health", "Health"),
                                              ("enemies", "Enemies"), ("clock", "Time"), ("moves", "Matches"))):
            stat = Stat(title, meter={"wave": "ticks", "health": "pips"}.get(key, "none"))
            grid.addWidget(stat, index // 2, index % 2)
            grid.setRowStretch(index // 2, 1)
            self.stats[key] = stat
        live.add(grid, 1)
        self.max_health = 0
        box.addWidget(live, 1)
        self.played = 0

        rewards = Card("Totals", icon_name="trophy")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        for index, (key, title) in enumerate((("wins", "Wins"), ("losses", "Losses"), ("rate", "Win rate"),
                                              ("gems", "Gems"), ("running", "Run time"),
                                              ("per_hour", "Per hour"), ("per_match", "Avg match"),
                                              ("fragments", "Fragments"))):
            stat = Stat(title)
            grid.addWidget(stat, index // 2, index % 2)
            grid.setRowStretch(index // 2, 1)
            self.stats[key] = stat
        rewards.add(grid, 1)
        self.result_text = label("No result yet. Screenshots go to the webhook.", "dim")
        rewards.add(self.result_text)
        box.addWidget(rewards, 1)

    def _build_right(self):
        x = self.hole.right() + 1
        box = self._rail(x, self.width() - x)
        windows = Card("Windows", spacing=2, icon_name="main")
        for icon_name, title, subtitle, color, opener in (
                ("main", "Main", "Strategies per map", None, lambda: self.strategy.open()),
                ("tasks", "Tasks", "What to play", None, lambda: self.tasks.open()),
                ("config", "Config", "Settings, webhook", None, lambda: self.config.open()),
                ("extras", "Extras", "Tools", None, lambda: self.extras.open()),
                ("safety", "Setup", "PC, game settings, team", None, lambda: self.setup_window.open()),
                ("about", "About", "Version, support", None, lambda: self.about.open())):
            button = NavButton(icon_name, title, subtitle, color)
            button.clicked.connect(opener)
            windows.add(button)
        box.addWidget(windows)

        keys = Card("Hotkeys", spacing=1, icon_name="keys")
        self.key_rows = {}
        for key, text, action in (("F1", "Attach Roblox", self.attach),
                                  ("F2", "Start queue", self.start_run),
                                  ("F3", "Stop", self.stop_run),
                                  ("F4", "Test webhook", self.test_webhook),
                                  ("F5", "Collect rewards", self.collect_now),
                                  ("F6", "Pause / Resume", self.pause_or_resume),
                                  ("F7", "Screenshot", self.screenshot)):
            row = KeyRow(key, text)
            row.clicked.connect(action)
            keys.add(row)
            self.key_rows[key] = (row, action)
        f8 = KeyRow("F8", "Emergency stop")
        f8.text_label.setStyleSheet(f"background: transparent; font-size: 13px; color: {BAD};")
        f8.setToolTip("Always works during a run, even when this window is hidden")
        f8.clicked.connect(self.stop_run)
        keys.add(f8)
        box.addWidget(keys)

        box.addStretch(1)
        controls = Card("Run", icon_name="play")
        self.queue_text = label("", "muted")
        controls.add(self.queue_text)
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start_run)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_or_resume)
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("danger")
        self.stop_button.clicked.connect(self.stop_run)
        self.stop_button.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(self.pause_button)
        row.addWidget(self.stop_button)
        controls.add(self.start_button)
        controls.add(row)
        box.addWidget(controls)

    def _build_bottom(self):
        """A band under the game, edge to edge: the log, and the plan as a chain."""
        y = self.hole.bottom() + 1 + BEZEL
        holder = QWidget(self)
        holder.setGeometry(0, y, self.width(), self.height() - y)
        row = QHBoxLayout(holder)
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(12)
        clear = QPushButton("Clear")
        clear.setObjectName("small")
        logs = Card("Log", icon_name="logs", extra=clear, margins=12, spacing=4)
        self.logs = LogView()
        clear.clicked.connect(self.logs.clear)
        logs.add(self.logs, 1)
        row.addWidget(logs, 2)

        head = QWidget()
        head_box = QHBoxLayout(head)
        head_box.setContentsMargins(0, 0, 0, 0)
        head_box.setSpacing(12)
        self.plan_text = label("", "dim", wrap=False)
        head_box.addWidget(self.plan_text)
        edit = QPushButton("Edit")
        edit.setObjectName("small")
        edit.clicked.connect(lambda: self.tasks.open())
        head_box.addWidget(edit)
        plan = Card("Plan", icon_name="order", extra=head, margins=12, spacing=2)
        self.chain = TaskChain()
        self.chain.clicked.connect(lambda: self.tasks.open())
        plan.add(self.chain, 1)
        row.addWidget(plan, 3)
        self.toast_area = QRect(0, y, self.width(), self.height() - y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        backdrop = self.backdrop
        # The ground: the game's own light, spread and smoked.
        if backdrop.fade < 1.0 and backdrop.previous_ground is not None:
            painter.drawPixmap(0, 0, backdrop.previous_ground)
            painter.setOpacity(backdrop.fade)
        painter.drawPixmap(0, 0, backdrop.ground)
        painter.setOpacity(1.0)
        # Contact shadows under every pane of glass on this window. Panes don't move, so
        # the shadows are drawn once into a layer and reused.
        hole = self.hole
        outer = hole.adjusted(-BEZEL, -BEZEL, BEZEL, BEZEL)
        radius = BEZEL + 10
        panes = tuple((card.mapTo(self, QPoint(0, 0)).x(), card.mapTo(self, QPoint(0, 0)).y(), card.width(), card.height())
                      for card in self.findChildren(Card) if card.isVisible() and card.window() is self)
        if self._shadow_key != panes:
            self._shadow_key = panes
            self._shadows = QPixmap(self.size())
            self._shadows.fill(Qt.GlobalColor.transparent)
            layer = QPainter(self._shadows)
            layer.setRenderHint(QPainter.RenderHint.Antialiasing)
            for x, y, width, height in panes:
                paint_shadow(layer, QRectF(x, y, width, height), Card.RADIUS, depth=0.8)
            paint_shadow(layer, QRectF(outer), radius, depth=1.0)
            layer.end()
        painter.drawPixmap(0, 0, self._shadows)
        # The game is set in a rim of glass, like a screen in its bezel.
        pixmap = backdrop.pane(outer, radius, hole=(BEZEL, BEZEL, hole.width(), hole.height()),
                               band=BEZEL, strength=5.0)
        previous = self._bezel_previous if backdrop.fade < 1.0 else None
        if backdrop.fade >= 1.0:
            self._bezel_previous = pixmap
        painter.setClipRegion(QRegion(outer).subtracted(QRegion(hole)))
        paint_glass(painter, QRectF(outer), radius, pixmap, previous, backdrop.fade, strength=1.2)
        painter.setClipping(False)
        # The inner edge: where the glass meets the picture, a fine dark line, then light.
        painter.setPen(QPen(QColor(0, 0, 0, 120), 1))
        painter.drawRect(QRectF(hole).adjusted(-0.5, -0.5, 0.5, 0.5))
        painter.setPen(QPen(QColor(255, 255, 255, 60 if self.attached else 26), 1))
        painter.drawRect(QRectF(hole).adjusted(-1.5, -1.5, 1.5, 1.5))

    def _backdrop_changed(self):
        self.update()
        for sheet in self.findChildren(SubWindow):
            if sheet.isVisible():
                sheet.update()

    def sample_game(self):
        """Take the game's picture for the glass to be lit by, when it can be seen as itself:
        attached, docked, not minimized, and nothing of ours over it."""
        if not self.attached or self.isMinimized() or not self.config.settings.get("live_glass", True):
            return
        hwnd = self.roblox()
        if hwnd is None or win.user32.IsIconic(hwnd) or not win.is_docked(hwnd):
            return
        for sheet in self.findChildren(SubWindow):
            if sheet.isVisible() and sheet.frameGeometry().intersects(self.hole):
                return
        foreground = win.user32.GetForegroundWindow()
        if foreground not in (hwnd, int(self.winId())) and not any(
                int(w.winId()) == foreground for w in self.findChildren(SubWindow) if w.isVisible()):
            return
        screen = QApplication.primaryScreen()
        picture = screen.grabWindow(0, self.hole.x(), self.hole.y(), self.hole.width(), self.hole.height())
        self.backdrop.feed(qimage_to_bgr(picture.toImage()))

    def glass_behind_sheets(self):
        """A sub-window is about to open: photograph this window so its glass bends what is
        really behind it. Under the sheet's blur a photo seconds old looks the same, so one is
        reused for a minute, and taken at the glass's working size (half): a full-size photo
        and its blur were ~45 ms of every open (13 Nov 2026)."""
        now = time.time()
        if now - getattr(self, "_sheets_photo_at", 0.0) < 60.0:
            return
        self._sheets_photo_at = now
        from PyQt6.QtGui import QImage, QPainter
        k = self.backdrop.WORK
        picture = QImage(max(1, self.width() // k), max(1, self.height() // k), QImage.Format.Format_RGB32)
        painter = QPainter(picture)
        painter.scale(1 / k, 1 / k)
        self.render(painter, QPoint(0, 0))
        painter.end()
        self.backdrop.under_sheets(picture)

    def prewarm_sheets(self, sheets=None):
        """Style each sub-window and give it its native window before it's first opened, one
        every 0.4 s after the start: done on the first open it added 30-50 ms (13 Nov 2026)."""
        if sheets is None:
            sheets = [s for s in (self.tasks, self.config, self.extras, self.about, self.strategy) if s is not None]
        if not sheets:
            return
        sheet, rest = sheets[0], sheets[1:]
        sheet.ensurePolished()
        sheet.winId()
        if sheet.layout() is not None:
            sheet.layout().activate()
        if sheet.fit:  # the size it opens at, so the shadow and glass pictures made now are the ones used
            sheet.resize(sheet.width(), sheet.sizeHint().height())
        sheet.grab()  # one paint off screen: its shadow, glass body and children's first paint
        QTimer.singleShot(400, lambda: self.prewarm_sheets(rest))

    # ---------------------------------------------------------------------------- feedback
    def toast(self, text, kind="info"):
        Toast(self, text, kind, self.toast_area)

    def log(self, text):
        stamp = time.strftime('%H:%M:%S')
        line = f"[{stamp}] {text}"
        self.logs.add(text, stamp)
        try:
            if self.log_file is None:
                os.makedirs("logs", exist_ok=True)
                self.log_file = open(f"logs/app-{time.strftime('%Y%m%d')}.log", "a", encoding="utf-8")
            self.log_file.write(line + "\n")
            self.log_file.flush()
        except OSError:
            pass

    def show_stats(self, stats):
        self.pill.set_state(stats.state)
        # "Crimson Shore Act 1 Normal, plan story, x2" reads better as a title and a line under it.
        title, _, rest = (stats.task or "").partition(", plan ")
        plan = rest.split(",")[0] if rest else ""
        self.task_text.setText(title.replace(" Normal", "") or "Nothing running")
        under = [f"Run {stats.run}"] if stats.run else []
        if plan:
            under.append(f"plan {plan}")
        self.run_text.setText("  ·  ".join(under) or "Pick what to play in Tasks, then Start.")
        for key in ("wave", "yen", "health", "enemies", "clock"):
            self.stats[key].set(getattr(stats, key))
        try:
            now, total = (int(v) for v in str(stats.wave).split("/"))
            self.stats["wave"].meter.set(now, total)
        except ValueError:
            self.stats["wave"].meter.set(0, 0)
        try:
            health = int(stats.health)
            self.max_health = max(self.max_health, health)
            self.stats["health"].meter.set(health, self.max_health)
        except ValueError:
            pass
        self.stats["moves"].set(str(stats.wins + stats.losses))
        self.stats["wins"].set(str(stats.wins))
        self.stats["losses"].set(str(stats.losses))
        played = stats.wins + stats.losses
        self.played = played
        self.stats["rate"].set(f"{round(100 * stats.wins / played)}%" if played else "-")
        self.stats["fragments"].set(str(stats.loot.get("Crumbling Fragment", 0)) if stats.loot else "-")
        wave = 0.0
        try:
            now, total = str(stats.wave).split("/")
            wave = max(0, int(now) - 1) / max(1, int(total))
        except ValueError:
            pass
        self.chain.set_progress(stats.index, stats.done, wave, stats.state)
        self.show_plan_text(stats)
        if stats.gems_start is not None and stats.gems_now is not None:
            self.stats["gems"].set(f"{stats.gems_now - stats.gems_start:+,}")
        self.pause_button.setText("Resume" if stats.state == "Paused" else "Pause")

    def show_result(self, path, outcome):
        image = cv2.imread(path)
        self.result_text.setText(f"Last: {outcome} at {time.strftime('%H:%M')}")
        if image is not None:
            folder = os.path.join(ROOT, "logs", "results")
            os.makedirs(folder, exist_ok=True)
            cv2.imwrite(os.path.join(folder, f"{time.strftime('%Y%m%d-%H%M%S')}_{outcome}.jpg"),
                        cv2.resize(image, (720, 405)), [cv2.IMWRITE_JPEG_QUALITY, 85])
        self.toast(f"Result: {outcome}", "good" if outcome in ("victory", "built") else "bad")

    def queue_changed(self):
        entries = self.tasks.entries() if hasattr(self, "tasks") else load_yaml(
            os.path.join(ROOT, "data", "queue.yaml"), [])
        if not self.busy_running():
            self.chain.set_plan(entries)
            self.chain.set_finished(False)
        if not entries:
            self.queue_text.setText("The queue is empty.")
        else:
            total = "forever" if any(not e.get("times") for e in entries) else \
                f"{sum(int(e.get('times') or 1) for e in entries)} matches"
            self.queue_text.setText(f"{len(entries)} task{'s' if len(entries) != 1 else ''}, {total}")
        if not self.busy_running():
            self.plan_text.setText(self.queue_text.text() if entries else "")

    def busy_running(self) -> bool:
        return self.runner is not None and self.runner.is_alive()

    def show_plan_text(self, stats):
        entries = self.chain.entries
        if 0 <= stats.index < len(entries):
            parts = [f"Task {stats.index + 1} of {len(entries)}", f"run {stats.run}"]
            if stats.wave not in ("-", ""):
                parts.append(f"wave {stats.wave}")
            self.plan_text.setText("  ·  ".join(parts))

    def tick_clock(self):
        if self.run_started is not None:
            seconds = int(time.time() - self.run_started)
            hours, rest = divmod(seconds, 3600)
            self.stats["running"].set(f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}")
            if self.played and seconds > 60:
                each = seconds / self.played  # trips, loading and results included: the real pace
                self.stats["per_hour"].set(f"{3600 / each:.1f}")
                self.stats["per_match"].set(f"{int(each) // 60}:{int(each) % 60:02d}")

    def plans_changed(self):
        self.tasks.refresh_plans()

    # ------------------------------------------------------------------------------ hotkeys
    def register_hotkeys(self):
        """Global F-keys, on their own thread with its own message loop, as the F8 guard does."""
        ready = threading.Event()
        taken = []

        def pump():
            self.hotkey_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            for number, key in enumerate(VK, start=1):
                if user32.RegisterHotKey(None, 100 + number, 0x4000, VK[key]):  # MOD_NOREPEAT
                    self.hotkeys[100 + number] = key
                else:
                    taken.append(key)
            ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam in self.hotkeys:
                    self.bridge.hotkey.emit(self.hotkeys[msg.wParam])
            for number in self.hotkeys:
                user32.UnregisterHotKey(None, number)
        threading.Thread(target=pump, daemon=True, name="hotkeys").start()
        ready.wait(2)
        if taken:
            self.log(f"another program holds {', '.join(taken)}, so those only work as buttons here")

    def hotkey_pressed(self, key):
        self.key_rows[key][1]()

    # ------------------------------------------------------------------ attaching to Roblox
    def first_attach(self):
        if not load_settings()["attach_on_launch"]:
            self.attach_state.setText("Roblox: not attached")
        elif self.platform.game_running():
            self.attach()
        else:
            self.attach_state.setText("Roblox: not running  ·  F1 to start it")

    def attach(self):
        if self.attaching or self.busy():
            return
        self.attaching = True
        self.attach_state.setText("Roblox: attaching")

        def work():
            try:
                problem = self.platform.make_game_ready(timeout=90)
            except Exception as error:
                problem = str(error)
            self.bridge.attached.emit(problem or "")
        threading.Thread(target=work, daemon=True).start()

    def attach_done(self, problem):
        self.attaching = False
        self.attached = not problem
        self.attach_state.setText("Roblox: attached" if self.attached else "Roblox: not attached")
        self.attach_dot.setStyleSheet(f"font-family: '{ICON_FONT}'; font-size: 12px; background: transparent; "
                                      f"color: {'#ffffff' if self.attached else WARN};")
        if self.attached:
            QTimer.singleShot(1500, self.sample_game)
        self.update()
        if problem:
            self.log(f"couldn't attach Roblox: {problem}")
            self.toast("Couldn't attach Roblox", "warn")
        self.keep_together()

    def detach(self):
        if self.busy():
            self.toast("Can't detach during a run", "warn")
            return
        self.platform.undock_game()
        self.attached = False
        self.attach_state.setText("Roblox: not attached")
        self.update()

    def roblox(self):
        windows = self.platform._game_windows()
        return windows[0] if windows else None

    def keep_together(self):
        """Roblox and this window act as one: minimized together, and always next to each other
        in the stack, so nothing else shows through the hole."""
        if not self.attached or self.attaching:
            return
        hwnd = self.roblox()
        if hwnd is None:
            self.attach_state.setText("Roblox: closed")
            return
        self.attach_state.setText("Roblox: attached")
        own = int(self.winId())
        foreground = win.user32.GetForegroundWindow()
        roblox_minimized = bool(win.user32.IsIconic(hwnd))
        if self.isMinimized():
            if not roblox_minimized and foreground == hwnd:
                self.showNormal()  # someone switched to Roblox: bring the frame along
            elif not roblox_minimized:
                win.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            return
        if roblox_minimized:
            win.user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
            return
        if not win.is_docked(hwnd) and not self.busy() and win.client_rect(hwnd)[2:] != (1920, 1080):
            self.platform.dock_game()
        flags = 0x0002 | 0x0001 | 0x0010  # no move, no size, no activate
        if foreground == own:
            win.user32.SetWindowPos(hwnd, own, 0, 0, 0, 0, flags)
        elif foreground == hwnd:
            win.user32.SetWindowPos(own, hwnd, 0, 0, 0, 0, flags)

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange and self.attached:
            hwnd = self.roblox()
            if hwnd is not None:
                if self.isMinimized():
                    win.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                    self.was_minimized = True
                elif self.was_minimized:
                    self.was_minimized = False
                    win.user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
                    self.setMask(QRegion(self.rect()).subtracted(QRegion(self.hole)))
                    win.user32.SetWindowPos(hwnd, int(self.winId()), 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)
        super().changeEvent(event)

    # --------------------------------------------------------------------------------- runs
    def busy(self):
        return (self.runner is not None and self.runner.is_alive()) or (self.job is not None and self.job.is_alive())

    def start_run(self):
        if self.runner is not None and self.runner.is_alive():
            return
        if self.busy():
            self.toast("Something else is running", "warn")
            return
        entries = self.tasks.entries()
        if not entries:
            self.toast("The queue is empty: add something in Tasks", "warn")
            self.tasks.open()
            return
        for window in (self.strategy, self.tasks, self.config, self.extras, self.about):
            if window.isVisible():
                window.close_animated()
        self.config.save()
        self.log(f"starting a queue of {len(entries)}. Hands off the mouse and keyboard.")
        self.chain.set_plan(entries)
        self.chain.set_progress(-1, 0, 0.0, "Starting")
        self.run_started = time.time()
        self.played = 0
        self.toast("Starting. Hands off the mouse and keyboard.")
        b = self.bridge
        self.runner = queue_runner.QueueRunner(entries, load_settings(), b.log.emit, b.stats.emit, b.paused.emit,
                                               b.result.emit, b.finished.emit)
        self.attached = True
        self.update()
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.runner.start()

    def stop_run(self):
        if self.runner and self.runner.is_alive():
            self.log("stopping")
            self.pill.set_state("Stopping")
            self.runner.request_stop()

    def pause_or_resume(self):
        runner = self.runner
        if runner is None or not runner.is_alive() or runner.p is None:
            return
        guard = runner.p.guard
        if self.paused:
            # Pressing F6 trips the guard itself: that press means "pause", not "resume".
            if time.perf_counter() - guard.trip_time < SAME_PRESS:
                return
            self.log("hands off: it resumes once the mouse and keyboard are still")
            runner.request_resume()
        elif guard.armed and not guard.tripped:
            guard.trip("paused with F6")

    def show_paused(self, reason):
        self.paused = bool(reason)
        self.pause_button.setText("Resume" if self.paused else "Pause")
        if self.paused:
            self.toast(f"Paused: {reason}. Resume or F6 to carry on.", "warn")

    # ------------------------------------------------------------------------------ updates
    def check_updates(self, manual=False):
        from macro import update

        def work():
            state, release = update.check(VERSION)
            self.bridge.update.emit(state, release, "manual" if manual else "")
        threading.Thread(target=work, daemon=True).start()

    def update_state(self, state, release, detail):
        if state in ("development", "offline", "current", "available"):
            self.about.show_update(state, release)
            manual = detail == "manual"
            if state == "available":
                self.log(f"{brand.UNIT} {release['version']} is out (this is {VERSION})")
                if manual or load_settings().get("auto_update", True):
                    self.install_update(release)
                else:
                    self.toast(f"{brand.UNIT} {release['version']} is out: About installs it")
            elif manual:
                self.toast({"current": "Up to date", "offline": "Couldn't reach GitHub",
                            "development": "Development copy: update it with git"}[state],
                           "good" if state == "current" else "warn")
        elif state == "downloading":
            self.about.show_update(state, release, detail)
        elif state == "failed":
            self.updating = False
            self.about.show_update(state, release, detail)
            self.log(f"update failed: {detail}")
            self.toast(f"The update didn't install: {detail}", "bad")
        elif state == "ready":
            self.log(f"installing {brand.UNIT} {release['version']}; it opens again by itself")
            self.toast(f"Updating to {release['version']}: back in a moment")
            from macro import update
            try:
                update.install_and_restart(detail)
            except OSError as error:
                self.update_state("failed", release, str(error))
                return
            QTimer.singleShot(1200, self.close)
            QTimer.singleShot(4000, QApplication.instance().quit)

    def install_update(self, release):
        """Downloads the release and restarts into it; while a queue runs it waits for the end."""
        if self.updating:
            return
        if self.busy():
            if self.update_waiting is None:
                self.toast(f"{brand.UNIT} {release['version']} installs when this run ends")
            self.update_waiting = release
            return
        self.updating = True
        self.update_waiting = None
        from macro import update

        def work():
            try:
                shown = [-1]

                def progress(share):
                    step = int(share * 10)
                    if step != shown[0]:
                        shown[0] = step
                        self.bridge.update.emit("downloading", release, f"Downloading {release['version']}: {step * 10}%")
                folder = update.download(release, progress)
                kept = update.keep_players_files(folder)
                if kept:
                    self.bridge.log.emit(f"update keeps your own {len(kept)} files: " + ", ".join(kept[:8])
                                         + (" ..." if len(kept) > 8 else ""))
                self.bridge.update.emit("ready", release, folder)
            except Exception as error:  # noqa: BLE001 (any failure: the app carries on as it is)
                self.bridge.update.emit("failed", release, str(error) or type(error).__name__)
        threading.Thread(target=work, daemon=True).start()

    def run_finished(self, ending):
        if self.update_waiting is not None:
            QTimer.singleShot(3000, lambda: self.update_waiting and self.install_update(self.update_waiting))
        self.log(f"run {ending}")
        self.run_started = None
        self.chain.set_finished(bool(self.runner and self.runner.stats.finished))
        self.paused = False
        self.pause_button.setText("Pause")
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.toast(f"Run {ending}", "good" if ending == "finished" else "warn")

    # -------------------------------------------------------------------------------- tools
    def test_webhook(self):
        self.config.save()
        url = self.config.settings["webhook"]
        if not url:
            self.toast("Put a webhook URL in Config first", "warn")
            self.config.open()
            return
        ping = self.config.settings["ping"]

        def send():
            text = (f"<@{ping}> " if ping else "") + f"{brand.NAME}: test message"
            error = webhook.send(url, text)
            self.bridge.log.emit(f"webhook test failed: {error}" if error else "webhook test sent")
            self.bridge.toast.emit("Webhook failed" if error else "Webhook sent", "bad" if error else "good")
        threading.Thread(target=send, daemon=True).start()

    def collect_now(self):
        if self.busy():
            self.toast("Something is already running", "warn")
            return
        from macro.sched.jobs import collect_now
        self.toast("Collecting rewards. Hands off for a moment.")

        def work():
            for line in collect_now(self.bridge.log.emit):
                self.bridge.log.emit(line)
            self.bridge.toast.emit("Rewards checked", "good")
        self.job = threading.Thread(target=work, daemon=True)
        self.job.start()

    def screenshot(self):
        from macro.sched.jobs import screenshot
        path = screenshot()
        if path:
            self.log(f"screenshot saved to {path}")
            self.toast("Screenshot saved", "good")
        else:
            self.toast("No game to screenshot", "warn")

    def picture_done(self, text):
        self.log(text)
        self.strategy.picture_done(text)
        self.tasks.refresh_maps()

    def start_bot(self, announce: bool = True):
        """The Discord remote control (macro/remote/), if Config has a bot token. The application
        id and owner ids are optional: blank, the bot asks Discord (its application's owner).
        Runs as a thread in this process: no second program, a few MB at most. Started again
        after Config changes."""
        from macro.remote import bot as remote
        from remote_control import AppRemote
        remote.stop()
        s = load_settings()
        token, app_id = str(s.get("discord_token") or "").strip(), str(s.get("discord_app_id") or "").strip()
        owners = [o.strip() for o in str(s.get("discord_owners") or "").replace(";", ",").split(",") if o.strip()]
        if not token:
            return
        config = remote.BotConfig(token=token, app_id=app_id, channel_id=str(s.get("discord_channel") or "").strip(),
                                  guild_id=str(s.get("discord_guild") or "").strip(), owners=owners)
        remote.start(config, AppRemote(self), log=self.bridge.log.emit)
        self.log("Discord bot starting")
        self._presence = None
        QTimer.singleShot(4000, self.presence_tick)
        if announce:  # started again from Config: the status card, as at the app's start
            QTimer.singleShot(6000, lambda: self.status_notice("The Discord bot restarted."))

    def _bot(self):
        from macro.remote import bot as remote
        b = remote.ACTIVE
        return b if b is not None and b.config.channel_id else None

    def opened_notice(self):
        """The status card in Discord when the app opens; says so if Windows itself just started."""
        import psutil
        up = (time.time() - psutil.boot_time()) / 60
        text = f"{brand.NAME} opened at {time.strftime('%H:%M')}."
        if up < 20:
            text += f" Windows started {up:.0f} min ago: the PC was restarted."
        self.status_notice(text)

    def status_notice(self, text: str):
        b = self._bot()
        if b is None:
            return
        from macro.remote.commands.info import status_embed
        threading.Thread(target=lambda: b.post(text, embed=status_embed(b.controller)), daemon=True).start()

    def presence_tick(self):
        """The bot's status line: what the farm is doing now, green while it plays, yellow when
        nothing runs, red when paused or stuck. Sent only when it changes."""
        from macro.remote import bot as remote
        b = remote.ACTIVE
        if b is None:
            return
        try:
            s = b.controller.status()
        except Exception:  # noqa: BLE001 - a status line must never break the app
            return
        state = str(s.get("state") or "Idle")
        candy = int(s.get("candy") or 0)
        wave = s.get("wave")
        if not self.busy_running():
            text, dot = "Idle: not farming", "idle"
        elif self._stuck_alerted:
            text, dot = "Stuck? Nothing in the log for 10+ min", "dnd"
        elif state.lower().startswith("pause"):
            text, dot = f"Paused · {candy:,} Candy Corn this session", "dnd"
        elif wave and str(wave) not in ("-", "0", "None"):
            text, dot = f"Wave {wave} · {candy:,} Candy Corn this session", "online"
        else:
            text, dot = f"Setting up a run · {candy:,} Candy Corn this session", "online"
        if (text, dot) != self._presence:
            self._presence = (text, dot)
            b.set_presence(text, dot)

    def report_tick(self):
        """Every minute: a farm summary when one is due (Config "Summary every", hours), and an
        alert (pinging the owners) when a run should be going but the log has been quiet 10 min."""
        b = self._bot()
        if b is None:
            return
        from datetime import datetime
        from macro.remote import reports
        now = time.time()
        try:
            hours = float(load_settings().get("discord_summary_hours") or 0)
        except (TypeError, ValueError):
            hours = 0.0
        if hours > 0 and now - self._last_summary >= hours * 3600:
            self._last_summary = now
            since = datetime.fromtimestamp(now - hours * 3600)

            def send_summary():
                s = reports.summarize(since)
                b.post(embed=reports.summary_embed(s, f"last {hours:g} h"))
            threading.Thread(target=send_summary, daemon=True).start()
        if self.busy_running() and not self.paused:
            quiet = now - reports.last_activity()
            if quiet > 600 and not self._stuck_alerted:
                self._stuck_alerted = True
                threading.Thread(target=b.alert, args=(
                    f"The farm looks stuck: nothing in its log for {quiet / 60:.0f} min "
                    f"(since {time.strftime('%H:%M', time.localtime(now - quiet))}).",), daemon=True).start()
            elif quiet < 120:
                self._stuck_alerted = False

    def closeEvent(self, event):
        try:
            from macro.remote import bot as remote
            remote.stop()
        except Exception:
            pass
        if getattr(self, "hotkey_thread", None):
            user32.PostThreadMessageW(self.hotkey_thread, 0x0012, 0, 0)  # WM_QUIT
        if self.runner and self.runner.is_alive():
            self.runner.request_stop()
            self.runner.join(5)
        if self.attached:
            self.platform.undock_game()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
