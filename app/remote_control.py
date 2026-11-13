"""What the Discord bot (macro/remote/) may do to the app, and nothing more. Every action goes
through the same path as its hotkey (bridge.hotkey -> the Qt thread), so a command from Discord
behaves exactly like F2/F3/F5/F6 at the laptop. Reads are taken from the runner's own stats."""
from __future__ import annotations

import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AppRemote:
    def __init__(self, window):
        self.w = window

    # ------------------------------------------------------------------ actions
    def start(self) -> str:
        if self.w.busy():
            return "It's already running."
        self.w.bridge.hotkey.emit("F2")
        return "Starting the queue."

    def stop(self) -> str:
        if not self.w.busy_running():
            return "Nothing is running."
        self.w.bridge.hotkey.emit("F3")
        return "Stopping the run."

    def pause_toggle(self) -> str:
        if not self.w.busy_running():
            return "Nothing is running."
        paused = self.w.runner.stats.state.lower().startswith("pause")
        self.w.bridge.hotkey.emit("F6")
        return "Carrying on." if paused else "Pausing."

    def collect(self) -> str:
        if self.w.busy():
            return "Something is running: collect when it's stopped."
        self.w.bridge.hotkey.emit("F5")
        return "Collecting rewards."

    # ------------------------------------------------------------------ reading
    def status(self) -> dict:
        runner = self.w.runner
        out = {"state": "Idle", "candy": 0, "runs": 0}
        if runner is None:
            return out
        s = runner.stats
        out.update(state=s.state if runner.is_alive() else "Idle", task=s.task, run=s.run, wave=s.wave,
                   yen=s.yen, health=s.health, enemies=s.enemies, candy=s.loot.get("Candy Corn", 0))
        runs = getattr(runner, "_furnace_runs", [])
        out["runs"] = len(runs)
        if runs:
            out["best_wave"] = max(w for w, _, _ in runs)
            wave, candy, seconds = runs[-1]
            out["last_result"] = f"wave {wave}, +{candy:,} Candy Corn in {int(seconds // 60)} min"
        started = getattr(runner, "run_started_at", None)
        if started and runner.is_alive():
            minutes = int((time.time() - started) // 60)
            out["running_for"] = f"{minutes // 60} h {minutes % 60:02d} min"
        return out

    def screenshot(self):
        """The whole screen (BGR): the app's panels and log around the game (user, 13 Nov 2026),
        or None if it can't be copied (a disconnected Remote Desktop session has no screen)."""
        from macro.platform.windows import grab_screen
        try:
            return grab_screen()
        except OSError:
            return None

    def logs(self, lines: int = 15) -> list[str]:
        path = os.path.join(ROOT, "logs", f"app-{time.strftime('%Y%m%d')}.log")
        try:
            with open(path, encoding="utf-8") as f:
                return [line.rstrip() for line in f.readlines()[-lines:]]
        except OSError:
            return []

    def queue(self) -> list[str]:
        from macro.sched.runner import describe
        return [describe(entry) for entry in self.w.tasks.entries()]

    # ------------------------------------------------------------------ session goals
    def set_goal(self, kind: str, value) -> str:
        from panels import SETTINGS_FILE, load_settings
        from ui import save_yaml
        settings = load_settings()
        if kind == "candy":
            settings["stop_at_candy"] = int(value)
        elif kind == "time":
            parts = str(value).split(":")
            if len(parts) != 2 or not all(p.isdigit() for p in parts) or not (0 <= int(parts[0]) < 24
                                                                              and 0 <= int(parts[1]) < 60):
                return "Give the time as HH:MM, like 07:30."
            settings["stop_at_time"] = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        elif kind == "clear":
            settings["stop_at_candy"], settings["stop_at_time"] = 0, ""
        save_yaml(SETTINGS_FILE, settings)
        runner = self.w.runner
        if runner is not None:  # the running session sees it at the next run
            for key in ("stop_at_candy", "stop_at_time"):
                runner.settings[key] = settings.get(key)
        candy, at = settings.get("stop_at_candy") or 0, settings.get("stop_at_time") or ""
        goals = [f"after {candy:,} Candy Corn" if candy else "", f"at {at}" if at else ""]
        text = " or ".join(g for g in goals if g)
        return f"The session stops {text}." if text else "No session goal: it runs until stopped."
