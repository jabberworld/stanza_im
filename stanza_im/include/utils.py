"""Miscellaneous utility functions."""
from __future__ import annotations

import os
import platform
import re
import time
import datetime


def get_home_dir() -> str:
    """Return the user's configuration directory for Stanza IM."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "Stanza IM")
    return os.path.join(os.path.expanduser("~"), ".stanza-im")


def format_time(timestamp: float | None = None) -> str:
    """Return *hh:mm:ss* for *timestamp* (default: now)."""
    if timestamp is None:
        timestamp = time.time()
    h, m, s = time.localtime(timestamp)[3:6]
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_time_short(timestamp: float | None = None) -> str:
    """Return *hh:mm* for *timestamp* (default: now)."""
    if timestamp is None:
        timestamp = time.time()
    h, m, _ = time.localtime(timestamp)[3:6]
    return f"{h:02d}:{m:02d}"


def ts_to_time(ts: str | None) -> str:
    """Format an ISO timestamp, including the date when older than one day."""
    if ts is None:
        return format_time()
    if not isinstance(ts, str):
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            ts = str(ts)
    if len(ts) >= 19 and ts[10] == "T":
        try:
            parsed = datetime.datetime.fromisoformat(
                ts.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone()
            now = datetime.datetime.now(parsed.tzinfo)
            fmt = "%Y-%m-%d %H:%M:%S" if now - parsed >= datetime.timedelta(days=1) \
                else "%H:%M:%S"
            return parsed.strftime(fmt)
        except ValueError:
            pass
        return ts[11:19]
    return ts or format_time()


def get_os_info() -> str:
    """Return a short OS description string for XEP-0092."""
    return f"{platform.system()} {platform.release()}"


def escape_html(text: str) -> str:
    """Minimal HTML escaping for status messages and nicknames."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_URL_RE = re.compile(
    r"(?:(?:https?|ftp)://|www\.)[^\s<>\"']+",
    re.IGNORECASE,
)
_URL_TRAILING_PUNCT = re.compile(r"[.,;:!?]+$")


def tokenize_urls(text: str) -> tuple[str, list[str]]:
    """Replace URL regions with NUL-byte tokens and return the anchor HTML.

    The tokenised text is safe to run through later text transforms (e.g.
    emoticon replacement) that could otherwise corrupt URL text.
    """
    anchors: list[str] = []

    def _repl(match):
        url = match.group(0)
        trimmed = _URL_TRAILING_PUNCT.sub("", url)
        if not trimmed:
            return url
        token = f"\x00{len(anchors)}\x00"
        anchors.append(f'<a href="{trimmed}">{trimmed}</a>')
        return token + url[len(trimmed):]

    tmp = _URL_RE.sub(_repl, text)
    return tmp, anchors


def restore_url_tokens(text: str, anchors: list[str]) -> str:
    """Swap NUL-byte tokens back to the anchor HTML from *tokenize_urls*."""
    for i, anchor in enumerate(anchors):
        text = text.replace(f"\x00{i}\x00", anchor)
    return text


def linkify(text: str) -> str:
    """Turn URLs in *text* (already HTML-escaped) into clickable links."""
    tmp, anchors = tokenize_urls(text)
    return restore_url_tokens(tmp, anchors)
