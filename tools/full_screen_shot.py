"""Save the whole screen, app and all: full_screen_shot.py OUT.png. Its own process, because a
screen-capture object can't be shared with a run going on in another thread."""
import ctypes
import sys
import time

ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
import cv2  # noqa: E402
import dxcam  # noqa: E402

camera = dxcam.create(output_color="BGR")
frame = None
end = time.perf_counter() + 2
while time.perf_counter() < end and frame is None:
    frame = camera.grab()
    time.sleep(0.02)
if frame is not None:
    cv2.imwrite(sys.argv[1], frame)
