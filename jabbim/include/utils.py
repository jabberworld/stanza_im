"""Miscellaneous utility functions."""
from __future__ import annotations

import os
import platform
import re
import time


def get_home_dir() -> str:
    """Return the user's configuration directory for Jabbim."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "Jabbim")
    return os.path.join(os.path.expanduser("~"), ".jabbim")


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
