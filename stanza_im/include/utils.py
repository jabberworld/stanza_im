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


def default_download_dir() -> str:
    """Default directory for received files.

    ``$XDG_DOWNLOAD_DIR`` when set, otherwise ``~/Downloads``.
    """
    xdg = os.environ.get("XDG_DOWNLOAD_DIR", "").strip()
    if xdg:
        return os.path.expandvars(os.path.expanduser(xdg))
    return os.path.join(os.path.expanduser("~"), "Downloads")


def safe_filename(name: str) -> str:
    """Sanitize a remote file name for local use (XEP-0234 §12).

    Strips directory separators, ``..`` components and control characters so a
    peer cannot escape the download directory.
    """
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = name.replace("\x00", "").strip().strip(".")
    cleaned = "".join(ch for ch in name
                      if ch.isprintable() and ch not in "/\\")
    return cleaned or "file"


def unique_path(path: str) -> str:
    """Return *path* or ``path (n).ext`` when the file already exists."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    index = 1
    while True:
        candidate = f"{base} ({index}){ext}"
        if not os.path.exists(candidate):
            return candidate
        index += 1


def format_size(size: int) -> str:
    """Human-readable file size, e.g. ``0 B``, ``1.5 KB``, ``2.3 MB``."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


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
    r"(?:(?:https?|ftp|aesgcm)://|www\.)[^\s<>\"']+",
    re.IGNORECASE,
)
_URL_TRAILING_PUNCT = re.compile(r"[.,;:!?]+$")


def tokenize_urls(text: str, media_render=None, geo_render=None
                  ) -> tuple[str, list[str]]:
    """Replace URL and geo: regions with NUL-byte tokens, return anchor HTML.

    The tokenised text is safe to run through later text transforms (e.g.
    emoticon replacement) that could otherwise corrupt URL text.

    When *media_render* is given, it is called with each trimmed http(s) URL
    and may return replacement markup (an embedded preview/player); ``None``
    falls back to a plain ``<a>`` link.

    When *geo_render* is given, it is called with each RFC 5870 ``geo:`` URI
    substring (e.g. ``geo:lat,lon;u=acc``) and may return replacement markup;
    ``None`` renders a plain (non-clickable-in-the-app) ``<a href="geo:..">``
    link.  The geo pass runs after URL tokenization so tokens stay valid.
    """
    anchors: list[str] = []

    def _repl(match):
        url = match.group(0)
        trimmed = _URL_TRAILING_PUNCT.sub("", url)
        if not trimmed:
            return url
        token = f"\x00{len(anchors)}\x00"
        markup = None
        if media_render is not None:
            try:
                markup = media_render(trimmed)
            except Exception:
                markup = None
        anchors.append(markup or f'<a href="{trimmed}">{trimmed}</a>')
        return token + url[len(trimmed):]

    def _geo_repl(match):
        uri = match.group(0)
        token = f"\x00{len(anchors)}\x00"
        markup = None
        if geo_render is not None:
            try:
                markup = geo_render(uri)
            except Exception:
                markup = None
        anchors.append(markup or f'<a href="{uri}">{uri}</a>')
        return token

    def _xmpp_repl(match):
        # XEP-0147 xmpp: URIs become plain anchors (never media embeds).
        url = match.group(0)
        trimmed = _URL_TRAILING_PUNCT.sub("", url)
        if not trimmed:
            return url
        token = f"\x00{len(anchors)}\x00"
        anchors.append(f'<a href="{trimmed}">{trimmed}</a>')
        return token + url[len(trimmed):]

    from stanza_im.include.geo import _GEO_IN_TEXT_RE
    tmp = _URL_RE.sub(_repl, text)
    if geo_render is not None or _GEO_IN_TEXT_RE.search(tmp):
        tmp = _GEO_IN_TEXT_RE.sub(_geo_repl, tmp)
    from stanza_im.include.xmpp_uri import _XMPP_URI_RE
    if _XMPP_URI_RE.search(tmp):
        tmp = _XMPP_URI_RE.sub(_xmpp_repl, tmp)
    return tmp, anchors


def restore_url_tokens(text: str, anchors: list[str]) -> str:
    """Swap NUL-byte tokens back to the anchor HTML from *tokenize_urls*."""
    for i, anchor in enumerate(anchors):
        text = text.replace(f"\x00{i}\x00", anchor)
    return text


def format_local_datetime(value) -> str:
    """Format a unix timestamp or ISO string as local ``YYYY-MM-DD HH:MM:SS``."""
    dt = None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            dt = datetime.datetime.fromtimestamp(float(value))
        except (OverflowError, OSError, ValueError):
            dt = None
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if len(text) >= 19 and text[10] == "T":
            try:
                parsed = datetime.datetime.fromisoformat(
                    text.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone()
                dt = parsed
            except ValueError:
                dt = None
        elif text.isdigit():
            try:
                dt = datetime.datetime.fromtimestamp(float(text))
            except (OverflowError, OSError, ValueError):
                dt = None
    if dt is None:
        return str(value) if value not in (None, "") else ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


_TZO_RE = re.compile(r"^([+-])(\d{2}):?(\d{2})$")


def local_time_from_tzo(tzo: str, now: float | None = None) -> str:
    """Return an entity's local ``YYYY-MM-DD HH:MM:SS`` from its tzo offset.

    *tzo* is the XEP-0202 offset (``+HH:MM``/``-HH:MM``); the current UTC time
    is shifted by it.  Returns ``""`` when *tzo* is missing or malformed.
    """
    if not tzo:
        return ""
    match = _TZO_RE.match(str(tzo).strip())
    if not match:
        return ""
    sign = 1 if match.group(1) == "+" else -1
    minutes = sign * (int(match.group(2)) * 60 + int(match.group(3)))
    if now is None:
        base = datetime.datetime.now(datetime.timezone.utc)
    else:
        base = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
    local = base + datetime.timedelta(minutes=minutes)
    return local.strftime("%Y-%m-%d %H:%M:%S")


def status_icon_html(show: str, size: int = 16) -> str:
    """Return an ``<img>`` tag for the presence status icon of *show*."""
    from stanza_im.include.constants import STATUS_DIR_16
    from stanza_im.include.enumerators import show_to_icon_key
    path = os.path.join(STATUS_DIR_16,
                        f"jabber-{show_to_icon_key(show)}.png")
    if not os.path.exists(path):
        return ""
    return f'<img src="{path}" width="{size}" height="{size}">'


def linkify(text: str) -> str:
    """Turn URLs in *text* (already HTML-escaped) into clickable links."""
    tmp, anchors = tokenize_urls(text)
    return restore_url_tokens(tmp, anchors)
