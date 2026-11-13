"""Render the plan chain alone, off screen, at a few moments of a run, into cap/ui/chain_*.png.
Doesn't touch the screen or the game.  .venv-win/Scripts/python.exe tools/render_chain.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from chain import TaskChain  # noqa: E402

PLAN = [
    {"mode": "story", "map": "Crimson Shore", "act": 1, "difficulty": "Normal", "times": 2},
    {"mode": "story", "map": "Crimson Shore", "act": 2, "difficulty": "Normal", "times": 1},
    {"mode": "challenge", "map": "Daily Challenge", "times": 1},
    {"mode": "rift", "map": "Demonic Rift", "times": 1},
    {"mode": "soul_furnace", "map": "Soul Furnace", "times": 3},
    {"mode": "story", "map": "Flaming Monastery", "act": 3, "difficulty": "Hard", "times": 0},
]
app = QApplication(sys.argv[:1])
out = os.path.join(ROOT, "cap", "ui")
os.makedirs(out, exist_ok=True)
for name, index, done, wave, flow in (("start", 0, 1, 0.45, 2.2), ("middle", 2, 0, 0.3, 3.1), ("idle", -1, 0, 0, 0)):
    chain = TaskChain()
    chain.resize(1110, 150)
    chain.set_plan(PLAN)
    if index >= 0:
        chain.set_progress(index, done, wave, "Running")
    chain.timer.stop()
    chain._shown = chain._target()
    chain._flow = flow
    image = QImage(chain.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(30, 30, 40))
    painter = QPainter(image)
    painter.fillRect(image.rect(), QColor(38, 34, 48))
    chain.render(painter)
    painter.end()
    image.scaled(image.width() * 2, image.height() * 2).save(os.path.join(out, f"chain_{name}.png"))
    print("saved", name)
