"""Per-profile set of explicitly added server JIDs.

A server JID (no localpart) is not an ordinary contact: the user adds it
explicitly, it is shown in the virtual ``Server`` roster group, and a background
``disco#info`` probe decides whether it is actually a gateway transport.  The
classification is cached here so the row survives a restart and a gateway never
reappears as a normal server row.

Stored as a JSON list of JIDs at
``$XDG_DATA_HOME/stanza-im/<jid>/servers.json``.
"""
from __future__ import annotations

import json
import logging
import os

from stanza_im.include.constants import DATA_DIR

logger = logging.getLogger("stanza_im.servers")

_FILE = "servers.json"


def set_profile(jid: str) -> None:
    """Point ``DATA_DIR`` at the active profile's data directory."""
    global DATA_DIR
    from stanza_im.include import constants
    constants.set_active_profile(jid)
    DATA_DIR = constants.profile_data_dir()


def path() -> str:
    return os.path.join(DATA_DIR, _FILE)


def load() -> set[str]:
    """Return the persisted server JIDs (empty set on any problem)."""
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return {str(jid) for jid in data if jid}
        if isinstance(data, dict):  # tolerate an object form
            return {str(jid) for jid in data if jid}
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Could not read %s: %s", path(), exc)
    return set()


def save(jids) -> None:
    """Persist the server JID set (atomically, 0600)."""
    clean = sorted({str(jid) for jid in (jids or []) if jid})
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path())
        os.chmod(path(), 0o600)
    except OSError as exc:
        logger.warning("Could not save %s: %s", path(), exc)
