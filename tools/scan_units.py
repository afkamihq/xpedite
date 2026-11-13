"""Read the whole unit collection off the Units window (H) and write data/collection.yaml.
  .venv-win/Scripts/python.exe tools/scan_units.py          (Roblox in the lobby, Units closed)
Each tile is selected (a click inside the grid only: never Quick Sell, Unequip, the bin or the
lock) and its detail panel is read: rarity, element, archetype, placement limit, trait, shiny.
Tiles are found by their "Lvl" label, and the scroll is measured from the picture, since rows are
evenly spaced and a scroll of exactly one row looks like none. Pictures go to cap/units/scan/.
About 3 minutes for 130 units (10 Nov 2026)."""
import os
import re
import sys
import time

import cv2
import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from macro.platform import open_platform  # noqa: E402
from macro.vision.ocr import read_text  # noqa: E402

OUT = "cap/units/scan"
os.makedirs(OUT, exist_ok=True)
TPL = cv2.imread("refs/units_lvl.png", cv2.IMREAD_GRAYSCALE)
COLX = [279, 386, 492, 598, 705]
TOP, BOTTOM = 166, 606  # the top row's label sits at y 175
PANEL = (830, 175, 1130, 600)
AWAY = (1300, 720)
TRAITS = ["Unbound", "Primordial", "Forsaken", "Draconic", "Investor", "Optics", "Bolt", "Precision 2",
          "Precision 1", "Limit Breaker", "Range 2", "Speed 2", "Strength 2", "Enlightenment", "Range 1",
          "Speed 1", "Strength 1"]
ELEMENTS = ["Neutral", "Plasma", "Hydro", "Dark", "Light", "Gale", "Flame", "Storm", "Terra", "Farm"]
RARITIES = ["Secret", "Exclusive", "Mythic", "Legendary", "Epic", "Rare"]


NAMES_FILE = os.path.join(ROOT, "data", "unit_names.txt")
NAMES = [line.strip() for line in open(NAMES_FILE, encoding="utf-8") if line.strip() and not line.startswith("#")]     if os.path.exists(NAMES_FILE) else []


def known_name(raw: str) -> str:
    """The wiki name closest to what OCR read ("CursedStudent (True Love)", "Crow (Black,Fire)"),
    or the reading itself if nothing is close."""
    import difflib
    squash = lambda t: re.sub(r"[^a-z0-9()]", "", t.lower())
    table = {squash(n): n for n in NAMES}
    if squash(raw) in table:
        return table[squash(raw)]
    best = difflib.get_close_matches(squash(raw), list(table), n=1, cutoff=0.8)
    return table[best[0]] if best else raw


def parse(header: str, level: str) -> dict:
    text = header.replace("|", " ")
    squashed = re.sub(r"\s+", "", text).lower()
    unit = {}
    rarity = next((r for r in RARITIES if r.lower()[:4] in squashed), None)
    m = re.search(r"(?:secret|exclusive|mythi.|legendary|epic|rare)\s*unit\s*(.+)", text, re.I)
    rest = m.group(1) if m else text
    trait = next((t for t in TRAITS if re.sub(r"\s", "", t).lower() in re.sub(r"\s", "", rest).lower()), None)
    name = rest
    if trait:
        name = re.split(re.escape(trait.split()[0]), rest, flags=re.I)[0]
    name = re.sub(r"[★☆*]+", "", name).strip(" -|")
    name = re.sub(r"\s+", " ", name).replace("lce ", "Ice ")
    name = re.sub(r"(\w)\(", r"\1 (", name)
    unit["name"] = known_name(name)
    unit["rarity"] = rarity
    unit["element"] = next((e for e in ELEMENTS if e.lower() in squashed), None)
    unit["archetype"] = next((a for a in ("Physical", "Magical", "Psychic") if a.lower() in squashed), None)
    lim = re.search(r"(?:physical|magical|psychic)\s+(\d)\b", text, re.I)
    unit["limit"] = int(lim.group(1)) if lim else 1
    unit["trait"] = trait
    unit["shiny"] = "shiny" in squashed
    lv = re.findall(r"\d+", level)
    unit["level"] = int(lv[-1]) if lv and int(lv[-1]) <= 60 else None
    return unit


def rows(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    r = cv2.matchTemplate(g[160:615, 270:820], TPL, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(r > 0.72)
    found = {}
    for x, y in zip(xs + 270, ys + 160):
        col = min(range(5), key=lambda c: abs(COLX[c] - x))
        if abs(COLX[col] - x) > 6:
            continue
        key = next((k for k in found if abs(k - y) < 6), y)
        found.setdefault(key, set()).add(col)
    # The grid fills left to right, so a row's tiles run from column 0 to its last one found, and
    # every row above the lowest is full: a selected tile's highlight hides its label (10 Nov).
    last = max(found) if found else None
    return {int(y): set(range(5)) if y != last else set(range(max(cols) + 1)) for y, cols in found.items()}


def band_shift(a, b):
    """How far the grid scrolled from frame a to frame b, by finding bands of a in b."""
    ga = cv2.cvtColor(a[172:606, 275:815], cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b[172:606, 275:815], cv2.COLOR_BGR2GRAY)
    best = (0, -1)
    for top in (40, 150, 260):
        r = cv2.matchTemplate(gb, ga[top:top + 90], cv2.TM_CCOEFF_NORMED)
        _, sc, _, loc = cv2.minMaxLoc(r)
        if sc > best[1]:
            best = (top - loc[1], sc)
    return best


with open_platform() as s:
    s.focus_game(); s.guard.start(); time.sleep(0.3); s.guard.arm()
    s.hover(*AWAY); s.sleep(0.3)
    if not rows(s.grab()):  # the Units window isn't open yet
        s.key("h"); s.sleep(1.5)

    s.hover(540, 400); s.scroll(-900); s.sleep(1.2); s.hover(*AWAY); s.sleep(0.5)
    offset, done, n, lines, still, units = 0, set(), 0, [], 0, []
    frame = s.grab(); view = rows(frame)
    y0 = min(view)
    while True:
        for y in sorted(view):
            absrow = round((y + offset - y0) / 106.5)
            if absrow in done or y - 4 < TOP or y + 100 > BOTTOM: continue
            for c in sorted(view[y]):
                x = COLX[c]
                s.click(x + 52, y + 50); s.sleep(0.15); s.hover(*AWAY); s.sleep(0.45)
                f = s.grab()
                cv2.imwrite(f"{OUT}/{n:03d}_panel.png", f[PANEL[1]:PANEL[3], PANEL[0]:PANEL[2]])
                cv2.imwrite(f"{OUT}/{n:03d}_tile.png", f[y - 2:y + 102, x:x + 106])
                head = read_text(f, (PANEL[0], 178, PANEL[2], 305), 2.0).replace("\n", " | ")
                lv = read_text(f, (x, y - 1, x + 48, y + 16), 3.0)
                lines.append(f"{n:03d} row{absrow} col{c} [{lv}] {head}"); print(lines[-1], flush=True)
                units.append(parse(head, lv))
                n += 1
            done.add(absrow)
        s.hover(540, 400); s.scroll(15); s.sleep(1.0); s.hover(*AWAY); s.sleep(0.5)
        nf = s.grab(); new = rows(nf)
        d, sc = band_shift(frame, nf); frame = nf
        if d < 3:
            still += 1
            if still >= 2: break
        else:
            still = 0
        offset += d; view = new
        print(f"   scrolled {d}px (match {sc:.2f}), offset {offset}", flush=True)
    s.key("h"); s.sleep(0.5)  # close the window again
    open(f"{OUT}/units.txt", "w", encoding="utf-8").write("\n".join(lines))
    with open(os.path.join(ROOT, "data", "collection.yaml"), "w", encoding="utf-8") as f:
        f.write(f"# Read off the Units window by tools/scan_units.py, {time.strftime('%d %b %Y %H:%M')}. Every copy.\n")
        yaml.safe_dump({"units": units}, f, sort_keys=False, allow_unicode=True, width=120)
    print("units read:", n)
