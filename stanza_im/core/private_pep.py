"""Publish one item to a private PEP node (XEP-0060/XEP-0163).

slixmpp's ``xep_0060.publish`` expects a data-form object in ``options``; a
plain dict is appended to the XML and raises a ``TypeError``.  The private
nodes used by Stanza IM build the IQ directly so the publish options are
always the XML form the server expects.
"""
from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

logger = logging.getLogger("stanza_im.pep")

NS_PUBSUB = "http://jabber.org/protocol/pubsub"
NS_DATA = "jabber:x:data"
FORM_TYPE = "http://jabber.org/protocol/pubsub#publish-options"


def build_publish_iq(client, node: str, payload: ET.Element,
                     item_id: str = "current", *,
                     access_model: str = "whitelist",
                     max_items: str = "1"):
    """Build the ``pubsub/publish`` IQ (not sent), used by tests too."""
    iq = client.xmpp.Iq()
    iq["type"] = "set"
    iq["to"] = ""
    pubsub = ET.SubElement(iq.xml, "{%s}pubsub" % NS_PUBSUB)
    publish = ET.SubElement(pubsub, "{%s}publish" % NS_PUBSUB)
    publish.set("node", node)
    item = ET.SubElement(publish, "{%s}item" % NS_PUBSUB)
    if item_id:
        item.set("id", item_id)
    item.append(payload)

    options = ET.SubElement(pubsub, "{%s}publish-options" % NS_PUBSUB)
    form = ET.SubElement(options, "{%s}x" % NS_DATA)
    form.set("type", "submit")
    for var, value, field_type in (
        ("FORM_TYPE", FORM_TYPE, "hidden"),
        ("pubsub#persist_items", "true", None),
        ("pubsub#max_items", str(max_items), None),
        ("pubsub#send_last_published_item", "never", None),
        ("pubsub#access_model", access_model, None),
    ):
        field = ET.SubElement(form, "{%s}field" % NS_DATA)
        field.set("var", var)
        if field_type:
            field.set("type", field_type)
        ET.SubElement(field, "{%s}value" % NS_DATA).text = value
    return iq


async def publish(client, node: str, payload: ET.Element,
                  item_id: str = "current") -> bool:
    """Publish *payload* to the private PEP *node*.

    The access model is ``whitelist`` so only the owner can read the node.
    A failure is logged (the caller may still ignore the boolean) and never
    raises into the UI.
    """
    try:
        await build_publish_iq(client, node, payload, item_id).send(timeout=10)
        return True
    except Exception as exc:  # noqa: BLE001 - best-effort PEP
        logger.warning("PEP publish to %s failed: %s", node, exc)
        return False
