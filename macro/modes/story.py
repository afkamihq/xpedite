"""Playing one Story stage from start to results, with our own placement.

Enter the stage, walk to the map's set position, place the layout as the Yen allows, and
watch until the results screen. Numbers read every frame also show whether the match is
really moving, so a stuck one gets noticed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


from macro.control import maps
from macro.control.engine import PlanEngine
from macro.control.plans import Plan
from macro.nav import stages
from macro.nav.navigator import NavError, Navigator
from macro.vision.digits import DigitReader
from macro.vision.screens import UNKNOWN

MATCH_LIMIT = 15 * 60.0  # seconds; far longer than any stage
STUCK_AFTER = 90.0  # the clock hasn't moved for this long
YEN_BLIND_AFTER = 20.0
RESULT_SCREENS = {"victory", "defeat"}


@dataclass
class MatchResult:
    outcome: str  # victory, defeat, or why it ended early
    seconds: float
    moves_made: int = 0
    moves_left: list = field(default_factory=list)
    waves_seen: list = field(default_factory=list)
    readings: int = 0
    unreadable: int = 0


from macro.nav.start_game import banner_outcome, press_start, start_window_showing  # noqa: E402,F401


def play_match(nav: Navigator, reader: DigitReader, profile: maps.MapProfile, plan: Plan, costs: dict[int, int],
               on_lost=None, log=None, on_frame=None, should_stop=None, stop_when_built: bool = False,
               yaw: int | None = None) -> MatchResult:
    """From the moment the match shows until results. Assumes the camera is as a fresh spawn
    leaves it, unless `yaw` says how far to turn a camera kept from the match before."""
    log = log or (lambda text: None)
    p = nav.p
    started = p.now()
    alignment = maps.go_to_position(p, profile, log=lambda t: log(f"  {t}"), yaw=yaw)
    engine = PlanEngine(p, reader, plan, alignment, costs, log=lambda t: log(f"  {t}"))
    result = MatchResult("unfinished", 0.0)
    if start_window_showing(p.grab()):
        # The clock waits for us: make the first move the starting Yen covers, then start.
        # Only one: before the start the Yen doesn't drop, and further placements would only
        # queue as the game's "phantom" units while the engine took them as built.
        hud = reader.read_hud(p.grab())
        engine.tick(hud["yen"], None)
        press_start(nav, log)
    clock_last, clock_moved = None, p.now()
    wave_last = None
    yen_seen = p.now()
    while p.now() - started < MATCH_LIMIT:
        if should_stop and should_stop():
            result.outcome = "stopped"
            break
        frame = p.grab()
        screen = nav.detector.classify(frame).name
        nav._last_frame = frame
        if on_frame:
            on_frame(screen, frame, None)
        if screen in RESULT_SCREENS:
            result.outcome = banner_outcome(frame) or screen
            break
        if screen == "match" and start_window_showing(frame):
            press_start(nav, log)  # a click that missed, or a fresh match started in place
            clock_moved = p.now()
            continue
        if screen == "match":
            hud = reader.read_hud(frame)
            if on_frame:
                on_frame(screen, frame, hud)
            result.readings += 1
            if hud["yen"] is None or hud["seconds"] is None:
                result.unreadable += 1
            if hud["yen"] is not None:
                yen_seen = p.now()
            elif p.now() - yen_seen > YEN_BLIND_AFTER:
                # Nothing can be placed without it, so don't sit through a lost match.
                result.outcome = "stuck: can't read the Yen"
                break
            if hud["wave"] is not None and hud["wave"] != wave_last:
                wave_last = hud["wave"]
                result.waves_seen.append((hud["wave"], hud["wave_total"]))
                log(f"  wave {hud['wave']}/{hud['wave_total']}, Yen {hud['yen']}, enemies {hud['enemies']}, "
                    f"health {hud['health']}, clock {hud['seconds']}")
            if hud["seconds"] is not None and hud["seconds"] != clock_last:
                clock_last, clock_moved = hud["seconds"], p.now()
            elif p.now() - clock_moved > STUCK_AFTER:
                result.outcome = "stuck: the clock stopped"
                break
            engine.tick(hud["yen"], hud["wave"])
            if stop_when_built and engine.finished:
                result.outcome = "built"
                break
        elif screen == UNKNOWN and on_lost:
            # Short flickers are normal, so only a screen that stays unknown counts.
            if nav.settle(2.0) == UNKNOWN:
                on_lost(UNKNOWN)
        elif screen not in ("match", UNKNOWN):
            # A panel or popup over the match that the macro didn't open: close it.
            log(f"  {screen} is covering the match")
            if nav.settle(1.0) == screen and screen != "match":
                nav.go("match", on_lost=on_lost, max_steps=3)
        p.sleep(0.25)
    else:
        result.outcome = "ran out of time"
    result.moves_made = engine.moves_made
    result.moves_left = engine.queue
    result.seconds = p.now() - started
    return result


def enter_story(nav: Navigator, map_name: str, act: int, difficulty: str, on_lost=None):
    stages.choose_story_stage(nav, map_name, act, difficulty, on_lost=on_lost)
    stages.start_from_picker(nav)
    nav.p.sleep(2.0)


def wait_fresh_match(nav: Navigator, reader: DigitReader, timeout: float = 40.0):
    """A match started from inside the last one has no trip to wait out, and the finished
    match's HUD stays up until it begins. Its first wave with a young clock is the sign."""
    start = nav.p.now()
    while nav.p.now() - start < timeout:
        if nav.see() == "match":
            hud = reader.read_hud(nav.last_frame)
            if start_window_showing(nav.last_frame):
                return  # waiting at wave 0 for Start Game: play_match presses it
            if hud["wave"] in (0, 1) and hud["seconds"] is not None and hud["seconds"] <= 20:
                return
        nav.p.sleep(0.2)
    raise NavError(f"the next match never started; on {nav.settle()}")


def repeat_stage(nav: Navigator, reader: DigitReader, screen: str):
    """From Victory or Defeat, the same stage again, in about a second."""
    nav.press(screen, "repeat_stage")
    wait_fresh_match(nav, reader)


def next_stage(nav: Navigator, reader: DigitReader):
    """From Victory, the map's next act, without leaving."""
    nav.press("victory", "next_stage")
    wait_fresh_match(nav, reader)


def enter_story_from_match(nav: Navigator, reader: DigitReader, map_name: str, act: int, difficulty: str,
                           on_lost=None):
    """From a finished match (results showing or closed), any Story stage without the lobby:
    close results, the ship button, then the Story maps, the usual picker, Start.

    The ship button opens the party room when a party is already set up (with Change Map to
    the Story maps), and otherwise the game-modes menu, which is the lobby's Play menu: seen
    10 Nov 2026, when the second trip in a row found no party left and the first had."""
    screen = nav.settle()
    if screen in RESULT_SCREENS:
        nav.press(screen, "close")
        if nav.wait_for("match", 8.0) is None:
            raise NavError(f"closing the results didn't show the match; on {nav.settle()}")
        nav.p.sleep(0.5)
    elif screen != "match":
        raise NavError(f"not in a finished match; on {screen}")
    nav.press("match", "party")
    opened = nav.wait_for({"match_party", "play_menu_top", "play_menu_bottom"}, 8.0)
    if opened is None:
        raise NavError(f"the ship button opened neither the party nor the game modes; on {nav.settle()}")
    nav.p.sleep(0.6)
    if opened == "match_party":
        nav.press("match_party", "change_map")
        if nav.wait_for("story_maps", 8.0) is None:
            raise NavError(f"Change Map didn't show the Story maps; on {nav.settle()}")
    # From the game modes, choose_story_stage finds its own way to the Story maps.
    stages.choose_story_stage(nav, map_name, act, difficulty, on_lost=on_lost)
    nav.press("story_act", "select_stage")
    if nav.wait_for("match_party", 8.0) is None:
        raise NavError(f"Select Stage didn't return to the party; on {nav.settle()}")
    nav.p.sleep(0.8)
    nav.press("match_party", "start")
    wait_fresh_match(nav, reader)


def leave_results(nav: Navigator, screen: str, on_lost=None):
    """From Victory or Defeat, back to the lobby."""
    nav.press(screen, "exit")
    if nav.wait_for("exit_confirm", 12.0) is None:
        raise NavError(f"the results' exit didn't ask to confirm; on {nav.settle()}")
    nav.go("lobby", on_lost=on_lost)
