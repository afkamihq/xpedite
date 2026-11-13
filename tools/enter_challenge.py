"""Enter one challenge row and stop as the match starts, to set up or play its map by hand.
  enter_challenge.py regular 1"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from macro.modes import challenge, story  # noqa: E402
from macro.nav.navigator import Navigator  # noqa: E402
from macro.nav.recovery import Recovery  # noqa: E402
from macro.platform import open_platform  # noqa: E402
from macro.platform.windows import wait_hands_off  # noqa: E402

kind, row = sys.argv[1], int(sys.argv[2])
wait_hands_off(seconds=10, timeout=300)
with open_platform() as p:
    print("ready:", p.make_game_ready(timeout=60) or "yes")
    p.guard.arm()
    nav = Navigator(p, log=print)
    recovery = Recovery(p, nav, log=print)
    screen = nav.settle()
    if screen in story.RESULT_SCREENS:
        story.leave_results(nav, screen, on_lost=recovery)
    nav.go("challenges", on_lost=recovery)
    offers = challenge.read_offers(nav, kind)
    for o in offers:
        print(o.describe())
    offer = next(o for o in offers if o.row == row)
    challenge.enter(nav, offer)
    print("in the match:", offer.describe())
