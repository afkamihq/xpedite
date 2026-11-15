"""Farming from a second Windows account over Remote Desktop (user, 15 Nov 2026): the macro gets
its own session, desktop and cursor, and the PC stays usable while it plays. This checks what that
needs and sets the parts xpedite can set; the players' guide is docs/SECOND_SESSION.md.

Windows lets one person use a home PC at a time. A wrapper (RDPWrapKit/TermWrap, or the classic
RDP Wrapper) lifts that; it isn't Microsoft's and xpedite never ships or installs it: the player
does. Everything else is here:
  - checks (read only): Windows edition and build; which wrapper the Remote Desktop service
    loads, and for the classic one whether its rdpwrap.ini knows this build; Remote Desktop on
    and listening; the farm account and whether it may sign in over Remote Desktop; the sessions
    signed in now; the RDP client's "keep drawing when minimized"; the connection file; the GPU
    policy for sessions and hardware H.264 off; memory; graphics adapters; whether other
    accounts can reach the macro's folder and its Python. Inside the farm session: its size,
    Roblox installed there, the desktop shortcut.
  - fixes without admin: the connection file (1920x1080, scaled into any window) and "keep
    drawing when minimized", both for the account that connects.
  - one admin step (Windows asks): Remote Desktop on, Roblox in sessions on the graphics card,
    hardware H.264 off (pink/green smears, 12 Nov), the farm account in Remote Desktop Users.
    Undo takes the two policy values back out.
Every value was measured on the user's laptop, 12-13 Nov 2026 (docs/WINDOWS.md, "Farming from a
second Windows account over Remote Desktop").

`python -m macro.setup.second_session` prints the checks. The admin step runs as
`--apply-admin` / `--undo-admin` in a process Windows elevates (`run_elevated`).
"""
from __future__ import annotations

import ctypes
import glob
import json
import os
import socket
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass

import winreg

from macro import brand
from macro.setup.checks import Check

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUIDE = os.path.join(ROOT, "docs", "SECOND_SESSION.md")
SHORTCUT_SCRIPT = os.path.join(ROOT, "scripts", "make-shortcut.bat")
SHORTCUT_NAME = f"{brand.ASCII_NAME}.lnk"          # what scripts/make-shortcut.bat makes
FILE_NAME = f"{brand.ASCII_NAME} farm.rdp"
LOOPBACK = "127.0.0.2"     # another loopback address: Windows refuses Remote Desktop to 127.0.0.1
SIZE = (1920, 1080)        # the session's screen: every picture was measured at this size

HKLM, HKCU = winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER
TS_KEY = r"SYSTEM\CurrentControlSet\Control\Terminal Server"
RDP_TCP = TS_KEY + r"\WinStations\RDP-Tcp"
TS_SERVICE = r"SYSTEM\CurrentControlSet\Services\TermService\Parameters"
POLICY = r"SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services"
CLIENT = r"Software\Microsoft\Terminal Server Client"
CURRENT = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
VIDEO_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
# (name, value) the admin step writes into POLICY; undo deletes them.
GPU_POLICY = (("bEnumerateHWBeforeSW", 1),          # sessions may use the graphics card
              ("AVCHardwareEncodePreferred", 0))    # no GPU H.264: it smeared the picture
# The connection file: the user's working macro.rdp of 12 Nov, without its signature.
RDP_FIELDS = (("screen mode id", "i", 1), ("use multimon", "i", 0),
              ("desktopwidth", "i", SIZE[0]), ("desktopheight", "i", SIZE[1]), ("session bpp", "i", 32),
              ("smart sizing", "i", 1), ("dynamic resolution", "i", 0),
              ("full address", "s", LOOPBACK), ("alternate full address", "s", LOOPBACK),
              ("autoreconnection enabled", "i", 1), ("compression", "i", 1), ("keyboardhook", "i", 0),
              ("audiocapturemode", "i", 0), ("audiomode", "i", 0), ("redirectclipboard", "i", 1),
              ("redirectdrives", "i", 0), ("redirectprinters", "i", 0), ("redirectsmartcards", "i", 0),
              ("redirectwebauthn", "i", 0), ("videoplaybackmode", "i", 1), ("connection type", "i", 7),
              ("displayconnectionbar", "i", 1), ("disable wallpaper", "i", 1),
              ("allow font smoothing", "i", 1), ("allow desktop composition", "i", 1),
              ("bitmapcachepersistenable", "i", 1), ("authentication level", "i", 0),
              ("prompt for credentials", "i", 0), ("negotiate security layer", "i", 1),
              ("enablecredsspsupport", "i", 1), ("promptcredentialonce", "i", 0))
WRAPPERS = {"termwrap.dll": "TermWrap (RDPWrapKit)", "rdpwrap.dll": "RDP Wrapper"}
WELL_KNOWN = {"everyone": "S-1-1-0", "authenticated": "S-1-5-11", "users": "S-1-5-32-545",
              "admins": "S-1-5-32-544", "remote_desktop_users": "S-1-5-32-555"}
NOT_A_PERSON = ("defaultuser", "wdagutilityaccount")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
netapi32 = ctypes.WinDLL("netapi32")
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
user32 = ctypes.WinDLL("user32")
version_dll = ctypes.WinDLL("version")


@dataclass
class Item(Check):
    """A check, plus what fixes it: "admin" (the elevated step), "file" (connection file and
    minimized drawing), "shortcut", "account" (the player makes one), "wrapper" (the player
    installs one), or "" (nothing to do, or only the guide helps)."""
    action: str = ""


# --------------------------------------------------------------------------------- reading
def _reg(root, path: str, name: str, default=None):
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def in_remote_session() -> bool:
    return bool(user32.GetSystemMetrics(0x1000))   # SM_REMOTESESSION


def me() -> str:
    return os.environ.get("USERNAME", "")


def windows() -> dict:
    edition = str(_reg(HKLM, CURRENT, "EditionID", "") or "")
    build = int(_reg(HKLM, CURRENT, "CurrentBuildNumber", "0") or 0)
    ubr = int(_reg(HKLM, CURRENT, "UBR", 0) or 0)
    words = {"core": "Home", "coresinglelanguage": "Home Single Language", "corecountryspecific": "Home China",
             "professional": "Pro", "professionalworkstation": "Pro for Workstations",
             "enterprise": "Enterprise", "education": "Education"}
    name = "Windows 11" if build >= 22000 else "Windows 10"
    return {"name": f"{name} {words.get(edition.lower(), edition)}".strip(), "build": f"{build}.{ubr}",
            "home": edition.lower().startswith("core"), "version": _reg(HKLM, CURRENT, "DisplayVersion", "")}


def file_version(path: str) -> str | None:
    """A DLL's file version, as rdpwrap.ini names its sections ("10.0.26100.1150")."""
    version_dll.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    version_dll.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    version_dll.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.POINTER(wintypes.UINT)]
    size = version_dll.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not version_dll.GetFileVersionInfoW(path, 0, size, data):
        return None
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not version_dll.VerQueryValueW(data, "\\", ctypes.byref(pointer), ctypes.byref(length)) or not pointer.value:
        return None
    words = (wintypes.DWORD * 4).from_address(pointer.value + 8)   # after signature and struct version
    ms, ls = words[0], words[1]
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def wrapper() -> dict:
    """Which DLL the Remote Desktop service loads. Windows' own is termsrv.dll; a wrapper puts
    itself there and loads termsrv.dll with the one-session limit patched out."""
    dll = os.path.expandvars(str(_reg(HKLM, TS_SERVICE, "ServiceDll", "") or ""))
    base = os.path.basename(dll).lower()
    found = {"dll": dll, "name": WRAPPERS.get(base), "ini": None, "ini_knows": None, "termsrv": None}
    if base not in ("", "termsrv.dll") and found["name"] is None:
        found["name"] = os.path.basename(dll)
    if base == "rdpwrap.dll":   # the classic one needs this Windows build listed in its rdpwrap.ini
        system = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                              "Sysnative" if sys.maxsize < 2 ** 32 else "System32")
        found["termsrv"] = file_version(os.path.join(system, "termsrv.dll"))
        found["ini"] = os.path.join(os.path.dirname(dll), "rdpwrap.ini")
        try:
            with open(found["ini"], encoding="utf-8", errors="replace") as f:
                found["ini_knows"] = found["termsrv"] is not None and f"[{found['termsrv']}]" in f.read()
        except OSError:
            pass
    return found


def rdp_port() -> int:
    return int(_reg(HKLM, RDP_TCP, "PortNumber", 3389) or 3389)


def listening(port: int | None = None) -> bool:
    try:
        with socket.create_connection((LOOPBACK, port or rdp_port()), timeout=1.0):
            return True
    except OSError:
        return False


class _UserInfo1(ctypes.Structure):
    _fields_ = [("name", wintypes.LPWSTR), ("password", wintypes.LPWSTR), ("password_age", wintypes.DWORD),
                ("priv", wintypes.DWORD), ("home_dir", wintypes.LPWSTR), ("comment", wintypes.LPWSTR),
                ("flags", wintypes.DWORD), ("script_path", wintypes.LPWSTR)]


def local_accounts() -> list[dict]:
    """This PC's local accounts that a person could sign in to: enabled, not built in."""
    netapi32.NetUserEnum.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
                                     wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                                     ctypes.POINTER(wintypes.DWORD)]
    accounts, resume = [], wintypes.DWORD(0)
    while True:
        buffer, read, total = ctypes.c_void_p(), wintypes.DWORD(), wintypes.DWORD()
        status = netapi32.NetUserEnum(None, 1, 2, ctypes.byref(buffer), 0xFFFFFFFF, ctypes.byref(read),
                                      ctypes.byref(total), ctypes.byref(resume))   # 2: normal accounts
        if status not in (0, 234) or not buffer.value:
            break
        rows = ctypes.cast(buffer, ctypes.POINTER(_UserInfo1))
        for i in range(read.value):
            row = rows[i]
            name = row.name or ""
            if row.flags & 0x2 or name.lower().startswith(NOT_A_PERSON):   # UF_ACCOUNTDISABLE
                continue
            accounts.append({"name": name, "admin": row.priv == 2})
        netapi32.NetApiBufferFree(buffer)
        if status != 234:   # ERROR_MORE_DATA
            break
    return accounts


def _sid_name(sid_text: str) -> str | None:
    """A well-known group's name in this Windows' language ("Remote Desktop Users")."""
    advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.LookupAccountSidW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, wintypes.LPWSTR,
                                           ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR,
                                           ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_int)]
    sid = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW(sid_text, ctypes.byref(sid)):
        return None
    try:
        name, domain = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
        n, d, use = wintypes.DWORD(256), wintypes.DWORD(256), ctypes.c_int()
        if not advapi32.LookupAccountSidW(None, sid, name, ctypes.byref(n), domain, ctypes.byref(d), ctypes.byref(use)):
            return None
        return name.value
    finally:
        kernel32.LocalFree(sid)


def account_groups(account: str) -> list[str]:
    netapi32.NetUserGetLocalGroups.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                               ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD,
                                               ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    buffer, read, total = ctypes.c_void_p(), wintypes.DWORD(), wintypes.DWORD()
    if netapi32.NetUserGetLocalGroups(None, account, 0, 1, ctypes.byref(buffer), 0xFFFFFFFF, ctypes.byref(read),
                                      ctypes.byref(total)) != 0 or not buffer.value:
        return []
    try:
        names = ctypes.cast(buffer, ctypes.POINTER(wintypes.LPWSTR))
        return [names[i] for i in range(read.value)]
    finally:
        netapi32.NetApiBufferFree(buffer)


def may_use_remote_desktop(account: str) -> bool:
    groups = {g.lower() for g in account_groups(account)}
    wanted = {(_sid_name(WELL_KNOWN["admins"]) or "Administrators").lower(),
              (_sid_name(WELL_KNOWN["remote_desktop_users"]) or "Remote Desktop Users").lower()}
    return bool(groups & wanted)


class _SessionInfo(ctypes.Structure):
    _fields_ = [("id", wintypes.DWORD), ("station", wintypes.LPWSTR), ("state", ctypes.c_int)]


STATES = {0: "active", 1: "connected", 4: "disconnected", 5: "idle", 6: "listening"}


def sessions() -> list[dict]:
    """Who is signed in to this PC right now, and whether each session is being shown."""
    wtsapi32.WTSEnumerateSessionsW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                               ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    wtsapi32.WTSQuerySessionInformationW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
                                                     ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    wtsapi32.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    buffer, count = ctypes.c_void_p(), wintypes.DWORD()
    if not wtsapi32.WTSEnumerateSessionsW(None, 0, 1, ctypes.byref(buffer), ctypes.byref(count)):
        return []
    found = []
    try:
        rows = ctypes.cast(buffer, ctypes.POINTER(_SessionInfo))
        for i in range(count.value):
            row = rows[i]
            name, size = ctypes.c_void_p(), wintypes.DWORD()
            user = ""
            if wtsapi32.WTSQuerySessionInformationW(None, row.id, 5, ctypes.byref(name), ctypes.byref(size)):
                user = ctypes.wstring_at(name.value) if name.value else ""
                wtsapi32.WTSFreeMemory(name)
            if user:
                found.append({"id": row.id, "station": row.station or "", "state": STATES.get(row.state, str(row.state)),
                              "user": user})
    finally:
        wtsapi32.WTSFreeMemory(buffer)
    return found


def desktop() -> str:
    """This account's Desktop folder, wherever it is (OneDrive moves it)."""
    path = ctypes.create_unicode_buffer(260)
    if shell32.SHGetFolderPathW(None, 0x10, None, 0, path) == 0:   # CSIDL_DESKTOPDIRECTORY
        return path.value
    return os.path.join(os.path.expanduser("~"), "Desktop")


def read_rdp(path: str) -> dict[str, str]:
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return {}
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
    fields = {}
    for line in text.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            fields[parts[0].strip().lower()] = parts[2].strip()
    return fields


def connection_files() -> list[str]:
    """Connection files on the Desktop (and one folder down) that point at this PC: ours first."""
    root = desktop()
    ours = os.path.join(root, FILE_NAME)
    found = [ours] if os.path.exists(ours) else []
    for path in glob.glob(os.path.join(root, "*.rdp")) + glob.glob(os.path.join(root, "*", "*.rdp")):
        if path not in found and read_rdp(path).get("full address", "").startswith("127."):
            found.append(path)
    return found


def rdp_problems(fields: dict[str, str], account: str | None) -> list[str]:
    problems = []
    if not fields.get("full address", "").startswith("127."):
        problems.append(f"address isn't {LOOPBACK}")
    if (fields.get("desktopwidth"), fields.get("desktopheight")) != (str(SIZE[0]), str(SIZE[1])):
        problems.append(f"size isn't {SIZE[0]}x{SIZE[1]}")
    if fields.get("dynamic resolution") != "0":
        problems.append("resizes with the window")
    if fields.get("smart sizing") != "1":
        problems.append("doesn't scale into the window")
    if account and fields.get("username", "").split("\\")[-1].lower() != account.lower():
        problems.append(f"signs in as {fields.get('username') or 'nobody set'}")
    return problems


def total_memory_gb() -> float:
    class Status(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD), ("total", ctypes.c_ulonglong),
                    ("free", ctypes.c_ulonglong), ("page_total", ctypes.c_ulonglong), ("page_free", ctypes.c_ulonglong),
                    ("virtual_total", ctypes.c_ulonglong), ("virtual_free", ctypes.c_ulonglong),
                    ("extended", ctypes.c_ulonglong)]
    status = Status()
    status.length = ctypes.sizeof(Status)
    kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.total / 2 ** 30


def graphics_adapters() -> list[str]:
    names = []
    try:
        with winreg.OpenKey(HKLM, VIDEO_CLASS, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                sub = winreg.EnumKey(key, i)
                if sub.isdigit():
                    name = _reg(HKLM, f"{VIDEO_CLASS}\\{sub}", "DriverDesc")
                    if name and name not in names and not any(
                            w in name.lower() for w in ("basic display", "remote display", "indirect display",
                                                        "virtual display", "parsec")):
                        names.append(name)
    except OSError:
        pass
    return names


class _Trustee(ctypes.Structure):
    _fields_ = [("multiple", ctypes.c_void_p), ("operation", ctypes.c_int), ("form", ctypes.c_int),
                ("type", ctypes.c_int), ("name", ctypes.c_void_p)]


def others_may(path: str, write: bool) -> bool | None:
    """Can any other account on this PC read (and write) this folder? Answered from the folder's
    own permissions for Everyone, Authenticated Users and Users, which every account belongs to.
    Folders inside C:\\Users\\<you> are yours alone by default."""
    advapi32.GetNamedSecurityInfoW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p,
                                               ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                                               ctypes.POINTER(ctypes.c_void_p)]
    advapi32.GetEffectiveRightsFromAclW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Trustee),
                                                    ctypes.POINTER(wintypes.DWORD)]
    dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    if advapi32.GetNamedSecurityInfoW(path, 1, 4, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor)):
        return None
    try:
        if not dacl.value:
            return True    # no permissions at all (FAT/exFAT drives): everyone may
        rights = 0
        for key in ("everyone", "authenticated", "users"):
            sid = ctypes.c_void_p()
            if not advapi32.ConvertStringSidToSidW(WELL_KNOWN[key], ctypes.byref(sid)):
                continue
            trustee = _Trustee(None, 0, 0, 5, sid.value)   # by SID, a well-known group
            mask = wintypes.DWORD()
            if advapi32.GetEffectiveRightsFromAclW(dacl, ctypes.byref(trustee), ctypes.byref(mask)) == 0:
                rights |= mask.value
            kernel32.LocalFree(sid)
        need = 0x1 | 0x20 | (0x2 | 0x4 if write else 0)   # list/read, traverse, add file/folder
        return rights & need == need
    finally:
        kernel32.LocalFree(descriptor)


def roblox_installed() -> str | None:
    local = os.environ.get("LOCALAPPDATA", "")
    for pattern in (r"Roblox\Versions\*\RobloxPlayerBeta.exe", r"Bloxstrap\Versions\*\RobloxPlayerBeta.exe",
                    r"Fishstrap\Versions\*\RobloxPlayerBeta.exe"):
        hits = glob.glob(os.path.join(local, pattern))
        if hits:
            return hits[0]
    return None


def default_account() -> str | None:
    """The farm account to suggest: the one our connection file names, else the only other one."""
    for path in connection_files():
        name = read_rdp(path).get("username", "").split("\\")[-1]
        if name and name.lower() != me().lower():
            return name
    others = [a["name"] for a in local_accounts() if a["name"].lower() != me().lower()]
    return others[0] if len(others) == 1 else None


# ---------------------------------------------------------------------------------- checks
def host_checks(account: str | None) -> list[Item]:
    """In the player's own account, the one that connects."""
    items = []
    win = windows()
    items.append(Item("Windows", "Edition", True, f"{win['name']}, build {win['build']}",
                      "Home has no Remote Desktop host and Pro allows one session at a time: either way a "
                      "wrapper is what lets the farm account sign in beside you."))
    wrap = wrapper()
    if wrap["name"] is None:
        items.append(Item("Windows", "Wrapper", False, "none (Windows' own termsrv.dll)",
                          "Install RDPWrapKit (or RDP Wrapper) yourself: step 2 of the guide.", "wrapper"))
    elif wrap["ini_knows"] is False:
        items.append(Item("Windows", "Wrapper", False, f"{wrap['name']}, doesn't know termsrv {wrap['termsrv']}",
                          "A Windows update moved past what its rdpwrap.ini knows. Replace rdpwrap.ini with the "
                          "newest one (guide, Troubleshooting), or switch to RDPWrapKit, which needs no ini.",
                          "wrapper"))
    else:
        items.append(Item("Windows", "Wrapper", True, wrap["name"]))
    deny = _reg(HKLM, TS_KEY, "fDenyTSConnections", 1)
    port = rdp_port()
    up = listening(port)
    items.append(Item("Windows", "Remote Desktop", up, "listening" if up else
                      ("off" if deny else f"not answering on {LOOPBACK}:{port}"),
                      "" if up else ("The admin step turns it on." if deny else
                                     "The wrapper isn't running: restart the PC; if it stays like this, "
                                     "reinstall the wrapper."), "" if up else ("admin" if deny else "wrapper")))
    now = sessions()
    accounts = local_accounts()
    names = {a["name"].lower(): a for a in accounts}
    if not account:
        items.append(Item("Account", "Farm account", False, "none picked" if len(accounts) > 1 else "none yet",
                          "Make a second Windows account with a password (step 3 of the guide), then pick it here.",
                          "account"))
    elif account.lower() not in names:
        items.append(Item("Account", "Farm account", False, f"{account}: not on this PC",
                          "Make it in Settings > Accounts > Other users, or pick another.", "account"))
    else:
        info = names[account.lower()]
        items.append(Item("Account", "Farm account", True, f"{account} ({'admin' if info['admin'] else 'standard'})"))
        allowed = info["admin"] or may_use_remote_desktop(account)
        items.append(Item("Account", "May use Remote Desktop", allowed,
                          "yes" if allowed else "not in Remote Desktop Users",
                          "" if allowed else "The admin step adds it.", "" if allowed else "admin"))
        farm = [s for s in now if s["user"].lower() == account.lower()]
        mine = [s for s in now if s["user"].lower() == me().lower()]
        if farm:
            shown = farm[0]["state"] == "active"
            both = shown and any(s["state"] == "active" for s in mine)
            items.append(Item("Account", "Farm session", True if shown else None,
                              f"signed in, {'showing' if shown else farm[0]['state']}"
                              + (", beside yours" if both else ""),
                              "" if shown else "Connect again: a disconnected session has no screen or input, "
                                               "so the macro can't play there."))
        else:   # once it has signed in, its password evidently works
            items.append(Item("Account", "Password", None, "can't be read",
                              "Remote Desktop refuses accounts without a password: give the farm account one."))

    keep = _reg(HKCU, CLIENT, "RemoteDesktop_SuppressWhenMinimized")
    items.append(Item("Connection", "Keeps drawing minimized", keep == 2, "yes" if keep == 2 else "no",
                      "" if keep == 2 else "Without it a minimized session stops drawing and the macro goes blind. "
                                           "\"Write the connection file\" sets it.", "" if keep == 2 else "file"))
    files = connection_files()
    if not files:
        items.append(Item("Connection", "Connection file", False, "none on the Desktop",
                          f"\"Write the connection file\" puts {FILE_NAME} on your Desktop.", "file"))
    else:
        problems = rdp_problems(read_rdp(files[0]), account)
        items.append(Item("Connection", "Connection file", not problems,
                          os.path.basename(files[0]) + ("" if not problems else ": " + ", ".join(problems)),
                          "" if not problems else "\"Write the connection file\" makes a right one.",
                          "" if not problems else "file"))

    items.extend(_gpu_items())
    memory = total_memory_gb()
    items.append(Item("Hardware", "Memory", True if memory >= 15 else (None if memory >= 7.5 else False),
                      f"{memory:.0f} GB",
                      "" if memory >= 15 else ("Roblox runs twice (yours and the farm's): close other apps while "
                                               "it plays." if memory >= 7.5 else
                                               "Two sessions with Roblox need about 3 GB more than one: "
                                               "farm in your own account instead.")))
    adapters = graphics_adapters()
    items.append(Item("Hardware", "Graphics", bool(adapters) or None, ", ".join(adapters) or "none found",
                      "" if adapters else "Without a graphics driver Roblox in the session draws on the CPU."))
    items.extend(_reach_items())
    return items


def _gpu_items() -> list[Item]:
    gpu = _reg(HKLM, POLICY, "bEnumerateHWBeforeSW")
    encode = _reg(HKLM, POLICY, "AVCHardwareEncodePreferred")
    return [Item("Graphics", "Sessions use the graphics card", gpu == 1, "yes" if gpu == 1 else "no",
                 "" if gpu == 1 else "Remote Desktop sessions draw on the CPU unless this policy is on: Roblox "
                                     "crawls. The admin step turns it on.", "" if gpu == 1 else "admin"),
            Item("Graphics", "Hardware H.264 off", encode != 1, "off" if encode != 1 else "on",
                 "" if encode != 1 else "It smeared pink and green over the picture on the user's laptop. "
                                        "The admin step turns it off.", "" if encode != 1 else "admin")]


def _reach_items() -> list[Item]:
    folder = others_may(ROOT, write=True)
    python = others_may(sys.base_prefix, write=False)
    return [Item("Files", "Macro folder reachable", folder,
                 ROOT if folder else f"{ROOT}: yours only" if folder is False else ROOT,
                 "" if folder else "The farm account can't open this folder. Move xpedite out of your user "
                                   "folder, for example to C:\\xpedite (guide, step 1)."),
            Item("Files", "Python reachable", python,
                 sys.base_prefix if python else f"{sys.base_prefix}: yours only" if python is False else sys.base_prefix,
                 "" if python else "The farm account can't run this Python. Install Python for all users, or "
                                   "keep a copy inside the macro folder (guide, step 1).")]


def session_checks() -> list[Item]:
    """Inside the farm account's Remote Desktop session."""
    items = [Item("Session", "Remote Desktop session", True, f"signed in as {me()}")]
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    size = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    items.append(Item("Session", "Screen size", size == SIZE, f"{size[0]}x{size[1]}",
                      "" if size == SIZE else f"Connect with {FILE_NAME} (made in your own account): it sets "
                                              f"{SIZE[0]}x{SIZE[1]} whatever your screen."))
    roblox = roblox_installed()
    items.append(Item("Session", "Roblox in this account", bool(roblox), "installed" if roblox else "not installed",
                      "" if roblox else "Install Roblox here (roblox.com) and sign in with the Roblox account "
                                        "that farms. One Roblox account plays in one place at a time."))
    link = os.path.join(desktop(), SHORTCUT_NAME)
    items.append(Item("Session", "Desktop shortcut", os.path.exists(link), "there" if os.path.exists(link) else "none",
                      "" if os.path.exists(link) else "\"Make the desktop shortcut\" puts the farm's shortcut here.",
                      "" if os.path.exists(link) else "shortcut"))
    items.extend(_gpu_items())
    items.extend(_reach_items())
    return items


def all_checks(account: str | None = None) -> list[Item]:
    return session_checks() if in_remote_session() else host_checks(account)


# ----------------------------------------------------------------------------------- fixes
def write_connection_file(account: str, folder: str | None = None) -> str:
    """The connection file, on this account's Desktop unless told otherwise. UTF-16 like mstsc
    writes its own. Also sets "keep drawing when minimized" for this account."""
    path = os.path.join(folder or desktop(), FILE_NAME)
    lines = [f"username:s:{account}"] + [f"{name}:{kind}:{value}" for name, kind, value in RDP_FIELDS]
    with open(path, "w", encoding="utf-16", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    keep_drawing_minimized()
    return path


def keep_drawing_minimized():
    with winreg.CreateKeyEx(HKCU, CLIENT, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "RemoteDesktop_SuppressWhenMinimized", 0, winreg.REG_DWORD, 2)


def connect(path: str | None = None):
    files = [path] if path else connection_files()
    if not files:
        raise FileNotFoundError("no connection file yet")
    subprocess.Popen(["mstsc.exe", files[0]])


def make_shortcut() -> str:
    result = subprocess.run(["cmd", "/c", SHORTCUT_SCRIPT], capture_output=True, text=True, timeout=30,
                            creationflags=0x08000000)   # CREATE_NO_WINDOW
    return (result.stdout or result.stderr).strip()


def admin_changes(account: str | None) -> list[str]:
    """What the admin step would change on this PC now (empty: nothing to do)."""
    changes = []
    if _reg(HKLM, TS_KEY, "fDenyTSConnections", 1) != 0:
        changes.append("turn Remote Desktop on")
    for name, value in GPU_POLICY:
        if _reg(HKLM, POLICY, name) != value:
            changes.append(f"set {name} = {value}")
    if account and account.lower() in {a["name"].lower() for a in local_accounts()}:
        if not any(a["admin"] for a in local_accounts() if a["name"].lower() == account.lower()) \
                and not may_use_remote_desktop(account):
            changes.append(f"add {account} to Remote Desktop Users")
    return changes


def apply_admin(account: str | None) -> list[str]:
    """Run elevated. Writes only what isn't set yet and says what it changed."""
    done = []
    with winreg.CreateKeyEx(HKLM, TS_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
        if _reg(HKLM, TS_KEY, "fDenyTSConnections", 1) != 0:
            winreg.SetValueEx(key, "fDenyTSConnections", 0, winreg.REG_DWORD, 0)
            done.append("Remote Desktop on")
    with winreg.CreateKeyEx(HKLM, POLICY, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
        for name, value in GPU_POLICY:
            if _reg(HKLM, POLICY, name) != value:
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
                done.append(f"{name} = {value}")
    if account and f"add {account} to Remote Desktop Users" in admin_changes(account):
        class Member(ctypes.Structure):
            _fields_ = [("name", wintypes.LPWSTR)]
        group = _sid_name(WELL_KNOWN["remote_desktop_users"]) or "Remote Desktop Users"
        member = Member(account)
        netapi32.NetLocalGroupAddMembers.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                                     ctypes.c_void_p, wintypes.DWORD]
        status = netapi32.NetLocalGroupAddMembers(None, group, 3, ctypes.byref(member), 1)
        done.append(f"{account} added to {group}" if status in (0, 1378) else
                    f"couldn't add {account} to {group} (error {status})")
    return done


def undo_admin() -> list[str]:
    """Takes out the two policy values. Remote Desktop and the group stay: the wrapper's own
    uninstaller and the player own those."""
    done = []
    try:
        with winreg.OpenKey(HKLM, POLICY, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
            for name, _value in GPU_POLICY:
                try:
                    winreg.DeleteValue(key, name)
                    done.append(f"{name} removed")
                except FileNotFoundError:
                    pass
    except FileNotFoundError:
        pass
    return done


class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("mask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                ("verb", wintypes.LPCWSTR), ("file", wintypes.LPCWSTR), ("parameters", wintypes.LPCWSTR),
                ("directory", wintypes.LPCWSTR), ("show", ctypes.c_int), ("instance", wintypes.HINSTANCE),
                ("id_list", ctypes.c_void_p), ("class_name", wintypes.LPCWSTR), ("class_key", wintypes.HKEY),
                ("hotkey", wintypes.DWORD), ("icon", wintypes.HANDLE), ("process", wintypes.HANDLE)]


def run_elevated(args: list[str], timeout: float = 120.0) -> dict:
    """This module in a process Windows elevates (it asks the player first). Returns what that
    process reported: {"done": [...]} or {"error": "..."}."""
    import tempfile
    out = os.path.join(tempfile.gettempdir(), f"{brand.UNIT}-second-session-{os.getpid()}.json")
    if os.path.exists(out):
        os.remove(out)
    python = sys.executable
    console = os.path.join(os.path.dirname(python), "python.exe")
    if os.path.basename(python).lower() == "pythonw.exe" and os.path.exists(console):
        python = console     # the elevated step's errors go to the result file either way
    info = _ShellExecuteInfo()
    info.size = ctypes.sizeof(info)
    info.mask = 0x40 | 0x100   # SEE_MASK_NOCLOSEPROCESS, SEE_MASK_NOASYNC
    info.verb = "runas"
    info.file = python
    info.parameters = subprocess.list2cmdline(["-m", "macro.setup.second_session", *args, "--result", out])
    info.directory = ROOT
    info.show = 0   # SW_HIDE
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_ShellExecuteInfo)]
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        return {"error": "Windows asked and was told no" if error == 1223 else f"couldn't start it (error {error})"}
    kernel32.WaitForSingleObject(info.process, int(timeout * 1000))
    kernel32.CloseHandle(info.process)
    try:
        with open(out, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"error": "the admin step didn't report back"}
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


# ------------------------------------------------------------------------------ command line
def _main(argv: list[str]) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Farming from a second Windows account: checks and fixes.")
    parser.add_argument("--account", help="the farm account (default: the one the connection file names)")
    parser.add_argument("--apply-admin", action="store_true", help="the admin step (run elevated)")
    parser.add_argument("--undo-admin", action="store_true", help="take the policy values out (run elevated)")
    parser.add_argument("--plan", action="store_true", help="say what the admin step would change, change nothing")
    parser.add_argument("--write-file", metavar="FOLDER", help="write the connection file into FOLDER")
    parser.add_argument("--result", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    account = args.account or default_account()
    if args.apply_admin or args.undo_admin:
        try:
            report = {"done": apply_admin(account) if args.apply_admin else undo_admin()}
        except Exception as error:   # reported to the app, which can't see this process
            report = {"error": f"{type(error).__name__}: {error}"}
        if args.result:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(report, f)
        print(report)
        return 0 if "done" in report else 1
    if args.plan:
        print("\n".join(admin_changes(account)) or "nothing to change")
        return 0
    if args.write_file:
        if not account:
            print("no farm account: pass --account")
            return 1
        print(write_connection_file(account, args.write_file))
        return 0
    print(f"{'inside the farm session' if in_remote_session() else 'your own account'}; farm account: {account}")
    for item in all_checks(account):
        mark = {True: "ok ", False: "BAD", None: " ? "}[item.ok]
        print(f"[{mark}] {item.group}: {item.name}: {item.found}" + (f"\n       {item.fix}" if item.fix and not item.ok else ""))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
