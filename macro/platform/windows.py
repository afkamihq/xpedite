"""Windows backend: DXGI capture, SendInput, and the safety guard.

The guard pauses the macro the moment any of these happens:
- any mouse event or key press that did not come from us (low-level hooks; our
  own events carry a private tag in dwExtraInfo);
- Roblox stops being the foreground window, or stops covering the 1920x1080
  monitor;
- the stop hotkey (F8), which also refuses every later resume. No modifiers on
  purpose: Ctrl toggles this game's pointer lock (see docs/GAME.md);
- Windows silently drops a hook, which it does to slow hooks without telling
  anyone. Our own events must show up in the hook, so a shortfall means it's gone.

Only the executable's name is ever asked of the Roblox process, through a
limited-information handle that has no access to its memory.
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Must happen before anything reads coordinates, or 125% scaling makes the
# screen look like 1536x864 and every click lands in the wrong place.
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2

import psutil  # noqa: E402

from .base import GuardTripped, Platform  # noqa: E402

def _load_frame() -> tuple[int, int, int, int] | None:
    """Where data/display.yaml puts the game: x, y, width, height. None means fullscreen."""
    import yaml

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "display.yaml")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        frame = (yaml.safe_load(f) or {}).get("frame")
    return tuple(frame) if frame else None


FRAME = _load_frame()
GAME_EXE = "robloxplayerbeta.exe"
PLACE_ID = 84515722934860
TAG = 0x584D4143  # "XMAC": marks events we injected
HOTKEY_TEXT = "F8"

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000
BUTTON_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_QUIT, WM_HOTKEY = 0x0012, 0x0312
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
MOD_NOREPEAT = 0x4000
VK_F8 = 0x77
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
MONITOR_DEFAULTTONEAREST = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumWindows.argtypes = [_ENUMPROC, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsHungAppWindow.argtypes = [wintypes.HWND]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]

user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]

# Set 1 scan codes: physical key positions, which Roblox reads reliably.
SCAN = {c: 0x10 + i for i, c in enumerate("qwertyuiop")}
SCAN.update({c: 0x1E + i for i, c in enumerate("asdfghjkl")})
SCAN.update({c: 0x2C + i for i, c in enumerate("zxcvbnm")})
SCAN.update({c: 0x02 + i for i, c in enumerate("123456789")})
SCAN.update({f"f{i}": 0x3A + i for i in range(1, 11)})
SCAN.update({
    "0": 0x0B, "escape": 0x01, "esc": 0x01, "backspace": 0x0E, "tab": 0x09 + 6, "return": 0x1C,
    "enter": 0x1C, "ctrl": 0x1D, "shift": 0x2A, "lshift": 0x2A, "alt": 0x38, "space": 0x39,
    "f11": 0x57, "f12": 0x58, "f24": 0x76,
})
EXTENDED = {"up": 0x48, "left": 0x4B, "right": 0x4D, "down": 0x50, "home": 0x47, "end": 0x4F,
            "pageup": 0x49, "pagedown": 0x51, "insert": 0x52, "delete": 0x53}


def scan_code(name: str) -> tuple[int, bool]:
    """(scan code, is extended) for a key name such as "w", "F11" or "Return"."""
    key = name.lower()
    if key in EXTENDED:
        return EXTENDED[key], True
    if key in SCAN:
        return SCAN[key], False
    raise ValueError(f"unknown key name: {name!r}")


def to_absolute(pixel: float, origin: int, size: int) -> int:
    """A pixel on the virtual desktop as SendInput's 0..65535 range, aimed at the
    pixel's centre so rounding can't land on its neighbour."""
    value = ((2 * (int(pixel) - origin) + 1) * 65536) // (2 * size)
    return max(0, min(65535, value))


def foreground_exe() -> str:
    """The foreground window's executable name, lower case ("" if none)."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return _exe_of(pid.value)


_exe_cache: dict[int, str] = {}


def _session_of(pid: int):
    """The Windows session (Terminal Services) a process runs in, or None if it can't be told."""
    session = wintypes.DWORD()
    if ctypes.windll.kernel32.ProcessIdToSessionId(wintypes.DWORD(pid), ctypes.byref(session)):
        return session.value
    return None


def _exe_of(pid: int) -> str:
    if pid in _exe_cache:
        return _exe_cache[pid]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
    finally:
        kernel32.CloseHandle(handle)
    name = os.path.basename(buf.value).lower()
    if len(_exe_cache) > 256:
        _exe_cache.clear()
    _exe_cache[pid] = name
    return name


def _game_window_pids() -> set[int]:
    """The Roblox processes showing a game-sized window (the tray helper has none)."""
    pids = set()

    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if user32.IsWindowVisible(hwnd) and _exe_of(pid.value) == GAME_EXE:
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            if rect.right - rect.left >= 200 and rect.bottom - rect.top >= 200:
                pids.add(pid.value)
        return True

    user32.EnumWindows(_ENUMPROC(visit), 0)
    return pids


def client_rect(hwnd) -> tuple[int, int, int, int]:
    """Where a window's picture is on the screen: x, y, width, height."""
    rect, origin = wintypes.RECT(), wintypes.POINT(0, 0)
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right, rect.bottom


def has_title_bar(hwnd) -> bool:
    """Whether a window has its caption. An undocked Roblox keeps its picture exactly where
    the frame is (see undock_game), so the picture's place alone can't tell docked apart."""
    return bool(user32.GetWindowLongPtrW(hwnd, -16) & 0x00C00000)  # GWL_STYLE, WS_CAPTION


def is_docked(hwnd) -> bool:
    return bool(FRAME) and client_rect(hwnd) == FRAME and not has_title_bar(hwnd)


def game_window_problem() -> str | None:
    """Why it isn't safe to send input to the game right now, or None."""
    # Windows reports no foreground window for a moment while switching. Nothing
    # receives input during that, so look again before calling it a problem.
    hwnd = user32.GetForegroundWindow()
    end = time.perf_counter() + 0.5
    while not hwnd and time.perf_counter() < end:
        time.sleep(0.01)
        hwnd = user32.GetForegroundWindow()
    exe = foreground_exe()
    if exe != GAME_EXE:
        # A window that has stopped responding is swapped for a "Ghost" owned by dwm.
        name = ctypes.create_unicode_buffer(32)
        if hwnd and user32.GetClassNameW(hwnd, name, 32) and name.value == "Ghost":
            return "a window has stopped responding (Roblox may be frozen)"
        return f"Roblox is not in front ({exe or 'no window'} is)"
    hwnd = user32.GetForegroundWindow()
    if FRAME:
        where = client_rect(hwnd)
        if where != FRAME:
            return f"Roblox isn't docked in the frame: it's at {where}, wants {FRAME}"
        if has_title_bar(hwnd):
            return "Roblox isn't docked in the frame: it still has its title bar"
        return None
    rect, info = wintypes.RECT(), MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)) or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return "can't read the Roblox window's size"
    m = info.rcMonitor
    if (m.right - m.left, m.bottom - m.top) != (Platform.width, Platform.height):
        return f"monitor is {m.right - m.left}x{m.bottom - m.top}, not {Platform.width}x{Platform.height}"
    if (rect.left, rect.top, rect.right, rect.bottom) != (m.left, m.top, m.right, m.bottom):
        return "Roblox is not fullscreen (press F11 in the game)"
    return None


class Guard:
    """Hooks and hotkey live on one thread with a message pump; a second thread
    does the releasing. Hook callbacks only set a flag: injecting from inside a
    hook would deadlock against SendInput waiting on that same hook."""

    def __init__(self, on_trip=None, window_problem=game_window_problem):
        self._remote = bool(user32.GetSystemMetrics(0x1000))  # SM_REMOTESESSION
        self.on_trip = on_trip
        self.window_problem = window_problem
        self.armed = False
        self.tripped = False
        self.stopped = False
        self.reason = ""
        self.trip_time = 0.0
        self.sent = 0  # our events injected...
        self.seen = 0  # ...and seen by the hooks
        self.foreign = 0  # events the hooks saw that weren't ours
        self.pausable = False  # a trip waits for pause_callback, rather than raising
        self.pause_callback = None  # blocks until it's fine to go on; raises GuardTripped to stop
        self.paused_total = 0.0
        self.last_foreign = None  # the latest mouse one: message, position, flags, tag
        self._last_sent = 0.0
        self._wake = threading.Event()
        self._running = False
        self._pump_id = 0
        self._pump = self._worker = None
        self._procs = (HOOKPROC(self._mouse_hook), HOOKPROC(self._key_hook))

    # ---------------------------------------------------------------- control
    def start(self):
        """Install the hooks and hotkey. Idempotent."""
        if self._running:
            return
        ready, errors = threading.Event(), []
        self._running = True
        self._pump = threading.Thread(target=self._pump_loop, args=(ready, errors), daemon=True, name="guard-pump")
        self._pump.start()
        ready.wait(5)
        if errors or not ready.is_set():
            self._running = False
            raise RuntimeError(errors[0] if errors else "guard thread did not start")
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="guard-worker")
        self._worker.start()

    def arm(self):
        """Start (or, after a pause, resume) allowing input. A stop-hotkey press
        can't be resumed: that takes a new run."""
        self.start()
        if self.stopped:
            raise GuardTripped(f"stopped with {HOTKEY_TEXT}; start a new run")
        problem = self.window_problem()
        if problem:
            raise GuardTripped(problem)
        self.sent = self.seen = 0
        self.reason, self.tripped = "", False
        self.armed = True

    def disarm(self):
        self.armed = False

    def wait_if_paused(self):
        if not self.pausable or not self.tripped or self.stopped:
            return
        started = time.perf_counter()
        try:
            self.pause_callback(self.reason)
        finally:
            self.paused_total += time.perf_counter() - started

    def check(self):
        """Raises GuardTripped unless input is allowed right now."""
        if not self.armed:
            raise GuardTripped(self.reason or "guard is not armed")
        if self.tripped:
            raise GuardTripped(self.reason)
        problem = self.window_problem()
        if problem:
            self.trip(problem)
            raise GuardTripped(problem)

    def trip(self, reason: str, stop: bool = False):
        if stop:
            self.stopped = True
            reason = f"stop hotkey ({HOTKEY_TEXT})"
        if not self.tripped or stop:
            self.reason = reason
        if not self.tripped:
            self.trip_time = time.perf_counter()
            self.tripped = True
        self._wake.set()

    def note_sent(self, count: int):
        self.sent += count
        self._last_sent = time.perf_counter()

    def close(self):
        self.armed = False
        if not self._running:
            return
        self._running = False
        self._wake.set()
        user32.PostThreadMessageW(self._pump_id, WM_QUIT, 0, 0)
        self._pump.join(2)
        self._worker.join(2)

    # ------------------------------------------------------------------ hooks
    def _mouse_hook(self, code, wparam, lparam):
        if code == 0:
            event = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if event.dwExtraInfo == TAG:
                self.seen += 1
            elif self._remote:
                # Over Remote Desktop every injected event comes back without the macro's tag
                # (12 Nov 2026: its own clicks and drags paused it), so nobody can be told apart:
                # that session is the macro's own, and F8 still stops it.
                pass
            else:
                self.foreign += 1
                self.last_foreign = (hex(wparam), (event.pt.x, event.pt.y), event.flags, event.dwExtraInfo)
                if wparam == 0x200 and not self._real_move(event.pt.x, event.pt.y):
                    # In a Remote Desktop session the macro's own camera drags come back untagged
                    # (12 Nov 2026: every turn paused halfway and the search span forever), so
                    # there only clicks, the wheel and keys count as someone at the controls.
                    return user32.CallNextHookEx(None, code, wparam, lparam)
                if self.armed and not self.tripped:
                    # Where and what it was (flags 1 = injected by another program), to tell a
                    # person from a stray source (11 Nov 2026: 14 pauses in an hour).
                    kind = {0x200: "move", 0x201: "left down", 0x204: "right down", 0x20A: "wheel"}.get(wparam, hex(wparam))
                    self.trip(f"you moved or clicked the mouse ({kind} at {event.pt.x},{event.pt.y}, "
                              f"flags {event.flags})")
        return user32.CallNextHookEx(None, code, wparam, lparam)

    MOVE_PAUSES_AT = 60  # px of the user's own mouse movement (within 1.5 s) before a pause

    def _real_move(self, x: int, y: int) -> bool:
        """A move of the user's mouse counts only once it has gone MOVE_PAUSES_AT px from where
        it started within 1.5 s: brushing the touchpad mustn't stop the run (user, 11 Nov 2026)."""
        import time as _time
        now = _time.monotonic()
        start = getattr(self, "_move_start", None)
        if start is None or now - start[2] > 1.5:
            self._move_start = (x, y, now)
            return False
        return abs(x - start[0]) + abs(y - start[1]) >= self.MOVE_PAUSES_AT

    def _key_hook(self, code, wparam, lparam):
        if code == 0:
            event = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if event.dwExtraInfo == TAG:
                self.seen += 1
            elif self._remote:
                pass  # see _mouse_hook: over Remote Desktop the macro's own keys come back untagged
            else:
                self.foreign += 1
                # Key-downs only: the release of the Enter that launched the
                # script must not count as taking over.
                if self.armed and not self.tripped and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    self.trip(f"you pressed a key (key code {event.vkCode}, flags {event.flags})")
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _pump_loop(self, ready, errors):
        self._pump_id = kernel32.GetCurrentThreadId()
        module = kernel32.GetModuleHandleW(None)
        hooks = []
        hotkey = False
        try:
            for kind, proc in ((WH_MOUSE_LL, self._procs[0]), (WH_KEYBOARD_LL, self._procs[1])):
                hook = user32.SetWindowsHookExW(kind, proc, module, 0)
                if not hook:
                    raise ctypes.WinError(ctypes.get_last_error())
                hooks.append(hook)
            hotkey = bool(user32.RegisterHotKey(None, 1, MOD_NOREPEAT, VK_F8))
            if not hotkey:
                raise RuntimeError(f"{HOTKEY_TEXT} is taken: another macro run or app already holds it")
        except Exception as error:
            errors.append(str(error))
            for hook in hooks:
                user32.UnhookWindowsHookEx(hook)
            ready.set()
            return
        ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                self.trip("", stop=True)
        user32.UnregisterHotKey(None, 1)
        for hook in hooks:
            user32.UnhookWindowsHookEx(hook)

    def _worker_loop(self):
        while self._running:
            self._wake.wait(0.05)
            self._wake.clear()
            if self.tripped:
                # Every tick, not once per trip: releasing is idempotent, and
                # this way a quick resume-then-trip can't leave a key held.
                if self.on_trip:
                    self.on_trip()
                continue
            if not self.armed:
                continue
            problem = self.window_problem()
            if problem:
                self.trip(problem)
            elif self.sent > self.seen and time.perf_counter() - self._last_sent > 1.0:
                self.trip("Windows dropped the input hook, so touching the mouse can't be detected")


ROBLOX_SETTINGS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Roblox", "GlobalBasicSettings_13.xml")


def set_lowest_graphics() -> bool:
    """Roblox's saved graphics to Manual, the lowest bar, in its settings file, just before a
    launch (Roblox isn't running, so it reads this on start and nothing overwrites it). Every
    reference picture is taken at that level; on 12 Nov 2026 the saved level was back at 10 and
    no map matched any more. True if it changed something."""
    import re
    try:
        with open(ROBLOX_SETTINGS, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    new = re.sub(r'(<token name="SavedQualityLevel">)\d+(</token>)', r"\g<1>1\g<2>", text)
    new = re.sub(r'(<int name="GraphicsQualityLevel">)\d+(</int>)', r"\g<1>1\g<2>", new)
    if new == text:
        return False
    with open(ROBLOX_SETTINGS + ".before_macro", "w", encoding="utf-8") as f:
        f.write(text)
    with open(ROBLOX_SETTINGS, "w", encoding="utf-8") as f:
        f.write(new)
    return True


SM_REMOTESESSION = 0x1000


def in_remote_session() -> bool:
    """This process runs in a Remote Desktop session (the macro's own account over RDP)."""
    return bool(user32.GetSystemMetrics(SM_REMOTESESSION))


class GdiCapture:
    """The screen copied with GDI (BitBlt), for where desktop duplication isn't offered: a Remote
    Desktop session (12 Nov 2026: the macro in its own account over RDP, so the user keeps the
    laptop). Copies only the given rectangle, top-down BGRA into one reused buffer."""

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    def __init__(self, x: int, y: int, width: int, height: int):
        import numpy as np
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        g, u = self.gdi32, user32
        for name, args, res in (("CreateCompatibleDC", [wintypes.HDC], wintypes.HDC),
                                ("CreateCompatibleBitmap", [wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.HBITMAP),
                                ("SelectObject", [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ),
                                ("BitBlt", [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                            wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD], wintypes.BOOL),
                                ("GetDIBits", [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                               ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT], ctypes.c_int),
                                ("DeleteObject", [wintypes.HGDIOBJ], wintypes.BOOL),
                                ("DeleteDC", [wintypes.HDC], wintypes.BOOL)):
            getattr(g, name).argtypes, getattr(g, name).restype = args, res
        u.GetDC.argtypes, u.GetDC.restype = [wintypes.HWND], wintypes.HDC
        u.ReleaseDC.argtypes, u.ReleaseDC.restype = [wintypes.HWND, wintypes.HDC], ctypes.c_int
        self.x, self.y, self.width, self.height = x, y, width, height
        self.screen = u.GetDC(None)
        self.memory = g.CreateCompatibleDC(self.screen)
        self.bitmap = g.CreateCompatibleBitmap(self.screen, width, height)
        g.SelectObject(self.memory, self.bitmap)
        self.info = self.BITMAPINFOHEADER()
        self.info.biSize = ctypes.sizeof(self.BITMAPINFOHEADER)
        self.info.biWidth, self.info.biHeight = width, -height  # negative: top-down rows
        self.info.biPlanes, self.info.biBitCount, self.info.biCompression = 1, 32, 0
        self.buffer = np.empty((height, width, 4), np.uint8)

    def grab(self):
        g = self.gdi32
        if not g.BitBlt(self.memory, 0, 0, self.width, self.height, self.screen, self.x, self.y, 0x00CC0020):
            raise OSError(f"BitBlt failed: {ctypes.WinError(ctypes.get_last_error())}")
        g.GetDIBits(self.memory, self.bitmap, 0, self.height, self.buffer.ctypes.data,
                    ctypes.byref(self.info), 0)
        return self.buffer[:, :, :3].copy()

    def release(self):
        self.gdi32.DeleteObject(self.bitmap)
        self.gdi32.DeleteDC(self.memory)
        user32.ReleaseDC(None, self.screen)


def grab_screen():
    """The whole screen (every monitor of this session) as BGR: the Discord bot's screenshot,
    with the app around the game. GDI, so it works in a Remote Desktop session too."""
    left, top, width, height = (user32.GetSystemMetrics(i) for i in (SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN,
                                                                   SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN))
    capture = GdiCapture(left, top, width, height)
    try:
        return capture.grab()
    finally:
        capture.release()


class WindowsPlatform(Platform):
    # Roblox on Windows ignored a click straight after an absolute jump, and took
    # it once the pointer had really moved over the button (measured 9 Nov 2026).
    nudge_to_hover = True

    def __init__(self, window_problem=game_window_problem):
        super().__init__()
        # Everything above this layer works inside the game's picture: (0, 0) is its corner.
        self.origin = FRAME[:2] if FRAME else (0, 0)
        if FRAME:
            self.width, self.height = FRAME[2:]
        self.guard = Guard(on_trip=self.release_all, window_problem=window_problem)
        self._camera = None
        self._gdi = None  # GDI capture, used in a Remote Desktop session or if duplication refuses
        self._last_frame = None
        self._residual = [0.0, 0.0]
        self._desktop = tuple(user32.GetSystemMetrics(i) for i in (SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN,
                                                                   SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN))

    def _pointer_at(self, x, y):
        return cursor_pos() == (int(x) + self.origin[0], int(y) + self.origin[1])

    @property
    def pointer_tries(self) -> int:
        # Over Remote Desktop a mouse moving over the client's window moves this same pointer (13 Nov
        # 2026: 52 refused clicks, every one while someone was on the window, none overnight), so
        # there it gets a couple of seconds to come back before a click is refused.
        return 8 if self.remote else 2

    def _crop(self, frame):
        x, y = self.origin
        return frame[y:y + self.height, x:x + self.width]

    def close(self):
        super().close()
        self.guard.close()
        if self._camera is not None:
            self._camera.release()
            self._camera = None
        if self._gdi is not None:
            self._gdi.release()
            self._gdi = None

    # ----------------------------------------------------------------- turning
    REMOTE_TAP = 0.125  # an arrow-key hold this long turns the camera 15 deg (24 make a circle,
    REMOTE_TAP_DEGREES = 15.0  # measured 10 Nov 2026 for Trick or Treat; Right turns right)
    PICTURE_DEG_PER_COUNT = 0.077  # what a count of mouse yaw turns the overhead picture (maps.py)
    REMOTE_FINE_MIN = 1.5  # degrees: less than this isn't worth a key press

    @property
    def remote(self) -> bool:
        """This runs in a Remote Desktop session (the macro's own account over RDP)."""
        return in_remote_session()

    def turn(self, dx: float, dy: float = 0.0, steps: int = 10, step_s: float = 0.01):
        """Over Remote Desktop a right-drag turns Roblox's camera by unpredictable amounts (the
        mouse arrives as absolute positions; 12 Nov 2026 every search span to a different place),
        so there the yaw is done with the arrow keys (15 deg taps, then a shorter hold for the
        rest), and only the tilt (which clamps) is still dragged."""
        if not dx or not self.remote:
            return super().turn(dx, dy, steps, step_s)
        degrees = dx * self.PICTURE_DEG_PER_COUNT
        key = "right" if degrees > 0 else "left"
        taps, rest = divmod(abs(degrees), self.REMOTE_TAP_DEGREES)
        for _ in range(int(taps)):
            self.key(key, hold=self.REMOTE_TAP)
            self.sleep(0.12)
        # What's left as a shorter hold: the camera turns at a steady rate while an arrow is
        # held. Rounding it to whole taps left 4.5-5 deg uncorrected (12 Nov 2026, 20:06): the
        # walk to the north view went astray, 8 of 16 phantoms, dead at wave 11 twice.
        if rest >= self.REMOTE_FINE_MIN:
            self.key(key, hold=self.REMOTE_TAP * rest / self.REMOTE_TAP_DEGREES)
            self.sleep(0.12)
        self.sleep(0.15)
        if dy:
            super().turn(0, dy, steps, step_s)

    # ----------------------------------------------------------------- seeing
    def _use_gdi(self):
        x, y = self.origin
        self._gdi = GdiCapture(x, y, self.width, self.height)

    def grab(self):
        if self._gdi is None and self._camera is None and in_remote_session():
            self._use_gdi()  # desktop duplication isn't offered to a Remote Desktop session
        if self._gdi is not None:
            frame = self._gdi.grab()
            self._last_frame = frame
            return frame
        import dxcam  # imported here so the input side doesn't load it

        if self._camera is None:
            # Desktop duplication can refuse for a moment ("device interface or feature level
            # is not supported", twice on 11 Nov 2026, fine a minute later): keep trying a while,
            # then copy the screen with GDI instead.
            give_up = time.perf_counter() + 30.0
            while True:
                try:
                    self._camera = dxcam.create(output_color="BGR")
                    if self._camera is None:
                        raise RuntimeError("no output to duplicate")
                    break
                except Exception:
                    if time.perf_counter() > give_up:
                        self._camera = None
                        self._use_gdi()
                        return self.grab()
                    time.sleep(2.0)
        # None means nothing changed on screen since the last frame.
        deadline = time.perf_counter() + 1.0
        while True:
            try:
                frame = self._camera.grab()
            except Exception:  # the duplication was lost (display change): start it again
                self._camera = None
                return self.grab()
            if frame is not None:
                self._last_frame = frame
                return self._crop(frame).copy()
            if self._last_frame is not None:
                return self._crop(self._last_frame).copy()
            if time.perf_counter() > deadline:
                raise RuntimeError("screen capture returned no frame in 1 s")
            time.sleep(0.005)

    # --------------------------------------------------------------- touching
    def _send(self, *inputs: INPUT):
        array = (INPUT * len(inputs))(*inputs)
        self.guard.note_sent(len(inputs))
        if user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT)) != len(inputs):
            raise OSError(f"SendInput was blocked: {ctypes.WinError(ctypes.get_last_error())}")

    @staticmethod
    def _mouse(flags: int, dx: int = 0, dy: int = 0, data: int = 0, tag: int = TAG) -> INPUT:
        event = INPUT(type=INPUT_MOUSE)
        event.u.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, tag)
        return event

    def _move(self, x, y):
        vx, vy, vw, vh = self._desktop
        self._send(self._mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                               to_absolute(x + self.origin[0], vx, vw), to_absolute(y + self.origin[1], vy, vh)))

    def _rel(self, dx, dy):
        # Only whole counts can be sent; keep the remainder so a split-up turn
        # adds up to exactly what was asked (yaw depends on it).
        self._residual[0] += dx
        self._residual[1] += dy
        whole_x, whole_y = round(self._residual[0]), round(self._residual[1])
        self._residual[0] -= whole_x
        self._residual[1] -= whole_y
        if whole_x or whole_y:  # Windows drops zero-distance moves before the hooks
            self._send(self._mouse(MOUSEEVENTF_MOVE, whole_x, whole_y))

    def _button(self, button, down):
        self._send(self._mouse(BUTTON_FLAGS[button][0 if down else 1]))

    def _wheel(self, amount):
        # Our unit: 15 a notch, positive down. Windows: 120 a notch, positive up.
        self._send(self._mouse(MOUSEEVENTF_WHEEL, data=round(-amount * 8)))

    @staticmethod
    def _keyboard(scan: int, flags: int, tag: int = TAG) -> INPUT:
        event = INPUT(type=INPUT_KEYBOARD)
        event.u.ki = KEYBDINPUT(0, scan, flags, 0, tag)
        return event

    def _key(self, name, down):
        scan, extended = scan_code(name)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0) | (0 if down else KEYEVENTF_KEYUP)
        self._send(self._keyboard(scan, flags))

    def _text(self, text):
        raw = text.encode("utf-16-le")
        for i in range(0, len(raw), 2):
            unit = int.from_bytes(raw[i:i + 2], "little")
            self._send(self._keyboard(unit, KEYEVENTF_UNICODE), self._keyboard(unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
            time.sleep(0.015)

    # ------------------------------------------------------------------- game
    @staticmethod
    def _own_games(include_tray: bool = False) -> list:
        """Roblox processes in this Windows session only. Another account's Roblox (the user's own,
        while the macro runs in its Remote Desktop account) can't be closed from here and isn't
        ours to count, and Roblox's tray helper ("--launch-to-tray", no window) isn't a game:
        on 12 Nov 2026, 23:39, the user's tray helper made every fresh start fail with
        AccessDenied, 20 times, until the supervisor gave up.

        But the tray helper becomes the game itself when Play is pressed (Roblox's tray mode,
        "AppState/TrayMode" in its log), keeping that flag. On 17 Nov 2026 such a game counted as
        not running, so Setup started Roblox again (the game left its server for the link) and
        recovery then closed it. A flagged process with a game window is the game."""
        mine = _session_of(os.getpid())
        found = []
        windowed = None
        for process in psutil.process_iter(["name"]):
            if (process.info["name"] or "").lower() != GAME_EXE or _session_of(process.pid) != mine:
                continue
            if not include_tray:
                try:
                    tray = "--launch-to-tray" in process.cmdline()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
                if tray:
                    if windowed is None:
                        windowed = _game_window_pids()
                    if process.pid not in windowed:
                        continue
            found.append(process)
        return found

    def game_running(self):
        return bool(self._own_games())

    def launch_game(self):
        set_lowest_graphics()
        # Through a cmd that exits at once, so Roblox is nobody's descendant. Started with
        # os.startfile it was the macro's child, and when the Claude app that had launched a test
        # restarted for an update, its tree kill ended Roblox too (10 Nov 2026). Explorer can't be
        # the middleman: it doesn't open roblox:// links (it showed the Documents folder instead).
        # The macro's own job lets children leave silently, so no job flag is needed.
        # The Config's private server if one is set (macro/platform/links.py), else a public one.
        import subprocess

        from macro.platform.links import launch_uri
        # Quoted for cmd: unquoted, the "&" in a private server address ends the command there, so
        # Roblox got only "roblox://placeId=..." (a public server) or a share link without its
        # "&type=Server" ("This link doesn't exist"). 10 Nov 2026.
        subprocess.Popen(f'cmd.exe /d /c start "" "{launch_uri()}"', close_fds=True,
                         creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP

    def _game_windows(self) -> list:
        found = []

        def visit(hwnd, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if user32.IsWindowVisible(hwnd) and _exe_of(pid.value) == GAME_EXE:
                found.append(hwnd)
            return True

        user32.EnumWindows(_ENUMPROC(visit), 0)
        return found

    @staticmethod
    def installer_running() -> bool:
        return any((pr.info["name"] or "").lower() == "robloxplayerinstaller.exe"
                   for pr in psutil.process_iter(["name"]))

    def game_frozen(self) -> bool:
        """Windows has marked the Roblox window as not responding."""
        return any(user32.IsHungAppWindow(hwnd) for hwnd in self._game_windows())

    def undock_game(self):
        """Give Roblox back its title bar, as a normal window, around the very same picture.

        Its picture must not change size here: resizing Roblox while it is loading (just after
        a teleport, or on its home page) sent its own core UI script into a loop, and its
        watchdog killed it a few minutes later (10 Nov 2026, twice, both in Roblox's log right
        after a resize to 1278x792). So the frame grows outward and the client area stays put.
        The move is posted, not waited on, so a busy Roblox can't hold this window up."""
        windows = self._game_windows()
        if not windows:
            return
        hwnd = windows[0]
        GWL_STYLE = -16
        styles = 0x00C00000 | 0x00040000 | 0x00020000 | 0x00010000 | 0x00080000
        style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE) | styles
        x, y, width, height = client_rect(hwnd)
        rect = wintypes.RECT(x, y, x + width, y + height)
        user32.AdjustWindowRectExForDpi(ctypes.byref(rect), wintypes.DWORD(style & 0xFFFFFFFF), False, 0,
                                        user32.GetDpiForWindow(hwnd))
        # Keep the title bar on screen.
        shift = max(0, -rect.top)
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
        SWP_NOZORDER, SWP_FRAMECHANGED, SWP_NOACTIVATE, SWP_ASYNCWINDOWPOS = 0x0004, 0x0020, 0x0010, 0x4000
        user32.SetWindowPos(hwnd, None, rect.left, rect.top + shift, rect.right - rect.left, rect.bottom - rect.top,
                            SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)

    def close_game(self):
        """End Roblox, for restarting after a freeze. Terminating is all it does: the
        process's memory is never read or touched."""
        for process in self._own_games(include_tray=True):
            try:
                process.kill()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
        time.sleep(1.0)

    def dock_game(self) -> bool:
        """Put Roblox's picture exactly in the frame. It stays its own window: this only
        takes off its title bar and moves it."""
        windows = self._game_windows()
        if not windows or not FRAME:
            return False
        hwnd = windows[0]
        x, y, width, height = FRAME
        # Its own fullscreen mode would fight the move, so leave that first. A fullscreen
        # Roblox has no title bar, unlike one we've already docked.
        monitor = MONITORINFO()
        monitor.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST), ctypes.byref(monitor))
        m = monitor.rcMonitor
        if client_rect(hwnd) == (m.left, m.top, m.right - m.left, m.bottom - m.top):
            self._key("f11", True)
            self._key("f11", False)
            time.sleep(1.5)
        if user32.IsZoomed(hwnd) or user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            time.sleep(0.5)
        GWL_STYLE = -16
        WS_CAPTION, WS_THICKFRAME, WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_SYSMENU = (0x00C00000, 0x00040000, 0x00020000,
                                                                                  0x00010000, 0x00080000)
        style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style & ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX
                                                            | WS_MAXIMIZEBOX | WS_SYSMENU))
        SWP_NOZORDER, SWP_FRAMECHANGED, SWP_NOACTIVATE = 0x0004, 0x0020, 0x0010
        user32.SetWindowPos(hwnd, None, x, y, width, height, SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE)
        time.sleep(0.5)
        return is_docked(hwnd)

    def make_game_ready(self, timeout: float = 90.0) -> str | None:
        """Start Roblox if it isn't running, bring it to the front and put it where it
        belongs: in the frame, or fullscreen. Returns None once ready, or what's still
        wrong. Starting it ends any other session on the account, so the caller needs
        permission."""
        if not self.game_running():
            self.launch_game()
        end = time.perf_counter() + timeout
        problem = "Roblox never opened a window"
        pressed_f11 = 0.0
        hung_since = None
        while time.perf_counter() < end:
            # Roblox updates itself on launch now and then: its installer runs first (about a
            # minute), so the wait doesn't count while it does (10 Nov 2026).
            if self.installer_running():
                end = max(end, time.perf_counter() + 30)
                time.sleep(1.0)
                continue
            # A Roblox that has stopped responding can't be moved or played: start it afresh.
            if self.game_frozen():
                hung_since = hung_since or time.perf_counter()
                if time.perf_counter() - hung_since > 10:
                    self.close_game()
                    self.launch_game()
                    hung_since = None
                    end = time.perf_counter() + timeout
                    time.sleep(3)
                    continue
            else:
                hung_since = None
            if self.focus_game():
                problem = game_window_problem()
                if problem is None:
                    return None
                if FRAME:
                    self.dock_game()
                    time.sleep(0.5)
                    continue
                # F11 toggles, so only press it once the last press has had time.
                if "not fullscreen" in problem and time.perf_counter() - pressed_f11 > 4:
                    self._key("f11", True)
                    self._key("f11", False)
                    pressed_f11 = time.perf_counter()
            time.sleep(0.5)
        return problem

    def focus_game(self) -> bool:
        """Bring the Roblox window to the front. Windows only lets a process do
        this just after a key event, hence the Alt tap."""
        found = self._game_windows()
        if not found:
            return False
        hwnd = found[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        alt = scan_code("alt")[0]
        self._send(self._keyboard(alt, KEYEVENTF_SCANCODE), self._keyboard(alt, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP))
        user32.SetForegroundWindow(hwnd)
        end = time.perf_counter() + 2
        while time.perf_counter() < end:
            if user32.GetForegroundWindow() == hwnd:
                return True
            time.sleep(0.02)
        return False


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds() -> float:
    """How long since any mouse or keyboard input (ours included)."""
    info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
    user32.GetLastInputInfo(ctypes.byref(info))
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def wait_hands_off(seconds: float = 3.0, timeout: float = 60.0) -> bool:
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        if idle_seconds() >= seconds:
            return True
        time.sleep(0.05)
    return False


def cursor_pos() -> tuple[int, int]:
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def mouse_settings() -> dict:
    """Windows pointer settings worth knowing for calibration (read only)."""
    SPI_GETMOUSE, SPI_GETMOUSESPEED = 0x0003, 0x0070
    accel = (ctypes.c_int * 3)()
    speed = ctypes.c_int()
    user32.SystemParametersInfoW(SPI_GETMOUSE, 0, accel, 0)
    user32.SystemParametersInfoW(SPI_GETMOUSESPEED, 0, ctypes.byref(speed), 0)
    return {"enhance_pointer_precision": bool(accel[2]), "pointer_speed": speed.value,
            "buttons_swapped": bool(user32.GetSystemMetrics(23))}
