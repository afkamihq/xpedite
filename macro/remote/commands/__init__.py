"""The bot's features, one module each, every one with setup(bot). Add a module here to add a
feature; nothing else needs to change. The controller each command uses is the app's
(app/remote_control.py): start(), stop(), pause_toggle(), collect(), status(), screenshot(),
logs(n), queue(), set_goal(kind, value)."""
from macro.remote.commands import control, goals, info

MODULES = [control, info, goals]
