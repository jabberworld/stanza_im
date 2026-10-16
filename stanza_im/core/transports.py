"""Per-profile set of roster JIDs classified as gateway transports.

The Transports tab shows the roster's server JIDs whose ``disco#info``
identity is a gateway, and such a JID is filtered out of the ordinary
Contacts roster.  Classification needs a live disco round-trip, so the result
is cached here (per profile) and read back at login **before** the roster is
rendered — otherwise a gateway flashes in the Contacts roster until the probe
answers (and stays there the whole time on a slow or offline login).

Stored as a JSON list of JIDs at
``$XDG_DATA_HOME/stanza-im/<jid>/transports.json``.
"""
from __future__ import annotations

import json
import logging
import os

from stanza_im.include.constants import DATA_DIR

logger = logging.getLogger("stanza_im.transports")

_FILE = "transports.json"


def set_profile(jid: str) -> None:
    """Point ``DATA_DIR`` at the active profile's data directory."""
    global DATA_DIR
    from stanza_im.include import constants
    constants.set_active_profile(jid)
    DATA_DIR = constants.profile_data_dir()


def path() -> str:
    return os.path.join(DATA_DIR, _FILE)


def load() -> set[str]:
    """Return the persisted transport JIDs (empty set on any problem)."""
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
    """Persist the transport JID set (atomically, 0600)."""
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
