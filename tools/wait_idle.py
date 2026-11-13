"""Wait until the mouse and keyboard have been idle. wait_idle.py [seconds] [timeout]; exit 1 on timeout."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from macro.platform.windows import wait_hands_off
seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 500
sys.exit(0 if wait_hands_off(seconds=seconds, timeout=timeout) else 1)
