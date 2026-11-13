"""Main: how each game mode is played on each map. The map's picture is shown, units are marked on
it, and every unit's placements, upgrades, priority and targeting are set here."""
from __future__ import annotations

import os
import threading

import cv2
from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QGridLayout,
                             QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
                             QPushButton, QVBoxLayout, QWidget)

from macro.control import maps, plans
from macro.control.engine import SLOT_X
from macro.control.placing import HUD_AREAS, on_hud
from macro.nav.stages import STORY_MAPS
from macro.sched.runner import SANDBOX_BUTTONS, folder_of
from macro.sched.setup_map import take_picture
from macro.vision.screens import GAME_HEIGHT, GAME_WIDTH, SCALE
from theme import MUTED, SLOT_COLORS
from ui import Card, SettingRow, SubWindow, Toggle, ToggleRow, number, rows, to_pixmap

VIEW = 0.75  # the picture is shown at three quarters of its real size; marks are stored full size
MODES = (("Story", "story", True), ("Sandbox test", "sandbox", True), ("Raid", None, False),
         ("Challenge", None, False), ("Infinite", None, False), ("Boss Rush", None, False))


class MapCanvas(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.pixmap = None
        self.guides = True
        self.dragging = None
        self.hover = None
        self.setFixedSize(round(GAME_WIDTH * VIEW), round(GAME_HEIGHT * VIEW))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    @staticmethod
    def to_picture(event):
        return round(event.position().x() / VIEW), round(event.position().y() / VIEW)

    def set_picture(self, pixmap):
        self.pixmap = pixmap.scaled(self.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation) if pixmap else None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#07080c"))
        if self.pixmap is None:
            painter.setPen(QColor(MUTED))
            painter.setFont(QFont("Segoe UI", 13))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "No picture of this map yet.\nSet the view below and press Take picture.")
            return
        painter.drawPixmap(0, 0, self.pixmap)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 60, 80, 38))
        for a, b, c, d in HUD_AREAS:
            painter.drawRect(QRect(round(a * SCALE * VIEW), round(b * SCALE * VIEW),
                                   round((c - a) * SCALE * VIEW), round((d - b) * SCALE * VIEW)))
        if self.guides:
            painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
            for x in range(135, self.width(), 135):
                painter.drawLine(x, 0, x, self.height())
            for y in range(68, self.height(), 68):
                painter.drawLine(0, y, self.width(), y)
        plan = self.editor.plan
        if plan is None:
            return
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        radius = 11
        for unit in plan.units:
            color = QColor(SLOT_COLORS[unit.slot])
            for index, (px, py) in enumerate(unit.spots):
                x, y = round(px * VIEW), round(py * VIEW)
                unused = not unit.enabled or (unit.count is not None and index >= unit.count)
                ring = QColor(color)
                if unused:
                    ring.setAlpha(80)
                selected = unit.slot == self.editor.slot
                painter.setPen(QPen(QColor(0, 0, 0, 190), 4))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPoint(x, y), radius, radius)
                painter.setPen(QPen(ring, 3 if selected else 2))
                painter.setBrush(QBrush(QColor(ring.red(), ring.green(), ring.blue(), 90 if selected else 60)))
                painter.drawEllipse(QPoint(x, y), radius, radius)
                painter.setPen(QColor("white"))
                painter.drawText(QRect(x - radius, y - radius, 2 * radius, 2 * radius), Qt.AlignmentFlag.AlignCenter,
                                 f"{unit.slot}.{index + 1}")
        if self.hover and not self.dragging:
            x, y = self.hover
            bad = on_hud(round(x / VIEW), round(y / VIEW))
            color = QColor("#f0556a" if bad else SLOT_COLORS[self.editor.slot])
            color.setAlpha(150)
            painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPoint(x, y), radius, radius)

    def nearest(self, x, y):
        best = None
        if self.editor.plan:
            for unit in self.editor.plan.units:
                for index, spot in enumerate(unit.spots):
                    distance = (spot[0] - x) ** 2 + (spot[1] - y) ** 2
                    if distance <= 20 ** 2 and (best is None or distance < best[0]):
                        best = (distance, unit, index)
        return best

    def mousePressEvent(self, event):
        if self.pixmap is None or self.editor.plan is None:
            return
        x, y = self.to_picture(event)
        hit = self.nearest(x, y)
        if event.button() == Qt.MouseButton.RightButton:
            if hit:
                self.editor.remove_spot(hit[1], hit[2])
            return
        if hit:
            self.dragging = (hit[1], hit[2])
            self.editor.select_slot(hit[1].slot)
        else:
            self.editor.add_spot(x, y)

    def mouseMoveEvent(self, event):
        self.hover = (round(event.position().x()), round(event.position().y()))
        if self.dragging:
            x, y = self.to_picture(event)
            unit, index = self.dragging
            unit.spots[index] = [max(0, min(GAME_WIDTH - 1, x)), max(0, min(GAME_HEIGHT - 1, y))]
        self.update()

    def leaveEvent(self, event):
        self.hover = None
        self.update()

    def mouseReleaseEvent(self, event):
        if self.dragging:
            unit, index = self.dragging
            self.dragging = None
            if on_hud(*unit.spots[index]):
                self.editor.note("That spot is over the game's buttons, so it was removed.")
                self.editor.remove_spot(unit, index)
            else:
                self.editor.commit()


class StrategyWindow(SubWindow):
    def __init__(self, main):
        super().__init__(main, "Main", "Strategy per mode and map", (1680, 960), "main")
        self.plan = None
        self.profile = None
        self.slot = 1
        self.loading = False
        self.canvas = MapCanvas(self)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self._left(), 0)
        middle = QVBoxLayout()
        middle.setSpacing(10)
        picture = Card("Map  ·  click adds  ·  drag moves  ·  right-click removes", margins=10, icon_name="map")
        picture.add(self.canvas)
        middle.addWidget(picture)
        middle.addWidget(self._view())
        middle.addStretch(1)
        row.addLayout(middle, 0)
        row.addWidget(self._right(), 1)
        self.body_box.addLayout(row, 1)
        self.refresh_maps()

    # ----------------------------------------------------------------------------- panels
    def _left(self):
        panel = QWidget()
        panel.setFixedWidth(270)
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        self.mode = QComboBox()
        model = QStandardItemModel(self.mode)
        for text, value, built in MODES:
            item = QStandardItem(text if built else f"{text}  · soon")
            item.setData(value, Qt.ItemDataRole.UserRole)
            item.setEnabled(built)
            model.appendRow(item)
        self.mode.setModel(model)
        self.map = QComboBox()
        self.plan_box = QComboBox()
        new_plan = QPushButton("New")
        new_plan.clicked.connect(self.new_plan)
        copy_plan = QPushButton("Copy")
        copy_plan.clicked.connect(self.copy_plan)
        buttons = QHBoxLayout()
        buttons.addWidget(new_plan)
        buttons.addWidget(copy_plan)
        for combo in (self.mode, self.map, self.plan_box):
            combo.setFixedWidth(170)
        which = Card("Plan", icon_name="map", spacing=0)
        rows(which, SettingRow("Mode", self.mode), SettingRow("Map", self.map), SettingRow("Plan", self.plan_box))
        which.box.addSpacing(8)
        which.add(buttons)
        box.addWidget(which)

        units = Card("Units", spacing=5, icon_name="unit")
        self.slot_buttons = {}
        group = QButtonGroup(panel)
        for slot in plans.SLOTS:
            button = QPushButton(f"Slot {slot}")
            button.setObjectName("slot")
            button.setCheckable(True)
            button.setFixedHeight(42)
            group.addButton(button)
            button.clicked.connect(lambda _, s=slot: self.select_slot(s))
            self.slot_buttons[slot] = button
            units.add(button)
        box.addWidget(units)

        self.enabled = ToggleRow("Use this unit")
        self.priority = number(1, 99, width=90)
        self.priority.setToolTip("Lower goes first")
        self.count = number(-1, 99, special="all", width=90)
        self.count.setToolTip("More than the game allows is fine: it stops at the game's limit")
        self.upgrade = number(-1, 99, special="max", width=90)
        self.upgrade.setToolTip("Higher than the unit's max is fine: it stops when the game says Maxed")
        self.targeting = QComboBox()
        self.targeting.addItem("As it is")
        self.targeting.addItems(plans.TARGETING)
        self.targeting.setFixedWidth(130)
        self.from_wave = number(1, 999, width=90)
        settings = Card("Slot 1", icon_name="config", spacing=0)
        self.settings_title = settings.title
        rows(settings, self.enabled, SettingRow("Priority", self.priority), SettingRow("Placements", self.count),
             SettingRow("Upgrade to", self.upgrade), SettingRow("Targeting", self.targeting),
             SettingRow("From wave", self.from_wave))
        settings.box.addSpacing(8)
        clear = QPushButton("Clear its spots")
        clear.clicked.connect(self.clear_spots)
        settings.add(clear)
        box.addWidget(settings)
        box.addStretch(1)

        self.mode.currentIndexChanged.connect(self.refresh_maps)
        self.map.currentIndexChanged.connect(self.map_changed)
        self.plan_box.currentIndexChanged.connect(self.plan_changed)
        self.enabled.toggled.connect(self.settings_changed)
        for spin in (self.priority, self.count, self.upgrade, self.from_wave):
            spin.valueChanged.connect(self.settings_changed)
        self.targeting.currentIndexChanged.connect(self.settings_changed)
        return panel

    def _view(self):
        view = Card("Map view", icon_name="view")
        self.zoom = number(0, 12, width=70)
        self.zoom.setToolTip("Notches in from fully zoomed out: show the path, not the whole map")
        self.rotate = number(-4600, 4600, 5, width=90)
        self.rotate.setToolTip("Turns the camera. About 11 counts a degree. Paths should run along the guide lines")
        self.route = QLineEdit()
        self.route.setPlaceholderText("Walk from spawn, e.g. w:0.6,d:0.3  (blank: stay at spawn)")
        self.guides = Toggle(True)
        self.guides.setToolTip("Level guide lines over the picture")
        self.guides.toggled.connect(self.guides_toggled)
        self.take = QPushButton("Take picture")
        self.take.setObjectName("primary")
        self.take.setFixedWidth(160)
        self.take.setToolTip("Opens a free Sandbox on this map. Again there is quick.")
        self.take.clicked.connect(self.take_picture)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.addWidget(QLabel("Zoom in"), 0, 0)
        grid.addWidget(self.zoom, 0, 1)
        grid.addWidget(QLabel("Rotate"), 0, 2)
        grid.addWidget(self.rotate, 0, 3)
        guides = QHBoxLayout()
        guides.setSpacing(8)
        guides.addWidget(QLabel("Guides"))
        guides.addWidget(self.guides)
        guides.addStretch(1)
        grid.addLayout(guides, 0, 4)
        grid.addWidget(self.take, 0, 5, 2, 1)
        grid.addWidget(QLabel("Walk to"), 1, 0)
        grid.addWidget(self.route, 1, 1, 1, 4)
        grid.setColumnStretch(4, 1)
        view.add(grid)
        for widget in (self.zoom, self.rotate):
            widget.valueChanged.connect(self.view_changed)
        self.route.editingFinished.connect(self.view_changed)
        return view

    def _right(self):
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        order = Card("Build order  ·  drag to reorder", icon_name="order")
        self.order = QListWidget()
        self.order.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.order.model().rowsMoved.connect(self.order_moved)
        order.add(self.order, 1)
        rebuild = QPushButton("Rebuild from priorities")
        rebuild.clicked.connect(self.rebuild_order)
        order.add(rebuild)
        self.order.setToolTip("Once this runs out, units keep upgrading by priority up to their Upgrade to.")
        box.addWidget(order, 3)
        notes = Card("Notes", icon_name="notes")
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlaceholderText("Anything in the plan that had to be adjusted shows here.")
        notes.add(self.notes, 1)
        box.addWidget(notes, 2)
        return panel

    # ---------------------------------------------------------------------------- loading
    def on_open(self):
        self.refresh_maps()

    def refresh_maps(self):
        keep = self.map.currentData()
        self.loading = True
        self.map.clear()
        sandbox = self.mode.currentData() == "sandbox"
        model = QStandardItemModel(self.map)
        for name in STORY_MAPS:
            item = QStandardItem(name)
            item.setData(name, Qt.ItemDataRole.UserRole)
            if sandbox and name not in SANDBOX_BUTTONS:
                item.setEnabled(False)
                item.setText(f"{name}  (not in Sandbox)")
            model.appendRow(item)
        self.map.setModel(model)
        self.map.setCurrentIndex(max(0, self.map.findData(keep or "Flaming Monastery")))
        self.loading = False
        self.map_changed()

    @property
    def folder(self):
        return folder_of(self.map.currentData())

    def map_changed(self):
        if self.loading or not self.map.currentData():
            return
        folder = self.folder
        path = os.path.join(plans.MAPS, folder, "profile.yaml")
        self.profile = maps.load_profile(folder) if os.path.exists(path) else maps.MapProfile(folder, zoom_in_notches=1)
        self.loading = True
        self.zoom.setValue(self.profile.zoom_in_notches)
        self.rotate.setValue(self.profile.yaw_counts)
        self.route.setText(",".join(f"{k}:{v}" for k, v in self.profile.route))
        self.plan_box.clear()
        self.plan_box.addItems(plans.names(folder) or ["story"])
        self.loading = False
        self.load_picture()
        self.plan_changed()

    def load_picture(self):
        """The map's reference picture and the slot icons cut from it. Kept while the file is
        unchanged: read and converted on every open it was ~30 ms of opening Main (13 Nov 2026)."""
        path = self.profile.reference_path
        try:
            key = (path, os.path.getmtime(path))
        except OSError:
            key = (path, None)
        if getattr(self, "_picture_key", None) == key:
            return
        self._picture_key = key
        image = cv2.imread(path)
        self.canvas.set_picture(to_pixmap(image) if image is not None else None)
        for slot, button in self.slot_buttons.items():
            if image is not None:
                x = SLOT_X[slot - 1]
                button.setIcon(QIcon(to_pixmap(image[694:770, x - 38:x + 38])))
                button.setIconSize(QSize(30, 30))
            else:
                button.setIcon(QIcon())

    def plan_changed(self):
        if self.loading or not self.plan_box.currentText():
            return
        self.plan = plans.load(self.folder, self.plan_box.currentText())
        for slot in plans.SLOTS:
            if self.plan.unit(slot) is None:
                self.plan.units.append(plans.UnitPlan(slot, priority=slot))
        self.plan.units.sort(key=lambda u: u.slot)
        self.notes.setPlainText("\n".join(n for n in self.plan.notes if "No such file" not in n))
        self.select_slot(self.slot)
        self.refresh_all()

    def refresh_all(self):
        for slot, button in self.slot_buttons.items():
            unit = self.plan.unit(slot) if self.plan else None
            spots = len(unit.spots) if unit else 0
            off = "" if not unit or unit.enabled else "  ·  off"
            button.setText(f"   Slot {slot}   ·   {spots} spot{'s' if spots != 1 else ''}{off}")
        self.order.blockSignals(True)
        self.order.clear()
        if self.plan:
            for n, step in enumerate(self.plan.steps, start=1):
                word = "Place" if step["do"] == "place" else "Upgrade"
                item = QListWidgetItem(f"{n:>2}   {word}  slot {step['slot']} #{step['spot'] + 1}")
                item.setData(Qt.ItemDataRole.UserRole, step)
                item.setForeground(QColor(SLOT_COLORS[step["slot"]]) if step["do"] == "place" else QColor("#aab0c6"))
                self.order.addItem(item)
        self.order.blockSignals(False)
        self.canvas.update()

    def select_slot(self, slot):
        self.slot = slot
        self.slot_buttons[slot].setChecked(True)
        self.settings_title.setText(f"SLOT {slot}")
        unit = self.plan.unit(slot) if self.plan else None
        if unit is None:
            return
        self.loading = True
        self.enabled.setChecked(unit.enabled)
        self.priority.setValue(max(1, min(99, unit.priority)))
        self.count.setValue(-1 if unit.count is None else min(99, unit.count))
        self.upgrade.setValue(-1 if unit.upgrade_to is None else min(99, unit.upgrade_to))
        self.targeting.setCurrentIndex(max(0, self.targeting.findText(unit.targeting or "As it is")))
        self.from_wave.setValue(unit.from_wave)
        self.loading = False
        self.canvas.update()

    # ---------------------------------------------------------------------------- editing
    def note(self, text):
        self.notes.appendPlainText(text)

    def add_spot(self, x, y):
        if on_hud(x, y):
            self.note("That spot is over the game's buttons, so it wasn't added.")
            return
        self.plan.unit(self.slot).spots.append([x, y])
        self.commit()

    def remove_spot(self, unit, index):
        del unit.spots[index]
        kept = []
        for step in self.plan.steps:  # steps name spots by number, so later ones shift down
            if step["slot"] == unit.slot:
                if step["spot"] == index:
                    continue
                if step["spot"] > index:
                    step = {**step, "spot": step["spot"] - 1}
            kept.append(step)
        self.plan.steps = kept
        self.commit()

    def clear_spots(self):
        self.plan.unit(self.slot).spots = []
        self.plan.steps = [s for s in self.plan.steps if s["slot"] != self.slot]
        self.commit()

    def settings_changed(self):
        if self.loading or not self.plan:
            return
        unit = self.plan.unit(self.slot)
        unit.enabled = self.enabled.isChecked()
        unit.priority = self.priority.value()
        unit.count = None if self.count.value() < 0 else self.count.value()
        unit.upgrade_to = None if self.upgrade.value() < 0 else self.upgrade.value()
        unit.targeting = None if self.targeting.currentIndex() == 0 else self.targeting.currentText()
        unit.from_wave = self.from_wave.value()
        self.commit()

    def order_moved(self, *args):
        self.plan.steps = [self.order.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.order.count())]
        self.plan.custom_order = True
        self.commit()

    def rebuild_order(self):
        self.plan.custom_order = False
        self.commit()
        self.note("Build order rebuilt from priorities.")

    def commit(self):
        """Save through normalize, so what's shown is exactly what the macro will run."""
        plan = self.plan
        if not plan.custom_order:
            plan.steps = plans.generate_steps(plan)
        else:
            plans.reconcile(plan)
        raw = {"custom_order": plan.custom_order,
               "units": [{"slot": u.slot, "priority": u.priority, "count": u.count, "upgrade_to": u.upgrade_to,
                          "targeting": u.targeting, "from_wave": u.from_wave, "enabled": u.enabled, "spots": u.spots}
                         for u in plan.units],
               "steps": plan.steps}
        checked = plans.normalize(raw, plan.map, plan.name)
        plan.steps = checked.steps
        plans.save(plan)
        for text in checked.notes:
            self.note(text)
        self.refresh_all()
        self.main.plans_changed()

    def new_plan(self):
        name, ok = QInputDialog.getText(self, "New plan", "Name:")
        self._make_plan(name, ok, blank=True)

    def copy_plan(self):
        name, ok = QInputDialog.getText(self, "Copy plan", "Name of the copy:")
        self._make_plan(name, ok, blank=False)

    def _make_plan(self, name, ok, blank):
        name = "".join(ch for ch in (name or "") if ch.isalnum() or ch in "-_ ").strip()
        if not ok or not name:
            return
        if blank:
            plan = plans.Plan(self.folder, name, units=[plans.UnitPlan(s, priority=s) for s in plans.SLOTS])
        else:
            plan = plans.load(self.folder, self.plan_box.currentText())
            plan.name = name
        plans.save(plan)
        self.plan_box.addItem(name)
        self.plan_box.setCurrentText(name)
        self.main.plans_changed()

    def view_changed(self):
        if self.loading or not self.profile:
            return
        self.profile.zoom_in_notches = self.zoom.value()
        self.profile.yaw_counts = self.rotate.value()
        route = []
        for part in self.route.text().split(","):
            key, _, seconds = part.partition(":")
            try:
                if key.strip().lower() in ("w", "a", "s", "d") and 0 < float(seconds) <= 30:
                    route.append([key.strip().lower(), float(seconds)])
                elif part.strip():
                    self.note(f"Walk to: ignored {part.strip()!r}. Use like w:0.6,d:0.3")
            except ValueError:
                self.note(f"Walk to: ignored {part.strip()!r}. Use like w:0.6,d:0.3")
        self.profile.route = route
        self.profile.save()

    def guides_toggled(self, on):
        self.canvas.guides = on
        self.canvas.update()

    def take_picture(self):
        name = self.map.currentData()
        if name not in SANDBOX_BUTTONS:
            self.note(f"{name} can't be opened in Sandbox yet.")
            return
        if self.main.busy():
            self.note("Something is already running.")
            return
        self.view_changed()
        profile, button, bridge = self.profile, SANDBOX_BUTTONS[name], self.main.bridge
        self.take.setEnabled(False)
        self.take.setText("Taking...")
        self.main.toast(f"Opening a Sandbox on {name}. Hands off for a moment.")
        self.hide()  # the game has to be visible

        def work():
            try:
                bridge.picture.emit(take_picture(button, profile, bridge.log.emit))
            except Exception as error:
                bridge.picture.emit(f"couldn't take the picture: {error}")
        self.main.job = threading.Thread(target=work, daemon=True)
        self.main.job.start()

    def picture_done(self, text):
        self.take.setEnabled(True)
        self.take.setText("Take picture")
        self.note(text)
        self.loading = True
        self.rotate.setValue(self.profile.yaw_counts)
        self.loading = False
        self.load_picture()
        self.open()



