"""XEP-0353 Jingle Message Initiation — a shared, application-agnostic helper.

A ``<propose>``/``<proceed>``/``<reject>``/``<retract>``/``<accept>`` message
carries the application ``<description/>`` elements of the *upcoming* Jingle
session, so several application types (RTP calls, the SVG whiteboard) can share
one implementation.  This module builds and parses the messages; the caller owns
the state machine.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

NS_JINGLE_MSG = "urn:xmpp:jingle-message:0"

#: The JMI actions, in match order.
ACTIONS = ("propose", "proceed", "reject", "retract", "accept")


def _q(ns: str, tag: str) -> str:
    return "{%s}%s" % (ns, tag)


def action_of(msg) -> str:
    """The JMI action of *msg* ("" when it is not a JMI message)."""
    for action in ACTIONS:
        if msg.xml.find(_q(NS_JINGLE_MSG, action)) is not None:
            return action
    return ""


def action_element(msg) -> ET.Element | None:
    """The ``<propose/>``/``<proceed/>``/… element of *msg* (or ``None``)."""
    action = action_of(msg)
    if not action:
        return None
    return msg.xml.find(_q(NS_JINGLE_MSG, action))


def description_ns(msg) -> str:
    """The namespace of the first ``<description/>`` in a ``<propose/>``."""
    element = msg.xml.find(_q(NS_JINGLE_MSG, "propose"))
    if element is None:
        return ""
    for child in element:
        tag = child.tag
        if tag.startswith("{") and tag.endswith("}description"):
            return tag[1:tag.index("}")]
    return ""


def build(client, action: str, to_jid: str, sid: str,
          descriptions=()) -> object:
    """Build a XEP-0353 message (the caller sends it).

    *descriptions* is a list of ``(namespace, attributes)`` pairs, one
    ``<description/>`` element each (empty for a response action).
    """
    msg = client.xmpp.Message()
    msg["to"] = to_jid
    msg["type"] = "chat"
    element = ET.SubElement(msg.xml, _q(NS_JINGLE_MSG, action))
    element.set("id", sid)
    for ns, attrs in descriptions:
        desc = ET.SubElement(element, _q(ns, "description"))
        for key, value in (attrs or {}).items():
            desc.set(key, str(value))
    # XEP-0353 §3 mandates the XEP-0334 <store/> hint on every JMI message.
    ET.SubElement(msg.xml, "{urn:xmpp:hints}store")
    return msg
