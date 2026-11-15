"""Setup: everything a new user needs set right before the macro can play, in one window.
Left, this PC and Roblox (read from Windows and Roblox's settings file, instantly) and a quick
start: the private server link and an Expedition task in three picks. Right, the game itself: one
button checks and sets the game's own settings and reads the team off the hotbar, then says how
the team compares with a good one.
"""
from __future__ import annotations

import os
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from theme import BAD, GOOD, WARN
from ui import Card, NavButton, SettingRow, SubWindow, icon, label, rows, secret_field

DONE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "setup_done")
ROLE_WORDS = {"dps": "Damage", "support": "Support", "farm": "Farm"}
# Quick start's Expedition goals -> minimums on the route (rerolled until a route promises them).
# Starting points from School Grounds difficulty 1 routes (15 Nov 2026: Cursed Timber 7-25, Fuel
# Cells 1-16 a route); Tasks changes them per map and difficulty.
GOALS = {"Its material": {"material": 18}, "Fuel Cells": {"Fuel Cell": 8},
         "Both": {"material": 15, "Fuel Cell": 6}, "Just play": {}}


def _row(ok: bool | None, title: str, found: str, fix: str = "") -> QWidget:
    row = QWidget()
    box = QHBoxLayout(row)
    box.setContentsMargins(2, 3, 2, 3)
    box.setSpacing(10)
    glyph, colour = ("check", GOOD) if ok else (("warn", WARN) if ok is None else ("warn", BAD))
    box.addWidget(icon(glyph, 9, colour), 0, Qt.AlignmentFlag.AlignTop)
    words = QVBoxLayout()
    words.setSpacing(1)
    top = QHBoxLayout()
    top.addWidget(label(title, wrap=False))
    top.addStretch(1)
    top.addWidget(label(found, "muted", wrap=False))
    words.addLayout(top)
    if fix:
        words.addWidget(label(fix, "dim"))
    box.addLayout(words, 1)
    return row


class SetupWindow(SubWindow):
    def __init__(self, main):
        super().__init__(main, "Setup", "Get everything ready to play", (900, 760), "config")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.pc = Card("This PC and Roblox", icon_name="game", spacing=2)
        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(self.pc, 1)
        second = NavButton("session", "Farm in a second session", "Keep using this PC while it plays")
        second.clicked.connect(self.open_second_session)
        left.addWidget(second)
        left.addWidget(self._quick_start())
        row.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(12)
        self.game = Card("The game's settings", icon_name="config", spacing=2)
        self.run_button = QPushButton("Check and fix in the game, then read my team")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run_in_game)
        self.game.add(label("Roblox needs to be open. It opens the game's Settings, sets what the macro "
                            "needs, then hovers each unit on your hotbar. Hands off for about a minute.", "dim"))
        self.game.add(self.run_button)
        self.game_rows = QVBoxLayout()
        self.game_rows.setSpacing(0)
        self.game.add(self.game_rows)
        right.addWidget(self.game)
        self.team = Card("Your team", icon_name="unit", spacing=2)
        self.team_rows = QVBoxLayout()
        self.team_rows.setSpacing(0)
        self.team.add(self.team_rows)
        self.team.add(label("Read in the step above.", "dim"))
        right.addWidget(self.team, 1)
        row.addLayout(right, 1)
        self.body_box.addLayout(row, 1)
        main.bridge.setup.connect(self.show_in_game)

    def on_open(self):
        from macro.setup.checks import all_offline_checks
        self._clear(self.pc.box, keep=1)
        checks = all_offline_checks()
        for check in checks:
            self.pc.add(_row(check.ok, f"{check.group}: {check.name}", check.found, check.fix))
        bad = sum(1 for c in checks if c.ok is False)
        self.pc.add(label("All set." if not bad else f"{bad} thing{'s' if bad != 1 else ''} to change.",
                          "muted"))
        self.pc.box.addStretch(1)

    def _quick_start(self) -> Card:
        """The private server and a first Expedition task, for players who'd rather not read Config
        and Tasks first."""
        from macro.modes import expedition
        from macro.platform import links
        card = Card("Quick start", icon_name="play", spacing=0)
        server_box, self.server = secret_field("roblox.com/share?code=...")
        server_box.setFixedWidth(230)
        self.server.setText(str(self.main.config.settings.get("private_server") or ""))
        self.server_note = label(links.describe(self.server.text()), "dim")
        self.server.textChanged.connect(lambda text: self.server_note.setText(links.describe(text)))
        self.server.editingFinished.connect(self.save_server)
        self.exp_map = QComboBox()
        self.exp_map.addItems(expedition.MAPS)
        self.exp_difficulty = QComboBox()
        self.exp_difficulty.addItems(["1", "2", "3"])
        self.exp_goal = QComboBox()
        self.exp_goal.addItems(list(GOALS))
        add = QPushButton("Add an Expedition task")
        add.setObjectName("primary")
        add.clicked.connect(self.add_expedition)
        rows(card, SettingRow("Private server", server_box))
        card.add(self.server_note)
        rows(card, SettingRow("Expedition", self.exp_map), SettingRow("Difficulty", self.exp_difficulty),
             SettingRow("Reroll for", self.exp_goal))
        card.add(add)
        return card

    def save_server(self):
        config = self.main.config
        if config.private_server.text().strip() != self.server.text().strip():
            config.private_server.setText(self.server.text().strip())
            config.save()
            self.main.toast("Private server saved", "good")

    def add_expedition(self):
        """Writes the map's reroll rule (data/expedition.yaml) and adds the task, forever."""
        from macro.modes import expedition
        name = self.exp_map.currentText()
        difficulty = int(self.exp_difficulty.currentText())
        goal = GOALS[self.exp_goal.currentText()]
        minimums = {(expedition.MATERIAL[name] if key == "material" else key): {"on": True, "min": least}
                    for key, least in goal.items()}
        settings = expedition.load_settings()
        settings.setdefault("maps", {})[f"{name}|{difficulty}"] = {
            "reroll": bool(minimums), "match": "all", "minimums": minimums, "max_rerolls": 50,
            "when_none": "best", "capped_counts_zero": True}
        expedition.save_settings(settings)
        tasks = self.main.tasks
        tasks._exp = expedition.load_settings()  # the Tasks card shows (and saves) the new rule
        tasks.exp_load_rule()
        tasks._append({"mode": "expedition", "map": name, "difficulty": difficulty, "plan": "tail", "times": 0})
        tasks.save()
        wanted = ", ".join(f"{k} {v['min']}" for k, v in minimums.items()) or "no rerolls"
        self.main.toast(f"Added: Expedition {name} D{difficulty}, forever ({wanted}). Start with F2.", "good")

    def open_second_session(self):
        """Made on first use: most players never open it."""
        if getattr(self.main, "second_session", None) is None:
            from second_session_window import SecondSessionWindow
            self.main.second_session = SecondSessionWindow(self.main)
        self.main.second_session.open()

    @staticmethod
    def _clear(layout, keep: int = 0):
        while layout.count() > keep:
            item = layout.takeAt(keep)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def run_in_game(self):
        if self.main.busy():
            self.main.toast("Wait until the run has stopped", "warn")
            return
        self.run_button.setEnabled(False)
        self.run_button.setText("Working in the game. Hands off...")
        from macro.sched.jobs import setup_in_game

        def work():
            self.main.bridge.setup.emit(setup_in_game(self.main.bridge.log.emit))
        self.main.job = threading.Thread(target=work, daemon=True)
        self.main.job.start()

    def show_in_game(self, result: dict):
        self.run_button.setEnabled(True)
        self.run_button.setText("Check and fix in the game, then read my team")
        self._clear(self.game_rows)
        self._clear(self.team_rows)
        if "error" in result:
            self.game_rows.addWidget(_row(False, "Couldn't finish", "", result["error"]))
            self.main.toast("Setup couldn't finish", "warn")
            return
        for s in result["settings"]:
            found = "not found" if s.found is None else ("on" if s.found else "off")
            if s.changed:
                found += ", just set"
            self.game_rows.addWidget(_row(s.found == s.wanted if s.found is not None else None, s.name, found,
                                          "" if s.found == s.wanted else f"Wanted {'on' if s.wanted else 'off'}: {s.why}"))
        for slot in result["team"]:
            role = ROLE_WORDS.get(slot.role or "", "Unknown role")
            self.team_rows.addWidget(_row(slot.known if slot.name else None, f"{slot.slot}. {slot.name or 'empty'}",
                                          role if slot.name else "", slot.note))
        for line in result["advice"]:
            self.team_rows.addWidget(label(f"•  {line}", "muted"))
        self.main.toast("Setup done: team preset updated", "good")
        try:
            with open(DONE_FILE, "w") as f:
                f.write("done\n")
        except OSError:
            pass
