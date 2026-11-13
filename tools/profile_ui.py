"""Where the app's time goes: repaints per second and their cost by widget class, and how long the
window stalls (a 5 ms timer's late arrivals), idle and while hovering and opening sub-windows.
Runs in the look-only preview mode (tools/preview_ui.py's guards): nothing reaches the game.

    .venv-win/Scripts/python.exe tools/profile_ui.py [seconds per phase]
"""
import builtins
import collections
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))
os.chdir(ROOT)

_open = builtins.open


def _guarded_open(file, mode="r", *args, **kwargs):
    if any(m in mode for m in "wax+") and isinstance(file, (str, bytes, os.PathLike)):
        if os.path.abspath(os.fsdecode(file)).lower().startswith(ROOT.lower()):
            return _open(os.devnull, mode, *args, **kwargs)
    return _open(file, mode, *args, **kwargs)


builtins.open = _guarded_open
from macro.platform import windows  # noqa: E402

windows.WindowsPlatform.launch_game = lambda self: (_ for _ in ()).throw(RuntimeError("profile"))
windows.WindowsPlatform._send = lambda self, *a: None
windows.WindowsPlatform.dock_game = lambda self: False

import main as app_main  # noqa: E402
from PyQt6.QtCore import QPoint, QTimer  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

W = app_main.MainWindow
W.register_hotkeys = lambda self: None
W.first_attach = lambda self: None
W.start_bot = lambda self, announce=True: None

# ------------------------------------------------------------------ paint timing by class
paints = collections.defaultdict(lambda: [0, 0.0])  # class -> [count, seconds]


def wrap(cls):
    original = cls.__dict__.get("paintEvent")
    if original is None:
        return

    def timed(self, event, _original=original, _name=cls.__name__):
        t = time.perf_counter()
        try:
            return _original(self, event)
        finally:
            entry = paints[_name]
            entry[0] += 1
            entry[1] += time.perf_counter() - t
    cls.paintEvent = timed


def all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from all_subclasses(sub)


import chain, glass, logview, panels, strategy, ui  # noqa: E402,F401

for cls in set(all_subclasses(QWidget)):
    if cls.__module__ in ("main", "ui", "glass", "chain", "logview", "panels", "strategy", "setup_window"):
        wrap(cls)

app = QApplication(sys.argv[:1])
w = W()
w.show()
PHASE = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0

# ------------------------------------------------------------------ stall meter
gaps = []
last = [time.perf_counter()]


def beat():
    now = time.perf_counter()
    gaps.append((now - last[0]) * 1000 - 5)
    last[0] = now


meter = QTimer()
meter.setInterval(5)
meter.timeout.connect(beat)
meter.start()

results = []


def report(name, seconds):
    g = sorted(gaps) or [0]
    total = sum(v[1] for v in paints.values())
    top = sorted(paints.items(), key=lambda kv: -kv[1][1])[:6]
    results.append((name, seconds, len(g), g[len(g) // 2], g[int(len(g) * 0.95)], g[-1],
                    sum(1 for x in g if x > 33), total, top))
    gaps.clear()
    paints.clear()


def hover_around():
    """Pointer sweeps over the right column's buttons and the cards, as a user looking around."""
    targets = [b for b in w.findChildren(QWidget) if b.isVisible() and type(b).__name__ in ("NavButton", "KeyRow", "QPushButton")]
    for n in range(60):
        b = targets[n % len(targets)]
        QTest.mouseMove(b, QPoint(b.width() // 2, b.height() // 2))
        QTest.qWait(60)


def phases():
    QTest.qWait(2500)  # settle: first paints, sample data
    gaps.clear(); paints.clear()
    from ui import SubWindow
    print("visible sub-windows while idle:", [type(s).__name__ for s in w.findChildren(SubWindow) if s.isVisible()])
    painted = collections.Counter()
    for s in w.findChildren(SubWindow):
        original = s.paintEvent
        def counting(event, _s=s, _o=original):
            painted[type(_s).__name__ + (" (hidden)" if not _s.isVisible() else "")] += 1
            return _o(event)
        s.paintEvent = counting
    QTest.qWait(int(PHASE * 1000)); report("idle", PHASE)
    print("sub-window paints while idle, by window:", dict(painted))
    t = time.perf_counter(); hover_around(); report("hovering buttons", time.perf_counter() - t)
    t = time.perf_counter()
    for window in (w.tasks, w.config, w.extras, w.strategy):
        window.open(); QTest.qWait(900); window.close_animated(); QTest.qWait(500)
    report("opening sub-windows", time.perf_counter() - t)
    w.tasks.open(); QTest.qWait(800); gaps.clear(); paints.clear()
    t = time.perf_counter()
    targets = [c for c in w.tasks.findChildren(QWidget) if c.isVisible() and type(c).__name__ in ("QPushButton", "Toggle", "QComboBox", "SettingRow")]
    for n in range(40):
        c = targets[n % len(targets)]
        QTest.mouseMove(c, QPoint(c.width() // 2, c.height() // 2)); QTest.qWait(60)
    report("hovering inside Tasks", time.perf_counter() - t)
    QTest.qWait(200)
    gaps.clear(); paints.clear()
    t = time.perf_counter()
    start = w.tasks.pos()
    for n in range(60):  # dragging the Tasks window across, as by its title bar
        w.tasks.move(start.x() + 4 * n, start.y() + 2 * n); QTest.qWait(16)
    report("dragging Tasks", time.perf_counter() - t)
    w.tasks.close_animated(); QTest.qWait(400)
    for name, secs, n, p50, p95, worst, long, total, top in results:
        print(f"\n== {name} ({secs:.1f} s): stalls p50 {p50:.1f} ms, p95 {p95:.1f} ms, worst {worst:.0f} ms, "
              f"{long} over 33 ms; painting {total * 1000:.0f} ms ({100 * total / secs:.0f}% of the time)")
        for cls, (count, spent) in top:
            print(f"   {cls:22} {count / secs:6.1f} paints/s  {1000 * spent / max(count, 1):6.1f} ms each  "
                  f"{1000 * spent:7.0f} ms total")
    app.quit()


QTimer.singleShot(100, phases)
app.exec()
