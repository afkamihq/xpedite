"""Reports for Discord, built from the app's log (logs/app-YYYYMMDD.log) rather than the runner, so
a summary covers every session, the supervisor's restarts included: a farm summary every few
hours (Config "Summary every"), /summary, and how long the log has been quiet (the stuck alert).
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS = os.path.join(ROOT, "logs")
LINE = re.compile(r"\[(\d\d):(\d\d):(\d\d)\] (.*)")
RESULT = re.compile(r"RESULT: Soul Furnace wave (\d+), \+(\d+) Candy Corn")
OUTCOME = re.compile(r"Soul Furnace: (.+?) at wave (\d+)")
BOOSTED = re.compile(r"DMG/RNG from wave (\d+)")
BINS = re.compile(r"bin (\d+)/(\d+)")
GREEN, AMBER, RED = 0x3BA55D, 0xF0B232, 0xED4245


def read_lines(since: datetime, until: datetime | None = None) -> list[tuple[datetime, str]]:
    until = until or datetime.now()
    out = []
    day = since.date()
    while day <= until.date():
        path = os.path.join(LOGS, f"app-{day:%Y%m%d}.log")
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for raw in f:
                    m = LINE.match(raw.rstrip("\n"))
                    if not m:
                        continue
                    t = datetime(day.year, day.month, day.day, int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    if since <= t < until:
                        out.append((t, m.group(4)))
        except OSError:
            pass
        day += timedelta(days=1)
    return out


def summarize(since: datetime, until: datetime | None = None) -> dict:
    until = until or datetime.now()
    runs, outcome, boosted, bins = [], None, None, None
    errors = disconnects = restarts = gave_up = 0
    last_disconnect = None
    for t, text in read_lines(since, until):
        m = OUTCOME.search(text)
        if m:
            outcome = m.group(1)
            b = BOOSTED.search(text)
            boosted = int(b.group(1)) if b else None
            n = BINS.search(text)
            bins = (int(n.group(1)), int(n.group(2))) if n else None
        m = RESULT.search(text)
        if m:
            runs.append({"wave": int(m.group(1)), "candy": int(m.group(2)), "outcome": outcome or "?",
                         "boosted": boosted, "bins": bins, "at": t})
            outcome = boosted = bins = None
        if "stopped by an error" in text and text.startswith("stopped"):
            errors += 1
        if "RECOVERY: disconnected" in text and (last_disconnect is None or (t - last_disconnect).seconds > 60):
            disconnects += 1
            last_disconnect = t
        if "starting it again in" in text:
            restarts += 1
        if "not starting again by itself" in text:
            gave_up += 1
    paid = [r for r in runs if not r["outcome"].startswith("lost")]
    hours = max((until - since).total_seconds() / 3600, 1e-6)
    return {"since": since, "until": until, "hours": hours, "runs": runs, "paid": paid,
            "candy": sum(r["candy"] for r in paid), "unsure": sum(r["candy"] for r in runs if r not in paid),
            "best": max((r["wave"] for r in runs), default=None),
            "avg": round(sum(r["wave"] for r in runs) / len(runs), 1) if runs else None,
            "errors": errors, "disconnects": disconnects, "restarts": restarts, "gave_up": gave_up,
            "bin_ok": sum(r["bins"][0] for r in runs if r["bins"]), "bin_tries": sum(r["bins"][1] for r in runs if r["bins"]),
            "boosted": [r["boosted"] for r in runs if r["boosted"]]}


def summary_embed(s: dict, title: str) -> dict:
    runs = s["runs"]
    trouble = s["errors"] + s["disconnects"] + s["gave_up"]
    colour = RED if s["gave_up"] else AMBER if trouble or not runs else GREEN
    if not runs:
        description = "No runs finished in this time."
    else:
        description = (f"**{len(runs)} runs** · **{s['candy']:,} Candy Corn** "
                       f"({s['candy'] / s['hours']:,.0f} an hour)")
        if s["unsure"]:
            description += f"\n+{s['unsure']:,} more from runs a disconnect ended (may not have paid)"
    fields = [
        {"name": "Waves", "value": f"best **{s['best'] or '-'}** · average {s['avg'] or '-'}", "inline": True},
        {"name": "Trouble", "value": (f"{_n(s['disconnects'], 'disconnect')} · {_n(s['errors'], 'error')} · "
                                      f"{_n(s['restarts'], 'restart')}" if trouble or s["restarts"] else "none"),
         "inline": True},
    ]
    if s["bin_tries"]:
        fields.append({"name": "Hotbar bin", "value": f"{s['bin_ok']}/{s['bin_tries']} drags worked", "inline": True})
    if s["boosted"]:
        fields.append({"name": "DMG/RNG", "value": f"in {len(s['boosted'])} runs, from wave "
                                                   f"{min(s['boosted'])}-{max(s['boosted'])}", "inline": True})
    if runs:
        last = runs[-5:]
        fields.append({"name": "Latest runs", "value": "\n".join(
            f"{r['at']:%H:%M} wave {r['wave']} · +{r['candy']:,}" + ("" if r in s["paid"] else " (disconnect)")
            for r in last), "inline": False})
    return {"title": f"Farm summary · {title}", "description": description, "color": colour, "fields": fields,
            "footer": {"text": f"{s['since']:%d %b %H:%M} to {s['until']:%H:%M}"}}


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def last_activity() -> float:
    """When the app last wrote its log (seconds since the epoch), 0 if there's no log yet."""
    path = os.path.join(LOGS, f"app-{datetime.now():%Y%m%d}.log")
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
