"""Drives the real app window from inside, so nothing physical trips the guard, and saves pictures
of the whole screen to cap/app/.
  test_app.py look       the two tabs, with a plan loaded
  test_app.py minimize   minimize and restore, checking Roblox follows
  test_app.py run MODE MAP ACT PLAN   run one queue item to the end, e.g. run sandbox "Flaming Monastery" 1 bad
  test_app.py queue JSON  run a whole queue
  test_app.py full        four matches over three tasks: a pretend touch, F6 both ways, F8, a webhook catcher
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))
import main as app_main  # noqa: E402

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from macro.platform import windows as win  # noqa: E402

OUT = os.path.join(ROOT, "cap", "app")
os.makedirs(OUT, exist_ok=True)
command = sys.argv[1]
app = QApplication(sys.argv[:1])
window = app_main.MainWindow()
window.show()
user32 = win.user32


def screen(name):
    subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "full_screen_shot.py"), os.path.join(OUT, name + ".png")])
    print("saving", name, flush=True)


def after(seconds, action):
    QTimer.singleShot(int(seconds * 1000), action)


def state():
    hwnd = window.roblox()
    return {"frame_minimized": window.isMinimized(), "roblox_minimized": bool(user32.IsIconic(hwnd)) if hwnd else None,
            "roblox_at": win.client_rect(hwnd) if hwnd else None, "attached": window.attached}


if command == "look":
    def step1():
        print(state(), flush=True)
        screen("run_tab")
        after(3, open_reference)

    def open_reference():
        window.reference_tab.click()
        window.editor.map.setCurrentIndex(window.editor.map.findData("Flaming Monastery"))
        after(2.0, step2)

    def step2():
        screen("reference_tab")
        after(3, app.quit)
    after(6, step1)
elif command == "minimize":
    def step1():
        print("attached:", state(), flush=True)
        window.showMinimized()
        after(1.5, step2)

    def step2():
        print("minimized:", state(), flush=True)
        screen("minimized")
        window.showNormal()
        after(2.0, step3)

    def step3():
        print("restored:", state(), flush=True)
        window.activateWindow()
        after(1.0, step4)

    def step4():
        screen("restored")
        print("fg is frame:", user32.GetForegroundWindow() == int(window.winId()), flush=True)
        after(3, app.quit)
    after(6, step1)
elif command in ("run", "queue"):
    # run MODE MAP ACT PLAN [DIFFICULTY] [TIMES]   one queue item
    # queue JSON [stop_after=SECONDS]              a whole queue, e.g. '[{"mode": "story", ...}, ...]'
    # A pause (someone touched the laptop) is waited out: after IDLE_BEFORE_RESUME s of no input, Resume.
    import json

    IDLE_BEFORE_RESUME = 60
    if command == "run":
        mode, map_name, act, plan = sys.argv[2:6]
        difficulty = sys.argv[6] if len(sys.argv) > 6 else "Normal"
        times = int(sys.argv[7]) if len(sys.argv) > 7 else 1
        entries = [{"mode": mode, "map": map_name, "act": int(act), "difficulty": difficulty, "plan": plan, "times": times}]
    else:
        entries = json.loads(sys.argv[2])
    saved_queue = window.tasks.entries()
    window.tasks.items.clear()
    for entry in entries:
        window.tasks._append(entry)
    window.queue_changed()
    window.bridge.log.connect(lambda t: print(t, flush=True))

    def begin():
        window.start_run()
        after(45, lambda: screen("during_run"))

    def watch_pause():
        if window.paused and win.idle_seconds() >= IDLE_BEFORE_RESUME:
            print("TEST: idle again, pressing Resume", flush=True)
            window.pause_or_resume()
    pause_timer = QTimer()
    pause_timer.timeout.connect(watch_pause)
    pause_timer.start(5000)

    def done(ending):
        print("ENDED:", ending, flush=True)
        after(1.0, finish)

    def finish():
        screen("after_run")
        window.tasks.items.clear()
        for entry in saved_queue:
            window.tasks._append(entry)
        window.queue_changed()
        after(3, app.quit)
    window.bridge.finished.connect(done)
    after(6, begin)
elif command == "picture":  # picture MAP: a new map's reference picture through the Reference tab
    map_name = sys.argv[2]
    window.bridge.log.connect(lambda t: print(t, flush=True))

    def begin():
        window.reference_tab.click()
        window.editor.map.setCurrentIndex(window.editor.map.findData(map_name))
        window.editor.zoom.setValue(1)
        window.editor.rotate.setValue(0)
        after(1.0, window.editor.take.click)

    def done(text):
        print("DONE:", text, flush=True)
        after(2.0, shot)

    def shot():
        window.editor.select_slot(1)
        window.editor.add_spot(700, 400)
        window.editor.select_slot(3)
        window.editor.add_spot(800, 300)
        window.editor.add_spot(1300, 600)  # over the game's buttons
        print("notes:", window.editor.notes.toPlainText()[-200:], flush=True)
        after(1.0, lambda: screen("new_map"))
        after(4.0, app.quit)
    window.bridge.picture.connect(done)
    after(6, begin)
elif command == "full":  # a whole queue with a pretend touch, real F6 and F8 presses, and a webhook catcher
    import http.server
    import threading

    received = []

    class Catch(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *a):
            pass
    server = http.server.HTTPServer(("127.0.0.1", 0), Catch)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    old_webhook = window.config.webhook.text()
    window.config.webhook.setText(f"http://127.0.0.1:{server.server_port}/hook")
    saved_queue = window.tasks.entries()
    window.tasks.items.clear()
    fm = {"mode": "story", "map": "Flaming Monastery", "act": 1, "difficulty": "Normal", "plan": "story"}
    for entry in ({**fm, "times": 2}, {**fm, "map": "Crimson Shore", "times": 1}, {**fm, "times": 1}):
        window.tasks._append(entry)
    window.queue_changed()
    matches = [0]
    F6, F8 = 0x40, 0x42

    def say(*parts):
        print("TEST:", *parts, flush=True)

    def real_key(scan):  # untagged, so it looks like a person's press
        p = window.runner.p
        p._send(p._keyboard(scan, win.KEYEVENTF_SCANCODE, tag=0),
                p._keyboard(scan, win.KEYEVENTF_SCANCODE | win.KEYEVENTF_KEYUP, tag=0))

    def touch():
        p = window.runner.p
        p._send(p._mouse(win.MOUSEEVENTF_MOVE, dx=1, tag=0))
        after(3, lambda: (say("after a touch, paused =", window.paused, "| button says", window.pause_button.text()),
                          screen("paused")))
        after(12, lambda: (say("pressing F6 to resume"), real_key(F6)))
        after(20, lambda: say("after F6, paused =", window.paused))

    def f6_pause():
        say("pressing F6 while running")
        real_key(F6)
        after(3, lambda: say("after F6, paused =", window.paused))
        after(12, lambda: (say("clicking Resume"), window.pause_button.click()))
        after(20, lambda: say("after Resume, paused =", window.paused))

    def f8():
        say("pressing F8")
        real_key(F8)

    def on_log(text):
        print(text, flush=True)
        if text.strip() == "match started":
            matches[0] += 1
            action = {1: touch, 2: f6_pause, 4: f8}.get(matches[0])
            if action:
                after(60, action)
    window.bridge.log.connect(on_log)

    def done(ending):
        print("ENDED:", ending, flush=True)
        for body in received:
            gap = bytes([13, 10, 13, 10])  # the blank line after a part's headers
            text = body.split(gap)[1][:160] if gap in body else body[:160]
            say("webhook call,", len(body), "bytes, picture:", b"result.jpg" in body, "|", text)
        say("webhook calls:", len(received))
        window.config.webhook.setText(old_webhook)
        window.config.save()
        window.tasks.items.clear()
        for entry in saved_queue:
            window.tasks._append(entry)
        window.queue_changed()
        screen("after_full")
        after(3, app.quit)
    window.bridge.finished.connect(done)
    after(6, window.start_run)
code = app.exec()
window.close()
sys.exit(code)
