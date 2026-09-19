"""Persistent per-contact unread counters.

Stored as a JSON dict ``{"<jid>": {"count": N, "displayed": "<sid>"}}`` at
``$XDG_DATA_HOME/stanza-im/unread.json`` so unread badges and tray blinking
survive a restart.  The optional ``displayed`` field is the last XEP-0490
stanza-id we published for the chat; it is seeded into the client on startup so
the MDS catch-up does not clear unread messages that arrived after it.  The
legacy ``{"<jid>": N}`` format is still accepted.
"""
from __future__ import annotations

import json
import logging
import os

from stanza_im.include.constants import DATA_DIR

logger = logging.getLogger(__name__)

_FILE = "unread.json"


def path() -> str:
    return os.path.join(DATA_DIR, _FILE)


def _parse(data) -> tuple[dict[str, int], dict[str, str]]:
    """Return ``(counts, displayed)`` from a decoded JSON payload."""
    counts: dict[str, int] = {}
    displayed: dict[str, str] = {}
    if not isinstance(data, dict):
        return counts, displayed
    for jid, value in data.items():
        jid = str(jid or "")
        if not jid:
            continue
        sid = ""
        if isinstance(value, dict):
            sid = value.get("displayed") or ""
            value = value.get("count")
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count > 0:
            counts[jid] = count
            if isinstance(sid, str) and sid:
                displayed[jid] = sid
    return counts, displayed


def load_state() -> tuple[dict[str, int], dict[str, str]]:
    """Return ``({jid: count}, {jid: displayed-sid})`` from disk."""
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Could not read %s: %s", path(), exc)
        return {}, {}
    return _parse(data)


def load() -> dict[str, int]:
    """Return the stored ``{jid: count}`` (only positive entries)."""
    return load_state()[0]


def save(counts: dict[str, int], displayed: dict[str, str] | None = None) -> None:
    """Persist *counts* and their last-displayed sids (atomic write, 0600)."""
    displayed = displayed or {}
    clean: dict[str, dict] = {}
    for jid, value in (counts or {}).items():
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if not jid or count <= 0:
            continue
        entry: dict = {"count": count}
        sid = displayed.get(jid)
        if isinstance(sid, str) and sid:
            entry["displayed"] = sid
        clean[str(jid)] = entry
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path())
        os.chmod(path(), 0o600)
    except OSError as exc:
        logger.warning("Could not save %s: %s", path(), exc)
