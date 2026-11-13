"""Render the sub-windows (Config, Tasks, Main, Extras, About) to cap/ui/sheet_<name>.png without
the main window or Roblox: each one over a game picture, as it looks in the app.
    .venv-win/Scripts/python.exe tools/render_sheets.py [config tasks main extras about]"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))
from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

OUT = os.path.join(ROOT, "cap", "ui")
GROUND = os.path.join(ROOT, "refs", "frames_win")


class Stub(QWidget):
    """Stands in for the main window: every action is a no-op."""
    backdrop = None

    def __getattr__(self, name):
        return lambda *a, **k: None


def ground_picture():
    for folder in (GROUND, os.path.join(ROOT, "refs", "frames_native")):
        if os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                if name.endswith(".png"):
                    return QImage(os.path.join(folder, name))
    return None


def main():
    wanted = sys.argv[1:] or ["config", "tasks", "main", "extras", "about"]
    app = QApplication(sys.argv[:1])
    import panels
    import strategy
    host = Stub()
    host.resize(1920, 1080)
    makers = {"config": lambda: panels.ConfigWindow(host), "tasks": lambda: panels.TasksWindow(host),
              "main": lambda: strategy.StrategyWindow(host), "extras": lambda: panels.ExtrasWindow(host),
              "about": lambda: panels.AboutWindow(host, "dev")}
    ground = ground_picture()
    os.makedirs(OUT, exist_ok=True)
    windows = []
    for name in wanted:
        window = makers[name]()
        if name == "tasks":  # the Soul card shows only for Soul Furnace
            window.mode.setCurrentIndex(window.mode.findData("furnace"))
        if window.fit:
            window.resize(window.width(), window.sizeHint().height())
        window.move(-4000, 0)
        window.show()
        windows.append((name, window))

    def save():
        for name, window in windows:
            sheet = window.grab().toImage()
            out = QImage(sheet.size(), QImage.Format.Format_RGB32)
            painter = QPainter(out)
            if ground is not None:  # blurred, as the glass shows it
                small = ground.scaled(max(1, out.width() // 24), max(1, out.height() // 24),
                                      transformMode=Qt.TransformationMode.SmoothTransformation)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawImage(out.rect(), small)
            painter.fillRect(out.rect(), QColor(0, 0, 0, 110))
            painter.drawImage(0, 0, sheet)
            painter.end()
            path = os.path.join(OUT, f"sheet_{name}.png")
            out.save(path)
            print("saved", path, sheet.width(), "x", sheet.height())
        app.quit()

    QTimer.singleShot(600, save)
    app.exec()


if __name__ == "__main__":
    main()
