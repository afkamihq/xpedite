import sys, time, cv2, json, subprocess, numpy as np, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from macro.wl import Screen
from tools.probe_camera import feats, compare
assert json.loads(subprocess.run(["hyprctl","activeworkspace","-j"],capture_output=True,text=True).stdout)['id']==13
s=Screen("wayland-1","/run/user/1000")
def grab():
    time.sleep(0.8); return s.grab()
try:
    s.move(960,540)
    C=grab(); fC=feats(C)
    for k,t in (("w",0.5),("s",0.5),("w",1.0),("s",1.0),("d",0.5),("a",0.5),("w",0.25),("w",0.25),("w",0.25),("w",0.25),("s",1.0)):
        t0=time.monotonic(); s.key(k, hold=t); dt=time.monotonic()-t0
        D=grab(); print(f'{k} {t:.2f}s (call {dt*1000:.0f} ms) vs C', compare(fC,feats(D)), flush=True)
    cv2.imwrite('cap/probe/w_end.png', D)
finally:
    s.close()
