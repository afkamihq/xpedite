"""The log, set for reading: the time small and quiet, the words in the UI's own type, each
task opening with a heading, results, pauses and failures marked, the engine's working
detail stepped back, and a line that only repeats with new numbers ("waiting for 5850
Yen, have 2415") updated in place instead of piling up. The log file stays plain text.
"""
from __future__ import annotations

import html
import re
import time

from PyQt6.QtGui import QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

from theme import BAD, GOOD, WARN

TIME = "#6c7385"
TEXT = "#dfe4ee"
DETAIL = "#8d94a6"
HEAD = "#ffffff"
NUMBERS = re.compile(r"[-+]?\d[\d,.]*")
BAD_WORDS = ("failed", "error", "couldn't", "can't", "stopped because", "never", "lost")
WARN_WORDS = ("paused", "run ended", "stopped", "recovery", "trying despite", "skipped")


def _shape(text: str) -> str:
    """What a line says without its numbers: two lines alike in shape are the same news."""
    return NUMBERS.sub("#", text)


class LogView(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setObjectName("logview")
        self.setReadOnly(True)
        self.setMaximumBlockCount(4000)
        self.document().setDocumentMargin(2)
        self._last_shape = None

    def clear(self):
        super().clear()
        self._last_shape = None

    def add(self, text: str, stamp: str | None = None):
        stamp = stamp or time.strftime("%H:%M:%S")
        shape = _shape(text)
        # Only progress that merely ticks over collapses; a second unit placed is news.
        ticking = "waiting for" in text or text.strip().startswith("wave ")
        repeat = shape == self._last_shape and ticking
        self._last_shape = shape
        bar = self.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        line = self._render(text, stamp)
        if repeat:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            self.setTextCursor(cursor)
        self.appendHtml(line)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        spacing = QTextBlockFormat()
        spacing.setLineHeight(128, 1)  # proportional: a little air between lines
        if text.startswith("--- "):
            spacing.setTopMargin(7)
        cursor.mergeBlockFormat(spacing)
        if at_end:
            bar.setValue(bar.maximum())

    @staticmethod
    def _render(text: str, stamp: str) -> str:
        when = f"<span style='font-family: Cascadia Mono, Consolas; font-size: 10px; color: {TIME};'>{stamp}</span>&nbsp;&nbsp;&nbsp;"
        lower = text.lower()
        if text.startswith("--- "):
            body = text[4:]
            title, _, rest = body.partition(", run ")
            title = title.replace(", plan ", "  ·  plan ").replace(", x1", "")
            extra = f"&nbsp;&nbsp;<span style='color: {DETAIL};'>run {html.escape(rest)}</span>" if rest else ""
            return f"{when}<span style='color: {HEAD}; font-weight: 600;'>{html.escape(title)}</span>{extra}"
        if text.startswith("RESULT: "):
            outcome, _, rest = text[8:].partition(" ")
            color = GOOD if outcome in ("victory", "built") else BAD
            return (f"{when}<span style='color: {color}; font-weight: 600;'>{html.escape(outcome.capitalize())}</span>"
                    f"<span style='color: {TEXT};'> {html.escape(rest)}</span>")
        if text.startswith("  "):
            color = WARN if "RECOVERY" in text or "trying despite" in lower else DETAIL
            return f"{when}<span style='color: {color}; font-size: 11px;'>&nbsp;&nbsp;{html.escape(text.strip())}</span>"
        if any(word in lower for word in BAD_WORDS):
            color = BAD
        elif any(word in lower for word in WARN_WORDS):
            color = WARN
        else:
            color = TEXT
        return f"{when}<span style='color: {color};'>{html.escape(text)}</span>"
