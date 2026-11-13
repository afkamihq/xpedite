"""The session's own end, from Discord: /goal candy 20000, /goal time 07:30, /goal clear."""
from macro.remote.bot import BOOLEAN, INTEGER, STRING


def setup(bot):
    c = bot.controller

    @bot.command("goal", "Stop the session at a time or after some Candy Corn",
                 [{"type": INTEGER, "name": "candy", "description": "Stop after this much Candy Corn this session",
                   "required": False, "min_value": 1},
                  {"type": STRING, "name": "time", "description": "Stop at this time, HH:MM (24 h)", "required": False},
                  {"type": BOOLEAN, "name": "clear", "description": "Remove both goals", "required": False}])
    def goal(ctx):
        o = ctx.options
        if o.get("clear"):
            ctx.reply(c.set_goal("clear", None))
        elif o.get("candy"):
            ctx.reply(c.set_goal("candy", int(o["candy"])))
        elif o.get("time"):
            ctx.reply(c.set_goal("time", str(o["time"]).strip()))
        else:
            ctx.reply(c.set_goal("show", None))
