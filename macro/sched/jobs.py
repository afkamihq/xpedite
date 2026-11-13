"""One-off jobs the app can run outside a queue."""
from __future__ import annotations

import os
import time

import cv2

from macro.modes import story
from macro.modes.collect import collect_rewards
from macro.nav.currency import SpendingDetected, SpendingWatch
from macro.nav.navigator import NavError, Navigator
from macro.nav.recovery import Recovery, RunStopped
from macro.platform import GuardTripped
from macro.platform.windows import FRAME, WindowsPlatform
from macro.vision.screens import ROOT, scaled


def collect_now(log) -> list[str]:
    """Collect quests and battlepasses, with gems and gold checked either side."""
    try:
        import comtypes

        comtypes.CoInitialize()
    except Exception:
        pass
    try:
        with WindowsPlatform() as p:
            problem = p.make_game_ready(timeout=60)
            if problem:
                return [f"couldn't collect: {problem}"]
            p.guard.arm()
            nav = Navigator(p, log=lambda t: log(f"  {t}"))
            recovery = Recovery(p, nav, log=lambda t: log(f"  RECOVERY: {t}"))
            watch = SpendingWatch(log=log)
            screen = nav.settle()
            if screen in story.RESULT_SCREENS:
                story.leave_results(nav, screen, on_lost=recovery)
            nav.go("lobby", on_lost=recovery)
            p.hover(*scaled(960, 300))
            p.sleep(0.8)
            watch.check(p.grab())
            lines = collect_rewards(nav, on_lost=recovery, log=log) or ["nothing was waiting to collect"]
            nav.go("lobby", on_lost=recovery)
            p.hover(*scaled(960, 300))
            p.sleep(0.8)
            watch.check(p.grab())
            return lines
    except (GuardTripped, NavError, RunStopped, SpendingDetected) as stopped:
        return [f"collecting stopped: {stopped}"]


def screenshot() -> str | None:
    """The game's picture, saved to captures/. Needs no input, so it's safe at any time."""
    try:
        import comtypes

        comtypes.CoInitialize()
    except Exception:
        pass
    platform = WindowsPlatform()
    if not platform.game_running() or not FRAME:
        return None
    frame = platform.grab()
    folder = os.path.join(ROOT, "captures")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"game-{time.strftime('%Y%m%d-%H%M%S')}.png")
    cv2.imwrite(path, frame)
    return path


def setup_in_game(log, fix_settings: bool = True) -> dict:
    """The setup's in-game half: the game's settings checked (and set), then the team read off
    the hotbar. Returns {"settings": [...], "team": [...], "advice": [...]} or {"error": ...}."""
    from macro.setup import game_settings, team as team_setup
    try:
        import comtypes

        comtypes.CoInitialize()
    except Exception:
        pass
    try:
        with WindowsPlatform() as p:
            problem = p.make_game_ready(timeout=60)
            if problem:
                return {"error": f"Roblox isn't ready: {problem}"}
            p.guard.arm()
            nav = Navigator(p, log=lambda t: log(f"  {t}"))
            recovery = Recovery(p, nav, log=lambda t: log(f"  RECOVERY: {t}"))
            screen = nav.settle()
            if screen in story.RESULT_SCREENS:
                story.leave_results(nav, screen, on_lost=recovery)
            nav.go("lobby", on_lost=recovery)
            settings = game_settings.check_and_fix(nav, fix=fix_settings, log=log, on_lost=recovery)
            nav.go("lobby", on_lost=recovery)
            team = team_setup.read_team(nav, log=log)
            team_setup.write_preset(team)
            return {"settings": settings, "team": team, "advice": team_setup.judge(team)}
    except (GuardTripped, NavError, RunStopped) as stopped:
        return {"error": f"setup stopped: {stopped}"}
