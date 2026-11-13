"""Measure how the camera and avatar respond on this platform, and save the numbers.

Start in Sandbox, School Grounds, waves off, at spawn. Replaces probe_camera.py,
probe_cam2.py and probe_walk.py, which only ran on Linux. Sends right-drag camera
turns, wheel and W/A/S/D holds: no clicks. Ends with the camera overhead.

Movement is measured with ORB features between frames, on the view without the
HUD or avatar. Pixels are full-screen pixels.

Run from the project root:  .venv-win/Scripts/python.exe tools/calibrate.py
Writes data/calibration/<platform>.yaml and cap/cal/overhead.png.
"""
import os
import sys
import time

import cv2
import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.nav.navigator import NavError, Navigator
from macro.nav.stages import start_sandbox
from macro.platform import GuardTripped, open_platform
from macro.vision.screens import GAME_WIDTH, scaled

CENTRE = scaled(960, 540)
PER_FEATURE_PIXEL = GAME_WIDTH / 960  # features are found on a 960-wide copy
ORB = cv2.ORB_create(3000)
MATCHER = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

MASK = np.full((540, 960), 255, np.uint8)
MASK[:60] = 0  # top HUD
MASK[420:] = 0  # hotbar
MASK[:, 800:] = 0  # right buttons
MASK[60:200, :90] = 0  # pinned objectives
MASK[200:420, 380:580] = 0  # the avatar


def features(image):
    gray = cv2.cvtColor(cv2.resize(image, (960, 540), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return ORB.detectAndCompute(gray, MASK)


def compare(a, b):
    """How b moved relative to a: dict(inliers, scale, roll degrees, dx, dy), or None."""
    (ka, da), (kb, db) = a, b
    if da is None or db is None:
        return None
    matches = MATCHER.match(da, db)
    if len(matches) < 12:
        return None
    pa = np.float32([ka[m.queryIdx].pt for m in matches])
    pb = np.float32([kb[m.trainIdx].pt for m in matches])
    A, inliers = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if A is None:
        return None
    centre = np.array([480, 270, 1.0])
    d = A @ centre - centre[:2]
    return {"inliers": int(inliers.sum()), "scale": round(float(np.hypot(A[0, 0], A[1, 0])), 4),
            "roll": round(float(np.degrees(np.arctan2(A[1, 0], A[0, 0]))), 2),
            "dx": round(float(d[0]) * PER_FEATURE_PIXEL, 1), "dy": round(float(d[1]) * PER_FEATURE_PIXEL, 1)}


def log(text):
    print(text, flush=True)


class Run:
    def __init__(self, p):
        self.p = p

    def settle(self, seconds=0.7):
        """Wait, and put the pointer back. The nudge releases what a turn leaves
        locked (docs/GAME.md)."""
        p = self.p
        p.sleep(seconds)
        p.move_rel(1, 0)
        p.move_rel(-1, 0)
        p.move(*CENTRE)
        p.sleep(0.2)
        return p.grab()

    def view(self, seconds=0.7):
        return features(self.settle(seconds))


def measure_zoom_pitch(p, out):
    r = Run(p)
    first = r.view()
    noise = compare(first, r.view(0.5))
    log(f"still scene, two frames apart: {noise}")
    out["still_scene_noise"] = noise

    # Zoom out until it stops changing.
    log("--- zoom")
    previous, notches, stuck = first, 0, 0
    for i in range(1, 16):
        p.scroll(15)
        now = r.view(0.4)
        move = compare(previous, now)
        log(f"out {i}: {move}")
        if move and abs(move["scale"] - 1) < 0.003 and abs(move["dx"]) < 3 and abs(move["dy"]) < 3:
            stuck += 1
            if stuck >= 2:
                break
        else:
            stuck, notches = 0, i
        previous = now
    out["zoom_notches_to_full_out"] = notches

    # Tilt down until it clamps.
    log("--- pitch")
    p.turn(0, 3000, steps=30)
    tilted = r.view()
    log(f"+3000 vs before: {compare(previous, tilted)}")
    p.turn(0, 500)
    overhead_frame = r.settle()
    overhead = features(overhead_frame)
    more = compare(tilted, overhead)
    log(f"+500 more: {more}")
    out["pitch_clamped_at_3000"] = bool(more and abs(more["dx"]) < 5 and abs(more["dy"]) < 5 and abs(more["roll"]) < 0.5)
    os.makedirs(os.path.join(ROOT, "cap", "cal"), exist_ok=True)
    cv2.imwrite(os.path.join(ROOT, "cap", "cal", "overhead.png"), overhead_frame)


def go_overhead(p, r):
    """Tilt and zoom both clamp, so this lands on the same view from anywhere."""
    p.turn(0, 3500, steps=30)
    for _ in range(15):
        p.scroll(15)
        p.sleep(0.03)
    return r.view()


def measure_yaw(p, out):
    r = Run(p)
    overhead = go_overhead(p, r)

    # Yaw, measured as image rotation in the overhead view.
    log("--- yaw")
    samples, returns = [], []
    for counts in (100, 200, 400):
        p.turn(counts, 0)
        there = compare(overhead, r.view())
        log(f"turn +{counts}: {there}")
        if there:
            samples.append((counts, abs(there["roll"])))
        p.turn(-counts, 0)
        back = compare(overhead, r.view())
        log(f"turn -{counts} (back): {back}")
        if back:
            returns.append(max(abs(back["dx"]), abs(back["dy"])))
    out["yaw_samples"] = samples
    out["yaw_return_error_px"] = max(returns) if returns else None

    # Does speed change it? "Enhance pointer precision" would show up here.
    log("--- speed")
    speeds = {}
    for name, steps, step_s in (("fast", 2, 0.01), ("normal", 10, 0.01), ("slow", 100, 0.005)):
        p.turn(200, 0, steps=steps, step_s=step_s)
        there = compare(overhead, r.view())
        log(f"200 counts, {name}: {there}")
        speeds[name] = abs(there["roll"]) if there else None
        p.turn(-200, 0, steps=steps, step_s=step_s)
        r.view(0.3)
    out["yaw_200_counts_by_speed"] = speeds
    known = [v for v in speeds.values() if v is not None]
    out["yaw_speed_independent"] = bool(known) and max(known) - min(known) < 1.0

    # A whole circle lands on the same picture, and any rotation left over says
    # how far off the count was. This beats dividing angles, because perspective
    # makes large turns read short. Positive counts read as negative roll.
    if samples:
        per_count = samples[0][1] / samples[0][0]  # the smallest turn skews least
        counts = round(360 / per_count)
        for attempt in range(4):
            p.turn(counts, 0, steps=60)
            left = compare(overhead, r.view())
            log(f"{counts} counts vs start: {left}")
            p.turn(-counts, 0, steps=60)
            r.view(0.3)
            if not left:
                break
            if abs(left["roll"]) < 0.05:
                out["yaw_counts_per_circle"] = counts
                out["yaw_deg_per_count"] = round(360 / counts, 5)
                out["yaw_full_circle_result"] = left
                log(f"yaw: {360 / counts:.5f} deg/count, a full circle is {counts} counts")
                break
            counts += round(left["roll"] / (360 / counts))
        else:
            log("full circle didn't converge")
    r.view()


def measure_walk(p, out):
    r = Run(p)
    go_overhead(p, r)

    # Walking, in the overhead view. Something can block a walk, so judge by the
    # median speed and drop any walk that fell well short of it from the drift.
    log("--- walk")
    runs = []
    for key, back_key in (("w", "s"), ("s", "w"), ("d", "a"), ("a", "d")):
        for hold in (0.25, 0.5):
            start = r.view()
            t = time.perf_counter()
            p.key(key, hold=hold)
            took = time.perf_counter() - t
            there = compare(start, r.view())
            p.key(back_key, hold=hold)
            back = compare(start, r.view())
            log(f"{key} {hold} s (call took {took * 1000:.0f} ms): {there}; back: {back}")
            if there and back:
                runs.append((key, float(np.hypot(there["dx"], there["dy"])) / hold, float(np.hypot(back["dx"], back["dy"]))))
    if runs:
        median = float(np.median([speed for _, speed, _ in runs]))
        clean = [run for run in runs if run[1] > 0.8 * median]
        out["walk_px_per_s"] = round(median, 1)
        out["walk_px_per_s_by_key"] = {key: round(float(np.median([s for k, s, _ in clean if k == key])), 1)
                                       for key in {k for k, _, _ in clean}}
        out["walk_return_drift_px_worst"] = round(max(d for _, _, d in clean), 1)
        out["walk_blocked_runs"] = len(runs) - len(clean)
        log(f"walk: {median:.0f} px/s; worst return {out['walk_return_drift_px_worst']} px; "
            f"{out['walk_blocked_runs']} of {len(runs)} runs blocked")


def p_width():
    return GAME_WIDTH


def p_height():
    return round(GAME_WIDTH * 9 / 16)


def main():
    """calibrate.py [zoom] [yaw] [walk] [--enter]: run those parts (default: all) and
    update the saved file. zoom needs to start at spawn; yaw and walk work from anywhere.
    --enter goes into Sandbox first, so it starts at spawn."""
    parts = {"zoom": measure_zoom_pitch, "yaw": measure_yaw, "walk": measure_walk}
    enter = "--enter" in sys.argv
    chosen = [a for a in sys.argv[1:] if not a.startswith("--")] or list(parts)
    folder = os.path.join(ROOT, "data", "calibration")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{sys.platform}.yaml")
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            out = yaml.safe_load(f) or {}
    out.update({"measured": time.strftime("%Y-%m-%d %H:%M"), "platform": sys.platform,
                "scene": "Sandbox, School Grounds", "graphics_quality": 1, "game_size": [p_width(), p_height()]})
    out.pop("incomplete", None)
    if sys.platform == "win32":
        from macro.platform.windows import mouse_settings
        out["mouse_settings"] = mouse_settings()
    code = 0
    with open_platform() as p:
        try:
            if hasattr(p, "make_game_ready"):
                problem = p.make_game_ready(timeout=30)
                if problem:
                    raise GuardTripped(problem)
            p.guard.arm()
            if enter:
                start_sandbox(Navigator(p))
                p.sleep(2.0)
            for name in chosen:
                parts[name](p, out)
        except (GuardTripped, NavError) as stopped:
            log(f"STOPPED: {stopped}. Numbers so far are saved, marked incomplete.")
            out["incomplete"] = str(stopped)
            code = 1
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, sort_keys=False)
    log(f"saved {path}")
    return code


if __name__ == "__main__":
    sys.exit(main())
