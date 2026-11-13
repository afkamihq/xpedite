"""Which reference pictures the macro loads when it runs, and which are only development captures.

The screen detector loads the frames data/screens.yaml and data/anchors.yaml name ("native/x",
"win/x", "linux/x") plus every refs/frames_native/<screen>__N.png; a few files are loaded by path
(an icon, the glass's fallback picture). Everything else in refs/ was captured while building.

    .venv-win/Scripts/python.exe tools/refs_in_use.py            # report
    .venv-win/Scripts/python.exe tools/refs_in_use.py --list     # also print every file kept
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = {"native": "frames_native", "win": "frames_win", "linux": "frames"}
BY_PATH = [("icons", "*"), ("frames_win", "lobby.png")]  # loaded by path in code


def in_use() -> set[str]:
    keep = set()
    for name in ("screens.yaml", "anchors.yaml", "nav.yaml"):
        path = os.path.join(ROOT, "data", name)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        for folder, stem in re.findall(r"\b(native|win|linux)/([A-Za-z0-9_\-]+)", text):
            keep.add(os.path.join("refs", FOLDERS[folder], stem + ".png"))
    for path in glob.glob(os.path.join(ROOT, "refs", "frames_native", "*__*.png")):
        keep.add(os.path.relpath(path, ROOT))
    for folder, pattern in BY_PATH:
        for path in glob.glob(os.path.join(ROOT, "refs", folder, pattern)):
            keep.add(os.path.relpath(path, ROOT))
    return {k for k in keep if os.path.exists(os.path.join(ROOT, k))}


def main():
    keep = in_use()
    every = [os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "refs", "**", "*"), recursive=True)
             if os.path.isfile(p)]
    size = lambda paths: sum(os.path.getsize(os.path.join(ROOT, p)) for p in paths)  # noqa: E731
    used = [p for p in every if p in keep]
    unused = [p for p in every if p not in keep]
    print(f"refs/: {len(every)} files, {size(every) / 2**20:.0f} MB")
    print(f"  loaded by the macro: {len(used)} files, {size(used) / 2**20:.0f} MB")
    print(f"  development only:    {len(unused)} files, {size(unused) / 2**20:.0f} MB")
    by_folder = {}
    for p in unused:
        folder = p.split(os.sep)[1]
        n, s = by_folder.get(folder, (0, 0))
        by_folder[folder] = (n + 1, s + os.path.getsize(os.path.join(ROOT, p)))
    for folder, (n, s) in sorted(by_folder.items(), key=lambda kv: -kv[1][1]):
        print(f"    {folder:15} {n:4} files {s / 2**20:6.1f} MB")
    if "--list" in sys.argv:
        print("\n".join(sorted(used)))


if __name__ == "__main__":
    main()
