"""Set a map's position and take its reference picture, in a free Sandbox match.

  map_setup.py school_grounds --route w:0.6,d:0.3

Goes into Sandbox (School Grounds is the only map it can pick so far), sets the overhead
camera, walks the route from spawn, and saves profile.yaml and reference.png to
data/maps/<map>/. Leaves the match running, to look around in.
Run from the project root:  .venv-win/Scripts/python.exe tools/map_setup.py school_grounds
"""
import os
import sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.control import maps
from macro.modes import story
from macro.nav.navigator import Navigator
from macro.nav.stages import start_sandbox
from macro.platform import open_platform


def main():
    name = sys.argv[1]
    route = []
    if "--route" in sys.argv:
        for part in sys.argv[sys.argv.index("--route") + 1].split(","):
            key, seconds = part.split(":")
            route.append([key, float(seconds)])
    existing = maps.load_profile(name) if os.path.exists(os.path.join(maps.MAPS, name, "profile.yaml")) else None
    profile = maps.MapProfile(name, route or (existing.route if existing else []),
                              yaw_counts=existing.yaw_counts if existing else 0,
                              zoom_in_notches=existing.zoom_in_notches if existing else 0)
    with open_platform() as p:
        problem = p.make_game_ready(timeout=30)
        if problem:
            print("game isn't ready:", problem)
            return 1
        p.guard.arm()
        nav = Navigator(p, log=print)
        screen = nav.settle()
        if screen in ("victory", "defeat") and "--here" not in sys.argv:
            story.leave_results(nav, screen)
        if "--here" not in sys.argv:  # --here: already in a match on this map
            nav.go("lobby")
            start_sandbox(nav, map_button=name)
            p.sleep(2.0)
        maps.set_overhead_camera(p, profile)
        maps.walk_route(p, profile)
        p.sleep(1.0)
        # Not over the top bar in event modes: the Heat bar's tooltip would be in the picture.
        p.hover(*((60, 330) if "--here" in sys.argv else (720, 100)))
        p.sleep(0.5)
        frame = p.grab()
    profile.save()
    cv2.imwrite(profile.reference_path, frame)
    cv2.imwrite(os.path.join(ROOT, "cap", "cal", f"reference_{name}.jpg"), frame)
    print(f"saved {profile.reference_path}: {frame.shape[1]}x{frame.shape[0]}, route {route}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
