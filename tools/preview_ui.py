"""The app in look-only mode: every window and sub-window works to look at, with a sample run in the
panels, but nothing can reach the game or change what the farm uses.

For opening the app in a second Windows account while the farm runs in its Remote Desktop one
(user, 13 Nov 2026). In this mode:
- no Discord bot (a second one would fight the farm's over commands and its status line),
- no global hotkeys (F2 here would launch Roblox and end the farm's game: one Roblox account),
- Roblox is never started, closed or docked, and no mouse or keyboard input is sent,
- nothing in the project folder is written: settings, queue, plans and the farm's log stay as
  they are (a write goes to nowhere), so clicking around Config or Tasks changes nothing.

    .venv-win/Scripts/pythonw.exe tools/preview_ui.py
"""
import builtins
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))
os.chdir(ROOT)

# ---------------------------------------------------------------- nothing written in the project
_open = builtins.open


def _guarded_open(file, mode="r", *args, **kwargs):
    if any(m in mode for m in "wax+") and isinstance(file, (str, bytes, os.PathLike)):
        path = os.path.abspath(os.fsdecode(file))
        if path.lower().startswith(ROOT.lower()):
            return _open(os.devnull, mode, *args, **kwargs)
    return _open(file, mode, *args, **kwargs)


builtins.open = _guarded_open

# ---------------------------------------------------------------- nothing reaches Roblox or input
from macro.platform import windows  # noqa: E402


def _no_launch(self):
    raise RuntimeError("preview: Roblox isn't started from here")


windows.WindowsPlatform.launch_game = _no_launch
windows.WindowsPlatform.close_game = lambda self: None
windows.WindowsPlatform.dock_game = lambda self: False
windows.WindowsPlatform.undock_game = lambda self: None
windows.WindowsPlatform._send = lambda self, *inputs: None

import main as app_main  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

W = app_main.MainWindow


def _only_looking(self, *args, **kwargs):
    self.toast("Preview: this copy only shows the windows. The farm runs in Remote Desktop.", "warn")


for name in ("start_run", "collect_now", "attach", "detach", "screenshot", "test_webhook"):
    setattr(W, name, _only_looking)
W.register_hotkeys = lambda self: None
W.first_attach = lambda self: None
W.start_bot = lambda self, announce=True: None

app = QApplication(sys.argv[:1])
w = W()
w.setWindowTitle(f"{app_main.brand.NAME} · preview")
w.show()


def sample():
    """The panels as they look mid-run: the real queue, a Soul Furnace run, the farm's latest log."""
    from macro.sched.runner import Stats
    entries = w.tasks.entries()
    w.chain.set_plan(entries)
    stats = Stats(state="Running", task="Soul Furnace Infinite Hard", run="3 of forever", wave="34",
                  yen="12,480", health="3", enemies="182", clock="14:52", wins=0, losses=2,
                  loot={"Candy Corn": 4180}, index=0, done=2)
    w.chain.timer.stop()
    w.show_stats(stats)
    w.chain._shown = w.chain._target()
    w.chain._flow = 0.4
    w.chain.update()
    w.run_started = time.time() - 3 * 3600 - 1520
    w.tick_clock()
    w.log("preview: a look-only copy. Nothing here touches the game or the farm's files.")
    try:
        with _open(os.path.join(ROOT, "logs", f"app-{time.strftime('%Y%m%d')}.log"), encoding="utf-8") as f:
            lines = [l.rstrip("\n") for l in f if "Discord connection" not in l and "position check" not in l]
        for line in lines[-25:]:
            w.log(line[11:] if line.startswith("[") else line)
    except OSError:
        pass


QTimer.singleShot(1200, sample)
sys.exit(app.exec())
