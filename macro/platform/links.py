"""Private server links to the roblox:// address that launches straight into the server.

A player can paste either form Roblox hands out:
- the share link, https://www.roblox.com/share?code=<32 hex>&type=Server. A browser turns it into
  the second form by asking Roblox's link API with the player's login, which the macro must never
  touch. The Roblox client resolves share links itself: roblox://navigation/share_links?code=..&type=Server
- the game link, https://www.roblox.com/games/<place>/<name>?privateServerLinkCode=<digits>:
  roblox://placeId=<place>&linkCode=<digits>.
No link (or an unreadable one) means a public server. No OS code here: both platforms use it.
"""

from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, urlparse

PLACE_ID = 84515722934860
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SETTINGS_FILE = os.path.join(ROOT, "data", "settings.yaml")


class BadLink(ValueError):
    pass


def to_launch_uri(link: str | None, place_id: int = PLACE_ID) -> str:
    """The roblox:// address for a private server link, or the public game for an empty one.
    Raises BadLink for something that is neither form, or a server of another game."""
    link = (link or "").strip()
    if not link:
        return f"roblox://placeId={place_id}"
    if not re.match(r"^[a-z]+://", link, re.I):
        link = "https://" + link
    url = urlparse(link)
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    host = url.netloc.lower()
    if not (host == "roblox.com" or host.endswith(".roblox.com")):
        raise BadLink("not a roblox.com link")
    if url.path.rstrip("/").lower() == "/share":
        code, kind = query.get("code", ""), query.get("type", "")
        if not re.fullmatch(r"[0-9a-fA-F]{16,64}", code):
            raise BadLink("the share link has no code")
        if kind.lower() != "server":
            raise BadLink(f"that share link is for {kind or 'something else'}, not a server")
        return f"roblox://navigation/share_links?code={code}&type=Server"
    found = re.match(r"^/games/(\d+)", url.path)
    if found and "privateServerLinkCode" in query:
        if int(found.group(1)) != place_id:
            raise BadLink("that private server is for another game")
        code = query["privateServerLinkCode"]
        if not re.fullmatch(r"\d{8,64}", code):
            raise BadLink("the private server code isn't a number")
        return f"roblox://placeId={place_id}&linkCode={code}"
    raise BadLink("not a private server link (want a share?code=... or a ...?privateServerLinkCode=... link)")


def launch_uri() -> str:
    """What the macro should launch now: the Config's private server, or the public game if
    none is set or it can't be read (a bad link mustn't stop a restart)."""
    try:
        import yaml
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            link = (yaml.safe_load(f) or {}).get("private_server", "")
        return to_launch_uri(link)
    except (OSError, BadLink, ValueError):
        return f"roblox://placeId={PLACE_ID}"


def describe(link: str | None) -> str:
    """One line for the Config window: what this link will do."""
    if not (link or "").strip():
        return "Empty: Roblox opens a public server."
    try:
        uri = to_launch_uri(link)
    except BadLink as why:
        return f"Can't use this: {why}."
    if "share_links" in uri:
        return "Share link: Roblox starts straight into your server."
    return "Private server link: Roblox starts straight into your server."
