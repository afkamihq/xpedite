"""Builds a release's two downloads from a public tree (the afkamihq/xpedite repository, or a tree
tools/build_release.py exported from the workshop):

  dist/xpedite-<version>-windows.zip   xpedite.exe (PyInstaller) with app/, macro/ and data/ beside it
  dist/xpedite-<version>-source.zip    the code, for setup.bat / xpedite.bat

Each has manifest.json (every file's SHA-256) for macro/update.py. The release workflow
(.github/workflows/release.yml) runs this on a version tag; needs PyInstaller for the exe.

    python packaging/build.py                 both zips, version from macro/version.py
    python packaging/build.py --tag v1.1.0    fails unless the tag is that version
    python packaging/build.py --source-only
"""
import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import zipfile

TREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Never in a download: the workflow, build output, caches, the player's own files.
LEAVE_OUT = [".git/*", ".github/*", "dist/*", "build/*", "*/__pycache__/*", "*.pyc", ".update/*",
             "data/settings*.yaml", "data/setup_done", "logs/*", "cap/*", ".venv*"]
# What the exe needs beside it: its code and data (the packages are frozen into it).
BESIDE_EXE = ["app/*", "macro/*", "data/*", "README.md", "LICENSE", "docs/EXPEDITION.md"]


def version_of(tree: str) -> str:
    with open(os.path.join(tree, "macro", "version.py"), encoding="utf-8") as f:
        found = re.search(r'VERSION = "([^"]+)"', f.read())
    if not found:
        sys.exit("macro/version.py has no VERSION")
    return found.group(1)


def files_of(tree: str) -> list[str]:
    """The tree's files: git's list when it's a checkout (no stray local files), else all of them."""
    try:
        listed = subprocess.run(["git", "-C", tree, "ls-files"], check=True, capture_output=True,
                                text=True).stdout.splitlines()
        if listed:
            return [p for p in listed if os.path.isfile(os.path.join(tree, p))]
    except (OSError, subprocess.CalledProcessError):
        pass
    out = []
    for dirpath, dirs, names in os.walk(tree):
        dirs[:] = [d for d in dirs if d not in (".git", "dist", "build", "__pycache__") and not d.startswith(".venv")]
        out += [os.path.relpath(os.path.join(dirpath, n), tree).replace(os.sep, "/") for n in names]
    return out


def shipped(path: str, patterns: list[str] | None = None) -> bool:
    if any(fnmatch.fnmatch(path, p) for p in LEAVE_OUT):
        return False
    return patterns is None or any(fnmatch.fnmatch(path, p) for p in patterns)


def manifest(folder: str, version: str) -> None:
    sys.path.insert(0, TREE)
    from macro.update import write_manifest
    write_manifest(folder, version)


def zip_folder(folder: str, out: str) -> None:
    top = os.path.basename(folder)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for dirpath, _, names in os.walk(folder):
            for name in sorted(names):
                full = os.path.join(dirpath, name)
                z.write(full, os.path.join(top, os.path.relpath(full, folder)).replace(os.sep, "/"))
    print(f"{out}: {os.path.getsize(out) / 2**20:.1f} MB")


def copy_files(tree: str, paths: list[str], folder: str) -> None:
    for path in paths:
        target = os.path.join(folder, *path.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(tree, *path.split("/")), target)


def build_source(tree: str, version: str, dist: str) -> str:
    folder = os.path.join(dist, "source", "xpedite")
    shutil.rmtree(os.path.dirname(folder), ignore_errors=True)
    copy_files(tree, [p for p in files_of(tree) if shipped(p)], folder)
    with open(os.path.join(folder, "VERSION.txt"), "w", encoding="utf-8") as f:
        f.write(f"xpedite {version}\n")
    manifest(folder, version)
    out = os.path.join(dist, f"xpedite-{version}-source.zip")
    zip_folder(folder, out)
    return out


def build_windows(tree: str, version: str, dist: str) -> str:
    work = os.path.join(tree, "build")
    frozen_dist = os.path.join(dist, "windows")
    shutil.rmtree(frozen_dist, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
                    "--distpath", frozen_dist, "--workpath", work,
                    os.path.join(tree, "packaging", "xpedite.spec")], check=True, cwd=tree)
    folder = os.path.join(frozen_dist, "xpedite")
    copy_files(tree, [p for p in files_of(tree) if shipped(p, BESIDE_EXE)], folder)
    with open(os.path.join(folder, "VERSION.txt"), "w", encoding="utf-8") as f:
        f.write(f"xpedite {version}\n")
    manifest(folder, version)
    out = os.path.join(dist, f"xpedite-{version}-windows.zip")
    zip_folder(folder, out)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", default=TREE, help="the public tree to build from")
    parser.add_argument("--tag", default="", help="the release tag; must match macro/version.py")
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--dist", default="")
    args = parser.parse_args()
    tree = os.path.abspath(args.tree)
    version = version_of(tree)
    if args.tag and args.tag.lstrip("vV") != version:
        sys.exit(f"tag {args.tag} isn't macro/version.py's {version}")
    dist = os.path.abspath(args.dist or os.path.join(tree, "dist"))
    os.makedirs(dist, exist_ok=True)
    build_source(tree, version, dist)
    if not args.source_only:
        build_windows(tree, version, dist)


if __name__ == "__main__":
    main()
