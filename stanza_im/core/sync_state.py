"""Account-level XEP-0313 archive synchronization cursor.

The global cursor belongs to the account, not to a single conversation: one
forward MAM pass over the account's own archive catches every message received
while this device was offline.  It is stored beside the other per-profile
state, so switching accounts can never reuse another account's cursor.
"""
from __future__ import annotations

import json
import logging
import os

from stanza_im.include.constants import DATA_DIR

logger = logging.getLogger(__name__)

_FILE = "sync_state.json"


def set_profile(jid: str) -> None:
    """Point ``DATA_DIR`` at the active profile's data directory."""
    global DATA_DIR
    from stanza_im.include import constants
    constants.set_active_profile(jid)
    DATA_DIR = constants.profile_data_dir()


def path() -> str:
    return os.path.join(DATA_DIR, _FILE)


def _read() -> dict | None:
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _account_matches(data, account: str | None) -> bool:
    if account is None or not isinstance(data, dict):
        return True
    stored = data.get("account")
    return not (isinstance(stored, str) and stored and stored != account)


def load_cursor(account: str | None = None) -> dict:
    """Return ``{"archive_id", "ts", "migrated"}`` for *account*."""
    data = _read()
    if not _account_matches(data, account):
        return {}
    mam = data.get("mam") if isinstance(data, dict) else None
    if not isinstance(mam, dict):
        return {}
    return {
        "archive_id": str(mam.get("archive_id") or ""),
        "ts": str(mam.get("ts") or ""),
        "migrated": bool(mam.get("migrated")),
    }


def save_cursor(*, archive_id: str = "", ts: str = "", migrated: bool = True,
                account: str = "") -> None:
    """Persist the account cursor, preserving any unrelated state keys."""
    payload = _read() or {}
    if account:
        payload["account"] = str(account)
    payload["mam"] = {
        "archive_id": str(archive_id or ""),
        "ts": str(ts or ""),
        "migrated": bool(migrated),
    }
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path())
        os.chmod(path(), 0o600)
    except OSError as exc:
        logger.warning("Could not save %s: %s", path(), exc)


def clear() -> None:
    """Forget the account cursor (used by diagnostics/tests)."""
    try:
        os.remove(path())
    except OSError:
        pass
