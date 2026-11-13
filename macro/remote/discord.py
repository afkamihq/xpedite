"""Discord's REST API and gateway, on the standard library only (urllib + macro/remote/ws.py).

Rest: JSON and multipart (files) requests with the bot token, retried on rate limits.
Gateway: one thread that keeps the connection (hello, heartbeats, identify, resume after a drop,
reconnect with backoff) and hands each dispatch to a callback. Intents 0: slash commands and
buttons arrive as INTERACTION_CREATE without any privileged intent, so no message content is read.
"""
from __future__ import annotations

import json
import random
import threading
import time
import urllib.error
import urllib.request
import uuid

from macro.remote.ws import WebSocket, WebSocketClosed

API = "https://discord.com/api/v10"
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
USER_AGENT = "DiscordBot (https://github.com/afkami/xpedite, 1.0)"
FATAL_CLOSES = {4004: "the bot token was refused", 4010: "invalid shard", 4011: "sharding required",
                4012: "invalid API version", 4013: "invalid intents", 4014: "intents not allowed"}


class DiscordError(Exception):
    pass


class Rest:
    def __init__(self, token: str):
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None,
                files: list[tuple[str, bytes]] | None = None, timeout: float = 20.0):
        """files: [(filename, bytes)], sent as files[n] beside payload_json. Returns the JSON reply
        (or None for an empty one). Raises DiscordError with Discord's message."""
        headers = {"Authorization": f"Bot {self.token}", "User-Agent": USER_AGENT}
        if files:
            boundary = uuid.uuid4().hex
            parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
                     f"Content-Type: application/json\r\n\r\n{json.dumps(payload or {})}\r\n".encode()]
            for n, (name, data) in enumerate(files):
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[{n}]\"; "
                             f"filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
                             + data + b"\r\n")
            parts.append(f"--{boundary}--\r\n".encode())
            body = b"".join(parts)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        else:
            body = None
        for _ in range(4):
            req = urllib.request.Request(API + path, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as reply:
                    text = reply.read()
                    return json.loads(text) if text else None
            except urllib.error.HTTPError as error:
                text = error.read().decode(errors="replace")
                if error.code == 429:
                    try:
                        wait = float(json.loads(text).get("retry_after", 1.0))
                    except ValueError:
                        wait = 1.0
                    time.sleep(min(wait, 30.0) + 0.1)
                    continue
                raise DiscordError(f"{method} {path}: HTTP {error.code} {text[:300]}") from None
            except urllib.error.URLError as error:
                raise DiscordError(f"{method} {path}: {error.reason}") from None
        raise DiscordError(f"{method} {path}: still rate limited")


class Gateway(threading.Thread):
    """Keeps the bot online. on_dispatch(event_name, data) runs on this thread: keep it quick
    (hand long work to another thread)."""

    def __init__(self, token: str, on_dispatch, log=print, intents: int = 0):
        super().__init__(daemon=True, name="discord-gateway")
        self.token, self.on_dispatch, self.log, self.intents = token, on_dispatch, log, intents
        self.presence: tuple | None = None  # (text, status): sent with identify and on each change
        self.ws: WebSocket | None = None
        self.seq = None
        self.session_id = None
        self.resume_url = None
        self.stopping = threading.Event()
        self.fatal: str | None = None
        self.user: dict | None = None
        self._acked = True

    def stop(self):
        self.stopping.set()
        if self.ws:
            self.ws.close()

    def run(self):
        delay = 2.0
        while not self.stopping.is_set():
            try:
                self._session()
                delay = 2.0
            except WebSocketClosed as closed:
                if closed.code in FATAL_CLOSES:
                    self.fatal = FATAL_CLOSES[closed.code]
                    self.log(f"Discord bot stopped: {self.fatal}")
                    return
                if closed.code in (4007, 4009):  # bad sequence / session timed out: start over
                    self.session_id = self.seq = None
            except Exception as error:  # noqa: BLE001 - network trouble: wait and connect again
                if self.stopping.is_set():
                    return
                self.log(f"Discord connection lost ({error}); trying again in {delay:.0f} s")
            if self.stopping.wait(delay):
                return
            delay = min(delay * 2, 120.0)

    def set_presence(self, text: str, status: str = "online"):
        """The bot's status line under its name ("Wave 34 · 1,420 Candy Corn") and dot: online,
        idle or dnd. Kept, so a reconnect shows it again."""
        self.presence = (text, status)
        if self.ws is not None and self.session_id:
            try:
                self._send(3, self._presence_payload())
            except OSError:
                pass

    def _presence_payload(self) -> dict:
        text, status = self.presence
        return {"since": None, "afk": False, "status": status,
                "activities": [{"type": 4, "name": "Custom Status", "state": text[:128]}]}

    def _send(self, op: int, data):
        if self.ws:
            self.ws.send(json.dumps({"op": op, "d": data}))

    def _heartbeat(self, ws, interval: float):
        time.sleep(interval * random.random())
        while not self.stopping.is_set() and self.ws is ws:
            if not self._acked:  # no ACK since the last beat: the connection is a zombie
                ws.close(4000)
                return
            self._acked = False
            try:
                self._send(1, self.seq)
            except OSError:
                return
            time.sleep(interval)

    def _session(self):
        url = self.resume_url if (self.session_id and self.resume_url) else GATEWAY
        if "?" not in url:
            url += "/?v=10&encoding=json"
        ws = WebSocket(url)
        self.ws = ws
        try:
            hello = json.loads(ws.recv())
            interval = hello["d"]["heartbeat_interval"] / 1000.0
            # With intents 0 nothing may come for a whole heartbeat (~41 s): the connect timeout
            # (30 s) dropped the connection every minute (12 Nov 2026). A dead one is caught by
            # the missing heartbeat ACK instead (_heartbeat closes it).
            ws.sock.settimeout(interval * 2 + 15)
            self._acked = True
            threading.Thread(target=self._heartbeat, args=(ws, interval), daemon=True).start()
            if self.session_id:
                self._send(6, {"token": self.token, "session_id": self.session_id, "seq": self.seq})
            else:
                identify = {"token": self.token, "intents": self.intents,
                               "properties": {"os": "windows", "browser": "afkami-xpedite",
                                              "device": "afkami-xpedite"}}
                if self.presence:
                    identify["presence"] = self._presence_payload()
                self._send(2, identify)
            while not self.stopping.is_set():
                message = json.loads(ws.recv())
                op = message.get("op")
                if message.get("s") is not None:
                    self.seq = message["s"]
                if op == 0:
                    name, data = message.get("t"), message.get("d") or {}
                    if name == "RESUMED" and self.presence:
                        self._send(3, self._presence_payload())
                    if name == "READY":
                        self.session_id = data.get("session_id")
                        self.resume_url = data.get("resume_gateway_url")
                        self.user = data.get("user")
                    try:
                        self.on_dispatch(name, data)
                    except Exception as error:  # noqa: BLE001 - one bad handler mustn't drop the bot
                        self.log(f"Discord: handling {name} failed: {error}")
                elif op == 11:
                    self._acked = True
                elif op == 1:
                    self._send(1, self.seq)
                elif op == 7:  # Discord asks for a reconnect: resume
                    return
                elif op == 9:  # invalid session
                    if not message.get("d"):
                        self.session_id = self.seq = None
                    time.sleep(1 + random.random() * 4)
                    return
        finally:
            self.ws = None
            ws.close()
