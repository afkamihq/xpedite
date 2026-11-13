"""Record the screen while a run plays, to review it afterwards: a half-size JPG every N seconds
to cap/review/<start time>/HHMMSS.jpg, for at most M minutes. Its own process and its own
capture, so the run is not slowed or touched.
  record_run.py [seconds_between=2] [minutes=45]
"""
import ctypes
import os
import sys
import time

ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
import cv2  # noqa: E402
import dxcam  # noqa: E402

every = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(ROOT, "cap", "review", time.strftime("%H%M"))
os.makedirs(out, exist_ok=True)
print(out, flush=True)
camera = dxcam.create(output_color="BGR")
end = time.time() + minutes * 60
while time.time() < end:
    started = time.time()
    frame = camera.grab()
    if frame is not None:
        small = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2), interpolation=cv2.INTER_AREA)
        cv2.imwrite(os.path.join(out, time.strftime("%H%M%S") + ".jpg"), small, [cv2.IMWRITE_JPEG_QUALITY, 70])
    time.sleep(max(0.0, every - (time.time() - started)))
