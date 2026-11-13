"""The game's screen, seen and touched through Wayland.

One client on the nested compositor Roblox runs in: frames come from
wlr-screencopy straight into numpy (no files), the pointer is a
wlr-virtual-pointer (absolute moves, exact to the pixel), and keys go
through wtype (it carries its own keymap).
"""

from __future__ import annotations

import mmap
import os
import subprocess
import time

import numpy as np
from pywayland.client import Display

from wlproto.wayland import WlOutput, WlSeat, WlShm
from wlproto.wlr_screencopy_unstable_v1 import ZwlrScreencopyManagerV1
from wlproto.wlr_virtual_pointer_unstable_v1 import ZwlrVirtualPointerManagerV1

BTN_LEFT = 0x110
BTN_RIGHT = 0x111


class Screen:
    def __init__(self, display: str, runtime_dir: str):
        self.display_name = display
        self.runtime_dir = runtime_dir
        os.environ["XDG_RUNTIME_DIR"] = runtime_dir
        self.display = Display(display)
        self.display.connect()
        self.shm = self.output = self.seat = None
        self.copier = self.pointer_manager = None
        self.width = self.height = 0

        registry = self.display.get_registry()
        registry.dispatcher["global"] = self._global
        self.display.roundtrip()
        self.display.roundtrip()  # the output's mode
        missing = [n for n, v in (("wl_shm", self.shm), ("wl_output", self.output), ("wl_seat", self.seat),
                                  ("screencopy", self.copier), ("virtual pointer", self.pointer_manager)) if v is None]
        if missing:
            raise RuntimeError("compositor lacks " + ", ".join(missing))
        self.pointer = self.pointer_manager.create_virtual_pointer(self.seat)
        self._t0 = time.monotonic()

    def _global(self, registry, name, interface, version):
        if interface == "wl_shm":
            self.shm = registry.bind(name, WlShm, 1)
        elif interface == "wl_output" and self.output is None:
            self.output = registry.bind(name, WlOutput, min(version, 2))
            self.output.dispatcher["mode"] = self._mode
        elif interface == "wl_seat" and self.seat is None:
            self.seat = registry.bind(name, WlSeat, 1)
        elif interface == "zwlr_screencopy_manager_v1":
            self.copier_version = min(version, 3)
            self.copier = registry.bind(name, ZwlrScreencopyManagerV1, self.copier_version)
        elif interface == "zwlr_virtual_pointer_manager_v1":
            self.pointer_manager = registry.bind(name, ZwlrVirtualPointerManagerV1, min(version, 2))

    def _mode(self, output, flags, width, height, refresh):
        if flags & 1:  # current
            self.width, self.height = width, height

    def close(self):
        self.pointer.destroy()
        self.display.flush()
        self.display.disconnect()

    def _ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000) & 0xFFFFFFFF

    # ------------------------------------------------------------ seeing
    def grab(self) -> np.ndarray:
        """The whole screen now, as a BGR image (height x width x 3)."""
        frame = self.copier.capture_output(0, self.output)
        state: dict = {}
        frame.dispatcher["buffer"] = lambda f, fmt, w, h, stride: state.update(fmt=fmt, w=w, h=h, stride=stride)
        frame.dispatcher["ready"] = lambda f, *a: state.update(done=True)
        frame.dispatcher["failed"] = lambda f: state.update(failed=True)
        frame.dispatcher["flags"] = lambda f, flags: state.update(flip=bool(flags & 1))
        frame.dispatcher["buffer_done"] = lambda f: state.update(described=True)
        # Version 3 lists every buffer kind then says buffer_done; before it,
        # the shm buffer event is all there is.
        while "fmt" not in state or ("described" not in state and self.copier_version >= 3):
            self.display.roundtrip()
            if state.get("failed"):
                raise RuntimeError("screencopy failed")
        w, h, stride = state["w"], state["h"], state["stride"]
        size = stride * h
        fd = os.memfd_create("frame", os.MFD_CLOEXEC)
        os.ftruncate(fd, size)
        buf = mmap.mmap(fd, size)
        pool = self.shm.create_pool(fd, size)
        wl_buffer = pool.create_buffer(0, w, h, stride, state["fmt"])
        frame.copy(wl_buffer)
        while not state.get("done"):
            self.display.dispatch(block=True)
            if state.get("failed"):
                break
        # 4 bytes a pixel (XRGB/ARGB8888: B, G, R, X in memory) or 3 (BGR888
        # is R, G, B in memory; RGB888 is B, G, R).
        bpp = stride // w
        rows = np.frombuffer(buf, dtype=np.uint8, count=size).reshape(h, stride)[:, : w * bpp].reshape(h, w, bpp)
        pixels = rows[:, :, :3].copy()
        if bpp == 3 and state["fmt"] == WlShm.format.bgr888.value:
            pixels = pixels[:, :, ::-1].copy()
        del rows  # the view into the shared memory, before it is closed
        wl_buffer.destroy(); pool.destroy(); frame.destroy()
        buf.close(); os.close(fd)
        if state.get("failed"):
            raise RuntimeError("screencopy failed")
        if state.get("flip"):
            pixels = pixels[::-1].copy()
        return pixels

    # ------------------------------------------------------------ touching
    def move(self, x: float, y: float):
        self.pointer.motion_absolute(self._ms(), int(x), int(y), self.width, self.height)
        self.pointer.frame()
        self.display.flush()

    def click(self, x: float, y: float, button: int = BTN_LEFT, hold: float = 0.06):
        # Roblox reads hover first: arrive, settle, press, release.
        self.move(x, y)
        time.sleep(0.05)
        self.pointer.button(self._ms(), button, 1); self.pointer.frame(); self.display.flush()
        time.sleep(hold)
        self.pointer.button(self._ms(), button, 0); self.pointer.frame(); self.display.flush()

    def drag(self, x1, y1, x2, y2, steps: int = 20, button: int = BTN_RIGHT):
        """A held drag (right button turns Roblox's camera)."""
        self.move(x1, y1)
        self.pointer.button(self._ms(), button, 1); self.pointer.frame(); self.display.flush()
        for i in range(1, steps + 1):
            self.move(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
            time.sleep(0.01)
        self.pointer.button(self._ms(), button, 0); self.pointer.frame(); self.display.flush()

    def move_rel(self, dx: float, dy: float):
        """Relative motion: what Roblox reads while it has the pointer
        locked (right button held turns the camera)."""
        self.pointer.motion(self._ms(), float(dx), float(dy))
        self.pointer.frame()
        self.display.flush()

    def turn(self, dx: float, dy: float = 0.0, steps: int = 10, step_s: float = 0.01):
        """Hold the right button and push the mouse by (dx, dy) counts."""
        self.pointer.button(self._ms(), BTN_RIGHT, 1); self.pointer.frame(); self.display.flush()
        time.sleep(0.03)
        for _ in range(steps):
            self.move_rel(dx / steps, dy / steps)
            time.sleep(step_s)
        time.sleep(0.03)
        self.pointer.button(self._ms(), BTN_RIGHT, 0); self.pointer.frame(); self.display.flush()

    def scroll(self, amount: float):
        """Positive: zoom out / scroll down."""
        self.pointer.axis(self._ms(), 0, float(amount))  # wl_fixed, 15 a notch
        self.pointer.frame()
        self.display.flush()

    def key(self, name: str, hold: float = 0.05):
        env = dict(os.environ, XDG_RUNTIME_DIR=self.runtime_dir, WAYLAND_DISPLAY=self.display_name)
        subprocess.run(["wtype", "-P", name, "-s", str(int(hold * 1000)), "-p", name], env=env, check=True)

def type_text(screen: "Screen", text: str):
    env = dict(os.environ, XDG_RUNTIME_DIR=screen.runtime_dir, WAYLAND_DISPLAY=screen.display_name)
    subprocess.run(["wtype", "-d", "15", text], env=env, check=True)
