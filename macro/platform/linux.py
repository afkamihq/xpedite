"""Linux backend: macro/wl.py (Hyprland + Sober) behind the shared interface.

The guard here is only the workspace check that act.py always did. The socket
events and pointer-takeover check from docs/ARCHITECTURE.md aren't built, and the
stop hotkey isn't either. Not yet run since the platform layer was split out.
"""

from __future__ import annotations

import json
import os
import subprocess

from .base import GuardTripped, Platform

BUTTONS = {"left": 0x110, "right": 0x111, "middle": 0x112}
GAME_WORKSPACE = 13
PLACE_ID = 84515722934860


class WorkspaceGuard:
    def __init__(self):
        self.armed = False
        self.tripped = False
        self.stopped = False
        self.reason = ""
        self.pausable = False
        self.paused_total = 0.0

    def wait_if_paused(self):
        pass

    def arm(self):
        self.armed = True
        self.tripped = False
        self.reason = ""
        self.check()

    def disarm(self):
        self.armed = False

    def check(self):
        if not self.armed:
            raise GuardTripped(self.reason or "guard is not armed")
        if self.tripped:
            raise GuardTripped(self.reason)
        out = subprocess.run(["hyprctl", "activeworkspace", "-j"], capture_output=True, text=True).stdout
        if json.loads(out).get("id") != GAME_WORKSPACE:
            self.tripped = True
            self.reason = f"workspace {GAME_WORKSPACE} is not showing"
            raise GuardTripped(self.reason)


class LinuxPlatform(Platform):
    def __init__(self):
        super().__init__()
        from macro.wl import Screen

        self.guard = WorkspaceGuard()
        self.screen = Screen(os.environ.get("XM_DISPLAY", "wayland-1"), "/run/user/1000")

    def close(self):
        super().close()
        self.screen.close()

    def grab(self):
        return self.screen.grab()

    def _move(self, x, y):
        self.screen.move(x, y)

    def _rel(self, dx, dy):
        self.screen.move_rel(dx, dy)

    def _button(self, button, down):
        s = self.screen
        s.pointer.button(s._ms(), BUTTONS[button], 1 if down else 0)
        s.pointer.frame()
        s.display.flush()

    def _wheel(self, amount):
        self.screen.scroll(amount)

    def _env(self):
        return dict(os.environ, XDG_RUNTIME_DIR=self.screen.runtime_dir, WAYLAND_DISPLAY=self.screen.display_name)

    def key(self, name, hold=0.05):
        # wtype's virtual keyboard dies with its process, so a held key has to be
        # one invocation: separate key_down/key_up can't exist here.
        self.guard.check()
        subprocess.run(["wtype", "-P", name, "-s", str(int(hold * 1000)), "-p", name], env=self._env(), check=True)

    def _key(self, name, down):
        raise NotImplementedError("wtype can't hold a key across calls; use key(name, hold)")

    def _text(self, text):
        subprocess.run(["wtype", "-d", "15", text], env=self._env(), check=True)

    def game_running(self):
        return subprocess.run(["pgrep", "-x", "sober"], capture_output=True).returncode == 0

    def launch_game(self):
        from macro.platform.links import launch_uri
        subprocess.Popen(["flatpak", "run", "org.vinegarhq.Sober", launch_uri()])
