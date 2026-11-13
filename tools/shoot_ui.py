"""Open the app, then each sub-window, and save pictures of the whole screen to cap/ui/."""
import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))
import main as app_main  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

OUT = os.path.join(ROOT, "cap", "ui")
os.makedirs(OUT, exist_ok=True)
app = QApplication(sys.argv[:1])
w = app_main.MainWindow()
w.show()
w.bridge.log.connect(lambda t: print(t, flush=True))
steps = []


def shot(name):
    subprocess.call([sys.executable, os.path.join(ROOT, "tools", "full_screen_shot.py"), os.path.join(OUT, name + ".png")])
    print("saved", name, flush=True)


def at(seconds, action):
    steps.append((seconds, action))


DEMO_PLAN = [
    {"mode": "story", "map": "Crimson Shore", "act": 1, "difficulty": "Normal", "plan": "story", "times": 2},
    {"mode": "story", "map": "Crimson Shore", "act": 2, "difficulty": "Normal", "plan": "story", "times": 1},
    {"mode": "challenge", "map": "Daily Challenge", "times": 1},
    {"mode": "rift", "map": "Demonic Rift", "times": 1},
    {"mode": "soul_furnace", "map": "Soul Furnace", "times": 3},
    {"mode": "story", "map": "Flaming Monastery", "act": 3, "difficulty": "Hard", "plan": "story", "times": 0},
]
DEMO_LOG = ["starting a queue of 6. Hands off the mouse and keyboard.",
            "--- Crimson Shore Act 1 Normal, plan story, x1, run 1 of 2",
            "balance at the start: 5935 gems, 16620 gold", "  lobby -> play_menu_top", "  play_menu_top -> story_maps",
            "match started", "  slot 6 #1 placed at (596, 351), Yen was 600", "  slot 1 #1 placed at (746, 362), Yen was 2045",
            "  slot 1 #1: waiting for 2850 Yen, have 523", "  slot 1 #1: waiting for 2850 Yen, have 1400",
            "  slot 1 #1: waiting for 2850 Yen, have 2510", "  slot 1 #1 upgraded to 1, next costs 4150, Yen was 3030",
            "PAUSED: you moved or clicked the mouse. Press Resume, or F8 to end the run.",
            "resuming once the mouse and keyboard are still", "20 moves made", "RESULT: victory after 263 s",
            "--- Crimson Shore Act 1 Normal, plan story, x1, run 2 of 2", "repeating the stage from the results",
            "match started", "  slot 6 #1 placed at (596, 351), Yen was 600"]


def demo():
    from macro.sched.runner import Stats
    w.chain.set_plan(DEMO_PLAN)
    stats = Stats(state="Running", task="Crimson Shore Act 1 Normal, plan story, x2", run="2 of 2", wave="7/15",
                  yen="3,120", health="3", enemies="18", clock="2:41", wins=5, losses=0, gems_start=5935,
                  gems_now=6160, index=0, done=1)
    w.chain.timer.stop()
    w.show_stats(stats)
    w.chain._shown = w.chain._target()
    w.chain._flow = 0.45
    w.chain.update()
    w.run_started = __import__("time").time() - 1520
    w.tick_clock()
    for line in DEMO_LOG:
        w.log(line)


if "--demo" in sys.argv:
    at(6, demo)
at(7, lambda: (w.toast("Toast check: this is how messages show", "good"), None))
at(8, lambda: (print("glass lit by the game:", w.backdrop.version > 1, flush=True), shot("main")))
at(9, lambda: w.strategy.open())
at(11, lambda: shot("strategy"))
at(12, lambda: w.strategy.close_animated())
at(12.5, lambda: w.tasks.open())
at(14, lambda: shot("tasks"))
at(15, lambda: w.tasks.close_animated())
at(15.5, lambda: w.config.open())
at(17, lambda: shot("config"))
at(18, lambda: w.config.close_animated())
at(18.5, lambda: w.extras.open())
at(20, lambda: shot("extras"))
at(21, lambda: w.extras.close_animated())
at(21.5, lambda: w.about.open())
at(23, lambda: shot("about"))
at(24, lambda: w.about.close_animated())
at(25, app.quit)
for seconds, action in steps:
    QTimer.singleShot(int(seconds * 1000), action)
sys.exit(app.exec())
