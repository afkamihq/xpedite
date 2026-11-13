"""Setup: everything a new user needs set right before the macro can play, in one window.
Left, this PC and Roblox (read from Windows and Roblox's settings file, instantly). Right, the
game itself: one button checks and sets the game's own settings and reads the team off the
hotbar, then says how the team compares with a good one.
"""
from __future__ import annotations

import os
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from theme import BAD, GOOD, WARN
from ui import Card, SubWindow, icon, label

DONE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "setup_done")
ROLE_WORDS = {"dps": "Damage", "support": "Support", "farm": "Farm"}


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
        super().__init__(main, "Setup", "Get everything ready to play", (900, 640), "config")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.pc = Card("This PC and Roblox", icon_name="game", spacing=2)
        row.addWidget(self.pc, 1)

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
