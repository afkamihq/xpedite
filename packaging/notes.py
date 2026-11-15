"""A release's notes: its section of CHANGELOG.md ("## 1.2.0 ..." up to the next "## ").
    python packaging/notes.py v1.2.0
"""
import os
import re
import sys

TREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
version = sys.argv[1].lstrip("vV")
try:
    with open(os.path.join(TREE, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
except OSError:
    text = ""
found = re.search(rf"^## v?{re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
body = found.group(1).strip() if found else ""
sys.stdout.write((body or f"xpedite {version}") + "\n\n"
                 "**Windows:** download `xpedite-" + version + "-windows.zip`, unzip it anywhere and open "
                 "`xpedite.exe` (no Python needed). It updates itself from here.\n"
                 "**From source:** `xpedite-" + version + "-source.zip`, then `setup.bat`.\n")
