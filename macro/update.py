"""Updates from the public repository's GitHub releases.

A release carries two zips, built by .github/workflows/release.yml when a version tag is pushed:
  xpedite-<version>-windows.zip   xpedite.exe and everything it needs (no Python install)
  xpedite-<version>-source.zip    the code for setup.bat / xpedite.bat installs
and each holds manifest.json: every file's SHA-256, so an update can tell which of the player's
data files they changed (kept) from the ones they never touched (replaced by the new version's).

Never in a development copy (a git checkout): that one updates through git.

    python -m macro.update            say whether there's a newer version
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "afkamihq/xpedite"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"
MANIFEST = "manifest.json"
STAGING = os.path.join(ROOT, ".update")
# The player's own files. Settings that aren't shipped are never touched; shipped data the player
# may edit (placements, the team, the Expedition settings) is kept when it differs from what the
# installed version shipped.
EDITABLE = ["data/*.yaml", "data/setup_done", "data/presets/*", "data/calibration/*", "data/maps/*",
            "data/expedition/anvil_cards.yaml"]


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def development_copy() -> bool:
    return os.path.isdir(os.path.join(ROOT, ".git"))


def version_tuple(text: str) -> tuple[int, ...]:
    parts = []
    for piece in text.strip().lstrip("vV").split("-")[0].split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts + [0] * (3 - len(parts)))


def _get(url: str, timeout: float = 15.0):
    from macro import brand
    headers = {"User-Agent": f"{brand.UNIT}-updater"}
    if url.startswith("https://api.github.com/"):
        headers["Accept"] = "application/vnd.github+json"
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=timeout)


def _from_release_page() -> dict | None:
    """The newest release without the API (it allows 60 asks an hour per address, and a shared
    address runs out): /releases/latest redirects to /releases/tag/v<version>, and the zips have
    fixed names."""
    try:
        with _get(PAGE) as response:
            final = response.geturl()
    except urllib.error.HTTPError as error:
        return {"none": True} if error.code == 404 else None
    except OSError:
        return None
    found = re.search(r"/releases/tag/v?([0-9][0-9A-Za-z.\-]*)$", final)
    if not found:
        return {"none": True}  # no tag to land on: nothing published yet
    version = found.group(1)
    kind = "windows" if frozen() else "source"
    return {"version": version, "notes": "", "url": final, "size": 0,
            "asset": f"https://github.com/{REPO}/releases/download/v{version}/xpedite-{version}-{kind}.zip"}


def latest() -> dict | None:
    """The newest release: {"version", "notes", "url", "asset", "size"} for this kind of install,
    {"none": True} when nothing is published, or None when it can't be read (offline)."""
    try:
        with _get(API) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {"none": True}
        return _from_release_page()  # 403/429: the API's hourly limit
    except (OSError, ValueError):
        return _from_release_page()
    if not isinstance(data, dict):
        return None
    kind = "windows" if frozen() else "source"
    asset = next((a for a in data.get("assets", []) if a.get("name", "").endswith(f"-{kind}.zip")), None)
    if asset is None:
        return None
    return {"version": data.get("tag_name", "").lstrip("vV"), "notes": data.get("body") or "",
            "url": data.get("html_url") or PAGE, "asset": asset["browser_download_url"],
            "size": int(asset.get("size") or 0)}


def newer(release: dict | None, current: str) -> bool:
    return bool(release) and "version" in release and version_tuple(release["version"]) > version_tuple(current)


def check(current: str) -> tuple[str, dict | None]:
    """("development" | "offline" | "current" | "available", release)."""
    if development_copy():
        return "development", None
    release = latest()
    if release is None:
        return "offline", None
    if release.get("none"):
        return "current", None
    return ("available" if newer(release, current) else "current"), release


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _load_manifest(folder: str) -> dict | None:
    try:
        with open(os.path.join(folder, MANIFEST), encoding="utf-8") as f:
            return json.load(f).get("files")
    except (OSError, ValueError, AttributeError):
        return None


def download(release: dict, progress=None) -> str:
    """The release's zip, unpacked into .update/ (one top folder in the zip is stepped into).
    Returns the folder with the new version's files."""
    shutil.rmtree(STAGING, ignore_errors=True)
    os.makedirs(STAGING, exist_ok=True)
    archive = os.path.join(STAGING, "release.zip")
    with _get(release["asset"], timeout=60) as response, open(archive, "wb") as out:
        total = int(response.headers.get("Content-Length") or release.get("size") or 0)
        done = 0
        while True:
            block = response.read(1 << 16)
            if not block:
                break
            out.write(block)
            done += len(block)
            if progress and total:
                progress(done / total)
    unpacked = os.path.join(STAGING, "files")
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():  # nothing may land outside the staging folder
            target = os.path.abspath(os.path.join(unpacked, name))
            if not target.startswith(os.path.abspath(unpacked) + os.sep) and target != os.path.abspath(unpacked):
                raise ValueError(f"unsafe path in the update: {name}")
        z.extractall(unpacked)
    os.remove(archive)
    entries = os.listdir(unpacked)
    if len(entries) == 1 and os.path.isdir(os.path.join(unpacked, entries[0])):
        unpacked = os.path.join(unpacked, entries[0])
    if not os.path.exists(os.path.join(unpacked, MANIFEST)):
        raise ValueError("the update has no manifest.json")
    return unpacked


def keep_players_files(new_folder: str) -> list[str]:
    """Takes out of the new version the files the player changed, so the copy keeps theirs.
    Returns their paths."""
    old = _load_manifest(ROOT)
    kept = []
    for dirpath, _, names in os.walk(new_folder):
        for name in names:
            path = os.path.relpath(os.path.join(dirpath, name), new_folder).replace(os.sep, "/")
            local = os.path.join(ROOT, *path.split("/"))
            if not os.path.exists(local) or not any(fnmatch.fnmatch(path, p) for p in EDITABLE):
                continue
            shipped = (old or {}).get(path)
            if old is not None and shipped == _sha(local):
                continue  # untouched: the new version's copy goes in
            os.remove(os.path.join(dirpath, name))
            kept.append(path)
    return kept


def install_and_restart(new_folder: str, pid: int | None = None) -> None:
    """Copies the new version over this one once this process has quit, then opens it again.
    The caller quits right after this returns (xpedite.exe and its DLLs are in use until then)."""
    pid = pid or os.getpid()

    def quoted(path: str) -> str:  # a PowerShell literal string
        return "'" + path.replace("'", "''") + "'"

    if frozen():
        reopen = f"Start-Process -FilePath {quoted(sys.executable)} -WorkingDirectory {quoted(ROOT)}"
    else:
        # setup.bat brings the packages up to date, then opens xpedite.
        reopen = f"Start-Process -FilePath {quoted(os.path.join(ROOT, 'setup.bat'))} -WorkingDirectory {quoted(ROOT)}"
    script = os.path.join(tempfile.gettempdir(), "xpedite-update.ps1")
    log = os.path.join(ROOT, "logs", "update.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(f"""$ErrorActionPreference = 'Continue'
Start-Transcript -Path {quoted(log)} -Append | Out-Null
try {{ Wait-Process -Id {int(pid)} -Timeout 120 -ErrorAction SilentlyContinue }} catch {{}}
Start-Sleep -Seconds 1
for ($try = 0; $try -lt 10; $try++) {{
  robocopy {quoted(new_folder)} {quoted(ROOT)} /E /R:2 /W:1 /NFL /NDL /NJH /NJS | Out-Null
  if ($LASTEXITCODE -lt 8) {{ break }}
  Start-Sleep -Seconds 2
}}
Remove-Item -Recurse -Force {quoted(STAGING)} -ErrorAction SilentlyContinue
{reopen}
Stop-Transcript | Out-Null
""")
    # No console window; not DETACHED_PROCESS (PowerShell then quits without running the script).
    # It must outlive this process, so it leaves this process's job when Windows allows it.
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script]
    no_window, new_group, breakaway = 0x08000000, 0x00000200, 0x01000000
    try:
        subprocess.Popen(command, creationflags=no_window | new_group | breakaway, close_fds=True)
    except OSError:  # the job doesn't allow breaking away
        subprocess.Popen(command, creationflags=no_window | new_group, close_fds=True)


def write_manifest(folder: str, version: str) -> None:
    """manifest.json for a built release folder (tools/build_release.py and the CI use it)."""
    files = {}
    for dirpath, _, names in os.walk(folder):
        for name in names:
            path = os.path.relpath(os.path.join(dirpath, name), folder).replace(os.sep, "/")
            if path != MANIFEST:
                files[path] = _sha(os.path.join(dirpath, name))
    with open(os.path.join(folder, MANIFEST), "w", encoding="utf-8") as f:
        json.dump({"version": version, "files": files}, f, indent=0, sort_keys=True)


def selftest() -> int:
    """Everything the app loads, loaded: for a fresh build (the release workflow runs it on the exe).
    Writes selftest.txt beside the app, since the exe has no console."""
    import importlib
    import traceback
    lines, failed = [], 0
    sys.path.insert(0, os.path.join(ROOT, "app"))
    for name in ("cv2", "numpy", "yaml", "PIL.Image", "PyQt6.QtWidgets", "rapidocr_onnxruntime", "psutil",
                 "comtypes", "dxcam", "macro.platform.windows", "macro.sched.runner", "macro.modes.expedition",
                 "panels", "strategy", "setup_window"):
        try:
            importlib.import_module(name)
            lines.append(f"ok   {name}")
        except Exception:
            if name == "dxcam" and os.environ.get("CI"):  # build machines have no real display
                lines.append(f"skip {name} (no display here)\n{traceback.format_exc()}")
                continue
            failed += 1
            lines.append(f"FAIL {name}\n{traceback.format_exc()}")
    try:
        import numpy as np
        from macro.vision import ocr
        frame = np.full((60, 260, 3), 255, np.uint8)
        import cv2
        cv2.putText(frame, "Bonus Match", (8, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 2)
        text = ocr.read_line(frame, (0, 0, 260, 60))
        ok = "bonus" in text.lower()
        failed += not ok
        lines.append(f"{'ok  ' if ok else 'FAIL'} OCR read {text!r}")
    except Exception:
        failed += 1
        lines.append(f"FAIL OCR\n{traceback.format_exc()}")
    report = "\n".join(lines) + ("\nall fine\n" if not failed else f"\n{failed} failed\n")
    with open(os.path.join(ROOT, "selftest.txt"), "w", encoding="utf-8") as f:
        f.write(report)
    if sys.stdout is not None:
        sys.stdout.write(report)
    return 1 if failed else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) >= 4 and sys.argv[1] == "manifest":
        write_manifest(sys.argv[2], sys.argv[3])
        print(f"manifest.json written for {sys.argv[3]}")
    else:
        from macro.version import VERSION
        state, release = check(VERSION)
        print(state, release and release["version"])
