"""Local invitation tokens for the client-side XEP-0379 fallback.

Server-side XEP-0401 invitations are validated by the server and are not kept
here.  Tokens created by this client (when the server has no invite command)
are single-use, expire after a week and live in the active profile's data
directory with mode 0600.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time

from stanza_im.include import constants

logger = logging.getLogger(__name__)

_FILE = "pars_tokens.json"
DEFAULT_TTL = 7 * 24 * 60 * 60


def path() -> str:
    return os.path.join(constants.DATA_DIR, _FILE)


def _load() -> dict:
    try:
        with open(path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    try:
        os.makedirs(constants.DATA_DIR, exist_ok=True)
        tmp = path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        os.replace(tmp, path())
        os.chmod(path(), 0o600)
    except OSError as exc:
        logger.warning("Could not save invitation tokens: %s", exc)


def issue(name: str = "", ttl: int = DEFAULT_TTL, uses: int = 1) -> str:
    """Create and persist a new URL-safe token (at least 128 bits)."""
    token = secrets.token_urlsafe(16)
    purge()
    now = time.time()
    data = _load()
    data[token] = {
        "name": str(name or ""),
        "created": now,
        "expires": now + max(1, int(ttl)),
        "uses": max(1, int(uses)),
    }
    _save(data)
    return token


def consume(token: str) -> dict | None:
    """Return and consume a valid token; invalid/expired tokens return None."""
    token = str(token or "")
    if not token:
        return None
    data = _load()
    entry = data.get(token)
    if not isinstance(entry, dict):
        return None
    now = time.time()
    try:
        expires = float(entry.get("expires") or 0)
        uses = int(entry.get("uses") or 0)
    except (TypeError, ValueError):
        expires, uses = 0, 0
    if expires <= now or uses <= 0:
        data.pop(token, None)
        _save(data)
        return None
    entry["uses"] = uses - 1
    if entry["uses"] <= 0:
        data.pop(token, None)
    else:
        data[token] = entry
    _save(data)
    return entry


def purge() -> None:
    """Drop expired tokens (called on issue/startup)."""
    now = time.time()
    data = _load()
    changed = False
    for token, entry in list(data.items()):
        try:
            expired = float(entry.get("expires") or 0) <= now
        except (TypeError, ValueError, AttributeError):
            expired = True
        if expired:
            data.pop(token, None)
            changed = True
    if changed:
        _save(data)
