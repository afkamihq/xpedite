"""Sending a result and its screenshot to a webhook URL the user gave, Discord-style.

Returns an error message rather than raising: a webhook that doesn't work must never stop a run.
Only ever sends to the URL in the user's settings.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

import cv2


GOOD, BAD, NEUTRAL = 0x7FE0B5, 0xFF8C8C, 0xD9E4FF


def clock(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    return f"{hours}h {rest // 60:02d}m" if hours else f"{rest // 60}:{rest % 60:02d}"


def result_embed(title: str, outcome: str, lines: list[str], fields: list[tuple[str, str]],
                 footer: str, with_picture: bool) -> dict:
    """One match's result as a Discord embed: coloured by outcome, the screenshot as its image."""
    embed = {
        "title": title,
        "color": GOOD if outcome in ("victory", "built") else BAD if outcome == "defeat" else NEUTRAL,
        "description": "\n".join(lines),
        "fields": [{"name": name, "value": value, "inline": True} for name, value in fields],
        "footer": {"text": footer},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if with_picture:
        embed["image"] = {"url": "attachment://result.jpg"}
    embed["thumbnail"] = {"url": "attachment://badge.gif"}
    return embed


BOT = "discord-bot"  # target() when the remote-control bot carries the results


def target(settings: dict) -> str:
    """Where results go: the Discord bot's channel when the bot is running (it replaces the
    webhook, 12 Nov 2026), else the webhook address, else "" (nowhere)."""
    from macro.remote import bot
    if bot.ACTIVE is not None and bot.ACTIVE.config.channel_id:
        return BOT
    return settings.get("webhook", "") or ""


def send(url: str, text: str, frame=None, timeout: float = 10.0, embed: dict | None = None,
         files: list[tuple[str, bytes, str]] = ()) -> str | None:
    from macro.remote import bot
    if url == BOT or (bot.ACTIVE is not None and bot.ACTIVE.config.channel_id):
        if bot.ACTIVE is None:
            return "the Discord bot isn't running"
        return bot.ACTIVE.post(text, frame, embed=embed, files=[(f[0], f[1]) for f in files])
    if not url.lower().startswith(("https://", "http://")):
        return f"that doesn't look like a web address: {url[:40]}"
    boundary = uuid.uuid4().hex
    from macro import brand
    payload = {"content": text or None, "username": brand.NAME}
    if embed is not None:
        payload["embeds"] = [embed]
    parts = [(f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
              f'Content-Type: application/json\r\n\r\n{json.dumps(payload)}\r\n').encode()]
    if frame is not None:
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="result.jpg"\r\n'
                          "Content-Type: image/jpeg\r\n\r\n").encode() + jpeg.tobytes() + b"\r\n")
    for number, (name, data, kind) in enumerate(files, start=1):
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file{number}"; filename="{name}"\r\n'
                      f"Content-Type: {kind}\r\n\r\n").encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(url, data=b"".join(parts), method="POST", headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "afkami-xpedite/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return None
    except urllib.error.HTTPError as error:
        return f"the server said {error.code}"
    except (urllib.error.URLError, OSError, ValueError) as error:
        return str(error)
