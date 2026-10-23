"""Persisted roster cache for cross-session roster versioning (XEP-0237).

Because slixmpp's roster lives only in memory, every login used to fetch the
full roster.  This module stores the roster items and the roster version so
that, on the next login, the client can send the cached version and let the
server answer with an empty "no changes" result.

One JSON file per account at
``$XDG_DATA_HOME/stanza-im/roster/<safe-account>.json`` (0600).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re

from stanza_im.include.constants import DATA_DIR

logger = logging.getLogger(__name__)


def set_profile(jid: str) -> None:
    """Point ``DATA_DIR`` at the active profile's data directory."""
    global DATA_DIR
    from stanza_im.include import constants
    constants.set_active_profile(jid)
    DATA_DIR = constants.profile_data_dir()


_STATE_FIELDS = ("name", "groups", "from", "to", "whitelisted",
                 "pending_out", "pending_in")
_SAFE_RE = re.compile(r"[^A-Za-z0-9_.@-]")
# A Unicode localpart is sanitised to underscores; the digest keeps two such
# accounts from sharing one roster cache.
_DIGEST_LEN = 10
_PREFIX_MAX = 180

_DIRNAME = "roster"


def _safe_name(account: str) -> str:
    value = str(account or "").lower()
    safe = _SAFE_RE.sub("_", value)
    if safe != value:
        digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:_DIGEST_LEN]
        safe = f"{safe[:_PREFIX_MAX]}-{digest}"
    return safe


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
    stored = str(data.get("account") or "")
    if stored and stored.lower() != account.lower():
        logger.debug("ROSTER[cache] ignoring %s written for %s",
                     path(account), stored)
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    clean: list[dict] = []
    for entry in items:
        if not isinstance(entry, dict) or not entry.get("jid"):
            continue
        clean.append({key: entry.get(key) for key in ("jid",) + _STATE_FIELDS})
    logger.debug("ROSTER[cache] load %s n=%d ver=%r", path(account),
                 len(clean), str(data.get("version") or ""))
    return {"version": str(data.get("version") or ""), "items": clean}


def save(account: str, version: str, items: list[dict]) -> None:
    """Persist the roster *items* and *version* for *account*."""
    if not account:
        return
    payload = {
        "account": str(account),
        "version": str(version or ""),
        "items": [
            {key: entry.get(key) for key in ("jid",) + _STATE_FIELDS}
            for entry in items
            if entry.get("jid")
        ],
    }
    target = path(account)
    logger.debug("ROSTER[cache] save %s n=%d ver=%r", target,
                 len(payload["items"]), payload["version"])
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    except OSError as exc:
        logger.warning("Could not save roster cache for %s: %s", account, exc)
