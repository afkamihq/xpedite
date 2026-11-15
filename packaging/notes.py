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


def unwrapped(markdown: str) -> str:
    """CHANGELOG.md is wrapped at 100 columns, and GitHub shows every newline in a release's notes
    as a line break: each wrapped line is joined back onto the one it continues."""
    out, fenced = [], False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            out.append(line)
            continue
        starts_block = re.match(r"\s*([-*+]\s|\d+[.)]\s|#|>|\||$)", line)
        if fenced or starts_block or not out or not out[-1].strip() or out[-1].lstrip().startswith(("#", "|", "```")):
            out.append(line)
        else:
            out[-1] = out[-1].rstrip() + " " + line.strip()
    return "\n".join(out)


body = unwrapped(body)
sys.stdout.reconfigure(encoding="utf-8")  # the Windows runner's console is cp1252: no "→"
sys.stdout.write((body or f"xpedite {version}") + "\n\n"
                 "**Windows:** download `xpedite-" + version + "-windows.zip`, unzip it anywhere and open "
                 "`xpedite.exe` (no Python needed). It updates itself from here.\n"
                 "**From source:** `xpedite-" + version + "-source.zip`, then `setup.bat`.\n")
