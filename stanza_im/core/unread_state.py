"""Persistent per-contact unread counters.

Stored as a JSON dict ``{"<jid>": <count>}`` at
``$XDG_DATA_HOME/stanza-im/unread.json`` so unread badges and tray blinking
survive a restart.
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


def load() -> dict[str, int]:
    """Return the stored ``{jid: count}`` (only positive entries)."""
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Could not read %s: %s", path(), exc)
        return {}
    if not isinstance(data, dict):
        return {}
    counts: dict[str, int] = {}
    for jid, value in data.items():
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if jid and count > 0:
            counts[str(jid)] = count
    return counts


def save(counts: dict[str, int]) -> None:
    """Persist *counts* (atomic write, 0600)."""
    clean: dict[str, int] = {}
    for jid, value in (counts or {}).items():
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if jid and count > 0:
            clean[str(jid)] = count
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path())
        os.chmod(path(), 0o600)
    except OSError as exc:
        logger.warning("Could not save %s: %s", path(), exc)
