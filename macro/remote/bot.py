"""The remote-control bot: slash commands and buttons on top of macro/remote/discord.py.

Modular: each feature is a module in macro/remote/commands/ with a setup(bot) that adds its
commands (@bot.command) and buttons (@bot.button). The bot itself knows nothing about the macro:
the commands talk to a controller object the app passes in (start, stop, status, screenshot...).

Safety: only the owners' Discord user ids may use it; anyone else gets a private refusal. With no
ids given, the owners are whoever owns the bot's application in the Developer Portal (or its team),
asked from Discord at start: so only the token is needed.
Results that used to go to the webhook go to the bot's channel instead (post()).
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from macro.remote.discord import DiscordError, Gateway, Rest

EPHEMERAL = 64
# Discord's option types
STRING, INTEGER, BOOLEAN = 3, 4, 5


@dataclass
class BotConfig:
    token: str
    app_id: str
    channel_id: str = ""  # where results and run events go
    guild_id: str = ""  # commands registered to this server appear at once (global ones can lag)
    owners: list = field(default_factory=list)  # Discord user ids allowed to control the macro


@dataclass
class Command:
    name: str
    description: str
    handler: object
    options: list = field(default_factory=list)


class Context:
    """One interaction: who, what, and how to answer it (within Discord's 3 s, or deferred)."""

    def __init__(self, bot: "Bot", data: dict):
        self.bot, self.data = bot, data
        self.started = time.monotonic()
        self.responded = False
        self.deferred = False
        member = data.get("member") or {}
        self.user = (member.get("user") or data.get("user") or {})
        self.options = {o["name"]: o.get("value") for o in (data.get("data") or {}).get("options") or []}
        self.custom_id = (data.get("data") or {}).get("custom_id", "")
        self.is_button = data.get("type") == 3

    @property
    def _base(self):
        return f"/interactions/{self.data['id']}/{self.data['token']}/callback"

    def defer(self, ephemeral: bool = False):
        """'Thinking...' now, the answer later (for anything that may take over 3 s)."""
        if self.responded or self.deferred:
            return
        kind = 6 if self.is_button else 5
        self.bot.rest.request("POST", self._base, {"type": kind, "data": {"flags": EPHEMERAL if ephemeral else 0}})
        self.deferred = True

    def reply(self, content: str = "", embed: dict | None = None, files: list | None = None,
              components: list | None = None, ephemeral: bool = False, update: bool = False):
        message = {"content": content, "embeds": [embed] if embed else [], "components": components or []}
        if ephemeral:
            message["flags"] = EPHEMERAL
        if self.deferred and not self.is_button:
            self.bot.rest.request("PATCH", f"/webhooks/{self.bot.config.app_id}/{self.data['token']}"
                                  "/messages/@original", message, files=files)
        elif self.deferred or self.responded:
            self.bot.rest.request("POST", f"/webhooks/{self.bot.config.app_id}/{self.data['token']}",
                                  message, files=files)
        else:
            kind = 7 if (update and self.is_button) else 4
            self.bot.rest.request("POST", self._base, {"type": kind, "data": message}, files=files)
        self.responded = True


class Bot:
    def __init__(self, config: BotConfig, controller, log=print):
        self.config, self.controller, self.log = config, controller, log
        self.rest = Rest(config.token)
        self.commands: dict[str, Command] = {}
        self.buttons: dict[str, object] = {}  # custom_id prefix -> handler(ctx, rest_of_id)
        self.gateway: Gateway | None = None
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="discord-cmd")

    # ------------------------------------------------------------------ registering
    def command(self, name: str, description: str, options: list | None = None):
        def add(handler):
            self.commands[name] = Command(name, description, handler, options or [])
            return handler
        return add

    def button(self, prefix: str):
        def add(handler):
            self.buttons[prefix] = handler
            return handler
        return add

    def load(self, modules):
        for module in modules:
            module.setup(self)

    def register_commands(self):
        body = [{"name": c.name, "description": c.description, "options": c.options, "type": 1}
                for c in self.commands.values()]
        where = (f"/applications/{self.config.app_id}/guilds/{self.config.guild_id}/commands"
                 if self.config.guild_id else f"/applications/{self.config.app_id}/commands")
        self.rest.request("PUT", where, body)
        self.log(f"Discord: {len(body)} commands registered" + (" (this server)" if self.config.guild_id else ""))

    def resolve_application(self):
        """The application id and owners from Discord itself when Config leaves them blank: the
        bot's own application (GET /oauth2/applications/@me), owned by a user or a team."""
        if self.config.app_id and self.config.owners:
            return
        app = self.rest.request("GET", "/oauth2/applications/@me") or {}
        if not self.config.app_id:
            self.config.app_id = str(app.get("id") or "")
        if not self.config.owners:
            team = app.get("team") or {}
            ids = [str((m.get("user") or {}).get("id")) for m in team.get("members") or []
                   if (m.get("user") or {}).get("id")]
            owner = (app.get("owner") or {}).get("id")
            self.config.owners = ids or ([str(owner)] if owner else [])
            names = ", ".join(self.config.owners) or "nobody"
            self.log(f"Discord: owner from the bot's application: {names}")

    # ------------------------------------------------------------------ running
    def start(self):
        def setup():
            try:
                self.resolve_application()
                self.register_commands()
            except DiscordError as error:
                self.log(f"Discord: couldn't register the commands: {error}")
        threading.Thread(target=setup, daemon=True, name="discord-setup").start()
        self.gateway = Gateway(self.config.token, self._dispatch, log=self.log)
        self.gateway.start()

    def stop(self):
        if self.gateway:
            self.gateway.stop()
        self.pool.shutdown(wait=False)

    @property
    def online(self) -> bool:
        return bool(self.gateway and self.gateway.session_id and not self.gateway.fatal)

    def _dispatch(self, name: str, data: dict):
        if name == "READY":
            user = data.get("user") or {}
            self.log(f"Discord bot online as {user.get('username', '?')}")
        elif name == "INTERACTION_CREATE":
            self.pool.submit(self._interaction, data)

    def _interaction(self, data: dict):
        ctx = Context(self, data)
        try:
            if str(ctx.user.get("id")) not in {str(o) for o in self.config.owners}:
                ctx.reply("This macro only takes orders from its owner.", ephemeral=True)
                return
            if data.get("type") == 2:
                command = self.commands.get((data.get("data") or {}).get("name", ""))
                if command:
                    command.handler(ctx)
            elif data.get("type") == 3:
                prefix, _, rest = ctx.custom_id.partition(":")
                handler = self.buttons.get(prefix)
                if handler:
                    handler(ctx, rest)
        except Exception as error:  # noqa: BLE001 - answer something rather than leave "thinking"
            self.log(f"Discord: a command failed: {error}")
            try:
                ctx.reply(f"That didn't work: {error}", ephemeral=True)
            except DiscordError:
                pass

    # ------------------------------------------------------------------ the old webhook's job
    def post(self, text: str = "", frame=None, embed: dict | None = None, files=None) -> str | None:
        """A message to the results channel; frame: a BGR picture attached and shown in the
        embed. Returns an error text, or None (webhook.send's contract)."""
        if not self.config.channel_id:
            return "no results channel set"
        attached = []
        if frame is not None:
            import cv2
            ok, png = cv2.imencode(".png", frame)
            if ok:
                attached.append(("result.png", png.tobytes()))
                if embed is not None:
                    embed = dict(embed, image={"url": "attachment://result.png"})
        for item in files or []:
            if isinstance(item, tuple):
                attached.append(item)
            else:
                import os
                with open(item, "rb") as f:
                    attached.append((os.path.basename(item), f.read()))
        message = {"content": text, "embeds": [embed] if embed else []}
        try:
            self.rest.request("POST", f"/channels/{self.config.channel_id}/messages", message, files=attached or None)
            return None
        except DiscordError as error:
            return str(error)


    def set_presence(self, text: str, status: str = "online"):
        if self.gateway is not None:
            self.gateway.set_presence(text, status)

    def alert(self, text: str, embed: dict | None = None) -> str | None:
        """A message to the results channel that pings the owners: for what needs someone (the
        supervisor gave up, the farm looks stuck). Returns an error text, or None."""
        if not self.config.channel_id:
            return "no results channel set"
        owners = [str(o) for o in self.config.owners]
        message = {"content": " ".join(f"<@{o}>" for o in owners) + f" {text}",
                   "allowed_mentions": {"users": owners}, "embeds": [embed] if embed else []}
        try:
            self.rest.request("POST", f"/channels/{self.config.channel_id}/messages", message)
            return None
        except DiscordError as error:
            return str(error)


ACTIVE: Bot | None = None  # the running bot, if any: webhook.send hands results to it


def start(config: BotConfig, controller, log=print) -> Bot:
    from macro.remote import commands
    global ACTIVE
    bot = Bot(config, controller, log)
    bot.load(commands.MODULES)
    bot.start()
    ACTIVE = bot
    return bot


def stop():
    global ACTIVE
    if ACTIVE:
        ACTIVE.stop()
    ACTIVE = None
