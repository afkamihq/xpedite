"""Taking a map's reference picture: into a free Sandbox on that map, set the camera, and save the
view that placements get marked on. It leaves the match open, so changing Rotate or Zoom and taking
it again only takes seconds.

Rotation is set by a person against guide lines. Measuring it automatically was tried and dropped:
on maps without long straight edges it read "straight" when it wasn't.
"""

from __future__ import annotations

import cv2

from macro.control import maps
from macro.modes import story
from macro.nav.navigator import Navigator
from macro.nav.stages import start_sandbox
from macro.platform.windows import WindowsPlatform
from macro.vision.screens import scaled

# What the open Sandbox match currently shows, so a retake can skip going back in.
_open = {"button": None, "yaw": 0, "zoom": 0, "route": None}


def take_picture(map_button: str, profile: maps.MapProfile, log) -> str:
    """Returns a line saying how it went. Raises if it couldn't be done."""
    try:
        import comtypes

        comtypes.CoInitialize()
    except Exception:
        pass
    with WindowsPlatform() as p:
        problem = p.make_game_ready(timeout=60)
        if problem:
            raise RuntimeError(problem)
        p.guard.arm()
        nav = Navigator(p, log=lambda t: log(f"  {t}"))
        screen = nav.settle()
        same_match = (screen == "match" and _open["button"] == map_button and _open["route"] == profile.route)
        if same_match:
            log("  still in that map's Sandbox, so just adjusting the camera")
            p.hover(*scaled(960, 300))
            for _ in range(maps.ZOOM_OUT_NOTCHES):
                p.scroll(maps.NOTCH)
                p.sleep(0.03)
            p.sleep(0.4)
            for _ in range(profile.zoom_in_notches):
                p.scroll(-maps.NOTCH)
                p.sleep(0.2)
            if profile.yaw_counts != _open["yaw"]:
                p.turn(profile.yaw_counts - _open["yaw"], 0)
        else:
            if screen in story.RESULT_SCREENS:
                story.leave_results(nav, screen)
            nav.go("lobby")
            start_sandbox(nav, map_button=map_button)
            p.sleep(2.0)
            maps.set_overhead_camera(p, profile)
            maps.walk_route(p, profile)
        _open.update(button=map_button, yaw=profile.yaw_counts, zoom=profile.zoom_in_notches, route=list(profile.route))
        p.hover(*scaled(960, 133))
        p.sleep(1.0)
        frame = p.grab()
    profile.save()
    cv2.imwrite(profile.reference_path, frame)
    return f"picture saved at rotation {profile.yaw_counts}, zoom {profile.zoom_in_notches}"
