"""Open the app and start its queue as soon as Roblox is attached, then leave it running: the
same as opening xpedite.bat and pressing Start, for unattended runs (scripts/farm.bat).
  .venv-win/Scripts/python.exe tools/run_app.py

Unattended means nobody is there to press Start again: a session that ends on an error (Roblox
not docked, lost, frozen, a dropped connection) is started again a minute later (12 Nov 2026:
an error at 03:30 ended the night's farming). Never after a stop by the user, a session goal
reached, or the spending safety stop; at most 20 restarts an hour.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))
import main as app_main  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

RESTART_AFTER_MS = 60_000
# A Roblox that never docks (13 Nov 2026, 00:15: stuck on "Failed to download or apply critical
# settings" over a slow connection) held the queue back for good: after this long the run starts
# anyway, and its fresh start closes that Roblox and opens a new one.
START_ANYWAY_S = 150
MAX_RESTARTS_AN_HOUR = 20

app = QApplication(sys.argv[:1])
window = app_main.MainWindow()
window.show()
tries = [0]
restarts: list = []


def start_when_attached():
    tries[0] += 1
    if window.attached and not window.attaching:
        window.start_run()
        return
    if tries[0] >= START_ANYWAY_S and not window.attaching:
        window.bridge.log.emit(f"Roblox didn't dock in {START_ANYWAY_S} s: starting anyway, with a fresh Roblox")
        window.start_run()
        return
    if tries[0] % 30 == 0 and not window.attaching:
        window.attach()  # F1, in case Roblox wasn't open yet
    QTimer.singleShot(1000, start_when_attached)


def tell(text: str, ping: bool = False):
    """A line in the Discord results channel (pinging the owners if `ping`), off the Qt thread."""
    import threading
    from macro.remote import bot
    b = bot.ACTIVE
    if b is None or not b.config.channel_id:
        return
    threading.Thread(target=b.alert if ping else b.post, args=(text,), daemon=True).start()


def on_finished(ending: str):
    text = str(ending)
    if text == "stopped" or text.startswith("finished") or "STOPPED BECAUSE" in text:
        return  # the user's stop, a goal reached or the queue done, or the spending safety stop
    if "ACCOUNT IN USE" in text:
        # Someone is playing on the farm's Roblox account (Error 273): starting again would throw
        # them out of their game, so it waits for a person (13 Nov 2026).
        window.bridge.log.emit("the Roblox account is being played somewhere else: not starting again by itself")
        tell("The farm stopped: its Roblox account joined a game somewhere else (Error 273), so it "
             "left that game alone. Use /start when you're done playing.", ping=True)
        return
    now = time.time()
    restarts[:] = [t for t in restarts if now - t < 3600]
    if len(restarts) >= MAX_RESTARTS_AN_HOUR:
        window.bridge.log.emit(f"{MAX_RESTARTS_AN_HOUR} restarts in an hour: not starting again by itself")
        tell(f"The farm has stopped: {MAX_RESTARTS_AN_HOUR} restarts in an hour, the last after: {text}. "
             f"It needs someone to look at it.", ping=True)
        return
    restarts.append(now)
    window.bridge.log.emit(f"the session ended ({text}); starting it again in {RESTART_AFTER_MS // 1000} s")
    tell(f"The session ended ({text[:300]}); starting it again in {RESTART_AFTER_MS // 1000} s.")

    def again():
        if not window.busy():
            tries[0] = 0
            start_when_attached()
    QTimer.singleShot(RESTART_AFTER_MS, again)


window.bridge.finished.connect(on_finished)
QTimer.singleShot(3000, start_when_attached)
sys.exit(app.exec())
