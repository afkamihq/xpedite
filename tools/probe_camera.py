"""Measure how the Roblox camera and avatar respond to our inputs.

Run in a still scene (Sandbox with waves off). Prints, for each step, how
far the image moved relative to the frame before the step and to the very
first frame, using ORB features on the view below the HUD.
"""
import json, os, subprocess, sys, time
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from macro.wl import Screen

ORB = cv2.ORB_create(3000)
BF = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


def mask():
    m = np.full((540, 960), 255, np.uint8)
    m[:60] = 0            # top HUD
    m[420:] = 0           # hotbar
    m[:, 800:] = 0        # right buttons
    m[60:200, :90] = 0    # pinned objectives
    m[200:420, 380:580] = 0  # the avatar itself
    return m


M = mask()


def feats(img):
    g = cv2.cvtColor(cv2.resize(img, (960, 540), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return ORB.detectAndCompute(g, M)


def compare(a, b):
    ka, da = a; kb, db = b
    if da is None or db is None:
        return None
    ms = BF.match(da, db)
    if len(ms) < 12:
        return None
    pa = np.float32([ka[m.queryIdx].pt for m in ms]); pb = np.float32([kb[m.trainIdx].pt for m in ms])
    A, inl = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if A is None:
        return None
    s = float(np.hypot(A[0, 0], A[1, 0])); rot = float(np.degrees(np.arctan2(A[1, 0], A[0, 0])))
    # translation of the screen centre, in full-res pixels
    c = np.array([480, 270, 1.0]); d = A @ c - c[:2]
    return dict(n=int(inl.sum()), scale=round(s, 4), roll=round(rot, 2), dx=round(float(d[0]) * 2, 1), dy=round(float(d[1]) * 2, 1))


def showing():
    return json.loads(subprocess.run(["hyprctl", "activeworkspace", "-j"], capture_output=True, text=True).stdout)["id"] == 13


def main(steps):
    s = Screen("wayland-1", "/run/user/1000")
    try:
        s.move(960, 540); time.sleep(0.3)
        first = feats(s.grab()); prev = first
        os.makedirs("cap/probe", exist_ok=True)
        for i, (name, fn) in enumerate(steps):
            if not showing():
                print("workspace 13 not showing; stopped"); return
            fn(s); time.sleep(0.7)
            img = s.grab(); f = feats(img)
            cv2.imwrite(f"cap/probe/{i:02d}_{name}.jpg", cv2.resize(img, (640, 360)), [cv2.IMWRITE_JPEG_QUALITY, 75])
            print(f"{i:02d} {name:18s} vs prev {compare(prev, f)}  vs first {compare(first, f)}", flush=True)
            prev = f
    finally:
        s.close()


def drag(dx, dy, steps=20):
    def f(s):
        s.drag(960, 540, 960 + dx, 540 + dy, steps=steps)
        s.move(960, 540)
    return f


def scroll(n):
    def f(s):
        for _ in range(abs(n)):
            s.scroll(15 if n > 0 else -15); time.sleep(0.05)
    return f


def walk(key, sec):
    return lambda s: s.key(key, hold=sec)


if __name__ == "__main__":
    plan = sys.argv[1] if len(sys.argv) > 1 else "zoom"
    P = {
        "zoom": [("noop", lambda s: None)] + [(f"out{i}", scroll(1)) for i in range(1, 9)] + [("in8", scroll(-8))]
                + [(f"in{i}", scroll(-1)) for i in range(1, 6)] + [("out5", scroll(5))],
        "yaw": [("noop", lambda s: None), ("r+100", drag(100, 0)), ("r-100", drag(-100, 0)), ("r+200", drag(200, 0)),
                ("r-200", drag(-200, 0)), ("r+50x4", lambda s: [drag(50, 0)(s) for _ in range(4)]), ("r-200b", drag(-200, 0)),
                ("r+200fast", drag(200, 0, steps=3)), ("r-200fast", drag(-200, 0, steps=3))],
        "pitch": [("noop", lambda s: None), ("p+60", drag(0, 60)), ("p-60", drag(0, -60)), ("p-60b", drag(0, -60)), ("p+60b", drag(0, 60))],
        "walk": [("noop", lambda s: None), ("w0.5", walk("w", 0.5)), ("s0.5", walk("s", 0.5)), ("w1.0", walk("w", 1.0)), ("s1.0", walk("s", 1.0)),
                 ("a0.5", walk("a", 0.5)), ("d0.5", walk("d", 0.5)), ("w0.2", walk("w", 0.2)), ("s0.2", walk("s", 0.2))],
    }
    main(P[plan])
