"""Persisted roster cache for cross-session roster versioning (XEP-0237).

Because slixmpp's roster lives only in memory, every login used to fetch the
full roster.  This module stores the roster items and the roster version so
that, on the next login, the client can send the cached version and let the
server answer with an empty "no changes" result.

One JSON file per account at
``$XDG_DATA_HOME/stanza-im/roster/<safe-account>.json`` (0600).
"""
from __future__ import annotations

import json
import logging
import os
import re

from stanza_im.include.constants import DATA_DIR

logger = logging.getLogger(__name__)

_STATE_FIELDS = ("name", "groups", "from", "to", "whitelisted",
                 "pending_out", "pending_in")
_SAFE_RE = re.compile(r"[^A-Za-z0-9_.@-]")

_DIRNAME = "roster"


def _safe_name(account: str) -> str:
    return _SAFE_RE.sub("_", str(account or "").lower())


def path(account: str) -> str:
    """Return the cache path for *account* (a bare JID)."""
    directory = os.path.join(DATA_DIR, _DIRNAME)
    return os.path.join(directory, _safe_name(account) + ".json")


def load(account: str) -> dict | None:
    """Return ``{"version": str, "items": [...]}`` or ``None``.

    A missing, unreadable or malformed file yields ``None`` so the caller
    falls back to a full roster request.
    """
    if not account:
        return None
    try:
        with open(path(account), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Could not read roster cache for %s: %s", account, exc)
        return None
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    clean: list[dict] = []
    for entry in items:
        if not isinstance(entry, dict) or not entry.get("jid"):
            continue
        clean.append({key: entry.get(key) for key in ("jid",) + _STATE_FIELDS})
    return {"version": str(data.get("version") or ""), "items": clean}


def save(account: str, version: str, items: list[dict]) -> None:
    """Persist the roster *items* and *version* for *account*."""
    if not account:
        return
    payload = {
        "version": str(version or ""),
        "items": [
            {key: entry.get(key) for key in ("jid",) + _STATE_FIELDS}
            for entry in items
            if entry.get("jid")
        ],
    }
    target = path(account)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    except OSError as exc:
        logger.warning("Could not save roster cache for %s: %s", account, exc)
