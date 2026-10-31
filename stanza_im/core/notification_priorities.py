"""Per-contact notification priority (local store + private PEP node).

A contact's notification priority is ``high`` or ``low``; the default
(``normal``) is the absence of an entry.  The map is kept per profile in
``notification_priorities.json`` and mirrored to a private PEP node on the
account (``urn:xmpp:notification-priority:0``, access model ``whitelist`` — only
the owner can read it) so it follows the user across clients.  The node payload
is::

    <notification-priorities xmlns='urn:xmpp:notification-priority:0'>
      <contact jid='alice@example.com' priority='high'/>
      ...
    </notification-priorities>

On login the server values are merged in (the server wins for a contact that
has a stored value); a change made in the client publishes the whole set.
"""
from __future__ import annotations

import json
import logging
import os

from slixmpp.exceptions import IqError

from stanza_im.include.constants import DATA_DIR

logger = logging.getLogger("stanza_im.priority")

NS = "urn:xmpp:notification-priority:0"
NODE = "urn:xmpp:notification-priority:0"

#: Stored (non-default) priorities.
VALID = ("high", "low")

_FILE = "notification_priorities.json"


def set_profile(jid: str) -> None:
    """Point ``DATA_DIR`` at the active profile's data directory."""
    global DATA_DIR
    from stanza_im.include import constants
    constants.set_active_profile(jid)
    DATA_DIR = constants.profile_data_dir()


def path() -> str:
    return os.path.join(DATA_DIR, _FILE)


def _load() -> dict[str, str]:
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()
                    if str(v) in VALID}
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Could not read %s: %s", path(), exc)
    return {}


def save(data: dict) -> None:
    clean = {str(jid): str(priority) for jid, priority in (data or {}).items()
             if jid and str(priority) in VALID}
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path())
        os.chmod(path(), 0o600)
    except OSError as exc:
        logger.warning("Could not save %s: %s", path(), exc)


def all() -> dict[str, str]:
    """Return the whole ``{jid: "high"|"low"}`` map."""
    return _load()


def get(jid: str) -> str:
    """Return the stored priority for *jid* ("" = normal/default)."""
    return _load().get(str(jid), "")


def set(jid: str, priority: str) -> None:
    """Set (or clear, for an empty/normal value) *jid*'s priority."""
    jid = str(jid or "").strip()
    if not jid:
        return
    data = _load()
    if str(priority) in VALID:
        data[jid] = str(priority)
    else:
        data.pop(jid, None)
    save(data)


def set_many(mapping: dict[str, str]) -> None:
    """Apply several ``{jid: priority}`` entries in one write."""
    data = _load()
    for jid, priority in (mapping or {}).items():
        jid = str(jid or "").strip()
        if not jid:
            continue
        if str(priority) in VALID:
            data[jid] = str(priority)
        else:
            data.pop(jid, None)
    save(data)


# ── server-side (private PEP node) ────────────────────────────────

def build_payload(entries: list[dict]) -> "object":
    from xml.etree import ElementTree as ET
    root = ET.Element(f"{{{NS}}}notification-priorities")
    for entry in entries:
        jid = str(entry.get("jid", ""))
        priority = str(entry.get("priority", ""))
        if not jid or priority not in VALID:
            continue
        el = ET.SubElement(root, f"{{{NS}}}contact")
        el.set("jid", jid)
        el.set("priority", priority)
    return root


def parse_payload(xml) -> list[dict]:
    entries: list[dict] = []
    if xml is None:
        return entries
    for el in xml.iter(f"{{{NS}}}contact"):
        jid = str(el.get("jid") or "")
        priority = str(el.get("priority") or "")
        if jid and priority in VALID:
            entries.append({"jid": jid, "priority": priority})
    return entries


async def fetch(client) -> list[dict] | None:
    """Fetch the priority entries from the account's private node.

    ``[]`` means the node does not exist yet (a normal first login);
    ``None`` means the request itself failed and the local state must not be
    treated as the complete server state.
    """
    try:
        iq = await client.xmpp["xep_0060"].get_items(client.jid_str, NODE)
    except IqError as exc:
        condition = str(getattr(exc, "condition", "") or "")
        if condition == "item-not-found":
            return []
        logger.debug("Notification priorities fetch failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Notification priorities fetch failed: %s", exc)
        return None
    try:
        items = iq["pubsub"]["items"]
        for item in items:
            payload = item["payload"]
            if (payload is not None
                    and payload.tag == f"{{{NS}}}notification-priorities"):
                return parse_payload(payload)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Notification priorities payload parse failed: %s", exc)
        return None
    return []


async def publish(client, entries: list[dict]) -> bool:
    """Publish the priority entries to the account's private node."""
    from stanza_im.core import private_pep
    return await private_pep.publish(client, NODE, build_payload(entries))
