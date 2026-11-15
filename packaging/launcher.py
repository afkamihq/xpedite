"""xpedite.exe's entry. The frozen Python runs xpedite's own code from the plain files beside the
exe (app/, macro/, data/), so paths, data and updates work just as in the source version.

    xpedite.exe                    the app
    xpedite.exe -m module args     like python -m (the elevated second-session step uses it)
    xpedite.exe script.py args     like python script.py
"""
import os
import runpy
import sys

if getattr(sys, "frozen", False):
    HERE = os.path.dirname(os.path.abspath(sys.executable))
else:  # packaging/launcher.py run by Python, for trying it
    HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HERE)
sys.path.insert(0, HERE)
args = sys.argv[1:]
if len(args) >= 2 and args[0] == "-m":
    sys.argv = [args[1]] + args[2:]
    runpy.run_module(args[1], run_name="__main__", alter_sys=True)
elif args and args[0].lower().endswith(".py"):
    sys.argv = args
    sys.path.insert(0, os.path.dirname(os.path.abspath(args[0])))
    runpy.run_path(args[0], run_name="__main__")
else:
    main = os.path.join(HERE, "app", "main.py")
    sys.argv = [main] + args
    sys.path.insert(0, os.path.join(HERE, "app"))
    runpy.run_path(main, run_name="__main__")
