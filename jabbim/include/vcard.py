"""vCard (XEP-0054) parsing and building helpers.

Parsing walks the raw XML payload directly (same approach as
``avatars.parse_vcard_photo``) so it does not depend on slixmpp's
interface-registration details.  Building produces a slixmpp ``VCardTemp``
stanza ready for ``xep_0054.publish_vcard``.
"""
from __future__ import annotations

import base64

from jabbim.include.avatars import parse_vcard_photo

_NS = "vcard-temp"


def _t(element, *path) -> str:
    """Return the text of the first element found by walking *path*."""
    try:
        node = element
        for tag in path:
            nodes = [c for c in node.iter() if c.tag == f"{{{_NS}}}{tag}"]
            if not nodes:
                nodes = [c for c in node.iter()
                         if str(c.tag).rsplit("}", 1)[-1].upper() == tag.upper()]
            if not nodes:
                return ""
            node = nodes[0]
        return (node.text or "").strip()
    except Exception:
        return ""


def parse_vcard(iq) -> dict:
    """Parse a vCard IQ into a plain dict.

    Returned keys: fn, nickname, email, url, bday, title, role, org,
    orgunit, tel, jid (from the IQ ``from``) and photo (raw bytes or None).
    Missing fields are empty strings.
    """
    card = {
        "jid": str(iq.get("from", "")),
        "fn": "",
        "nickname": "",
        "email": "",
        "url": "",
        "bday": "",
        "title": "",
        "role": "",
        "org": "",
        "orgunit": "",
        "tel": "",
        "street": "",
        "locality": "",
        "region": "",
        "pcode": "",
        "country": "",
        "description": "",
        "photo": None,
    }
    try:
        payload = iq.get_payload()
    except Exception:
        return card
    if not payload:
        return card
    if not isinstance(payload, list):
        payload = [payload]

    for root in payload:
        card["fn"] = _t(root, "FN") or card["fn"]
        card["nickname"] = _t(root, "NICKNAME") or card["nickname"]
        card["email"] = _t(root, "EMAIL", "USERID") or card["email"]
        card["url"] = _t(root, "URL") or card["url"]
        card["bday"] = _t(root, "BDAY") or card["bday"]
        card["title"] = _t(root, "TITLE") or card["title"]
        card["role"] = _t(root, "ROLE") or card["role"]
        card["org"] = _t(root, "ORG", "ORGNAME") or card["org"]
        card["orgunit"] = _t(root, "ORG", "ORGUNIT") or card["orgunit"]
        card["tel"] = _t(root, "TEL", "NUMBER") or card["tel"]
        card["street"] = _t(root, "ADR", "STREET") or card["street"]
        card["locality"] = _t(root, "ADR", "LOCALITY") or card["locality"]
        card["region"] = _t(root, "ADR", "REGION") or card["region"]
        card["pcode"] = _t(root, "ADR", "PCODE") or card["pcode"]
        card["country"] = _t(root, "ADR", "CTRY") or card["country"]
        card["description"] = (_t(root, "DESC")
                                or _t(root, "DESCRIPTION")
                                or card["description"])
        if card.get("photo") is None:
            card["photo"] = parse_vcard_photo(iq)
        break
    return card


def build_vcard(plugin, card: dict):
    """Build a slixmpp ``VCardTemp`` stanza from a :func:`parse_vcard` dict.

    *photo* may be raw bytes or a base64 ``str``; it becomes a PHOTO/BINVAL
    element with ``TYPE`` ``image/png``.
    """
    vcard = plugin.make_vcard()
    for key, interface in (
        ("fn", "FN"),
        ("nickname", "NICKNAME"),
        ("bday", "BDAY"),
        ("title", "TITLE"),
        ("role", "ROLE"),
        ("url", "URL"),
        ("description", "DESC"),
    ):
        value = (card.get(key) or "").strip()
        if value:
            vcard[interface] = value
    email = (card.get("email") or "").strip()
    if email:
        vcard["EMAIL"]["USERID"] = email
        vcard["EMAIL"]["INTERNET"] = True
    org = (card.get("org") or "").strip()
    orgunit = (card.get("orgunit") or "").strip()
    if org or orgunit:
        if org:
            vcard["ORG"]["ORGNAME"] = org
        if orgunit:
            vcard["ORG"]["ORGUNIT"] = orgunit
    address = {
        "street": "STREET",
        "locality": "LOCALITY",
        "region": "REGION",
        "pcode": "PCODE",
        "country": "CTRY",
    }
    for key, interface in address.items():
        value = (card.get(key) or "").strip()
        if value:
            vcard["ADR"][interface] = value
    photo = card.get("photo")
    if photo:
        if isinstance(photo, str):
            photo = base64.b64decode(photo)
        if isinstance(photo, (bytes, bytearray)):
            vcard["PHOTO"]["TYPE"] = "image/png"
            vcard["PHOTO"]["BINVAL"] = bytes(photo)
    return vcard
