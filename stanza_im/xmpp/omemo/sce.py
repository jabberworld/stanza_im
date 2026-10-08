"""Stanza Content Encryption (XEP-0420) envelope handling.

``slixmpp-omemo`` 2.2.0 implements the legacy OMEMO 0.3 message format but not
the SCE-based ``urn:xmpp:omemo:2`` one (it raises ``NotImplementedError`` on
decrypt).  To support OMEMO 2 we build and parse the ``urn:xmpp:sce:1``
``<envelope/>`` ourselves and feed its serialized form to the underlying
``SessionManager`` as the twomemo plaintext.

Only the OMEMO SCE profile is implemented: a mandatory ``<rpad/>``, a
``<from/>`` affix and, for group chats, a ``<to/>`` affix (XEP-0384 §5.5.1).
"""
from __future__ import annotations

import secrets
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import fromstring as _safe_fromstring

SCE_NS = "urn:xmpp:sce:1"
_CLIENT_NS = "jabber:client"

_HINTS_NS = "urn:xmpp:hints"
_SID_NS = "urn:xmpp:sid:0"
_EME_NS = "urn:xmpp:eme:0"
_ADDRESSES_NS = "http://jabber.org/protocol/address"

_LEGACY_NS = "eu.siacs.conversations.axolotl"
_OMEMO2_NS = "urn:xmpp:omemo:2"

_RPAD_MIN = 100        # minimum envelope size target (chars of padding)
_RPAD_RANDOM = 200     # extra random padding (0..N), per XEP-0420


def _rpad() -> str:
    length = _RPAD_MIN + secrets.randbelow(_RPAD_RANDOM + 1)
    return secrets.token_urlsafe(length)[:length]


def is_forbidden_in_content(element: ET.Element) -> bool:
    """True for server-processed elements that MUST stay outside the envelope."""
    tag = element.tag
    if tag == f"{{{_SID_NS}}}stanza-id":
        return True
    if tag == f"{{{_ADDRESSES_NS}}}addresses":
        return True
    if tag == f"{{{_EME_NS}}}encryption":
        return True
    if tag.startswith(f"{{{_HINTS_NS}}}"):
        return True
    if tag.startswith(f"{{{_LEGACY_NS}}}"):
        return True
    if tag.startswith(f"{{{_OMEMO2_NS}}}"):
        return True
    return False


def collect_content(message_xml: ET.Element) -> list[ET.Element]:
    """Return the sensitive children of a ``<message>`` to encrypt."""
    return [child for child in list(message_xml)
            if not is_forbidden_in_content(child)]


def build_envelope(content: list[ET.Element], from_jid: str,
                   to_jid: str = "") -> ET.Element:
    """Build a ``urn:xmpp:sce:1`` ``<envelope/>`` around *content*."""
    envelope = ET.Element(f"{{{SCE_NS}}}envelope")
    content_elt = ET.SubElement(envelope, f"{{{SCE_NS}}}content")
    for child in content:
        content_elt.append(child)
    ET.SubElement(envelope, f"{{{SCE_NS}}}rpad").text = _rpad()
    from_elt = ET.SubElement(envelope, f"{{{SCE_NS}}}from")
    from_elt.set("jid", from_jid)
    if to_jid:
        to_elt = ET.SubElement(envelope, f"{{{SCE_NS}}}to")
        to_elt.set("jid", to_jid)
    return envelope


def serialize(envelope: ET.Element) -> bytes:
    """Serialize the envelope to UTF-8 bytes (no XML declaration)."""
    return ET.tostring(envelope, encoding="utf-8")


def parse(payload: bytes) -> ET.Element:
    """Parse a decrypted SCE payload into its ``<envelope/>`` element.

    Raises ``ValueError`` for malformed XML or a wrong root element.
    """
    try:
        envelope = _safe_fromstring(payload)
    except Exception as exc:  # noqa: BLE001 - defusedxml raises several types
        raise ValueError(f"Invalid SCE envelope: {exc}") from exc
    if envelope.tag != f"{{{SCE_NS}}}envelope":
        raise ValueError(f"Not an SCE envelope: {envelope.tag}")
    return envelope


def extract_content(envelope: ET.Element) -> list[ET.Element]:
    """Return the (allowed) extension elements inside ``<content/>``."""
    content_elt = envelope.find(f"{{{SCE_NS}}}content")
    if content_elt is None:
        return []
    return [child for child in list(content_elt)
            if not is_forbidden_in_content(child)]


def affix(envelope: ET.Element, name: str) -> ET.Element | None:
    """Return an affix child (``rpad``/``from``/``to``/``time``) or ``None``."""
    return envelope.find(f"{{{SCE_NS}}}{name}")
