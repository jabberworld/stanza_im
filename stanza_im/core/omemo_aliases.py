"""Server-side OMEMO device names/aliases (a private PEP node).

Device names the user assigns are useful on every one of their clients, so they
are mirrored to a private PEP node on the account
(``urn:xmpp:omemo:aliases:0``, access model ``whitelist`` — only the owner can
read it).  The node payload is::

    <omemo-aliases xmlns='urn:xmpp:omemo:aliases:0'>
      <device jid='alice@example.com' id='123' alias='Laptop' last_seen='...'/>
      ...
    </omemo-aliases>

The local store remains the source of truth; the node is merged in on login
(local entries win).
"""
from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

logger = logging.getLogger("stanza_im.omemo")

NS = "urn:xmpp:omemo:aliases:0"
NODE = "urn:xmpp:omemo:aliases:0"


def build_payload(entries: list[dict]) -> ET.Element:
    root = ET.Element(f"{{{NS}}}omemo-aliases")
    for entry in entries:
        el = ET.SubElement(root, f"{{{NS}}}device")
        el.set("jid", str(entry.get("jid", "")))
        el.set("id", str(entry.get("id", "")))
        if entry.get("alias"):
            el.set("alias", str(entry["alias"]))
        if entry.get("last_seen"):
            el.set("last_seen", str(entry["last_seen"]))
    return root


def parse_payload(xml) -> list[dict]:
    entries: list[dict] = []
    if xml is None:
        return entries
    for el in xml.iter(f"{{{NS}}}device"):
        entries.append({
            "jid": str(el.get("jid") or ""),
            "id": str(el.get("id") or ""),
            "alias": str(el.get("alias") or ""),
            "last_seen": str(el.get("last_seen") or ""),
        })
    return entries


async def fetch(client) -> list[dict]:
    """Fetch the alias entries from the account's private node."""
    try:
        iq = await client.xmpp["xep_0060"].get_items(client.jid_str, NODE)
    except Exception as exc:  # noqa: BLE001
        logger.debug("OMEMO aliases fetch failed: %s", exc)
        return []
    items = iq["pubsub"]["items"]
    for item in items:
        payload = item["payload"]
        for child in payload:
            if child.tag == f"{{{NS}}}omemo-aliases":
                return parse_payload(child)
    return []


async def publish(client, entries: list[dict]) -> bool:
    """Publish the alias entries to the account's private node."""
    payload = build_payload(entries)
    try:
        await client.xmpp["xep_0060"].publish(
            client.jid_str, NODE, id="current", payload=payload,
            options={"pubsub#access_model": "whitelist",
                     "pubsub#persist_items": "true",
                     "pubsub#max_items": "1"})
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("OMEMO aliases publish failed: %s", exc)
        return False
