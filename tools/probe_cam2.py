import sys, time, cv2, json, subprocess, numpy as np, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from macro.wl import Screen
from tools.probe_camera import feats, compare
assert json.loads(subprocess.run(["hyprctl","activeworkspace","-j"],capture_output=True,text=True).stdout)['id']==13
s=Screen("wayland-1","/run/user/1000")
def grab():
    time.sleep(0.6); s.move(960,540); time.sleep(0.2); return s.grab()
try:
    s.move(960,540)
    s.turn(-200,0); A=grab(); fA=feats(A); cv2.imwrite('cap/probe/r_A.png',A)
    s.turn(0,3000,steps=30); B=grab(); fB=feats(B); print('pitch +3000 vs A', compare(fA,fB))
    s.turn(0,500); C=grab(); fC=feats(C); print('pitch +500 more vs B', compare(fB,fC))
    cv2.imwrite('cap/probe/r_C.png',C)
    for d in (100,-100,200,-200,400,-400):
        s.turn(d,0); D=grab(); print(f'turn {d:+d} vs C', compare(fC,feats(D)))
    s.turn(100,0); s.turn(100,0); D=grab(); print('turn +100+100 vs C', compare(fC,feats(D)))
    s.turn(-200,0,steps=2); D=grab(); print('turn -200 in 2 steps vs C', compare(fC,feats(D)))
    s.turn(-1000,0,steps=50,step_s=0.005); s.turn(1000,0,steps=5); D=grab(); print('turn -1000 slow, +1000 fast vs C', compare(fC,feats(D)))
    cv2.imwrite('cap/probe/r_D.png',D)
finally:
    s.close()
