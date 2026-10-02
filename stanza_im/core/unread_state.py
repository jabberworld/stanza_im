"""Persistent per-conversation read state (unread counters, mention counters
and the "last read" anchor).

The current payload (v2) is::

    {"account": "<jid>",
     "chats": {"<chat-key>": {"unread": N, "mentions": M,
                             "read_sid": "<stanza-id>", "read_ts": "<ts>",
                             "read_ref": "<message-id>"}}}

It is stored as JSON at ``$XDG_DATA_HOME/stanza-im/unread.json`` so roster
badges, tray blinking and the read anchor survive a restart.

The **chat-key** identifies a conversation the way the UI keys its chat tabs:
a bare JID for 1:1 chats and for MUC private messages (the real JID when the
room reveals it, otherwise ``room/nick``), and the bare room JID for a
conference.

* ``unread`` — incoming messages since the conversation was last read.
* ``mentions`` — the subset of those that mention our own nickname (MUC).
* ``read_sid`` — the last XEP-0490 stanza-id we published for the chat; it is
  seeded into the client on startup so the MDS catch-up cannot clear messages
  that arrived after our own last displayed point.
* ``read_ref`` / ``read_ts`` — the last message we actually read; an
  unread conversation is restored from this anchor.

Two legacy layouts are still read: ``{"<jid>": {"count": N, "displayed":
"<sid>"}}`` (v1) and ``{"<jid>": N}`` (v0).
"""
from __future__ import annotations

import json
import logging
import os

from stanza_im.include.constants import DATA_DIR

logger = logging.getLogger(__name__)

_FILE = "unread.json"

_FIELDS = ("unread", "mentions", "read_sid", "read_ts", "read_ref")


def path() -> str:
    return os.path.join(DATA_DIR, _FILE)


def blank() -> dict:
    """Return an empty read-state record."""
    return {"unread": 0, "mentions": 0, "read_sid": "", "read_ts": "",
            "read_ref": ""}


def _positive_int(value) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return count if count > 0 else 0


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _entry(value) -> dict:
    """Normalize one stored value (v2 record, v1 dict or a bare count)."""
    entry = blank()
    if isinstance(value, dict):
        entry["unread"] = _positive_int(value.get("unread", value.get("count")))
        entry["mentions"] = _positive_int(value.get("mentions"))
        entry["read_sid"] = _text(value.get("read_sid") or value.get("displayed"))
        entry["read_ts"] = _text(value.get("read_ts"))
        entry["read_ref"] = _text(value.get("read_ref"))
    else:
        entry["unread"] = _positive_int(value)
    return entry


def _is_empty(entry: dict) -> bool:
    return not any(entry.get(field) for field in _FIELDS)


def _compact(entry: dict) -> dict:
    return {field: entry[field] for field in _FIELDS if entry[field]}


def _parse_chats(data) -> dict[str, dict]:
    """Return ``{chat-key: record}`` from a decoded v2, v1 or v0 payload."""
    chats: dict[str, dict] = {}
    if not isinstance(data, dict):
        return chats
    nested = data.get("chats")
    if isinstance(nested, dict):
        items = nested.items()
    else:
        items = ((key, value) for key, value in data.items()
                 if key != "account")
    for key, value in items:
        key = _text(key)
        if not key:
            continue
        entry = _entry(value)
        if not _is_empty(entry):
            chats[key] = entry
    return chats


def _read() -> dict | None:
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Could not read %s: %s", path(), exc)
        return None


def _account_matches(data, account: str | None) -> bool:
    """Counters stored for another account must never be loaded."""
    if account is None or not isinstance(data, dict):
        return True
    stored = data.get("account")
    if isinstance(stored, str) and stored and stored != account:
        return False
    return True


def load_account() -> str:
    """Return the account JID the stored state belongs to ("" = legacy)."""
    data = _read()
    if isinstance(data, dict) and isinstance(data.get("account"), str):
        return data["account"]
    return ""


def load_chats(account: str | None = None) -> dict[str, dict]:
    """Return ``{chat-key: record}`` from disk (legacy layouts are read too).

    When *account* is given, state stored for a **different** account is
    ignored (the tray must not blink with another account's unread).
    """
    data = _read()
    if data is None or not _account_matches(data, account):
        return {}
    return _parse_chats(data)


def load_state(account: str | None = None
               ) -> tuple[dict[str, int], dict[str, str]]:
    """Return ``({chat-key: unread}, {chat-key: read-sid})`` from disk."""
    chats = load_chats(account)
    return ({key: entry["unread"] for key, entry in chats.items()},
            {key: entry["read_sid"] for key, entry in chats.items()
             if entry["read_sid"]})


def load(account: str | None = None) -> dict[str, int]:
    """Return the stored ``{chat-key: unread}`` (only positive entries)."""
    return {key: entry["unread"] for key, entry in load_chats(account).items()
            if entry["unread"]}


def _write(payload: dict) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path())
        os.chmod(path(), 0o600)
    except OSError as exc:
        logger.warning("Could not save %s: %s", path(), exc)


def save_chats(chats: dict, account: str = "") -> None:
    """Persist the per-conversation read state and the owning *account*."""
    clean: dict[str, dict] = {}
    for key, value in (chats or {}).items():
        key = _text(key)
        if not key:
            continue
        entry = _entry(value)
        if not _is_empty(entry):
            clean[key] = _compact(entry)
    payload: dict = {"chats": clean}
    if account:
        payload["account"] = str(account)
    _write(payload)


def save(counts: dict[str, int], displayed: dict[str, str] | None = None,
         account: str = "") -> None:
    """Legacy writer: persist counts plus their last-displayed sids."""
    displayed = displayed or {}
    chats: dict[str, dict] = {}
    for jid, value in (counts or {}).items():
        entry = blank()
        entry["unread"] = _positive_int(value)
        entry["read_sid"] = _text(displayed.get(jid))
        chats[jid] = entry
    save_chats(chats, account=account)
