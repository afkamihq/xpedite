"""Second session: farm in another Windows account over Remote Desktop and keep using this PC
(user, 15 Nov 2026). Left, what this PC has (macro/setup/second_session.py: read only, instant);
right, the steps in order, each with a button where xpedite can do it. Inside the farm session it
shows that session's own checks and steps instead. Players' guide: docs/SECOND_SESSION.md.
"""
from __future__ import annotations

import os
import threading

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from setup_window import _row
from ui import Card, NavButton, SubWindow, label

WRAPPER_PAGE = "https://github.com/cpdx4/RDPWrapKit"
ACCOUNTS_PAGE = "ms-settings:otherusers"


def _step(number: int, title: str, text: str = "") -> QWidget:
    widget = QWidget()
    widget.setObjectName("step")
    widget.setStyleSheet("QWidget#step { background: transparent; }")
    box = QVBoxLayout(widget)
    box.setContentsMargins(0, 4, 0, 0)
    box.setSpacing(1)
    box.addWidget(label(f"{number}   {title}", "navtitle", wrap=False))
    if text:
        box.addWidget(label(text, "dim"))
    return widget


def _button(text: str, action, name: str = "small") -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.clicked.connect(action)
    return button


class SecondSessionWindow(SubWindow):
    admin_done = pyqtSignal(dict)

    def __init__(self, main):
        super().__init__(main, "Second session", "Farm in another Windows account, keep using this PC",
                         (960, 680), "session")
        from macro.setup import second_session
        self.ss = second_session
        self.remote = second_session.in_remote_session()
        self.body_box.addWidget(label(
            "xpedite plays in its own Windows account over Remote Desktop: its own screen and cursor, so "
            "this PC stays yours. The wrapper that allows two sessions is yours to install; everything "
            "else is here.", "muted"))
        row = QHBoxLayout()
        row.setSpacing(12)
        self.checks = Card("This session" if self.remote else "This PC", icon_name="safety", spacing=0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: 0; }")
        holder = QWidget()
        holder.setObjectName("rows")
        holder.setStyleSheet("QWidget#rows { background: transparent; }")
        self.rows = QVBoxLayout(holder)
        self.rows.setContentsMargins(0, 4, 4, 0)
        self.rows.setSpacing(0)
        scroll.setWidget(holder)
        self.checks.add(scroll, 1)
        row.addWidget(self.checks, 3)

        self.steps = Card("Set it up", icon_name="order", spacing=6)
        guide = NavButton("notes", "The guide", "Every step, and what to do when it breaks")
        guide.clicked.connect(self.open_guide)
        self.steps.add(guide)
        if self.remote:
            self._session_steps()
        else:
            self._host_steps()
        self.steps.box.addStretch(1)
        bottom = QHBoxLayout()
        bottom.addWidget(_button("Check again", self.refresh))
        bottom.addStretch(1)
        if not self.remote:
            bottom.addWidget(_button("Undo admin settings", self.undo_admin))
        self.steps.add(bottom)
        row.addWidget(self.steps, 2)
        self.body_box.addLayout(row, 1)
        self.admin_done.connect(self._admin_finished)

    # ------------------------------------------------------------------------------ steps
    def _host_steps(self):
        self.steps.add(_step(1, "Install the wrapper yourself",
                             "RDPWrapKit is what xpedite was measured with. Antivirus may flag it: it isn't "
                             "Microsoft's. xpedite never installs it."))
        self.steps.add(_button("Open its page", lambda: os.startfile(WRAPPER_PAGE)))
        self.steps.add(_step(2, "The farm account", "A second Windows account, with a password."))
        pick = QHBoxLayout()
        self.account = QComboBox()
        self.account.currentTextChanged.connect(lambda _text: self.refresh())
        pick.addWidget(self.account, 1)
        pick.addWidget(_button("Make one", lambda: os.startfile(ACCOUNTS_PAGE)))
        self.steps.add(pick)
        self.admin_text = label("", "dim")
        self.steps.add(_step(3, "Admin settings"))
        self.steps.add(self.admin_text)
        self.admin_button = _button("Apply (Windows asks)", self.apply_admin, "primary")
        self.steps.add(self.admin_button)
        self.steps.add(_step(4, "Connection file", f"{self.ss.SIZE[0]}x{self.ss.SIZE[1]}, scaled into any "
                                                   "window, kept drawing when minimized."))
        self.steps.add(_button("Write it to the Desktop", self.write_file))
        self.steps.add(_step(5, "Connect", "Sign in with the farm account's password and tick Remember me. "
                                           f"In there, open xpedite from {self.ss.ROOT}."))
        self.steps.add(_button("Connect now", self.connect))

    def _session_steps(self):
        self.steps.add(_step(1, "Roblox in this account",
                             "Install it here and sign in with the Roblox account that farms. One Roblox "
                             "account plays in one place at a time."))
        self.steps.add(_step(2, "The farm's shortcut", "On this account's desktop, to start the farm."))
        self.steps.add(_button("Make the desktop shortcut", self.make_shortcut))
        self.steps.add(_step(3, "Setup here too", "Game settings and team, in this account's Roblox."))
        self.steps.add(_step(4, "While it plays",
                             "Minimize the Remote Desktop window; don't close it. Closed, the session has no "
                             "screen and the macro stops seeing the game. F8 in here stops it."))

    # ---------------------------------------------------------------------------- checks
    def on_open(self):
        if not self.remote:
            self.account.blockSignals(True)
            chosen = self.account.currentText() or self.ss.default_account() or ""
            self.account.clear()
            others = [a["name"] for a in self.ss.local_accounts() if a["name"].lower() != self.ss.me().lower()]
            self.account.addItems(others)
            if chosen in others:
                self.account.setCurrentText(chosen)
            self.account.blockSignals(False)
        self.refresh()

    def chosen(self) -> str | None:
        return None if self.remote else (self.account.currentText() or None)

    def refresh(self):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        items = self.ss.all_checks(self.chosen())
        for item in items:
            self.rows.addWidget(_row(item.ok, f"{item.group}: {item.name}", item.found,
                                     "" if item.ok else item.fix))
        bad = sum(1 for i in items if i.ok is False)
        self.rows.addWidget(label("All set." if not bad else f"{bad} thing{'s' if bad != 1 else ''} to change.",
                                  "muted"))
        self.rows.addStretch(1)
        if not self.remote:
            changes = self.ss.admin_changes(self.chosen())
            self.admin_text.setText("Will " + "; ".join(changes) + "." if changes else "Nothing to change.")
            self.admin_button.setEnabled(bool(changes))

    # ---------------------------------------------------------------------------- actions
    def open_guide(self):
        try:
            os.startfile(self.ss.GUIDE)
        except OSError:
            import subprocess
            subprocess.Popen(["notepad.exe", self.ss.GUIDE])

    def apply_admin(self):
        self._elevated(["--apply-admin"] + (["--account", self.chosen()] if self.chosen() else []))

    def undo_admin(self):
        self._elevated(["--undo-admin"])

    def _elevated(self, args):
        self.admin_button.setEnabled(False)
        self.admin_button.setText("Waiting for Windows...")
        threading.Thread(target=lambda: self.admin_done.emit(self.ss.run_elevated(args)), daemon=True).start()

    def _admin_finished(self, report: dict):
        self.admin_button.setText("Apply (Windows asks)")
        if "error" in report:
            self.main.toast(f"Admin settings: {report['error']}", "warn")
        else:
            done = report.get("done") or []
            self.main.toast("Admin settings: " + (", ".join(done) if done else "nothing to change")
                            + (". Connect again for them to take effect." if done else ""), "good")
        self.refresh()

    def write_file(self):
        account = self.chosen()
        if not account:
            self.main.toast("Pick the farm account first", "warn")
            return
        try:
            path = self.ss.write_connection_file(account)
        except OSError as error:
            self.main.toast(f"Couldn't write it: {error}", "warn")
            return
        self.main.toast(f"{os.path.basename(path)} is on your Desktop", "good")
        self.refresh()

    def connect(self):
        try:
            self.ss.connect()
        except (OSError, FileNotFoundError):
            self.main.toast("Write the connection file first", "warn")

    def make_shortcut(self):
        said = self.ss.make_shortcut()
        self.main.toast(said or "Shortcut made", "good")
        self.refresh()
