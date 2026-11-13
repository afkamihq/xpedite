"""Collect finished quests and battlepass rewards, with gems and gold checked either side.
Run from the project root:  .venv-win/Scripts/python.exe tools/collect.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.modes.collect import collect_rewards
from macro.nav.currency import SpendingWatch
from macro.nav.navigator import Navigator
from macro.nav.recovery import Recovery
from macro.platform import open_platform
from macro.vision.screens import scaled


def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


with open_platform() as p:
    problem = p.make_game_ready(timeout=30)
    if problem:
        sys.exit(f"game isn't ready: {problem}")
    p.guard.arm()
    nav = Navigator(p, log=lambda t: log(f"    {t}"))
    recovery = Recovery(p, nav, log=lambda t: log(f"    RECOVERY: {t}"))
    watch = SpendingWatch(log=log)
    nav.go("lobby", on_lost=recovery)
    p.hover(*scaled(960, 300))
    p.sleep(0.8)
    watch.check(p.grab())
    for line in collect_rewards(nav, on_lost=recovery, log=log):
        log(line)
    nav.go("lobby", on_lost=recovery)
    p.hover(*scaled(960, 300))
    p.sleep(0.8)
    balance = watch.check(p.grab())
    log(f"balance after: {balance.gems} gems, {balance.gold} gold")
