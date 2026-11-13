"""Driving the macro: /start, /stop, /pause, /collect, and /panel, a message with buttons for all
of it (Start, Pause/Resume, Stop, Status, Screenshot)."""
from macro.remote.commands.info import status_embed


def panel_buttons() -> list:
    def button(label, custom_id, style):
        return {"type": 2, "label": label, "custom_id": custom_id, "style": style}
    return [{"type": 1, "components": [button("Start", "ctl:start", 3), button("Pause / Resume", "ctl:pause", 2),
                                       button("Stop", "ctl:stop", 4)]},
            {"type": 1, "components": [button("Status", "ctl:status", 1), button("Screenshot", "ctl:shot", 2)]}]


def setup(bot):
    c = bot.controller

    @bot.command("start", "Start the queue (Soul Furnace forever, or whatever Tasks says)")
    def start(ctx):
        ctx.reply(c.start())

    @bot.command("stop", "Stop the run (Roblox stays open)")
    def stop(ctx):
        ctx.reply(c.stop())

    @bot.command("pause", "Pause the run, or carry on if it's paused")
    def pause(ctx):
        ctx.reply(c.pause_toggle())

    @bot.command("collect", "Collect quests and battlepass rewards (when nothing is running)")
    def collect(ctx):
        ctx.reply(c.collect())

    @bot.command("panel", "A control panel with buttons")
    def panel(ctx):
        ctx.reply(embed=status_embed(c), components=panel_buttons())

    @bot.button("ctl")
    def on_button(ctx, action):
        if action == "status":
            ctx.reply(embed=status_embed(c), components=panel_buttons(), update=True)
            return
        if action == "shot":
            ctx.defer()
            frame = c.screenshot()
            if frame is None:
                ctx.reply("Couldn't copy the screen (is the Remote Desktop window connected?).", ephemeral=True)
                return
            import cv2
            ok, png = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            ctx.reply(embed={"title": "The screen now", "image": {"url": "attachment://screen.jpg"}},
                      files=[("screen.jpg", png.tobytes())])
            return
        text = {"start": c.start, "stop": c.stop, "pause": c.pause_toggle}.get(action, lambda: "?")()
        ctx.reply(text, embed=status_embed(c), components=panel_buttons(), update=True)
