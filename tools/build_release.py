"""Builds a release's downloads in the workshop, the way the release workflow does on GitHub:
the committed version's public files (tools/export_repo.py's allow-list, pictures blurred by
release/privacy.py, the public README/LICENSE) go to dist/tree-<version>/, and
packaging/build.py builds from there:

  dist/xpedite-<version>-windows.zip   xpedite.exe, no Python needed (PyInstaller, from .venv-build)
  dist/xpedite-<version>-source.zip    the code, for setup.bat

Nothing is uploaded: a version tag pushed to afkamihq/xpedite makes the real release.

    .venv-win/Scripts/python.exe tools/build_release.py              # HEAD
    .venv-win/Scripts/python.exe tools/build_release.py --ref v1.1.0 --source-only
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "release"))
import export_repo  # noqa: E402
import privacy  # noqa: E402

BUILD_PYTHON = os.path.join(ROOT, ".venv-build", "Scripts", "python.exe")  # has PyInstaller


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    every = export_repo.files_at(args.ref)
    chosen = {p: privacy.filter_file(p, b) for p, b in every.items() if export_repo.wanted(p)}
    for src, dst in export_repo.RELEASE_FILES.items():
        if src in every:
            chosen[dst] = every[src]
    tree = os.path.join(ROOT, "dist", "tree")
    shutil.rmtree(tree, ignore_errors=True)
    for path, blob in chosen.items():
        out = os.path.join(tree, *path.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(blob)
    print(f"{len(chosen)} public files from {args.ref} in {tree}")
    python = BUILD_PYTHON if os.path.exists(BUILD_PYTHON) and not args.source_only else sys.executable
    command = [python, os.path.join(tree, "packaging", "build.py"), "--tree", tree,
               "--dist", os.path.join(ROOT, "dist")]
    if args.source_only:
        command.append("--source-only")
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
