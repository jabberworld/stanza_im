"""Persistent registry of JID → display name / roster groups / conference flag.

Kept separately from the live roster so contacts and rooms keep their last
known names and groups after being removed from (or never present in) the
roster.  This drives the history manager's contact list.

Stored as a JSON dict at ``$XDG_DATA_HOME/stanza-im/known_contacts.json``.
"""
from __future__ import annotations

import json
import logging
import os

from stanza_im.include.constants import DATA_DIR

logger = logging.getLogger(__name__)

_FILE = "known_contacts.json"


def path() -> str:
    return os.path.join(DATA_DIR, _FILE)


def _load() -> dict:
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", path(), exc)
    return {}


def save(data: dict) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path())
        os.chmod(path(), 0o600)
    except OSError as exc:
        logger.warning("Could not save %s: %s", path(), exc)


def _merge(entry: dict, name: str, groups: list[str],
           is_conference: bool) -> dict:
    if name:
        entry["name"] = name
    if groups is not None:
        entry["groups"] = [g for g in groups if g]
    entry["is_conference"] = bool(is_conference)
    return entry


def update(jid: str, name: str = "", groups: list[str] | None = None,
           is_conference: bool = False) -> None:
    """Upsert *jid* into the registry and persist the change."""
    data = _load()
    entry = data.get(jid)
    if entry is None:
        entry = {}
        data[jid] = entry
    _merge(entry, name, groups, is_conference)
    save(data)


def get(jid: str) -> dict:
    """Return the stored entry (``{"name", "groups", "is_conference"}``)
    or an empty dict when unknown."""
    data = _load()
    entry = data.get(jid)
    if not isinstance(entry, dict):
        return {}
    return {
        "name": entry.get("name", ""),
        "groups": list(entry.get("groups", []) or []),
        "is_conference": bool(entry.get("is_conference", False)),
    }


def all() -> dict[str, dict]:
    """Return the whole registry: ``{jid: {...}}``."""
    data = _load()
    return {
        jid: {
            "name": entry.get("name", ""),
            "groups": list(entry.get("groups", []) or []),
            "is_conference": bool(entry.get("is_conference", False)),
        }
        for jid, entry in data.items() if isinstance(entry, dict)
    }