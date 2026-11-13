"""Read the hotbar's six units in the lobby (hover each slot, read its card) and print them.
  read_team.py          print only
  read_team.py --write  also rewrite data/presets/current_team.yaml
Roblox must be in the lobby."""
import os
import sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.nav.navigator import Navigator  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.setup import team as team_setup  # noqa: E402

with open_platform() as p:
    import time; p.focus_game(); p.guard.start(); time.sleep(0.3); p.guard.arm()
    nav = Navigator(p, log=print)
    team = team_setup.read_team(nav, log=print)
    cv2.imwrite(os.path.join(ROOT, "cap", "hotbar.png"), p.grab())
    for s in team:
        print(f"slot {s.slot}: {s.name!r} rarity {s.rarity!r} cost {s.cost} role {s.role} limit {s.limit} known {s.known}")
    for line in team_setup.judge(team):
        print(" -", line)
    if "--write" in sys.argv:
        team_setup.write_preset(team)
        print("preset written")
