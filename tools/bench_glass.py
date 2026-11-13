"""How much the glass costs: a new game picture (feed) and a full repaint of the main window.
Doesn't touch the game.  .venv-win/Scripts/python.exe tools/bench_glass.py"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))
import cv2  # noqa: E402
import main as app_main  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])
w = app_main.MainWindow()
w.keeper.stop()
w.ambient.stop()
pictures = [cv2.imread(os.path.join(ROOT, "refs", "frames_win", name)) for name in ("lobby.png", "match_hud.png")]
feeds = []
for i in range(6):
    start = time.perf_counter()
    w.backdrop._thumb = None
    w.backdrop.feed(pictures[i % 2], animate=False)
    feeds.append(time.perf_counter() - start)
w.grab()  # first paint fills the caches
paints = []
for i in range(10):
    start = time.perf_counter()
    w.grab()
    paints.append(time.perf_counter() - start)
w.backdrop._thumb = None
w.backdrop.feed(pictures[0], animate=False)
start = time.perf_counter()
w.grab()
cold = time.perf_counter() - start
print(f"feed: median {sorted(feeds)[3] * 1000:.1f} ms")
print(f"repaint, panes cached: median {sorted(paints)[5] * 1000:.1f} ms")
print(f"repaint after a new picture (panes rebuilt): {cold * 1000:.1f} ms")
