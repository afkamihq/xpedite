"""Tasks (what to play), Config (how the macro behaves), Extras (one-off tools) and About."""
from __future__ import annotations

import os
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QLabel,
                             QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSpinBox,
                             QVBoxLayout, QWidget)

from macro.control import plans
from macro.platform import links
from macro.nav.stages import STORY_MAPS
from macro.sched.runner import SANDBOX_BUTTONS, describe, folder_of
from ui import (Card, NavButton, SettingRow, SubWindow, Toggle, ToggleRow, label, load_yaml, number, rows, save_yaml,
                secret_field, show_row)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_FILE = os.path.join(ROOT, "data", "queue.yaml")
SETTINGS_FILE = os.path.join(ROOT, "data", "settings.yaml")
UNSUPPORTED_MAPS = {}
MODES = (("Story", "story", True), ("Sandbox test", "sandbox", True), ("Story Infinite", None, False),
         ("Story Mastery", None, False), ("Raid", None, False), ("Challenge", "challenge", True), ("Boss Rush", None, False),
         ("Expedition", "expedition", True), ("Tower", None, False), ("Soul Furnace", "furnace", True),
         ("Demonic Rift", None, False), ("The Ancient One", None, False), ("Trick or Treat", "trick", True))
DEFAULTS = {"collect": True, "webhook": "", "ping": "", "send_victory": True, "send_defeat": True, "send_end": True,
            "may_restart": True, "resume_idle": 2.0, "auto_resume": 3.0, "attach_on_launch": True,
            "live_glass": True, "repeat_queue": False, "auto_update": True,
            "upgrades": "plan", "refresh_hours": 1.0, "private_server": "", "fresh_start": True,
            "stop_at_time": "", "stop_at_candy": 0, "shutdown_when_done": False,
            "discord_token": "", "discord_app_id": "", "discord_channel": "", "discord_guild": "",
            "discord_owners": "", "discord_summary_hours": 3.0}


def load_settings() -> dict:
    return {**DEFAULTS, **load_yaml(SETTINGS_FILE, {})}


# ====================================================================================== Tasks
class TasksWindow(SubWindow):
    """Add a task (only the fields its mode uses) | the Soul plan (Soul Furnace only) | the queue.
    Rows and switches, no tips: the user (12 Nov 2026) wants it quick to scan."""

    def __init__(self, main):
        super().__init__(main, "Tasks", "What to play, in order", (1040, 640), "tasks")
        row = QHBoxLayout()
        row.setSpacing(12)

        self.mode = QComboBox()
        model = QStandardItemModel(self.mode)
        for text, value, built in MODES:
            item = QStandardItem(text if built else f"{text}  · soon")
            item.setData(value, Qt.ItemDataRole.UserRole)
            item.setEnabled(built)
            model.appendRow(item)
        self.mode.setModel(model)
        self.map = QComboBox()
        self.act = number(1, 5, width=70)
        self.difficulty = QComboBox()
        self.difficulty.addItems(["Normal", "Hard"])
        self.plan = QComboBox()
        for combo in (self.mode, self.map, self.difficulty, self.plan):
            combo.setFixedWidth(176)
        self.times = number(1, 99999, width=70)
        self.forever = Toggle()
        self.forever.toggled.connect(lambda on: self.times.setEnabled(not on))
        times = QWidget()
        times_box = QHBoxLayout(times)
        times_box.setContentsMargins(0, 0, 0, 0)
        times_box.setSpacing(8)
        times_box.addWidget(self.times)
        times_box.addWidget(label("Forever", "muted", wrap=False))
        times_box.addWidget(self.forever)
        self.task_rows = {name: SettingRow(name, widget) for name, widget in
                          (("Mode", self.mode), ("Map", self.map), ("Act", self.act),
                           ("Difficulty", self.difficulty), ("Plan", self.plan), ("Times", times))}
        add = QPushButton("Add to queue")
        add.setObjectName("primary")
        add.clicked.connect(self.add_entry)
        adding = Card("Add a task", icon_name="add", spacing=0)
        rows(adding, *self.task_rows.values())
        adding.box.addSpacing(10)
        adding.add(add)
        adding.box.addStretch(1)
        adding.setFixedWidth(300)
        row.addWidget(adding)
        row.addWidget(self._souls_card())
        row.addWidget(self._expedition_card())

        self.items = QListWidget()
        self.items.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.items.setWordWrap(True)
        self.items.model().rowsMoved.connect(lambda *a: self.save())
        buttons = QGridLayout()
        buttons.setSpacing(8)
        for index, (text, action) in enumerate((("Duplicate", self.duplicate), ("Remove", self.remove_selected),
                                                ("Up", lambda: self.shift(-1)), ("Down", lambda: self.shift(1)),
                                                ("Clear", self.clear))):
            button = QPushButton(text)
            button.clicked.connect(action)
            buttons.addWidget(button, 0, index)
        queue = Card("Queue  ·  drag to reorder", icon_name="order")
        queue.add(self.items, 1)
        queue.add(buttons)
        self.start = QPushButton("Start queue  (F2)")
        self.start.setObjectName("primary")
        self.start.clicked.connect(main.start_run)
        queue.add(self.start)
        row.addWidget(queue, 1)
        self.body_box.addLayout(row, 1)

        self.map.currentIndexChanged.connect(self.refresh_plans)
        self.difficulty.currentIndexChanged.connect(
            lambda *a: self.exp_load_rule() if self.mode.currentData() == "expedition" else None)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        for entry in load_yaml(QUEUE_FILE, []):
            self._append(entry)
        self.mode_changed()

    def _souls_card(self):
        """Where the Soul Furnace's Souls go after SPA is maxed (the layout's "souls:" section,
        read by every run): the user's plan, 11 Nov 2026. Top to bottom is the order."""
        from macro.modes import souls
        names_tip = "The start of a unit's name. Cid = atom, Starrk = wolf, Alucard = impaler, Ichigo = reaper."

        def field(placeholder, tip=names_tip):
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setToolTip(tip)
            edit.setFixedWidth(170)
            return edit

        self.souls_ours = field("atom x3")
        self.souls_extra = ToggleRow("Random Units")
        self.souls_new = field("wolf, atom, impaler")
        self.souls_bin = number(0, 999, special="never", width=70)
        self.souls_more = field("blade x3")
        self.souls_boosts = field("dmg, rng", "dmg, rng or spa, in order")
        self.souls_boosts_from = number(0, 1_000_000, 100, special="off", width=70)
        self.souls_boosts_wave = number(0, 999, special="off", width=70)
        self.souls_boosts_wave.setToolTip("From this wave, once the Random Units are done, DMG/RNG come "
                                          "before more Unbound Tomes")
        self.souls_boss = ToggleRow("Final Boss")
        self.souls_save_from = number(1, 999, width=70)
        self.souls_boss_wave = number(1, 999, width=70)
        self.save_row = SettingRow("Save from wave", self.souls_save_from)
        self.buy_row = SettingRow("Buy from wave", self.souls_boss_wave)
        card = Card("Souls  ·  after SPA max", icon_name="config", spacing=0)
        card.setFixedWidth(340)
        rows(card, SettingRow("Unbound, ours", self.souls_ours), self.souls_extra,
             SettingRow("Unbound, new units", self.souls_new), SettingRow("Bin hotbar from wave", self.souls_bin),
             SettingRow("Then Unbound", self.souls_more), SettingRow("Boosts", self.souls_boosts),
             SettingRow("Boosts from wave", self.souls_boosts_wave),
             SettingRow("or past Candy Corn", self.souls_boosts_from), self.souls_boss, self.save_row, self.buy_row)
        card.box.addStretch(1)

        config = souls.load_config()
        self._souls_config = config
        self.souls_ours.setText(souls.show_counts(config.unbound))
        self.souls_new.setText(", ".join(config.unbound_new))
        self.souls_extra.setChecked(config.extra_units)
        self.souls_bin.setValue(config.bin_after_wave)
        self.souls_boosts.setText(", ".join(config.boosts))
        self.souls_boosts_from.setValue(int(config.boosts_from_candy or 0))
        self.souls_boosts_wave.setValue(int(config.boosts_from_wave or 0))
        self.souls_boss.setChecked(config.final_boss)
        self.souls_more.setText(souls.show_counts(config.unbound_more))
        self.souls_save_from.setValue(config.final_boss_save_from)
        self.souls_boss_wave.setValue(config.final_boss_wave)
        for edit in (self.souls_ours, self.souls_new, self.souls_boosts, self.souls_more):
            edit.setCursorPosition(0)  # long lists show their start
        self._boss_rows(config.final_boss)
        self.souls_boss.toggled.connect(self._boss_rows)
        for edit in (self.souls_ours, self.souls_new, self.souls_boosts, self.souls_more):
            edit.editingFinished.connect(self.save_souls)
        for switch in (self.souls_extra, self.souls_boss):
            switch.toggled.connect(self.save_souls)
        for box in (self.souls_bin, self.souls_boosts_from, self.souls_boosts_wave, self.souls_save_from,
                    self.souls_boss_wave):
            box.valueChanged.connect(self.save_souls)
        self.souls_card = card
        card.setVisible(False)
        return card

    # ------------------------------------------------------------------ Expedition
    def _expedition_card(self):
        """Expedition settings: the reroll minimums for the map and difficulty picked on the left,
        then how runs are played (data/expedition.yaml). A minimum of 0 is off."""
        from macro.modes import expedition
        self._exp = expedition.load_settings()
        self.exp_reroll = ToggleRow("Reroll until a route qualifies")
        self.exp_match = QComboBox()
        self.exp_match.addItems(["All of them", "Any one of them"])
        self.exp_max = number(0, 9999, width=70)
        self.exp_none = QComboBox()
        self.exp_none.addItems(["Play the best seen", "Play the current one", "Skip to the next task", "Stop"])
        self.exp_capped = ToggleRow("Capped items count as 0")
        self.exp_min = {}
        for name in expedition.RESOURCES:
            box = number(0, 1_000_000, special="off", width=80)
            self.exp_min[name] = box
        self.exp_hire = ToggleRow("Hire units at checkpoints")
        self.exp_hire_max = number(0, 4, width=70)
        self.exp_tomes = ToggleRow("Tomes: Unbound for units, Investor for farms")
        self.exp_tomes_own = ToggleRow("Tomes on my own units (for good)")
        self.exp_tomes_own.setToolTip("A tome used in an Expedition changes the unit's trait permanently. "
                                      "Off: tomes only go on units hired in the run.")
        self.exp_upgrades = QComboBox()
        self.exp_upgrades.addItems(["Auto Upgrade, farms first", "The macro clicks upgrades"])
        self.exp_anvils = ToggleRow("Anvils at every shop")
        self.exp_bank = number(0, 200000, 1000, special="spend it all", width=90)
        self.exp_repair = number(0, 2000, 50, special="never", width=70)
        self.exp_hero = ToggleRow("Barter with The Hero (500 Yen)")
        self.exp_extract = QComboBox()
        self.exp_extract.addItems(["Never", "Payload HP below", "After N nodes"])
        self.exp_extract_at = number(0, 5000, width=70)
        self.exp_levelups = QLineEdit()
        self.exp_levelups.setPlaceholderText("Fortified Cargo, Yen Hunger, ...")
        self.exp_levelups.setFixedWidth(170)
        self.exp_anvil_cards = QLineEdit()
        self.exp_anvil_cards.setPlaceholderText("Bonus Match, Critical Chance, ...")
        self.exp_anvil_cards.setToolTip("Stat Anvil cards, first wanted first. Every card the macro sees is "
                                        "listed in data/expedition/anvil_cards.yaml.")
        self.exp_anvil_cards.setFixedWidth(170)
        self.exp_title = label("", "muted", wrap=False)

        inner = QWidget()
        box = QVBoxLayout(inner)
        box.setContentsMargins(0, 0, 6, 0)
        box.setSpacing(0)
        for widget in (self.exp_title, self.exp_reroll, SettingRow("Need", self.exp_match),
                       SettingRow("Max rerolls", self.exp_max), SettingRow("When none qualifies", self.exp_none),
                       self.exp_capped):
            box.addWidget(widget)
        box.addSpacing(6)
        box.addWidget(label("Minimums on the route, at the start and at each checkpoint", "muted", wrap=False))
        self.exp_route_check = ToggleRow("Extract when the rest falls short")
        box.addWidget(self.exp_route_check)
        # The map's own material and Fuel Cells first (user: the materials and the blue Fuel Cells
        # are what an Expedition is farmed for); the other maps' materials are hidden.
        materials = set(expedition.MATERIAL.values())
        order = ["Fuel Cell"] + [r for r in expedition.RESOURCES if r != "Fuel Cell"]
        self.exp_min_rows = {}
        for name in sorted(order, key=lambda r: (r not in materials, order.index(r))):
            row = SettingRow(name, self.exp_min[name])
            self.exp_min_rows[name] = row
            box.addWidget(row)
        box.addSpacing(6)
        box.addWidget(label("Every Expedition", "muted", wrap=False))
        for widget in (SettingRow("Upgrades", self.exp_upgrades), self.exp_anvils,
                       SettingRow("Yen kept for the shop", self.exp_bank),
                       self.exp_hire, SettingRow("Hires per run", self.exp_hire_max), self.exp_tomes,
                       self.exp_tomes_own,
                       SettingRow("Repair Hammer below HP", self.exp_repair), self.exp_hero,
                       SettingRow("Extract", self.exp_extract), SettingRow("Extract at", self.exp_extract_at),
                       SettingRow("Level-up cards", self.exp_levelups),
                       SettingRow("Anvil cards", self.exp_anvil_cards)):
            box.addWidget(widget)
        box.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner.setObjectName("expInner")
        scroll.setStyleSheet("QScrollArea { background: transparent; } #expInner { background: transparent; }")
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(inner)
        card = Card("Expedition", icon_name="config", spacing=0)
        card.setFixedWidth(360)
        card.add(scroll, 1)

        g = self._exp
        self.exp_hire.setChecked(bool(g["hire"].get("on")))
        self.exp_hire_max.setValue(int(g["hire"].get("max", 2)))
        self.exp_tomes.setChecked(bool(g["shop"].get("tomes", True)))
        self.exp_tomes_own.setChecked(bool(g["shop"].get("tomes_on_own", False)))
        self.exp_upgrades.setCurrentIndex(0 if g.get("upgrades", "auto") == "auto" else 1)
        self.exp_anvils.setChecked(bool(g["shop"].get("anvils", True)))
        self.exp_bank.setValue(int(g["shop"].get("keep_for_shop", 10000)))
        self.exp_repair.setValue(int(g["shop"].get("repair_below", 0)))
        self.exp_hero.setChecked((g.get("encounters") or {}).get("The Hero", "barter") == "barter")
        self.exp_extract.setCurrentIndex({"never": 0, "hp_below": 1, "after_nodes": 2}.get(g["extract"].get("rule"), 0))
        self.exp_extract_at.setValue(int(g["extract"].get("hp_below" if g["extract"].get("rule") != "after_nodes" else "after_nodes", 0)))
        self.exp_levelups.setText(", ".join(g.get("levelup_priority") or []))
        self.exp_route_check.setChecked(bool(g["extract"].get("route_check", True)))
        self.exp_levelups.setCursorPosition(0)
        self.exp_anvil_cards.setText(", ".join(g.get("anvil_priority") or []))
        self.exp_anvil_cards.setCursorPosition(0)
        self._exp_key = None
        self.exp_load_rule()
        for switch in (self.exp_reroll, self.exp_capped, self.exp_hire, self.exp_tomes, self.exp_tomes_own,
                       self.exp_hero, self.exp_anvils,
                       self.exp_route_check):
            switch.toggled.connect(self.save_expedition)
        for combo in (self.exp_match, self.exp_none, self.exp_extract, self.exp_upgrades):
            combo.currentIndexChanged.connect(self.save_expedition)
        for spin in [self.exp_max, self.exp_hire_max, self.exp_repair, self.exp_extract_at, self.exp_bank,
                     *self.exp_min.values()]:
            spin.valueChanged.connect(self.save_expedition)
        self.exp_levelups.editingFinished.connect(self.save_expedition)
        self.exp_anvil_cards.editingFinished.connect(self.save_expedition)
        self.expedition_card = card
        card.setVisible(False)
        return card

    def _exp_stage(self):
        name = self.map.currentData() or "School Grounds"
        try:
            difficulty = int(self.difficulty.currentText() or 1)
        except ValueError:
            difficulty = 1
        return name, difficulty

    def exp_load_rule(self):
        """Show the reroll rule of the map and difficulty picked on the left."""
        from macro.modes import expedition
        name, difficulty = self._exp_stage()
        if name not in expedition.MAPS:
            return
        self._exp_key = None  # no saving while the boxes are filled
        for res, row in self.exp_min_rows.items():
            show_row(row, res not in expedition.MATERIAL.values() or res == expedition.MATERIAL[name])
        rule = expedition.rule_for(self._exp, name, difficulty)
        self.exp_title.setText(f"{name}, difficulty {difficulty}")
        self.exp_reroll.setChecked(bool(rule.get("reroll", True)))
        self.exp_match.setCurrentIndex(0 if rule.get("match", "all") == "all" else 1)
        self.exp_max.setValue(int(rule.get("max_rerolls", 50)))
        self.exp_none.setCurrentIndex(["best", "current", "skip", "stop"].index(rule.get("when_none", "best")))
        self.exp_capped.setChecked(bool(rule.get("capped_counts_zero", True)))
        for res, box in self.exp_min.items():
            m = rule["minimums"].get(res) or {}
            box.setValue(int(m.get("min", 0)) if m.get("on") else 0)
        self._exp_key = f"{name}|{difficulty}"

    def save_expedition(self, *args):
        from macro.modes import expedition
        g = self._exp
        if self._exp_key:
            g.setdefault("maps", {})[self._exp_key] = {
                "reroll": self.exp_reroll.isChecked(),
                "match": "all" if self.exp_match.currentIndex() == 0 else "any",
                "max_rerolls": self.exp_max.value(),
                "when_none": ["best", "current", "skip", "stop"][self.exp_none.currentIndex()],
                "capped_counts_zero": self.exp_capped.isChecked(),
                "minimums": {res: {"on": box.value() > 0, "min": box.value()}
                             for res, box in self.exp_min.items() if box.value() > 0},
            }
        g["hire"] = {**g.get("hire", {}), "on": self.exp_hire.isChecked(), "max": self.exp_hire_max.value()}
        g["shop"] = {**g.get("shop", {}), "tomes": self.exp_tomes.isChecked(), "repair_below": self.exp_repair.value(),
                     "anvils": self.exp_anvils.isChecked(), "keep_for_shop": self.exp_bank.value(),
                     "tomes_on_own": self.exp_tomes_own.isChecked()}
        g["upgrades"] = "auto" if self.exp_upgrades.currentIndex() == 0 else "manual"
        g.setdefault("encounters", {})["The Hero"] = "barter" if self.exp_hero.isChecked() else "leave"
        rule = ["never", "hp_below", "after_nodes"][self.exp_extract.currentIndex()]
        g["extract"] = {**g.get("extract", {}), "rule": rule, "route_check": self.exp_route_check.isChecked()}
        if rule != "never":
            g["extract"][rule] = self.exp_extract_at.value()
        g["levelup_priority"] = [n.strip() for n in self.exp_levelups.text().split(",") if n.strip()]
        g["anvil_priority"] = [n.strip() for n in self.exp_anvil_cards.text().split(",") if n.strip()]
        try:
            expedition.save_settings(g)
        except OSError as error:
            self.main.toast(f"Couldn't save the Expedition settings: {error}", "warn")

    def _boss_rows(self, on):
        show_row(self.save_row, on)
        show_row(self.buy_row, on)

    def save_souls(self, *args):
        from macro.modes import souls
        config = self._souls_config
        config.unbound = souls.parse_counts(self.souls_ours.text())
        config.unbound_new = [souls._key(n) for n in self.souls_new.text().split(",") if souls._key(n)]
        config.extra_units = self.souls_extra.isChecked()
        config.bin_after_wave = self.souls_bin.value()
        config.boosts = [b for b in (souls._key(n) for n in self.souls_boosts.text().split(","))
                         if b in ("dmg", "rng", "spa")]
        config.boosts_from_candy = self.souls_boosts_from.value()
        config.boosts_from_wave = self.souls_boosts_wave.value()
        config.final_boss = self.souls_boss.isChecked()
        config.unbound_more = souls.parse_counts(self.souls_more.text())
        config.final_boss_save_from = self.souls_save_from.value()
        config.final_boss_wave = self.souls_boss_wave.value()
        try:
            souls.save_config(config)
        except OSError as error:
            self.main.toast(f"Couldn't save the Soul plan: {error}", "warn")

    def on_open(self):
        self.refresh_maps()

    def refresh_maps(self):
        keep = self.map.currentData()
        sandbox = self.mode.currentData() == "sandbox"
        model = QStandardItemModel(self.map)
        if self.mode.currentData() == "trick":
            # No map to pick: the macro goes round the lobby's Ethereal Doors, and a Trick's map is
            # read when it happens.
            item = QStandardItem("Lobby doors")
            item.setData("Trick or Treat", Qt.ItemDataRole.UserRole)
            model.appendRow(item)
            self.map.setModel(model)
            self.plan.clear()
            self.plan.addItem("story")
            return
        if self.mode.currentData() == "furnace":
            # One stage: the Halloween event's Soul Furnace, Infinite Hard. Plans are the map's own.
            item = QStandardItem("Infinite Hard")
            item.setData("Soul Furnace", Qt.ItemDataRole.UserRole)
            model.appendRow(item)
            self.map.setModel(model)
            self.plan.clear()
            # "paths" (units over all three paths, placed from several spots) is the one that's
            # played and tuned; the others were first tries.
            names = plans.names("soul_furnace") or ["paths"]
            self.plan.addItems(sorted(names, key=lambda n: n != "paths"))
            return
        if self.mode.currentData() == "expedition":
            from macro.modes import expedition
            for name in expedition.MAPS:
                item = QStandardItem(name)
                item.setData(name, Qt.ItemDataRole.UserRole)
                model.appendRow(item)
            self.map.setModel(model)
            self.map.setCurrentIndex(max(0, self.map.findData(keep)))
            self.plan.clear()
            self.plan.addItem("tail")
            self.exp_load_rule()
            return
        if self.mode.currentData() == "challenge":
            # The stage is read from the Challenges window when it's played: the choice here is
            # which tab, and the macro takes the offer it has a plan for, Trait Crystals first.
            for text, value in (("Regular", "Regular"), ("Daily", "Daily")):
                item = QStandardItem(text)
                item.setData(value, Qt.ItemDataRole.UserRole)
                model.appendRow(item)
            self.map.setModel(model)
            self.map.setCurrentIndex(max(0, self.map.findData(keep)))
            self.plan.clear()
            self.plan.addItem("story")
            return
        for name in STORY_MAPS:
            has_picture = os.path.exists(os.path.join(plans.MAPS, folder_of(name), "reference.png"))
            problem = (UNSUPPORTED_MAPS.get(name) or (None if has_picture else "not set up")
                       or ("no Sandbox" if sandbox and name not in SANDBOX_BUTTONS else None))
            item = QStandardItem(name + (f"  · {problem}" if problem else ""))
            item.setData(name, Qt.ItemDataRole.UserRole)
            item.setEnabled(problem is None)
            model.appendRow(item)
        self.map.setModel(model)
        self.map.setCurrentIndex(max(0, self.map.findData(keep or "Flaming Monastery")))
        self.refresh_plans()

    def refresh_plans(self):
        if self.mode.currentData() == "expedition":
            self.exp_load_rule()
            return
        if self.mode.currentData() in ("furnace", "trick", "challenge"):
            return
        name = self.map.currentData()
        keep = self.plan.currentText()
        self.plan.clear()
        if name:
            self.plan.addItems(plans.names(folder_of(name)))
        if self.plan.findText(keep) >= 0:
            self.plan.setCurrentText(keep)

    def mode_changed(self):
        mode = self.mode.currentData()
        self.souls_card.setVisible(mode == "furnace")
        self.expedition_card.setVisible(mode == "expedition")
        wanted = ["1", "2", "3"] if mode == "expedition" else ["Normal", "Hard"]
        if [self.difficulty.itemText(i) for i in range(self.difficulty.count())] != wanted:
            self.difficulty.blockSignals(True)
            self.difficulty.clear()
            self.difficulty.addItems(wanted)
            self.difficulty.blockSignals(False)
        show_row(self.task_rows["Act"], mode == "story")
        show_row(self.task_rows["Difficulty"], mode in ("story", "expedition"))
        show_row(self.task_rows["Plan"], mode not in ("challenge", "trick", "expedition"))
        self.task_rows["Map"].findChild(QLabel).setText({"challenge": "Tab", "furnace": "Stage",
                                                          "trick": "Where"}.get(mode, "Map"))
        self.refresh_maps()

    def add_entry(self):
        if not self.map.currentData() or not self.map.model().item(self.map.currentIndex()).isEnabled():
            self.main.toast("Pick a map that's set up first", "warn")
            return
        entry = {"mode": self.mode.currentData(), "map": self.map.currentData(), "act": self.act.value(),
                 "difficulty": self.difficulty.currentText(), "plan": self.plan.currentText() or "story",
                 "times": 0 if self.forever.isChecked() else self.times.value()}
        if entry["mode"] == "expedition":
            entry["difficulty"] = int(entry["difficulty"])
            entry.pop("act")
        self._append(entry)
        self.save()

    def _append(self, entry, row=None):
        item = QListWidgetItem(describe(entry))
        item.setData(Qt.ItemDataRole.UserRole, entry)
        if row is None:
            self.items.addItem(item)
        else:
            self.items.insertItem(row, item)

    def entries(self):
        return [self.items.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.items.count())]

    def duplicate(self):
        for item in self.items.selectedItems():
            self._append(dict(item.data(Qt.ItemDataRole.UserRole)), self.items.row(item) + 1)
        self.save()

    def shift(self, step):
        row = self.items.currentRow()
        if row < 0 or not 0 <= row + step < self.items.count():
            return
        item = self.items.takeItem(row)
        self.items.insertItem(row + step, item)
        self.items.setCurrentRow(row + step)
        self.save()

    def remove_selected(self):
        for item in self.items.selectedItems():
            self.items.takeItem(self.items.row(item))
        self.save()

    def clear(self):
        self.items.clear()
        self.save()

    def save(self):
        save_yaml(QUEUE_FILE, self.entries())
        self.main.queue_changed()


# ===================================================================================== Config
class ConfigWindow(SubWindow):
    """Every setting as one short row: toggles, numbers and fields, in a few sections. No prose:
    the user (12 Nov 2026) wants it quick to scan, no checkboxes, nothing obvious spelled out."""

    def __init__(self, main):
        super().__init__(main, "Config", "How the macro behaves", (900, 700), "config")
        self.settings = load_settings()
        s = self.settings

        def spin(low, high, step, suffix, special="", decimals=True):
            box = QDoubleSpinBox() if decimals else QSpinBox()
            box.setRange(low, high)
            box.setSingleStep(step)
            box.setSuffix(suffix)
            if decimals:
                box.setDecimals(1)
            if special:
                box.setSpecialValueText(special)
            box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            box.setFixedWidth(110)
            return box

        def field(placeholder, width=230):
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setFixedWidth(width)
            return edit

        # ---------------------------------------------------------------- left column
        self.attach_on_launch = ToggleRow("Attach Roblox on open")
        self.fresh_start = ToggleRow("Fresh Roblox each session")
        self.may_restart = ToggleRow("Restart a frozen Roblox")
        self.repeat_queue = ToggleRow("Repeat the queue")
        self.collect = ToggleRow("Collect rewards after matches")
        self.auto_upgrades = ToggleRow("Game's own Auto Upgrade")
        self.live_glass = ToggleRow("Glass lit by the game")
        self.auto_update = ToggleRow("Update by itself")
        run = Card("Run", icon_name="play", spacing=0)
        rows(run, self.attach_on_launch, self.fresh_start, self.may_restart, self.repeat_queue, self.collect,
             self.auto_upgrades, self.live_glass, self.auto_update)

        self.auto_resume = spin(0, 600, 1.0, " s", "off")
        self.resume_idle = spin(0.5, 30.0, 0.5, " s")
        self.refresh_hours = spin(0, 24, 0.5, " h", "never")
        timing = Card("Timing", icon_name="clock", spacing=0)
        rows(timing, SettingRow("Resume after a touch", self.auto_resume),
             SettingRow("Hands off before resuming", self.resume_idle),
             SettingRow("Restart Roblox every", self.refresh_hours))

        server_box, self.private_server = secret_field("roblox.com/share?code=...")
        server = Card("Private server", icon_name="link", spacing=0)
        server.add(server_box)
        self.private_server_note = label("", "dim")
        server.add(self.private_server_note)

        left = QVBoxLayout()
        left.setSpacing(12)
        for card in (run, timing, server):
            left.addWidget(card)
        left.addStretch(1)

        # ---------------------------------------------------------------- right column
        self.stop_at_time = field("HH:MM", 130)
        self.stop_at_candy = spin(0, 10_000_000, 1000, "", "never", decimals=False)
        self.shutdown_when_done = ToggleRow("Shut down when it ends")
        session = Card("Session", icon_name="session", spacing=0)
        rows(session, SettingRow("Stop at", self.stop_at_time), SettingRow("Stop after Candy Corn", self.stop_at_candy),
             self.shutdown_when_done)

        token_box, self.discord_token = secret_field("Bot token")
        token_box.setFixedWidth(230)
        self.discord_app_id = field("auto")
        self.discord_owners = field("auto: the bot's owner")
        self.discord_channel = field("Channel ID")
        self.discord_guild = field("Server ID")
        self.discord_summary = spin(0, 48, 1.0, " h", "never")
        discord = Card("Discord bot", icon_name="send", spacing=0)
        rows(discord, SettingRow("Token", token_box), SettingRow("Application", self.discord_app_id),
             SettingRow("Owner", self.discord_owners), SettingRow("Results channel", self.discord_channel),
             SettingRow("Server", self.discord_guild), SettingRow("Summary every", self.discord_summary))

        hook_box, self.webhook = secret_field("discord.com/api/webhooks/...")
        hook_box.setFixedWidth(230)
        self.ping = field("User ID to mention")
        self.send_victory = Toggle()
        self.send_defeat = Toggle()
        self.send_end = Toggle()
        sends = QWidget()
        sends_box = QHBoxLayout(sends)
        sends_box.setContentsMargins(0, 0, 0, 0)
        sends_box.setSpacing(8)
        for text, switch in (("Wins", self.send_victory), ("Losses", self.send_defeat), ("Ends", self.send_end)):
            sends_box.addWidget(label(text, "muted", wrap=False))
            sends_box.addWidget(switch)
        test = QPushButton("Test  F4")
        test.clicked.connect(main.test_webhook)
        hook = Card("Webhook", icon_name="hook", spacing=0, extra=test)
        rows(hook, SettingRow("Address", hook_box), SettingRow("Mention", self.ping), SettingRow("Send", sends))

        right = QVBoxLayout()
        right.setSpacing(12)
        for card in (session, discord, hook):
            right.addWidget(card)
        right.addStretch(1)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        self.body_box.addLayout(columns, 1)
        self.fit = True

        # ---------------------------------------------------------------- values and saving
        self.attach_on_launch.setChecked(s["attach_on_launch"])
        self.collect.setChecked(s["collect"])
        self.may_restart.setChecked(s["may_restart"])
        self.live_glass.setChecked(s["live_glass"])
        self.auto_update.setChecked(bool(s.get("auto_update", True)))
        self.repeat_queue.setChecked(s["repeat_queue"])
        self.fresh_start.setChecked(bool(s.get("fresh_start", True)))
        self.auto_upgrades.setChecked(s["upgrades"] == "auto")
        self.refresh_hours.setValue(float(s["refresh_hours"]))
        self.resume_idle.setValue(float(s["resume_idle"]))
        self.auto_resume.setValue(float(s.get("auto_resume", DEFAULTS["auto_resume"])))
        self.stop_at_time.setText(str(s.get("stop_at_time") or ""))
        self.stop_at_candy.setValue(int(s.get("stop_at_candy") or 0))
        self.shutdown_when_done.setChecked(bool(s.get("shutdown_when_done")))
        self.webhook.setText(s["webhook"])
        self.private_server.setText(str(s.get("private_server") or ""))
        self.private_server_note.setText(links.describe(self.private_server.text()))
        self.ping.setText(str(s["ping"]))
        self.send_victory.setChecked(s["send_victory"])
        self.send_defeat.setChecked(s["send_defeat"])
        self.send_end.setChecked(s["send_end"])
        for box in (self.attach_on_launch, self.collect, self.may_restart, self.live_glass, self.repeat_queue,
                    self.fresh_start, self.auto_upgrades, self.send_victory, self.send_defeat, self.send_end,
                    self.shutdown_when_done, self.auto_update):
            box.toggled.connect(self.save)
        self.discord_summary.setValue(float(s.get("discord_summary_hours", DEFAULTS["discord_summary_hours"]) or 0))
        for box in (self.resume_idle, self.auto_resume, self.refresh_hours, self.stop_at_candy, self.discord_summary):
            box.valueChanged.connect(self.save)
        for edit in (self.webhook, self.private_server, self.ping, self.stop_at_time):
            edit.editingFinished.connect(self.save)
        self.private_server.textChanged.connect(lambda text: self.private_server_note.setText(links.describe(text)))
        for edit, key in ((self.discord_token, "discord_token"), (self.discord_app_id, "discord_app_id"),
                          (self.discord_owners, "discord_owners"), (self.discord_channel, "discord_channel"),
                          (self.discord_guild, "discord_guild")):
            edit.setText(str(s.get(key) or ""))
            edit.editingFinished.connect(self.save_discord)

    def save(self, *args):
        ping = "".join(ch for ch in self.ping.text() if ch.isdigit())
        self.settings = {"collect": self.collect.isChecked(), "webhook": self.webhook.text().strip(), "ping": ping,
                         "send_victory": self.send_victory.isChecked(), "send_defeat": self.send_defeat.isChecked(),
                         "send_end": self.send_end.isChecked(), "may_restart": self.may_restart.isChecked(),
                         "resume_idle": self.resume_idle.value(), "auto_resume": self.auto_resume.value(),
                         "attach_on_launch": self.attach_on_launch.isChecked(),
                         "live_glass": self.live_glass.isChecked(), "repeat_queue": self.repeat_queue.isChecked(),
                         "auto_update": self.auto_update.isChecked(),
                         "upgrades": "auto" if self.auto_upgrades.isChecked() else "plan",
                         "refresh_hours": self.refresh_hours.value(),
                         "private_server": self.private_server.text().strip(),
                         "fresh_start": self.fresh_start.isChecked(),
                         "stop_at_time": self.stop_at_time.text().strip(),
                         "stop_at_candy": self.stop_at_candy.value(),
                         "shutdown_when_done": self.shutdown_when_done.isChecked(),
                         "discord_token": self.discord_token.text().strip(),
                         "discord_app_id": self.discord_app_id.text().strip(),
                         "discord_channel": self.discord_channel.text().strip(),
                         "discord_guild": self.discord_guild.text().strip(),
                         "discord_owners": self.discord_owners.text().strip(),
                         "discord_summary_hours": self.discord_summary.value()}
        save_yaml(SETTINGS_FILE, self.settings)

    def save_discord(self):
        """Saved, and the bot started again with the new settings (only if they changed)."""
        keys = ("discord_token", "discord_app_id", "discord_channel", "discord_guild", "discord_owners")
        before = {k: self.settings.get(k) for k in keys}
        self.save()
        if any(self.settings.get(k) != before[k] for k in keys):
            self.main.start_bot()


# ===================================================================================== Extras
class ExtrasWindow(SubWindow):
    def __init__(self, main):
        super().__init__(main, "Extras", "Tools", (680, 330), "extras")
        grid = QGridLayout()
        grid.setSpacing(12)
        tools = (
            ("gift", "Collect rewards", "Quests and battlepasses", main.collect_now),
            ("camera", "Screenshot", "To captures", main.screenshot),
            ("link", "Attach Roblox", "Into the frame", main.attach),
            ("unlink", "Detach Roblox", "Its own window", main.detach),
            ("logs", "Logs", "What it saw and did", lambda: open_folder("logs")),
            ("folder", "Captures", "Screenshots", lambda: open_folder("captures")),
        )
        for index, (icon_name, title, hint, action) in enumerate(tools):
            button = NavButton(icon_name, title, hint)
            button.setFixedHeight(64)
            button.clicked.connect(action)
            grid.addWidget(button, index // 2, index % 2)
        self.body_box.addLayout(grid)
        self.fit = True


def open_folder(name):
    path = os.path.join(ROOT, name)
    os.makedirs(path, exist_ok=True)
    subprocess.Popen(["explorer", path])


# ====================================================================================== About
class AboutWindow(SubWindow):
    def __init__(self, main, version):
        from macro import brand
        super().__init__(main, "About", brand.NAME, (560, 300), "about")
        info = Card(f"Version {version}", icon_name="info", spacing=0)
        info.add(label(f"{brand.UNIT}: the {brand.HUB} macro for {brand.GAME}. Free, and screen reading only.",
                       "muted"))
        self.body_box.addWidget(info)
        works = Card("Plays", icon_name="check")
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for name in ("Expeditions", "Soul Furnace", "Story", "Challenges", "Trick or Treat"):
            chip = label(name, "chip", wrap=False)
            chips.addWidget(chip)
        chips.addStretch(1)
        works.add(chips)
        self.body_box.addWidget(works)
        self.update_button = QPushButton("Check now")
        self.update_button.clicked.connect(self._update_clicked)
        updates = Card("Updates", icon_name="sync", spacing=0, extra=self.update_button)
        self.update_note = label("Not checked yet", "muted")
        updates.add(self.update_note)
        self.body_box.addWidget(updates)
        self.main_window = main
        self._release = None
        logs = NavButton("logs", "Something went wrong?", "The logs say what it saw and did")
        logs.setFixedHeight(60)
        logs.clicked.connect(lambda: open_folder("logs"))
        self.body_box.addWidget(logs)
        self.fit = True

    def show_update(self, state: str, release: dict | None, detail: str = "") -> None:
        """The Updates card: what the last check found (macro/update.py's states)."""
        self._release = release if state == "available" else None
        text = {"development": "A development copy: it updates through git.",
                "offline": "Couldn't reach GitHub. It tries again later.",
                "current": "Up to date.",
                "available": f"Version {release['version'] if release else '?'} is out." if release else "",
                "downloading": detail or "Downloading the update...",
                "failed": f"The update didn't install: {detail}"}.get(state, detail)
        self.update_note.setText(text)
        self.update_button.setText(f"Install {release['version']}" if self._release else "Check now")
        self.update_button.setEnabled(state != "downloading")

    def _update_clicked(self):
        if self._release:
            self.main_window.install_update(self._release)
        else:
            self.update_note.setText("Checking...")
            self.main_window.check_updates(manual=True)
