"""Export a version of this project into one of the afkamihq repositories' working copies, with
only what may leave this folder: the code, the data the macro runs on and the brand, plus the
public README, LICENSE and .gitignore from release/. Never the private notes (CLAUDE.md,
docs/WINDOWS.md), settings, logs, captures or the screenshots in refs/.

This folder is the workshop; afkamihq/xpedite-early gets each early-access version, and
afkamihq/xpedite (open source) gets a version once its early-access window has passed.

    .venv-win/Scripts/python.exe tools/export_repo.py ..\\afkamihq\\xpedite-early            # HEAD
    .venv-win/Scripts/python.exe tools/export_repo.py ..\\afkamihq\\xpedite --ref v0.5.0
    add --dry-run to list the files instead
"""
import argparse
import fnmatch
import io
import os
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "release"))
import privacy  # noqa: E402  (release/privacy.py: names and levels blurred out of pictures)

# The repositories' top level is the launcher and the essentials; other scripts live in scripts/.
# Left out: the Linux development helpers (act.py, shot.py, find_setting.py, the Wayland bindings in
# protocols/ and wlproto/) and RESTART_FARM.bat, kept here only for an old desktop shortcut.
INCLUDE = ["app/*", "macro/*", "data/*", "tools/*", "scripts/*",
           "docs/ARCHITECTURE.md", "docs/GAME.md", "docs/WIKI.md", "docs/SECOND_SESSION.md", "docs/art/*",
           "xpedite.bat", "setup.bat", "requirements.txt", "docs/EXPEDITION.md",
           "packaging/*", ".github/*", "CHANGELOG.md"]
EXCLUDE = ["data/settings*.yaml", "data/setup_done", "*/__pycache__/*", "*.pyc",
           "tools/hide_claude.py", "tools/restart_app_at_result.sh", "dist/*", "build/*", ".update/*",
           "hub/*", "release/*", "refs/*", "cap/*", "logs/*", "sidekeys/*", ".claude/*",
           "CLAUDE.md", "docs/WINDOWS.md", "PROMPT-original.md", "START-ON-WINDOWS.md"]
RELEASE_FILES = {"release/README.md": "README.md", "release/LICENSE": "LICENSE", "release/.gitignore": ".gitignore"}


def wanted(path: str) -> bool:
    return (any(fnmatch.fnmatch(path, p) for p in INCLUDE)
            and not any(fnmatch.fnmatch(path, p) for p in EXCLUDE))


def files_at(ref: str) -> dict[str, bytes]:
    """Every file of the commit `ref`, as committed (git archive: no working-copy changes)."""
    data = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", ref], check=True,
                          capture_output=True).stdout
    out = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                out[member.name] = tar.extractfile(member).read()
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="the repository's working copy (a git clone)")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--message", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", args.ref], check=True,
                            capture_output=True, text=True).stdout.strip()
    every = files_at(args.ref)
    chosen = {p: privacy.filter_file(p, b) for p, b in every.items() if wanted(p)}
    for src, dst in RELEASE_FILES.items():
        if src in every:
            chosen[dst] = every[src]
    size = sum(len(b) for b in chosen.values())
    print(f"{len(chosen)} of {len(every)} files from {args.ref} ({source}), {size / 2**20:.1f} MB")
    if args.dry_run:
        print("\n".join(sorted(chosen)))
        return
    target = os.path.abspath(args.target)
    if not os.path.isdir(os.path.join(target, ".git")):
        sys.exit(f"{target} isn't a git working copy")
    for name in os.listdir(target):  # the old tree goes; .git stays
        if name != ".git":
            path = os.path.join(target, name)
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    for path, blob in chosen.items():
        out = os.path.join(target, *path.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(blob)
    subprocess.run(["git", "-C", target, "add", "-A"], check=True)
    if subprocess.run(["git", "-C", target, "diff", "--cached", "--quiet"]).returncode == 0:
        print("nothing changed")
        return
    message = args.message or f"xpedite from {source}"
    subprocess.run(["git", "-C", target, "commit", "-q", "-m", message], check=True)
    print("committed:", message)


if __name__ == "__main__":
    main()
