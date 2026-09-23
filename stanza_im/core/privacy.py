"""XEP-0016 Privacy Lists: parsing and building of ``jabber:iq:privacy``.

The wire format is handled directly with :mod:`xml.etree.ElementTree` because
slixmpp's ``xep_0016`` stanza has a bug in its ``presence-out`` accessors.
Items are plain dicts::

    {"type": "jid"|"group"|"subscription"|"",
     "value": str, "action": "allow"|"deny", "order": int,
     "message": bool, "iq": bool, "presence_in": bool, "presence_out": bool}

An item with none of the four stanza flags applies to all stanzas.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

NS_PRIVACY = "jabber:iq:privacy"

# XML tag -> item key, in display order.
STANZA_TAGS = (("message", "message"), ("iq", "iq"),
               ("presence-in", "presence_in"), ("presence-out", "presence_out"))


def parse_lists(xml) -> dict:
    """Return ``{"active", "default", "lists"}`` from a ``<query/>``."""
    result = {"active": "", "default": "", "lists": []}
    if xml is None:
        return result
    query = xml.find(f"{{{NS_PRIVACY}}}query")
    if query is None:
        query = xml if xml.tag == f"{{{NS_PRIVACY}}}query" else None
    if query is None:
        return result
    for child in query:
        if child.tag == f"{{{NS_PRIVACY}}}active":
            result["active"] = str(child.get("name") or "")
        elif child.tag == f"{{{NS_PRIVACY}}}default":
            result["default"] = str(child.get("name") or "")
        elif child.tag == f"{{{NS_PRIVACY}}}list":
            name = str(child.get("name") or "")
            if name and name not in result["lists"]:
                result["lists"].append(name)
    return result


def _parse_item(el) -> dict:
    item = {
        "type": str(el.get("type") or ""),
        "value": str(el.get("value") or ""),
        "action": str(el.get("action") or "deny"),
        "order": _order(el.get("order")),
        "message": False,
        "iq": False,
        "presence_in": False,
        "presence_out": False,
    }
    for tag, key in STANZA_TAGS:
        if el.find(f"{{{NS_PRIVACY}}}{tag}") is not None:
            item[key] = True
    return item


def _order(value) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def parse_list(xml, name: str = "") -> list[dict]:
    """Return the items of the ``<list name=…/>`` in *xml* (empty if absent)."""
    if xml is None:
        return []
    for lst in xml.iter(f"{{{NS_PRIVACY}}}list"):
        if name and str(lst.get("name") or "") != name:
            continue
        return [_parse_item(item) for item in lst
                if item.tag == f"{{{NS_PRIVACY}}}item"]
    return []


def _build_item(parent, item: dict) -> ET.Element:
    el = ET.SubElement(parent, f"{{{NS_PRIVACY}}}item")
    if item.get("type"):
        el.set("type", str(item["type"]))
    if item.get("value"):
        el.set("value", str(item["value"]))
    el.set("action", str(item.get("action") or "deny"))
    el.set("order", str(_order(item.get("order"))))
    for tag, key in STANZA_TAGS:
        if item.get(key):
            ET.SubElement(el, f"{{{NS_PRIVACY}}}{tag}")
    return el


def lists_query() -> ET.Element:
    """A ``<query/>`` requesting the list names / active / default."""
    return ET.Element(f"{{{NS_PRIVACY}}}query")


def list_query(name: str, items: list[dict]) -> ET.Element:
    """A ``<query/>`` fetching (no items) or setting a list."""
    query = ET.Element(f"{{{NS_PRIVACY}}}query")
    lst = ET.SubElement(query, f"{{{NS_PRIVACY}}}list")
    lst.set("name", name)
    for item in items:
        _build_item(lst, item)
    return query


def _named_query(tag: str, name: str) -> ET.Element:
    query = ET.Element(f"{{{NS_PRIVACY}}}query")
    element = ET.SubElement(query, f"{{{NS_PRIVACY}}}{tag}")
    if name:
        element.set("name", name)
    return query


def active_query(name: str) -> ET.Element:
    """A ``<query/>`` activating (or, with an empty name, deactivating) a list."""
    return _named_query("active", name)


def default_query(name: str) -> ET.Element:
    """A ``<query/>`` setting (or, with an empty name, clearing) the default."""
    return _named_query("default", name)


def sort_items(items: list[dict]) -> list[dict]:
    """Return *items* ordered by ascending ``order``."""
    return sorted(items, key=lambda item: _order(item.get("order")))


def next_order(items: list[dict]) -> int:
    """An order placing a new item before every existing one."""
    orders = [_order(item.get("order")) for item in items]
    return (min(orders) - 10) if orders else 100
