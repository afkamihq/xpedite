"""Looking at the macro: /status, /screenshot, /logs, /queue, /summary."""
from macro.remote.bot import INTEGER

GREEN, AMBER, GREY = 0x3BA55D, 0xF0B232, 0x80848E


def status_embed(controller) -> dict:
    s = controller.status()
    state = s.get("state", "?")
    colour = GREEN if state.lower().startswith("run") else AMBER if state.lower().startswith("pause") else GREY
    lines = [f"**{s.get('task') or 'Nothing running'}**" + (f" · run {s['run']}" if s.get("run") else "")]
    fields = [
        {"name": "Match", "value": f"Wave **{s.get('wave', '-')}** · Yen {s.get('yen', '-')}\n"
                                   f"Health {s.get('health', '-')} · Enemies {s.get('enemies', '-')}", "inline": True},
        {"name": "Session", "value": f"Candy Corn **{s.get('candy', 0):,}**\n"
                                     f"Runs {s.get('runs', 0)} · best wave {s.get('best_wave', '-')}", "inline": True},
    ]
    if s.get("running_for"):
        fields.append({"name": "Running for", "value": s["running_for"], "inline": True})
    if s.get("last_result"):
        fields.append({"name": "Last run", "value": s["last_result"], "inline": False})
    from macro import brand
    return {"title": f"{brand.UNIT} · {state}", "description": "\n".join(lines), "color": colour,
            "fields": fields}


def setup(bot):
    c = bot.controller

    @bot.command("summary", "Runs, Candy Corn and trouble over the last few hours",
                 [{"type": INTEGER, "name": "hours", "description": "How far back (default 3)", "required": False,
                   "min_value": 1, "max_value": 72}])
    def summary(ctx):
        from datetime import datetime, timedelta
        from macro.remote import reports
        hours = int(ctx.options.get("hours") or 3)
        ctx.defer()
        s = reports.summarize(datetime.now() - timedelta(hours=hours))
        ctx.reply(embed=reports.summary_embed(s, f"last {hours} h"))

    @bot.command("status", "What the macro is doing now")
    def status(ctx):
        ctx.reply(embed=status_embed(c))

    @bot.command("screenshot", "A picture of the game right now")
    def screenshot(ctx):
        ctx.defer()
        frame = c.screenshot()
        if frame is None:
            ctx.reply("Couldn't copy the screen (is the Remote Desktop window connected?).")
            return
        import cv2
        ok, png = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        ctx.reply(embed={"title": "The screen now", "image": {"url": "attachment://screen.jpg"}, "color": GREY},
                  files=[("screen.jpg", png.tobytes())])

    @bot.command("logs", "The last lines of the macro's log",
                 [{"type": INTEGER, "name": "lines", "description": "How many (default 15)",
                   "required": False, "min_value": 1, "max_value": 60}])
    def logs(ctx):
        lines = c.logs(int(ctx.options.get("lines") or 15))
        text = "\n".join(lines)[-1900:] or "(empty)"
        ctx.reply(f"```\n{text}\n```")

    @bot.command("queue", "What the macro plays, in order")
    def queue(ctx):
        items = c.queue()
        ctx.reply("\n".join(f"{n}. {item}" for n, item in enumerate(items, 1)) or "The queue is empty.")
