"""XMPP client wrapper around slixmpp.

Provides a high-level async API and emits Qt-style callbacks that the UI
layer connects to.
"""
from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import logging
import io
import mimetypes
import os
import secrets
import platform
import ssl
import time
import uuid
from typing import Any, Callable
from xml.etree import ElementTree as ET

import slixmpp
from slixmpp.jid import JID

from stanza_im.include.enumerators import SHOW_ORDER
from stanza_im.include.vcard import parse_vcard as _parse_vcard, build_vcard as _build_vcard
from stanza_im.core.vcard_cache import VCardCache
from stanza_im.core import privacy, roster_cache
from stanza_im.include import constants
from stanza_im.include.constants import APP_NAME, VERSION
from stanza_im.i18n import current_language as _current_language
from stanza_im.xmpp import jingle as jingle_mod
from stanza_im.xmpp import jingle_rtp
from stanza_im.xmpp.jingle import JingleFileTransferManager
from stanza_im.xmpp.jingle_rtp import JingleRtpManager
from stanza_im.xmpp import muji as muji_mod
from stanza_im.xmpp.muji import MujiManager
from stanza_im.include import pep
from stanza_im.include import hats as hats_mod
from stanza_im.include import clients as clients_mod

logger = logging.getLogger(__name__)

_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
NS_REPLY = "urn:xmpp:reply:0"      # XEP-0461 Message Replies
NS_SID = "urn:xmpp:sid:0"          # XEP-0359 Unique and Stable Stanza IDs
NS_CARBONS = "urn:xmpp:carbons:2"  # XEP-0280 Message Carbons
NS_FORWARD = "urn:xmpp:forward:0"  # XEP-0297 Stanza Forwarding
NS_MDS = "urn:xmpp:mds:displayed:0"          # XEP-0490 Displayed Synchronization
NS_MDS_ASSIST = "urn:xmpp:mds:server-assist:0"
NS_PUBSUB = "http://jabber.org/protocol/pubsub"
NS_PUBSUB_EVENT = "http://jabber.org/protocol/pubsub#event"
NS_PUBSUB_OWNER = "http://jabber.org/protocol/pubsub#owner"
NS_DISCO_INFO = "http://jabber.org/protocol/disco#info"
NS_DISCO_ITEMS = "http://jabber.org/protocol/disco#items"
NS_DATA = "jabber:x:data"
NS_CORRECT = "urn:xmpp:message-correct:0"  # XEP-0308 Last Message Correction
NS_REACTIONS = "urn:xmpp:reactions:0"      # XEP-0444 Message Reactions
NS_OCCUPANT_ID = "urn:xmpp:occupant-id:0"  # XEP-0421 Occupant IDs
NS_UPLOAD = "urn:xmpp:http:upload:0"      # XEP-0363 HTTP File Upload
NS_MUC_INVITE = "jabber:x:conference"     # XEP-0249 Direct MUC Invitation
NS_ROSTERX = "http://jabber.org/protocol/rosterx"  # XEP-0144 Roster Item Exchange
NS_MUC_USER = "http://jabber.org/protocol/muc#user"  # XEP-0045 MUC user data
NS_TIME = "urn:xmpp:time"                 # XEP-0202 Entity Time
NS_STATS = "http://jabber.org/protocol/stats"  # XEP-0039 Statistics Gathering
NS_LAST = "jabber:iq:last"                # XEP-0012 Last Activity (uptime)
NS_RETRACT = "urn:xmpp:message-retract:1"   # XEP-0424 Message Retraction
NS_RETRACT_LEGACY = "urn:xmpp:message-retract:0"
NS_MODERATE = "urn:xmpp:message-moderate:1"  # XEP-0425 Moderated Message Retraction
NS_FALLBACK = "urn:xmpp:fallback:0"        # XEP-0428 Fallback Indication
NS_HINTS = "urn:xmpp:hints"                # XEP-0334 Message Processing Hints
NS_CAPTCHA = "urn:xmpp:captcha"            # XEP-0158 CAPTCHA Forms
NS_MEDIA = "urn:xmpp:media-element"        # XEP-0221 Data Forms Media Element
NS_OOB = "jabber:x:oob"                    # XEP-0066 Out-of-Band Data
NS_SIMS = "urn:xmpp:sims:1"                # XEP-0385 Stateless Inline Media Sharing
NS_REFERENCE = "urn:xmpp:reference:0"      # XEP-0372 References
NS_HASHES = "urn:xmpp:hashes:2"            # XEP-0300 Hash Functions
NS_FT = "urn:xmpp:jingle:apps:file-transfer:5"  # XEP-0234 file description
NS_CHAT_MARKERS = "urn:xmpp:chat-markers:0"     # XEP-0333 Chat Markers
NS_SCHEMA = "https://schema.org/"          # SIMS width/height extension
NS_AVATAR_DATA = "urn:xmpp:avatar:data"        # XEP-0084 User Avatar
NS_AVATAR_METADATA = "urn:xmpp:avatar:metadata"
NS_VCARD_UPDATE = "vcard-temp:x:update"        # XEP-0153 vCard-Based Avatars
NS_BOOKMARKS2 = "urn:xmpp:bookmarks:1"          # XEP-0402 PEP Native Bookmarks
NS_BOOKMARKS2_COMPAT = "urn:xmpp:bookmarks:1#compat"
NS_BOOKMARKS2_COMPAT_PEP = "urn:xmpp:bookmarks:1#compat-pep"
NS_CAPS = "http://jabber.org/protocol/caps"    # XEP-0115 Entity Capabilities
NS_PRIVACY = "jabber:iq:privacy"                # XEP-0016 Privacy Lists
NS_PRIVATE = "jabber:iq:private"                # XEP-0049 Private XML Storage
NS_ATTENTION = "urn:xmpp:attention:0"           # XEP-0224 Attention
NS_NOTES = "http://miranda-im.org/storage#notes"  # Miranda notes storage
NS_BLOCKING = "urn:xmpp:blocking"               # XEP-0191 Blocking Command
NS_REPORTING = "urn:xmpp:reporting:1"           # XEP-0377 Blocking Command Reports
_RETRACT_NAMESPACES = (NS_RETRACT, NS_RETRACT_LEGACY)

# XEP-0410 MUC self-ping: after this much silence from a room, verify that we
# are still an occupant; the check runs on this interval.
_MUC_SELF_PING_IDLE = 900.0
_MUC_SELF_PING_INTERVAL = 60.0
NS_PING = "urn:xmpp:ping"


class _UploadProgress:
    """Thread-safe upload fraction shared between the PUT worker thread and
    the polling coroutine (plain float writes/reads under the GIL)."""

    def __init__(self):
        self.pct = 0.0

    def update(self, value: float) -> None:
        self.pct = float(value)


def file_hashes_b64(path: str,
                    algos: tuple[str, ...] = ("sha-256", "sha-1")) -> dict:
    """Compute XEP-0300 base64 hashes of *path* (``{algo: base64}``)."""
    import base64 as _b64
    hashers = {}
    for algo in algos:
        try:
            hashers[algo] = hashlib.new(algo.replace("-", ""))
        except ValueError:
            continue
    if not hashers:
        return {}
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(128 * 1024)
                if not chunk:
                    break
                for hasher in hashers.values():
                    hasher.update(chunk)
    except OSError:
        return {}
    return {algo: _b64.b64encode(h.digest()).decode("ascii")
            for algo, h in hashers.items()}


def _replace_reference(stanza) -> str:
    """Return the ``id`` of a XEP-0308 ``<replace/>`` on *stanza* ("" if none)."""
    xml = getattr(stanza, "xml", None)
    if xml is None:
        return ""
    for el in xml:
        if el.tag == "{%s}replace" % NS_CORRECT:
            return str(el.get("id", ""))
    return ""


def _carbon_inner(msg, which: str):
    """Return the forwarded inner ``<message>`` element of a XEP-0280 carbon
    (``which`` is ``received`` or ``sent``), or ``None``."""
    xml = getattr(msg, "xml", None)
    if xml is None:
        return None
    for el in xml:
        if el.tag == "{%s}%s" % (NS_CARBONS, which):
            for fw in el:
                if fw.tag == "{%s}forwarded" % NS_FORWARD:
                    for child in fw:
                        if child.tag.rsplit("}", 1)[-1] == "message":
                            return child
    return None


_NS_ADDRESSES = "http://jabber.org/protocol/address"


def _replyto_address(msg) -> str:
    """Bare JID of a XEP-0033 ``<address type='replyto'/>`` on *msg* ("" none).

    Some servers relay PEP events from a service JID and carry the real sender
    in the extended stanza addressing; use it to attribute the event.
    """
    xml = getattr(msg, "xml", None)
    if xml is None:
        return ""
    for el in xml:
        if el.tag != "{%s}addresses" % _NS_ADDRESSES:
            continue
        for addr in el:
            if (addr.tag == "{%s}address" % _NS_ADDRESSES
                    and addr.get("type") == "replyto"):
                jid = str(addr.get("jid") or "").split("/")[0]
                if jid:
                    return jid
    return ""


def _reply_reference(stanza) -> tuple[str, str]:
    """Return ``(to, id)`` of a XEP-0461 ``<reply/>`` on *stanza* ("" if none)."""
    xml = getattr(stanza, "xml", None)
    if xml is None:
        return ("", "")
    for el in xml:
        if el.tag == "{%s}reply" % NS_REPLY:
            return (str(el.get("to", "")), str(el.get("id", "")))
    return ("", "")


def _retract_reference(stanza) -> str:
    """Return the target id of a XEP-0424 ``<retract/>`` on *stanza*, else ""."""
    xml = getattr(stanza, "xml", None)
    if xml is None:
        return ""
    for el in xml:
        if el.tag in ("{%s}retract" % NS_RETRACT,
                      "{%s}retract" % NS_RETRACT_LEGACY):
            return str(el.get("id", ""))
    return ""


def _retracted_tombstone(stanza) -> tuple[str, str]:
    """Return ``(id, stamp)`` of a XEP-0424 ``<retracted/>`` tombstone."""
    xml = getattr(stanza, "xml", None)
    if xml is None and hasattr(stanza, "iter"):
        xml = stanza
    if xml is None:
        return ("", "")
    for el in xml.iter():
        if el.tag in ("{%s}retracted" % NS_RETRACT,
                      "{%s}retracted" % NS_RETRACT_LEGACY):
            return (str(el.get("id", "")), str(el.get("stamp", "")))
    return ("", "")


def _moderation_info(stanza) -> dict:
    """Return XEP-0425 moderation details of a retraction/tombstone.

    ``{"moderated": bool, "by": str, "reason": str}`` — ``moderated`` is True
    when a ``<moderated/>`` element (XEP-0425) accompanies the XEP-0424
    ``<retract/>``/``<retracted/>``.  ``<reason/>`` may live in either the
    message-retract or the message-moderate namespace depending on direction.
    """
    empty = {"moderated": False, "by": "", "reason": ""}
    xml = getattr(stanza, "xml", None)
    if xml is None and hasattr(stanza, "iter"):
        xml = stanza
    if xml is None:
        return empty
    for el in xml.iter():
        if el.tag not in ("{%s}retract" % NS_RETRACT,
                          "{%s}retract" % NS_RETRACT_LEGACY,
                          "{%s}retracted" % NS_RETRACT,
                          "{%s}retracted" % NS_RETRACT_LEGACY):
            continue
        moderated = el.find("{%s}moderated" % NS_MODERATE)
        if moderated is None:
            continue
        reason = ""
        for child in el:
            if child.tag in ("{%s}reason" % NS_MODERATE,
                             "{%s}reason" % NS_RETRACT,
                             "{%s}reason" % NS_RETRACT_LEGACY,
                             "reason"):
                reason = str(child.text or "").strip()
                break
        return {
            "moderated": True,
            "by": str(moderated.get("by", "") or ""),
            "reason": reason,
        }
    return empty


def _origin_id(stanza) -> str:
    """Return the XEP-0359 ``origin-id`` value of *stanza*, else ""."""
    xml = getattr(stanza, "xml", None)
    if xml is None and hasattr(stanza, "iter"):
        xml = stanza
    if xml is None:
        return ""
    for el in xml.iter():
        if el.tag == "{%s}origin-id" % NS_SID:
            return str(el.get("id", ""))
    return ""


def _stanza_id(stanza, by: str) -> str:
    """Return the XEP-0359 ``stanza-id`` registered by *by*, else "".

    ``by`` is matched against the element's ``by`` attribute both verbatim
    and as the bare JID (some servers stamp the full JID).
    """
    xml = getattr(stanza, "xml", None)
    if xml is None and hasattr(stanza, "iter"):
        xml = stanza
    if xml is None:
        return ""
    for el in xml.iter():
        if el.tag != "{%s}stanza-id" % NS_SID:
            continue
        el_by = str(el.get("by", ""))
        if el_by and (el_by == by or el_by.split("/")[0] == by.split("/")[0]):
            return str(el.get("id", ""))
    return ""


def _bob_data_uris(root) -> dict[str, str]:
    """Map XEP-0231 ``cid`` values to ``data:`` URIs.

    A CAPTCHA image is often delivered as XEP-0231 Bits of Binary: the media
    URI references a ``cid:`` and the bytes sit in a sibling
    ``<data xmlns='urn:xmpp:bob'/>`` element.  Returning them as data URIs
    lets the form widget render the image without any network access.
    """
    uris: dict[str, str] = {}
    if root is None:
        return uris
    for data in root.iter("{urn:xmpp:bob}data"):
        cid = str(data.get("cid") or "")
        payload = (data.text or "").strip()
        if not cid or not payload:
            continue
        mime = str(data.get("type") or "application/octet-stream")
        uris[cid] = f"data:{mime};base64,{payload}"
    return uris


def _resolve_bob_media(xml, bob: dict[str, str]) -> None:
    """Rewrite ``cid:`` media URIs in *xml* to the matching data URIs."""
    if xml is None or not bob:
        return
    for uri in xml.iter("{urn:xmpp:media-element}uri"):
        value = str(uri.text or "").strip()
        if value.startswith("cid:") and value[4:] in bob:
            uri.text = bob[value[4:]]


def _avatar_data_from_iq(iq) -> bytes:
    """Return the XEP-0084 ``<data/>`` payload of an avatar items IQ."""
    xml = getattr(iq, "xml", None)
    if xml is None:
        return b""
    for data in xml.iter("{%s}data" % NS_AVATAR_DATA):
        text = (data.text or "").strip()
        if not text:
            continue
        try:
            return bytes(base64.b64decode(text))
        except (ValueError, TypeError):
            return b""
    return b""


def _build_bookmarks2_conference(nick: str, password: str, autojoin: bool,
                                 name: str) -> ET.Element:
    """Build a XEP-0402 ``<conference/>`` payload."""
    conf = ET.Element("{%s}conference" % NS_BOOKMARKS2)
    if name:
        conf.set("name", str(name))
    conf.set("autojoin", "true" if autojoin else "false")
    if nick:
        ET.SubElement(conf, "{%s}nick" % NS_BOOKMARKS2).text = str(nick)
    if password:
        ET.SubElement(conf, "{%s}password" % NS_BOOKMARKS2).text = str(password)
    return conf


def _bookmarks2_publish_options(x) -> None:
    """Fill the ``<x type='submit'/>`` publish-options of XEP-0402 §3.3."""
    fields = (
        ("FORM_TYPE",
         "http://jabber.org/protocol/pubsub#publish-options", "hidden"),
        ("pubsub#persist_items", "true", None),
        ("pubsub#max_items", "max", None),
        ("pubsub#send_last_published_item", "never", None),
        ("pubsub#access_model", "whitelist", None),
    )
    for var, value, field_type in fields:
        field = ET.SubElement(x, "{%s}field" % NS_DATA)
        field.set("var", var)
        if field_type:
            field.set("type", field_type)
        ET.SubElement(field, "{%s}value" % NS_DATA).text = value


def _parse_bookmarks2(xml) -> list[dict]:
    """Parse a XEP-0402 ``pubsub/items`` payload into bookmark dicts."""
    out: list[dict] = []
    if xml is None:
        return out
    for item in xml.iter("{%s}item" % NS_PUBSUB):
        room = str(item.get("id") or "")
        conf = item.find("{%s}conference" % NS_BOOKMARKS2)
        if not room or conf is None:
            continue
        out.append({
            "jid": room,
            "nick": str(conf.findtext("{%s}nick" % NS_BOOKMARKS2) or ""),
            "password": str(conf.findtext("{%s}password" % NS_BOOKMARKS2) or ""),
            "autojoin": conf.get("autojoin", "") in ("1", "true"),
            "name": str(conf.get("name") or ""),
        })
    return out


def _parse_notes(xml) -> list[dict]:
    """Parse a XEP-0049 notes ``storage`` payload into note dicts."""
    out: list[dict] = []
    if xml is None:
        return out
    for note in xml.iter("{%s}note" % NS_NOTES):
        out.append({
            "title": str(note.findtext("{%s}title" % NS_NOTES) or ""),
            "text": str(note.findtext("{%s}text" % NS_NOTES) or ""),
            "tags": str(note.get("tags") or ""),
        })
    return out


def muc_invite_from_message(msg) -> dict | None:
    """Parse a MUC invitation (XEP-0249 / XEP-0045 §7.8) from *msg*.

    Returns a dict with ``inviter`` (the inviter's JID, or "" when the room
    relayed the invitation without naming one), ``room``, ``password``,
    ``reason`` and ``mediated``, or ``None`` when the stanza carries no
    invitation.

    A direct XEP-0249 invitation names the inviter in the message ``from``;
    a mediated one is relayed by the room (``from`` is the room JID) and the
    real inviter sits in the XEP-0045
    ``<x xmlns='http://jabber.org/protocol/muc#user'><invite from='…'/></x>``.
    """
    xml = getattr(msg, "xml", None)
    if xml is None:
        return None
    conf = xml.find("{%s}x" % NS_MUC_INVITE)
    if conf is None or conf.get("jid") is None:
        return None
    frm = str(msg["from"])
    room = str(conf.get("jid", ""))
    password = str(conf.get("password", "") or "")
    reason = str(conf.get("reason", "") or "")
    inviter = ""
    mediated = False
    user = xml.find("{%s}x" % NS_MUC_USER)
    if user is not None:
        invite = user.find("{%s}invite" % NS_MUC_USER)
        if invite is not None:
            mediated = True
            inviter = str(invite.get("from", "") or "")
            invite_reason = invite.findtext("{%s}reason" % NS_MUC_USER)
            if invite_reason:
                reason = str(invite_reason)
    if not inviter:
        # A direct invitation names the inviter in `from`; a room relay whose
        # `from` is the room itself carries no inviter at all.
        inviter = "" if frm.split("/", 1)[0] == room else frm
    return {
        "inviter": inviter,
        "room": room,
        "password": password,
        "reason": reason,
        "mediated": mediated,
    }


def _is_muc_invite(msg) -> bool:
    """True when *msg* carries a MUC invitation in either shape."""
    xml = getattr(msg, "xml", None)
    if xml is None:
        return False
    if xml.find("{%s}x" % NS_MUC_INVITE) is not None:
        return True
    user = xml.find("{%s}x" % NS_MUC_USER)
    return (user is not None
            and user.find("{%s}invite" % NS_MUC_USER) is not None)


def _is_captcha_message(msg) -> bool:
    """True when *msg* carries a XEP-0158 ``<captcha/>`` challenge."""
    xml = getattr(msg, "xml", None)
    if xml is None:
        return False
    return xml.find("{%s}captcha" % NS_CAPTCHA) is not None


def _is_roster_exchange(msg) -> bool:
    """True when *msg* carries a XEP-0144 ``<x xmlns='…rosterx'/>``."""
    xml = getattr(msg, "xml", None)
    if xml is None:
        return False
    return xml.find("{%s}x" % NS_ROSTERX) is not None


def parse_roster_exchange(msg) -> list[dict]:
    """Parse a XEP-0144 ``<x/>`` into ``{action, jid, name, groups}`` rows.

    The ``action`` defaults to ``add`` per XEP-0144 §3.1; items without a JID
    are ignored.
    """
    xml = getattr(msg, "xml", None)
    if xml is None:
        return []
    root = xml.find("{%s}x" % NS_ROSTERX)
    if root is None:
        return []
    items: list[dict] = []
    for el in root.findall("{%s}item" % NS_ROSTERX):
        jid = str(el.get("jid") or "").strip()
        if not jid:
            continue
        action = str(el.get("action") or "add").strip().lower()
        if action not in ("add", "delete", "modify"):
            action = "add"
        groups = [str(g.text).strip()
                  for g in el.findall("{%s}group" % NS_ROSTERX)
                  if (g.text or "").strip()]
        items.append({"action": action, "jid": jid,
                      "name": str(el.get("name") or ""), "groups": groups})
    return items


def build_roster_exchange(items: list[dict]) -> ET.Element:
    """Build a XEP-0144 ``<x xmlns='…rosterx'/>`` payload."""
    root = ET.Element("{%s}x" % NS_ROSTERX)
    for entry in items:
        jid = str(entry.get("jid") or "").strip()
        if not jid:
            continue
        item = ET.SubElement(root, "{%s}item" % NS_ROSTERX)
        item.set("action", str(entry.get("action") or "add"))
        item.set("jid", jid)
        if entry.get("name"):
            item.set("name", str(entry["name"]))
        for group in entry.get("groups") or []:
            if str(group).strip():
                ET.SubElement(item, "{%s}group" % NS_ROSTERX).text = \
                    str(group).strip()
    return root


def _oob_url(msg) -> str:
    """Return the XEP-0066 ``<url/>`` of *msg* (or its captcha), else ""."""
    xml = getattr(msg, "xml", None)
    if xml is None:
        return ""
    for el in xml.iter():
        if el.tag == "{%s}url" % NS_OOB:
            return str(el.text or "")
    return ""


def _int_or_zero(text: str) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return 0


def _parse_file_element(file_el) -> dict:
    """Parse a XEP-0234/SIMS ``<file/>`` into a media dict."""
    media = {"name": "", "size": 0, "media_type": "", "width": 0, "height": 0,
             "hashes": {}}
    for child in file_el:
        tag = child.tag.rsplit("}", 1)[-1]
        text = (child.text or "").strip()
        if tag == "name":
            media["name"] = text
        elif tag == "size":
            media["size"] = _int_or_zero(text)
        elif tag == "media-type":
            media["media_type"] = text
        elif tag == "width":
            media["width"] = _int_or_zero(text)
        elif tag == "height":
            media["height"] = _int_or_zero(text)
        elif tag == "hash":
            algo = child.get("algo", "")
            if algo and text:
                media["hashes"][algo] = text
    return media


def _reference_url(msg) -> str:
    """The first XEP-0372 ``type='data'`` reference URI of *msg*, else ""."""
    xml = getattr(msg, "xml", None)
    if xml is None:
        return ""
    for el in xml.iter("{%s}reference" % NS_REFERENCE):
        if el.get("type") == "data" and el.get("uri"):
            return el.get("uri", "")
    return ""


def _fallback_body_range(msg, for_ns: str) -> tuple[int, int] | None:
    """The XEP-0428 fallback ``(start, end)`` body range for *for_ns*."""
    xml = getattr(msg, "xml", None)
    if xml is None:
        return None
    for fb in xml.iter("{%s}fallback" % NS_FALLBACK):
        if fb.get("for") != for_ns:
            continue
        body = fb.find("{%s}body" % NS_FALLBACK)
        if body is None:
            body = fb.find("body")
        if body is None:
            continue
        return (_int_or_zero(body.get("start", "0")),
                _int_or_zero(body.get("end", "0")))
    return None


def message_media(msg) -> dict | None:
    """Auxiliary media metadata carried by *msg*, or ``None``.

    Understands XEP-0385 SIMS (optionally wrapped in a XEP-0372 reference),
    a bare XEP-0372 ``type='data'`` reference and XEP-0066 OOB, plus the
    XEP-0428 fallback body range that a supporting client must not render.
    """
    xml = getattr(msg, "xml", None)
    if xml is None:
        return None
    sharing = next(xml.iter("{%s}media-sharing" % NS_SIMS), None)
    if sharing is not None:
        file_el = sharing.find("{%s}file" % NS_FT)
        media = _parse_file_element(file_el) if file_el is not None else {
            "name": "", "size": 0, "media_type": "", "width": 0, "height": 0,
            "hashes": {}}
        url = ""
        for ref in sharing.iter("{%s}reference" % NS_REFERENCE):
            if ref.get("uri"):
                url = ref.get("uri", "")
                break
        media["url"] = url or _oob_url(msg)
        media["hide_body"] = _fallback_body_range(msg, NS_SIMS)
        return media
    url = _reference_url(msg)
    if url:
        return {"name": "", "size": 0, "media_type": "", "width": 0,
                "height": 0, "hashes": {}, "url": url,
                "hide_body": _fallback_body_range(msg, NS_REFERENCE)}
    url = _oob_url(msg)
    if url:
        return {"name": "", "size": 0, "media_type": "", "width": 0,
                "height": 0, "hashes": {}, "url": url,
                "hide_body": _fallback_body_range(msg, NS_OOB)}
    return None


def message_markup(msg) -> dict | None:
    """XEP-0394 ``<markup/>`` carried by *msg*, or ``None``.

    Returns a JSON-serialisable dict of spans/blocks (see
    :mod:`stanza_im.xmpp.message_markup`); unknown elements are ignored.
    """
    xml = getattr(msg, "xml", None)
    if xml is None:
        return None
    try:
        from stanza_im.xmpp import message_markup as _markup
        return _markup.parse_message(xml)
    except Exception:  # noqa: BLE001
        logger.debug("Could not parse message markup", exc_info=True)
        return None


def muc_mediated_invite_from_message(msg) -> dict | None:
    """Parse a XEP-0045 §7.8 mediated invitation (room relay).

    The room is the message sender and the inviter sits in
    ``<x xmlns='http://jabber.org/protocol/muc#user'><invite from='…'/></x>``.
    Returns the same shape as :func:`muc_invite_from_message`, or ``None``.
    """
    xml = getattr(msg, "xml", None)
    if xml is None:
        return None
    user = xml.find("{%s}x" % NS_MUC_USER)
    if user is None:
        return None
    invite = user.find("{%s}invite" % NS_MUC_USER)
    if invite is None:
        return None
    return {
        "inviter": str(invite.get("from", "") or ""),
        "room": str(msg["from"]).split("/", 1)[0],
        "password": "",
        "reason": str(invite.findtext("{%s}reason" % NS_MUC_USER) or ""),
        "mediated": True,
    }


NS_MUC_REQUEST = "http://jabber.org/protocol/muc#request"


def _muc_voice_request(msg) -> dict | None:
    """Detect a XEP-0045 §7.13 voice request.

    Two shapes are recognised:

    * the standard one — a ``<message>`` (no ``type``) with a
      ``muc#request`` data form (``FORM_TYPE`` + ``muc#role``);
    * a legacy ``<x xmlns='…muc#user'><item affiliation='member'/></x>`` in a
      ``<message>`` without an ``<invite/>``.

    Returns ``{"room", "nick", "from"}`` or ``None``.
    """
    xml = getattr(msg, "xml", None)
    if xml is None:
        return None
    frm = str(msg["from"] or "")
    room = frm.split("/", 1)[0]
    nick = frm.split("/", 1)[1] if "/" in frm else ""

    # Data-form request (XEP-0045 §7.13).
    data = xml.find("{jabber:x:data}x")
    if data is not None:
        fields = {el.get("var"): el for el in data
                  if str(el.tag) == "{jabber:x:data}field"}
        fmt = fields.get("FORM_TYPE")
        if fmt is not None:
            value = next((c.text or "" for c in fmt
                          if str(c.tag) == "{jabber:x:data}value"), "")
            if value.strip() == NS_MUC_REQUEST:
                # The room is the sender's bare JID (``from = room/nick``);
                # ``to`` is our own address, not the room.
                return {"room": room, "nick": nick, "from": frm}

    # Legacy muc#user shape.
    user = xml.find("{%s}x" % NS_MUC_USER)
    if user is None or user.find("{%s}invite" % NS_MUC_USER) is not None:
        return None
    item = user.find("{%s}item" % NS_MUC_USER)
    if item is None or (item.get("affiliation") or "") != "member":
        return None
    return {"room": room, "nick": nick, "from": frm}


def _make_unique_id(xml) -> str:
    """Return a stable, per-stanza unique id used as the ``origin-id``.

    Prefers the message ``id`` attribute when available, otherwise derives a
    short value from the message content (hash of the XML serialisation).
    """
    aid = str(xml.get("id", "") or "")
    if aid:
        return aid
    try:
        return "%04x" % (hash(ET.tostring(xml)) & 0xFFFFFFFF)
    except Exception:
        return aid


def compose_reply_body(prefix: str) -> str:
    """Build a XEP-0393 quote body referencing a message, used as the
    XEP-0421 compatibility fallback when replying without a known stanza-id.

    *prefix* is the quoted ``"Sender wrote:\\n<text>"`` block; it is added
    verbatim as a ``> `` quoted block in the body so non-reply-aware clients
    still see the referenced message (XEP-0461 §4).
    """
    lines = ["> " + line if line else "> " for line in prefix.splitlines()]
    return "\n".join(lines) + "\n\n" if prefix else ""


def _message_subjects(stanza) -> list[tuple[str, str]]:
    """Return all ``<subject>`` variants as ``(lang, text)`` pairs.

    ``lang`` is ``""`` for the default (unspecified) subject. Matches any
    namespaced ``subject`` element (client or ``muc#user``) by local name.
    """
    if stanza is None:
        return []
    xml = getattr(stanza, "xml", None)
    if xml is None and hasattr(stanza, "iter"):
        xml = stanza
    if xml is None:
        return []
    items: list[tuple[str, str]] = []
    for el in xml.iter():
        tag = el.tag
        if not isinstance(tag, str):
            continue
        if tag.rsplit("}", 1)[-1] != "subject" or el.text is None:
            continue
        items.append((el.get(_XML_LANG, "") or "", str(el.text)))
    return items


class TLSOnlyUnavailable(Exception):
    """Raised when "TLS only" is selected but no _xmpps-client SRV record."""

    def __init__(self, domain: str):
        super().__init__(domain)
        self.domain = domain


def tls_flags(tls_mode: str, starttls_mode: str) -> dict:
    """Map the UI selectors to slixmpp connection flags.

    ``tls_mode``: ``direct`` | ``prefer`` | ``normal``.
    ``starttls_mode``: ``always`` | ``opportunistic`` | ``never``.
    """
    direct = tls_mode in ("direct", "prefer")
    if tls_mode == "direct":
        return {"enable_direct_tls": True, "enable_starttls": False,
                "enable_plaintext": False, "require_starttls": False}
    if starttls_mode == "never":
        return {"enable_direct_tls": direct, "enable_starttls": False,
                "enable_plaintext": True, "require_starttls": False}
    if starttls_mode == "opportunistic":
        return {"enable_direct_tls": direct, "enable_starttls": True,
                "enable_plaintext": True, "require_starttls": False}
    return {"enable_direct_tls": direct, "enable_starttls": True,
            "enable_plaintext": False, "require_starttls": True}


def _is_tls(sock) -> bool:
    return isinstance(sock, (ssl.SSLSocket, ssl.SSLObject))


def _name_parts(sequence) -> dict:
    """Flatten an ``ssl`` certificate name sequence into a field dict."""
    parts: dict = {}
    for rdn in sequence or ():
        for key, value in rdn:
            parts.setdefault(key, value)
    return parts


def _format_fingerprint(der: bytes) -> str:
    """Colon-separated uppercase SHA-256 fingerprint of DER bytes."""
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def _stream_feature_namespaces(features) -> set[str]:
    """Namespaces of the children of a ``<stream:features/>`` stanza.

    The element tags are ``{namespace}local``, so only the namespace part is
    kept (e.g. ``urn:xmpp:sm:3``), matching the server-feature keys.
    """
    try:
        return {child.tag.split("}", 1)[0].lstrip("{")
                for child in features.xml if isinstance(child.tag, str)}
    except Exception:
        return set()


def _block_items(xml) -> set[str]:
    """JIDs of the ``<item/>`` children of a ``urn:xmpp:blocking`` element.

    Works with the XML of a ``<blocklist>`` reply and of the ``<block>`` /
    ``<unblock>`` pushes alike; slixmpp changed the stanza's ``items`` shape
    between versions (a set of JIDs in 1.10, iterable items in 1.17), so the
    XML is read directly.
    """
    if xml is None:
        return set()
    return {str(el.get("jid") or "") for el in
            xml.iter("{%s}item" % NS_BLOCKING) if el.get("jid")}


def _caps_node(pres) -> str:
    """The XEP-0115 ``<c node=…/>`` of a presence stanza ("" when absent)."""
    xml = getattr(pres, "xml", None)
    if xml is None:
        return ""
    element = xml.find("{%s}c" % NS_CAPS)
    return str(element.get("node") or "") if element is not None else ""


def _occupant_id(pres) -> str:
    """The XEP-0421 ``<occupant-id id=…/>`` of a MUC presence ("" if absent)."""
    xml = getattr(pres, "xml", None)
    if xml is None:
        return ""
    element = xml.find("{%s}occupant-id" % NS_OCCUPANT_ID)
    return str(element.get("id") or "") if element is not None else ""


def _reactions(msg) -> tuple[str, list[str]] | None:
    """Parse a XEP-0444 ``<reactions/>`` child of *msg*.

    Returns ``(target_id, [emoji…])`` or ``None`` when the message carries no
    reactions.  An empty list means "remove all reactions".
    """
    xml = getattr(msg, "xml", None)
    if xml is None:
        return None
    element = xml.find("{%s}reactions" % NS_REACTIONS)
    if element is None:
        return None
    target_id = str(element.get("id") or "")
    emojis = [str(child.text or "").strip()
              for child in element.findall("{%s}reaction" % NS_REACTIONS)]
    emojis = [emoji for emoji in emojis if emoji]
    return target_id, emojis


def _upload_max_file_size(xml) -> int:
    """Return the XEP-0363 ``max-file-size`` from a disco#info form, else 0."""
    if xml is None:
        return 0
    for field in xml.iter("{%s}field" % NS_DATA):
        if str(field.get("var") or "") != "max-file-size":
            continue
        value = field.find("{%s}value" % NS_DATA)
        try:
            return int(str(value.text or "0").strip())
        except (TypeError, ValueError):
            return 0
    return 0


def _peer_certificate(sock) -> dict:
    """Extract the peer (server) TLS certificate of the live connection.

    ``getpeercert()`` needs a verifying context; when only the DER form is
    available (e.g. verification disabled) the fingerprint is still reported.
    """
    cert: dict = {}
    der = None
    try:
        der = sock.getpeercert(binary_form=True)
    except Exception:
        der = None
    try:
        cert = sock.getpeercert() or {}
    except Exception:
        cert = {}
    data = {
        "available": bool(cert or der),
        "verified": bool(cert),
        "subject_cn": "", "subject_o": "",
        "issuer_cn": "", "issuer_o": "",
        "not_before": cert.get("notBefore", "") or "",
        "not_after": cert.get("notAfter", "") or "",
        "serial": cert.get("serialNumber", "") or "",
        "sans": [value for (kind, value) in cert.get("subjectAltName", ())
                 if kind == "DNS"],
        "fingerprint": _format_fingerprint(der) if der else "",
        "expired": False,
        "days_left": None,
    }
    subject = _name_parts(cert.get("subject"))
    data["subject_cn"] = subject.get("commonName", "")
    data["subject_o"] = subject.get("organizationName", "")
    issuer = _name_parts(cert.get("issuer"))
    data["issuer_cn"] = issuer.get("commonName", "")
    data["issuer_o"] = issuer.get("organizationName", "")
    if data["not_after"]:
        try:
            end = ssl.cert_time_to_seconds(data["not_after"])
            remaining = end - time.time()
            data["expired"] = remaining < 0
            data["days_left"] = int(remaining // 86400)
        except Exception:
            pass
    return data


def filter_plus_mechs(mechanisms, tls_version: str, binding_types) -> set:
    """Drop ``*-PLUS`` SASL mechanisms when their channel binding is unusable.

    Over TLS 1.3 the binding requires ``tls-exporter``; on Python builds
    without it (e.g. 3.11) a SCRAM-PLUS attempt would send an invalid binding
    and the server would reject it, causing a transient auth error.  TLS 1.2
    uses ``tls-unique`` and is unaffected.
    """
    mechanisms = set(mechanisms)
    if tls_version == "TLSv1.3" and "tls-exporter" not in binding_types:
        return {m for m in mechanisms if not m.endswith("-PLUS")}
    return mechanisms


def order_tls_first(records: list, tls_services) -> list:
    """Sort SRV records so direct-TLS services come before the rest."""
    if not tls_services:
        return records
    return sorted(records, key=lambda rec: 0 if rec[0] in tls_services else 1)


class _StanzaXMPP(slixmpp.ClientXMPP):
    """ClientXMPP with deterministic TLS ordering and STARTTLS enforcement."""

    _tls_first = False
    _require_starttls = False
    _dns_hosts: dict = {}
    _connected_target: tuple | None = None

    def start_stream_handler(self, xml):
        super().start_stream_handler(xml)
        # Advertise the UI language on outgoing stanzas so servers localize
        # data forms (e.g. the MUC room configuration) to it, like Psi does.
        self.peer_default_lang = self.default_lang

    async def get_dns_records(self, domain, port=None):
        records = await super().get_dns_records(domain, port)
        # (address, port) -> SRV target host, so the actual endpoint can be
        # reported in the connection info.
        self._dns_hosts = {(rec[2], rec[3]): rec[1] for rec in records}
        if self._tls_first:
            records = order_tls_first(records, self.tls_services)
        return records

    async def _attempt_connection(self, host, port, tls, server_hostname):
        ok = await super()._attempt_connection(host, port, tls, server_hostname)
        if ok:
            target = self._dns_hosts.get((host, port), host)
            self._connected_target = (target, port, tls)
        return ok

    def _drop_unusable_plus_mechs(self, features) -> None:
        """Avoid a doomed SCRAM-*-PLUS attempt on TLS 1.3 without binding."""
        sock = getattr(self, "socket", None)
        if not _is_tls(sock) or 'mechanisms' not in features['features']:
            return
        try:
            version = sock.version() or ""
        except Exception:
            return
        mechs = filter_plus_mechs(features['mechanisms'], version,
                                  ssl.CHANNEL_BINDING_TYPES)
        if mechs != set(features['mechanisms']):
            logger.info("SASL: disabling -PLUS without channel binding "
                        "(TLS %s)", version)
            self.plugin['feature_mechanisms'].use_mechs = mechs

    async def _handle_stream_features(self, features):
        # Raw namespaces advertised in <stream:features>, for the "Server
        # info" dialog (SM, CSI, rosterver, Bind 2, SASL2, ...).
        self.stream_feature_ns = _stream_feature_namespaces(features)
        if (self._require_starttls and not _is_tls(getattr(self, "socket", None))
                and 'starttls' not in features['features']):
            logger.error(
                "STARTTLS is required but the server does not offer it")
            self.auto_reconnect = False
            self.event('tls_required')
            self.disconnect()
            return True
        self._drop_unusable_plus_mechs(features)
        return await super()._handle_stream_features(features)


class JabberClient:
    """High-level XMPP client built on top of slixmpp.ClientXMPP."""

    # XEP-0045 §17.1 status → resource priority used when the priority mode
    # is "status".  "chat" (free for chat) counts as available.
    _STATUS_PRIORITY = {"online": 50, "chat": 50, "away": 40, "xa": 30,
                        "dnd": 0}

    def __init__(self, jid: str, password: str, resource: str = "jabbim",
                 host: str = "", port: int = 0,
                 auto_join_conferences: bool = True,
                 send_chatstates: bool = True,
                 send_typing_notifications: bool = True,
                 send_activity_notifications: bool = True,
                 send_software: bool = True,
                 message_carbons: bool = True,
                 message_displayed_sync: bool = True,
                 allow_incoming_edits: bool = True,
                 allow_incoming_deletions: bool = True,
                 priority_mode: str = "status", priority: int = 50,
                 proxy_mode: str = "none", proxy_host: str = "",
                 proxy_port: int = 0,
                 keepalive: bool = True,
                 stream_management: bool = True,
                 csi: bool = True,
                 pep_sweep_interval: int = 0,
                 tls_mode: str = "prefer",
                 starttls_mode: str = "always",
                 omemo_enabled: bool = True,
                 omemo_btbv: bool = True):
        self.jid_str = str(jid).split("/")[0]
        self.resource = resource
        self.host = host
        self.port = int(port or 0)
        self.priority_mode = priority_mode
        self.priority = int(priority or 0)
        self.proxy_mode = proxy_mode
        self.proxy_host = proxy_host
        self.proxy_port = int(proxy_port or 0)
        # STUN/TURN settings (set by MainWindow from connection.*); used by
        # ice_servers() as a fallback when XEP-0215 yields nothing.
        self.stun_turn_mode = "auto"
        self.stun_turn_manual = ""
        self.keepalive = bool(keepalive)
        self.stream_management = bool(stream_management)
        self.csi = bool(csi)
        self.pep_sweep_interval = int(pep_sweep_interval or 0)
        self._client_active = True
        self._sm_resumed = False
        self._csi_enabled = False
        self._csi_handler_registered = bool(csi)
        self.tls_mode = tls_mode
        self.starttls_mode = starttls_mode
        self._discovered: dict | None = None
        self.auto_join_conferences = auto_join_conferences
        self.autojoin_rooms: set[str] = set()
        self.message_carbons = message_carbons
        self.message_displayed_sync = message_displayed_sync
        self.allow_incoming_edits = allow_incoming_edits
        self.allow_incoming_deletions = allow_incoming_deletions
        self._mds_last_sid: dict[str, str] = {}
        self._mds_last_id: dict[str, str] = {}
        self._mds_local: dict[str, str] = {}
        self._mds_server_assist = False
        self._mds_pubsub_options = False
        self._upload_service_cache: str | None = None
        self._upload_limit: int | None = None
        self._hats_support: dict[str, bool] = {}
        # XEP-0016/0191: cached account-domain features and blocked JIDs.
        self._server_features: set[str] | None = None
        self._blocked: set[str] = set()
        self._moderation_support: dict[str, bool] = {}
        self.send_typing_notifications = send_typing_notifications if send_chatstates else False
        self.send_activity_notifications = send_activity_notifications if send_chatstates else False
        self.send_chatstates = (self.send_typing_notifications
                                or self.send_activity_notifications)
        self.send_software = send_software
        self.omemo_enabled = bool(omemo_enabled)
        self.omemo_btbv = bool(omemo_btbv)
        self._full_jid = f"{self.jid_str}/{resource}"

        self.xmpp = _StanzaXMPP(jid, password, lang=_current_language())
        self.xmpp.requested_jid = JID(f"{self.jid_str}/{resource}")
        # Our own reconnect state (slixmpp has no ``auto_reconnect`` option).
        self._reconnect_enabled = True
        self._shutting_down = False
        self._reconnect_task: asyncio.Task | None = None
        self._reconnect_handle = None          # resumable QTimer-like handle
        self._reconnect_attempt = 0
        self._resume_deadline = 0.0            # monotonic; SM resume window
        # Messages queued while offline (sent on reconnect) — future feature;
        # currently a stub list so callers can rely on the hook being present.
        self._offline_outbox: list = []

        flags = tls_flags(tls_mode, starttls_mode)
        self.xmpp.enable_direct_tls = flags["enable_direct_tls"]
        self.xmpp.enable_starttls = flags["enable_starttls"]
        self.xmpp.enable_plaintext = flags["enable_plaintext"]
        self.xmpp._require_starttls = flags["require_starttls"]
        self.xmpp._tls_first = (tls_mode == "prefer")
        self.xmpp.whitespace_keepalive = self.keepalive
        self.xmpp.add_event_handler("tls_required", self._on_tls_required)

        # Register XEP plugins
        self.xmpp.register_plugin("xep_0054")  # vCard
        self.xmpp.register_plugin("xep_0045")  # MUC
        self.xmpp.register_plugin("xep_0066")  # OOB (file transfer)
        self.xmpp.register_plugin("xep_0085")  # Chat State Notifications
        self.xmpp.register_plugin("xep_0184")  # Message Receipts
        self.xmpp.register_plugin("xep_0224")  # Attention
        self.xmpp.register_plugin("xep_0048")  # Bookmarks
        self.xmpp.register_plugin("xep_0402")  # PEP Native Bookmarks
        self.xmpp.register_plugin("xep_0050")  # Ad-hoc Commands
        self.xmpp.register_plugin("xep_0004")  # Data Forms
        self.xmpp.register_plugin("xep_0077")  # In-Band Registration
        self.xmpp.register_plugin("xep_0055")  # Search
        self.xmpp.register_plugin("xep_0049")  # Private XML Storage
        self.xmpp.register_plugin("xep_0128")  # Service Discovery Extensions
        self.xmpp.register_plugin("xep_0030")  # Service Discovery
        self.xmpp.register_plugin("xep_0092", {
            "name": APP_NAME if send_software else "",
            "version": VERSION,
            "os": f"Python {platform.python_version()}" if send_software else "",
        })
        self.xmpp.register_plugin("xep_0199")  # Ping
        self.xmpp.register_plugin("xep_0202")  # Entity time
        # slixmpp's XEP-0202 responder is broken in 1.17 (it feeds a time-only
        # string to xep_0082.parse); replace it with a correct one.
        self._register_time_handler()
        self.xmpp.register_plugin("xep_0313")  # Message Archive Management (MAM)
        # xep_0313 pulls in xep_0059 (RSM) and xep_0297 (Forward) automatically
        self.xmpp.register_plugin("xep_0280")  # Message Carbons
        self.xmpp.register_plugin("xep_0163")  # PEP
        self.xmpp.register_plugin("xep_0060")  # PubSub
        self.xmpp.register_plugin("xep_0153")  # vCard-Based Avatars
        self.xmpp.register_plugin("xep_0084")  # User Avatar (PEP)
        self.xmpp.register_plugin("xep_0065")  # SOCKS5 Bytestreams (file proxy)
        for _block_plugin in ("xep_0191", "xep_0377"):  # blocking + reports
            try:
                self.xmpp.register_plugin(_block_plugin)
            except Exception:
                logger.warning("Could not register %s", _block_plugin)
        if self.stream_management:
            self.xmpp.register_plugin("xep_0198")  # Stream Management
        if self.csi:
            self.xmpp.register_plugin("xep_0352")  # Client State Indication

        # XEP-0380 Explicit Message Encryption (used by OMEMO messages).
        try:
            self.xmpp.register_plugin("xep_0380")
        except Exception:  # noqa: BLE001
            logger.warning("Could not register xep_0380")

        # XEP-0384 OMEMO — optional and detected at runtime.  The feature is
        # disabled (with a logged warning) when the stack is not installed.
        from stanza_im.xmpp.omemo import availability
        from stanza_im.xmpp.omemo.manager import NullOmemo, OmemoManager
        self.omemo = NullOmemo(self)
        availability.log_availability()
        if self.omemo_enabled and availability.AVAILABLE:
            try:
                from stanza_im.xmpp.omemo.plugin import OmemoPlugin  # noqa: F401
                storage_path = os.path.join(
                    constants.profile_data_dir(), "omemo.json")
                self.xmpp.register_plugin("xep_0384", {
                    "storage_path": storage_path,
                    "btbv": self.omemo_btbv,
                })
                self.omemo = OmemoManager(self)
                # Advertise both protocol versions (XEP-0115 picks these up).
                for _ns in (availability.LEGACY_NAMESPACE,
                            availability.OMEMO2_NAMESPACE):
                    self.xmpp["xep_0030"].add_feature(_ns)
                self.xmpp["xep_0030"].add_feature(
                    availability.OMEMO2_NAMESPACE + ":devices+notify")
            except ImportError as exc:
                # A partial install (e.g. a missing transitive dependency):
                # report it briefly, without a traceback.
                logger.warning("OMEMO could not be initialised: %s", exc)
                logger.debug("OMEMO import failed", exc_info=True)
                self.omemo = NullOmemo(self)
            except Exception:  # noqa: BLE001
                logger.warning("Could not initialise OMEMO", exc_info=True)
                self.omemo = NullOmemo(self)

        # XEP-0393 Message Styling (urn:xmpp:styling:0) — advertised in disco.
        self.xmpp["xep_0030"].add_feature("urn:xmpp:styling:0")
        # XEP-0461 Message Replies (urn:xmpp:reply:0) — advertised in disco.
        self.xmpp["xep_0030"].add_feature(NS_REPLY)
        # XEP-0424 Message Retraction (urn:xmpp:message-retract:1).
        self.xmpp["xep_0030"].add_feature(NS_RETRACT)
        # XEP-0490 Displayed Synchronization — advertise PEP notification support.
        self.xmpp["xep_0030"].add_feature(NS_MDS + "+notify")
        # XEP-0402 PEP Native Bookmarks — receive updates from other resources.
        self.xmpp["xep_0030"].add_feature(NS_BOOKMARKS2 + "+notify")
        # XEP-0144 Roster Item Exchange.
        self.xmpp["xep_0030"].add_feature(NS_ROSTERX)
        # XEP-0444 Message Reactions.
        self.xmpp["xep_0030"].add_feature(NS_REACTIONS)
        # Media sharing: XEP-0385 SIMS, XEP-0372 References, XEP-0300 hashes,
        # XEP-0066 OOB and XEP-0428 fallback, plus XEP-0333 chat markers.
        for _feature in (NS_SIMS, NS_REFERENCE, NS_HASHES, NS_OOB,
                         NS_FALLBACK, NS_CHAT_MARKERS):
            self.xmpp["xep_0030"].add_feature(_feature)
        # XEP-0191 blocklist pushes (XEP-0191 §5 carries the full list).
        self.xmpp.add_event_handler("blocked", self._on_blocked_push)
        self.xmpp.add_event_handler("unblocked", self._on_unblocked_push)
        # Jingle file transfer (XEP-0166/0234) with SOCKS5 (XEP-0260) and
        # In-Band (XEP-0261) transports — advertise support in disco.
        self.xmpp["xep_0030"].add_feature(jingle_mod.NS_JINGLE)
        self.xmpp["xep_0030"].add_feature(jingle_mod.NS_FT)
        self.xmpp["xep_0030"].add_feature(jingle_mod.NS_S5B)
        self.xmpp["xep_0030"].add_feature(jingle_mod.NS_IBB)

        # Extended presence PEP nodes (XEP-0080/0107/0108/0118) — advertise the
        # "+notify" variants so the server pushes contact updates.
        for _node in (pep.NS_MOOD, pep.NS_ACTIVITY, pep.NS_TUNE, pep.NS_GEOLOC):
            self.xmpp["xep_0030"].add_feature(_node + "+notify")

        # Jingle FT manager + incoming stanza handlers.
        self.file_transfer = JingleFileTransferManager(self)
        # Jingle RTP calls (XEP-0167/0176, DTLS) + XEP-0353 jingle-message.
        self.rtp_calls = JingleRtpManager(self)
        # Multiparty Jingle (Muji, XEP-0272).
        self.muji = MujiManager(self)
        # Call settings populated by MainWindow from config.
        self.call_devices: dict = {}
        self.call_auto_accept = False
        self._register_jingle_handlers()

        # Advertise our calling capabilities in disco (XEP-0115 picks these up).
        for _feature in (
                jingle_rtp.NS_RTP, jingle_rtp.NS_RTP_AUDIO,
                jingle_rtp.NS_RTP_VIDEO, jingle_rtp.NS_DTLS,
                jingle_rtp.NS_ICE, jingle_rtp.NS_JINGLE_MSG,
                jingle_rtp.NS_MUJI, "urn:xmpp:extdisco:2"):
            self.xmpp["xep_0030"].add_feature(_feature)

        # Client identity + caps branding (XEP-0030/0115).  Without a named
        # identity slixmpp advertises a nameless ``client/bot``; and clients
        # that keep a node→name table (Psi+, Gajim, Conversations) display the
        # caps node verbatim for unknown clients, so make it human-readable
        # instead of slixmpp's ``http://slixmpp.com/ver/…``.
        self.xmpp["xep_0030"].add_identity(
            category="client", itype="pc", name=APP_NAME)
        _caps = self.xmpp.plugin.get("xep_0115", None)
        if _caps is not None:
            _caps.caps_node = f"{APP_NAME} {VERSION}"
        _version = self.xmpp.plugin.get("xep_0092", None)
        if _version is not None:
            # slixmpp's plugin_init only honours the "name" config key; set
            # the version/os explicitly so XEP-0092 reports ours.
            _version.software_name = APP_NAME if send_software else ""
            _version.version = VERSION if send_software else ""
            _version.os = (f"Python {platform.python_version()}"
                           if send_software else "")

        if (self.proxy_mode == "socks5" and self.proxy_host
                and self.proxy_port):
            self._install_socks_proxy(self.proxy_host, self.proxy_port)

        # Callbacks: list of callables keyed by event name
        self._callbacks: dict[str, list[Callable]] = {}

        # Internal state
        self.roster: dict[str, Any] = {}  # {jid_str: roster_entry}
        self.contacts: dict[str, ContactInfo] = {}
        self.groupchats: dict[str, GroupChatInfo] = {}
        # Bare JIDs known to be MUC rooms (joined or seen), so the room's own
        # presence is never mistaken for a contact.
        self._known_rooms: set[str] = set()
        self.presences: dict[str, dict] = {}  # {full_jid: {show, status, ...}}
        # Extended presence (XEP-0080/0107/0108/0118): bare JID -> parsed kinds
        self.pep_data: dict[str, dict] = {}
        self._pep_fetched: set[str] = set()
        self._pep_inflight: set[str] = set()   # bare JIDs being PEP-fetched
        # Last presence-driven PEP pull per bare JID (monotonic timestamp).
        self._pep_last_refresh: dict[str, float] = {}
        self._pep_refresh_interval = 15.0      # s between pulls per contact
        # XEP-0163 subscriptions per contact: bare JID -> set of PEP nodes.
        self._pep_subscribed: dict[str, set[str]] = {}
        self._pep_subscribe_inflight: set[tuple[str, str]] = set()
        self._pep_subscribe_failed: dict[str, float] = {}  # bare -> last ts
        self._pep_subscribe_cooldown = 300.0               # s before a retry
        self._pep_sweep_task: asyncio.Task | None = None
        self._pep_sweep_paused = False
        # XEP-0115 features per full JID (for call-capability gating)
        self.contact_features: dict[str, set] = {}
        self._caps_inflight: set[str] = set()
        self._muc_subjects: dict[str, list[tuple[str, str]]] = {}
        self._mam_inflight: set[str] = set()  # JIDs with an active MAM query
        self._mam_cursors: dict[str, str] = {}
        self._vcard_cache = VCardCache()
        self._vcard_inflight: set[str] = set()
        # XEP-0237: cached roster items + version for the next login; loaded
        # lazily by ``_seed_roster_cache`` so a throwaway registration client
        # never touches the disk.
        self._roster_cache = None
        self._roster_save_handle = None
        self._muc_join_tasks: dict[str, asyncio.Task] = {}
        self._muc_last_activity: dict[str, float] = {}
        self._muc_self_ping_task: asyncio.Task | None = None
        self._muc_self_ping_busy: set[str] = set()
        # ids of sent XEP-0045 §7.13 voice requests awaiting a server reply
        self._voice_requests: set[str] = set()
        self._version_probed: set[str] = set()        # full JIDs (XEP-0092)
        self._muc_version_probed: set[tuple[str, str]] = set()
        # bare JID -> SHA-1 of the currently applied avatar (XEP-0084/0153/0398)
        self._avatar_ids: dict[str, str] = {}
        self._avatar_inflight: set[str] = set()
        # (jid, avatar_id) pairs whose fetch failed — don't retry this session.
        self._avatar_failed: set[tuple[str, str]] = set()
        # XEP-0402 server-side bookmark unification ("unified"/"dual"), cached
        self._bookmarks2_compat: str | None = None

        # Hook up slixmpp events
        self.xmpp.add_event_handler("session_start", self._on_session_start)
        self.xmpp.add_event_handler("disco_info", self._on_disco_info)
        self.xmpp.add_event_handler("message", self._on_message)
        # XEP-0224: slixmpp's ``xep_0224`` plugin raises an ``attention`` event
        # for an incoming ``<attention/>``.  The core ``message`` event only
        # fires for stanzas that carry a ``<body>``, so a bodyless attention
        # (which SHOULD use ``headline`` to avoid offline storage) never
        # reaches ``_on_message`` — the plugin's event is the only path.
        self.xmpp.add_event_handler("attention", self._on_attention_event)
        # slixmpp folds a bare <show> value into the presence ``type`` (so a
        # transport presence with ``<show>away</show>`` but no ``type`` emits
        # ``presence_away``, not ``presence_available``).  Subscribe to the
        # generic ``presence`` event instead and filter in the handler.
        self.xmpp.add_event_handler("presence", self._on_presence)
        self.xmpp.add_event_handler("presence_subscribed", self._on_subscribed)
        self.xmpp.add_event_handler("presence_unsubscribed", self._on_unsubscribed)
        self.xmpp.add_event_handler("presence_subscribe",
                                    self._on_subscription_request)
        self.xmpp.add_event_handler("presence_unsubscribe",
                                    self._on_unsubscribe_request)
        self.xmpp.add_event_handler("groupchat_message", self._on_groupchat_message)
        self.xmpp.add_event_handler("groupchat_subject", self._on_groupchat_subject)
        self.xmpp.add_event_handler("groupchat_presence", self._on_groupchat_presence)
        self.xmpp.add_event_handler("got_online", self._on_got_online)
        self.xmpp.add_event_handler("failed_auth", self._on_auth_failed)
        self.xmpp.add_event_handler("disconnected", self._on_disconnected)
        self.xmpp.add_event_handler("presence_error", self._on_presence_error)
        self.xmpp.add_event_handler("roster_update", self._on_roster_update)
        self.xmpp.add_event_handler("chatstate", self._on_chatstate)
        self.xmpp.add_event_handler("entity_caps", self._on_entity_caps)
        self.xmpp.add_event_handler("receipt_received", self._on_receipt_received)
        self.xmpp.add_event_handler("carbon_received", self._on_carbon_received)
        self.xmpp.add_event_handler("carbon_sent", self._on_carbon_sent)
        self.xmpp.add_event_handler("vcard_avatar_update",
                                    self._on_vcard_avatar_update)
        if self.stream_management:
            self.xmpp.add_event_handler("sm_enabled", self._on_sm_enabled)
            self.xmpp.add_event_handler("session_resumed", self._on_session_resumed)
            self.xmpp.add_event_handler("sm_failed", self._on_sm_failed)
            self.xmpp.add_event_handler("sm_disabled", self._on_sm_disabled)
        if self.csi:
            self.xmpp.add_event_handler("csi_enabled", self._on_csi_enabled)

    # ── Public API ────────────────────────────────────────────────

    def _register_jingle_handlers(self) -> None:
        """Register the Jingle / IBB stanza handlers (XEP-0234/0261)."""
        from slixmpp.xmlstream.handler import CoroutineCallback
        from slixmpp.xmlstream.matcher.xpath import MatchXPath

        manager = self.file_transfer
        jabber = "{jabber:client}iq"

        def _handler(name, path, callback):
            self.xmpp.register_handler(CoroutineCallback(
                name, MatchXPath("%s/%s" % (jabber, path)), callback))

        # One router for all Jingle IQs: it acks once and dispatches to the
        # file-transfer or the RTP (call) manager.
        _handler("Jingle", "{%s}jingle" % jingle_mod.NS_JINGLE,
                 self._dispatch_jingle_iq)
        _handler("IBB Open",
                 "{%s}open" % jingle_mod.NS_IBB_OLD,
                 manager.handle_ibb_open)
        _handler("IBB Close",
                 "{%s}close" % jingle_mod.NS_IBB_OLD,
                 manager.handle_ibb_close)
        _handler("IBB Data",
                 "{%s}data" % jingle_mod.NS_IBB_OLD,
                 manager.handle_ibb_data)

        # slixmpp only fires the `message` event for messages that carry a
        # <body> (basexmpp registers the IM handler as message/body), so
        # bodyless XEP-0353 proposals, XEP-0482 invites and XEP-0163 PEP /
        # XEP-0490 MDS `pubsub#event` notifications need their own matchers.
        msg_ns = "{jabber:client}message"
        self.xmpp.register_handler(CoroutineCallback(
            "Jingle Message",
            MatchXPath("%s/{%s}*" % (msg_ns, jingle_rtp.NS_JINGLE_MSG)),
            self._on_jingle_message_stanza))
        self.xmpp.register_handler(CoroutineCallback(
            "Call Invite",
            MatchXPath("%s/{%s}*" % (msg_ns, muji_mod.NS_CALL_INVITES)),
            self._on_call_invite_stanza))
        self.xmpp.register_handler(CoroutineCallback(
            "MUC Invite",
            MatchXPath("%s/{%s}x" % (msg_ns, NS_MUC_INVITE)),
            self._on_muc_invite_stanza))
        self.xmpp.register_handler(CoroutineCallback(
            "MUC Mediated Invite",
            MatchXPath("%s/{%s}x" % (msg_ns, NS_MUC_USER)),
            self._on_muc_mediated_invite_stanza))
        self.xmpp.register_handler(CoroutineCallback(
            "PEP Event",
            MatchXPath("%s/{%s}event" % (msg_ns, NS_PUBSUB_EVENT)),
            self._on_pubsub_event_stanza))
        self.xmpp.register_handler(CoroutineCallback(
            "CAPTCHA",
            MatchXPath("%s/{%s}captcha" % (msg_ns, NS_CAPTCHA)),
            self._on_captcha_stanza))
        # XEP-0144 roster item exchange (may be bodyless).
        self.xmpp.register_handler(CoroutineCallback(
            "Roster Exchange",
            MatchXPath("%s/{%s}x" % (msg_ns, NS_ROSTERX)),
            self._on_roster_exchange_stanza))
        # XEP-0424/0425 retractions are bodyless; slixmpp's MUC handler
        # requires a <body>, so the room's moderation broadcast would never
        # reach groupchat_message without a dedicated matcher.
        self.xmpp.register_handler(CoroutineCallback(
            "Message Retraction",
            MatchXPath("%s/{%s}retract" % (msg_ns, NS_RETRACT)),
            self._on_bodyless_retract_stanza))
        self.xmpp.register_handler(CoroutineCallback(
            "Message Retraction (legacy)",
            MatchXPath("%s/{%s}retract" % (msg_ns, NS_RETRACT_LEGACY)),
            self._on_bodyless_retract_stanza))
        # XEP-0444 reactions are bodyless too.
        self.xmpp.register_handler(CoroutineCallback(
            "Message Reactions",
            MatchXPath("%s/{%s}reactions" % (msg_ns, NS_REACTIONS)),
            self._on_bodyless_reactions_stanza))
        # XEP-0333 chat markers: a bodyless ``<displayed id='…'/>``.
        self.xmpp.register_handler(CoroutineCallback(
            "Chat Marker",
            MatchXPath("%s/{%s}displayed" % (msg_ns, NS_CHAT_MARKERS)),
            self._on_bodyless_chat_marker_stanza))
        # XEP-0045 §7.13 voice request — a bodyless ``jabber:x:data`` message
        # (no <body>, so slixmpp's IM handler never fires).
        self.xmpp.register_handler(CoroutineCallback(
            "MUC Voice Request",
            MatchXPath("%s/{jabber:x:data}x" % msg_ns),
            self._on_bodyless_voice_stanza))
        # A MUC message rejected by the server (e.g. a visitor without voice
        # -> ``forbidden``) is a bodyless ``<message type='error'>``.
        self.xmpp.register_handler(CoroutineCallback(
            "MUC Message Error",
            MatchXPath("%s/{%s}error" % (msg_ns, "jabber:client")),
            self._on_muc_message_error_stanza))

    async def _on_muc_message_error_stanza(self, msg) -> None:
        """Surface a MUC message rejected with ``forbidden`` (no voice)."""
        from_room = str(msg["from"] or "").split("/", 1)[0]
        if from_room not in self.groupchats:
            return
        xml = getattr(msg, "xml", None)
        if xml is None:
            return
        err = xml.find("{jabber:client}error")
        if err is None:
            return
        condition = ""
        text = ""
        for child in err:
            tag = str(child.tag).rsplit("}", 1)[-1]
            if tag == "text":
                if not text:
                    text = (child.text or "").strip()
            elif not condition:
                condition = tag
        if condition != "forbidden":
            return
        logger.info("MUC %s rejected a message (forbidden): %s",
                    from_room, text)
        self.emit("muc_send_forbidden", from_room, text)

    async def _on_bodyless_voice_stanza(self, msg) -> None:
        """Route a bodyless ``jabber:x:data`` message (voice request/error)."""
        voice_err = self._voice_request_error(msg)
        if voice_err is not None:
            room, condition, text = voice_err
            logger.info("VOICE request error in %s: %s", room,
                        condition or "error")
            self.emit("voice_request_failed", room, condition, text)
            return
        if str(msg["type"] or "") == "error":
            return
        voice = _muc_voice_request(msg)
        if voice is not None:
            logger.info("VOICE request in %s from %s", voice["room"],
                        voice["from"])
            self.emit("muc_voice_requested", voice["room"], voice["from"],
                      voice["nick"])

    async def _on_bodyless_reactions_stanza(self, msg) -> None:
        """Route a bodyless XEP-0444 ``<reactions/>`` to the right handler.

        A reactions message that carries a fallback ``<body>`` is already
        delivered through the ``message``/``groupchat_message`` events, so it
        is ignored here to avoid handling it twice.
        """
        if str(msg["body"] or ""):
            return
        if str(msg["type"] or "") == "groupchat":
            self._on_groupchat_message(msg)
        else:
            self._on_message(msg)

    async def _on_bodyless_chat_marker_stanza(self, msg) -> None:
        """A bodyless XEP-0333 ``<displayed id='…'/>`` (peer read our message)."""
        xml = getattr(msg, "xml", None)
        displayed = (xml.find("{%s}displayed" % NS_CHAT_MARKERS)
                     if xml is not None else None)
        if displayed is None:
            return
        ref = str(displayed.get("id", "") or "")
        if ref:
            self.emit("chat_marker_displayed", str(msg["from"]), ref)

    async def _on_bodyless_retract_stanza(self, msg) -> None:
        """Route a bodyless XEP-0424/0425 retraction to the right handler.

        Messages that do carry a ``<body>`` (a XEP-0424 fallback) are already
        delivered through the ``message``/``groupchat_message`` events, so
        they are ignored here to avoid handling them twice.
        """
        if str(msg["body"] or ""):
            return
        if str(msg["type"] or "") == "groupchat":
            self._on_groupchat_message(msg)
        else:
            self._on_message(msg)

    async def _on_pubsub_event_stanza(self, msg) -> None:
        """Route bodyless pubsub#event messages (PEP, MDS) to their handlers."""
        logger.debug("PEP/MDS event stanza from %s", msg["from"])
        try:
            self._maybe_mds_event(msg)
            self._maybe_pep_event(msg)
        except Exception:
            logger.exception("PEP/MDS event handling failed")

    async def _on_captcha_stanza(self, msg) -> None:
        """A XEP-0158 CAPTCHA challenge arrived."""
        form = self._captcha_form(msg)
        if form is None:
            return
        jid = str(msg["from"])
        try:
            body = str(msg["body"])
        except (KeyError, TypeError):
            body = ""
        logger.info("CAPTCHA challenge from %s", jid)
        self.emit("captcha_challenge", jid, form, _oob_url(msg), body)

    async def _on_roster_exchange_stanza(self, msg) -> None:
        """A XEP-0144 roster item exchange arrived."""
        items = parse_roster_exchange(msg)
        if not items:
            return
        frm = str(msg["from"])
        try:
            body = str(msg["body"])
        except (KeyError, TypeError):
            body = ""
        logger.info("Roster exchange from %s (%d items)", frm, len(items))
        self.emit("roster_exchange_received", frm, items, body)

    def send_roster_exchange(self, jid: str, items: list[dict],
                             body: str = "") -> str:
        """Send *items* to *jid* as a XEP-0144 message; returns the id."""
        if not jid or not items:
            return ""
        msg = self.xmpp.Message()
        msg["to"] = jid
        msg["type"] = "chat"
        if body:
            msg["body"] = body
        msg.xml.append(build_roster_exchange(items))
        logger.debug("Sending roster exchange to %s (%d items)", jid,
                     len(items))
        msg.send()
        return str(msg["id"])

    def apply_roster_exchange(self, items: list[dict]) -> int:
        """Apply the user-approved XEP-0144 *items* to the roster.

        Returns the number of roster changes sent.  Follows the XEP-0144 §3
        processing rules: an existing item in the suggested group is left
        alone, a "delete" only drops the suggested group when other groups
        remain (otherwise the contact is removed), and a "modify" only touches
        an existing item.
        """
        applied = 0
        for entry in items:
            jid = str(entry.get("jid") or "").strip()
            action = str(entry.get("action") or "add").lower()
            if not jid:
                continue
            current = self.roster.get(jid) or {}
            groups = [g for g in (current.get("groups") or []) if g]
            name = current.get("name") or ""
            suggested = [g for g in (entry.get("groups") or []) if g]
            suggested_name = str(entry.get("name") or "")
            if action == "add":
                if jid in self.roster and (
                        not suggested or set(suggested) <= set(groups)):
                    continue  # already there, in the suggested group
                merged = sorted(set(groups) | set(suggested),
                                key=str.casefold)
                if jid not in self.roster:
                    self.add_contact(jid, suggested_name or name, merged,
                                     request_subscription=True)
                else:
                    self.update_contact(jid, suggested_name or name, merged)
                applied += 1
            elif action == "delete":
                if jid not in self.roster:
                    continue
                remaining = [g for g in groups if g not in suggested]
                if suggested and remaining:
                    self.update_contact(jid, name, remaining)
                else:
                    self.remove_contact(jid)
                applied += 1
            elif action == "modify":
                if jid not in self.roster:
                    continue
                self.update_contact(jid, suggested_name or name,
                                    suggested or groups)
                applied += 1
        if applied:
            self.request_roster()
        return applied

    @staticmethod
    def _captcha_form(msg):
        """Return the XEP-0158 CAPTCHA data form of *msg* (slixmpp Form)."""
        from slixmpp.plugins.xep_0004.stanza import Form
        xml = getattr(msg, "xml", None)
        if xml is None:
            return None
        for captcha in xml.iter("{%s}captcha" % NS_CAPTCHA):
            for child in captcha:
                if (child.tag == "{%s}x" % NS_DATA
                        and child.get("type") == "form"):
                    try:
                        form = Form(xml=child)
                    except Exception:
                        logger.debug("Could not parse CAPTCHA form",
                                     exc_info=True)
                        return None
                    _resolve_bob_media(form.xml, _bob_data_uris(xml))
                    return form
        return None

    async def _on_jingle_message_stanza(self, msg) -> None:
        try:
            self.rtp_calls.handle_message(msg)
        except Exception:
            logger.exception("CALL jingle-message handling failed")

    async def _on_call_invite_stanza(self, msg) -> None:
        try:
            self.muji.handle_invite_message(msg)
        except Exception:
            logger.exception("MUJI invite handling failed")

    async def _on_muc_invite_stanza(self, msg) -> None:
        """A bodyless XEP-0249 invitation (slixmpp ignores it without a body)."""
        invite = muc_invite_from_message(msg)
        if invite is None:
            return
        logger.info("MUC invite to %s (inviter=%r mediated=%s)",
                    invite["room"], invite["inviter"], invite["mediated"])
        self.emit("muc_invite_received", invite["inviter"], invite["room"],
                  invite["password"], invite["reason"])

    async def _on_muc_mediated_invite_stanza(self, msg) -> None:
        """A room-relayed invitation may carry only the XEP-0045 ``muc#user``
        invite; when a ``jabber:x:conference`` element is present the XEP-0249
        handler already covers the stanza."""
        voice = _muc_voice_request(msg)
        if voice is not None:
            # XEP-0045 §7.13: a visitor asks for voice (affiliation ``member``).
            self.emit("muc_voice_requested", voice["room"], voice["from"],
                      voice["nick"])
            return
        if msg.xml.find("{%s}x" % NS_MUC_INVITE) is not None:
            return
        invite = muc_mediated_invite_from_message(msg)
        if invite is None:
            return
        logger.info("Mediated MUC invite to %s from %s", invite["room"],
                    invite["inviter"])
        self.emit("muc_invite_received", invite["inviter"], invite["room"],
                  invite["password"], invite["reason"])

    async def _dispatch_jingle_iq(self, iq) -> None:
        """Ack a Jingle IQ once and route it to FT or RTP."""
        jingle = iq.xml.find("{%s}jingle" % jingle_mod.NS_JINGLE)
        if jingle is None:
            return
        action = (jingle.get("action") or "").strip()
        sid = jingle.get("sid", "")
        is_rtp = jingle_rtp.is_rtp_jingle(jingle) or sid in self.rtp_calls.sessions
        logger.debug("JINGLE action=%s sid=%s rtp=%s", action, sid, is_rtp)
        try:
            self.xmpp.send(iq.reply())
        except Exception:
            logger.debug("Could not ack Jingle IQ", exc_info=True)
        if is_rtp:
            self._start_task(self.rtp_calls.dispatch(action, jingle, iq))
        else:
            self._start_task(self.file_transfer._dispatch(action, jingle, iq))

    # ── XEP-0202 Entity Time ──────────────────────────────────────

    def _register_time_handler(self) -> None:
        """Answer ``<time/>`` requests without slixmpp's broken set_tzo."""
        from slixmpp.xmlstream.handler import Callback
        from slixmpp.xmlstream.matcher import StanzaPath

        try:
            self.xmpp.remove_handler("Entity Time")
        except Exception:
            logger.debug("Could not remove slixmpp Entity Time handler",
                         exc_info=True)
        self.xmpp.register_handler(Callback(
            "Entity Time", StanzaPath("iq@type=get/entity_time"),
            self._on_time_request))

    def _on_time_request(self, iq) -> None:
        """Reply to a XEP-0202 time request with a correct utc/tzo child."""
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            offset = datetime.datetime.now().astimezone().utcoffset()
            seconds = int((offset or datetime.timedelta(0)).total_seconds())
            sign = "+" if seconds >= 0 else "-"
            seconds = abs(seconds)
            tzo = "%s%02d:%02d" % (sign, seconds // 3600,
                                   (seconds % 3600) // 60)
            reply = iq.reply()
            time_el = ET.SubElement(reply.xml, "{%s}time" % NS_TIME)
            ET.SubElement(time_el, "{%s}utc" % NS_TIME).text = now.strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            ET.SubElement(time_el, "{%s}tzo" % NS_TIME).text = tzo
            self.xmpp.send(reply)
            logger.debug("XEP-0202 time reply to %s (tzo=%s)", iq["from"], tzo)
        except Exception:
            logger.exception("XEP-0202 time reply failed")

    async def _get_entity_time(self, jid: str) -> dict:
        """Query *jid* for its local time; returns ``{utc, tzo}``."""
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        iq["to"] = jid
        ET.SubElement(iq.xml, "{%s}time" % NS_TIME)
        result = await iq.send(timeout=8)
        utc = tzo = ""
        for el in result.xml.iter("{%s}time" % NS_TIME):
            utc_el = el.find("{%s}utc" % NS_TIME)
            tzo_el = el.find("{%s}tzo" % NS_TIME)
            if utc_el is not None and utc_el.text:
                utc = utc_el.text.strip()
            if tzo_el is not None and tzo_el.text:
                tzo = tzo_el.text.strip()
        return {"utc": utc, "tzo": tzo}

    def _start_task(self, coro):
        """Schedule *coro* on the current event loop; returns the task."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return None
        return loop.create_task(coro)

    def on(self, event: str, callback: Callable) -> None:
        """Register a callback for an internal event name."""
        self._callbacks.setdefault(event, []).append(callback)

    def detach(self) -> None:
        """Drop every internal event callback.

        Called when the client is logged out and replaced: the old instance may
        still emit ``disconnected`` (and other events) while its stream closes
        asynchronously, which would otherwise clobber the freshly started
        session's UI (e.g. show a stale "connection lost" status).
        """
        self._callbacks.clear()

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Invoke all callbacks registered for *event*."""
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args, **kwargs)
            except Exception:
                logger.exception("Error in callback for %s", event)

    async def connect_async(self) -> None:
        """Connect to the XMPP server and start the session."""
        self.xmpp._connected_target = None
        if (self.tls_mode == "direct" and not self.host):
            domain = self.jid_str.split("@")[-1]
            from stanza_im.core.discovery import resolve_client_srv
            records = await resolve_client_srv(domain, "xmpps-client")
            if not records:
                self.xmpp.auto_reconnect = False
                raise TLSOnlyUnavailable(domain)
        result = self.xmpp.connect(self.host or None, self.port or None)
        if asyncio.iscoroutine(result):
            await result
        elif isinstance(result, asyncio.Future):
            await result

    async def connect_for_registration(self) -> None:
        """Connect without authenticating, for XEP-0077 account creation.

        The SASL feature is disabled on this throwaway connection so the
        stream stops after the pre-auth features; the caller then requests the
        in-band registration form with :meth:`get_registration_form`.
        """
        plugin = self.xmpp.plugin.get("feature_mechanisms", None)
        if plugin is not None:
            try:
                self.xmpp.unregister_feature("mechanisms",
                                             plugin.config["order"])
            except (KeyError, ValueError):
                logger.debug("Could not disable SASL for registration")
        loop = asyncio.get_event_loop()
        negotiated = loop.create_future()

        def _on_negotiated(_event=None):
            if not negotiated.done():
                negotiated.set_result(True)

        self.xmpp.add_event_handler("stream_negotiated", _on_negotiated)
        try:
            await self.connect_async()
            await asyncio.wait_for(negotiated, timeout=20)
        finally:
            self.xmpp.del_event_handler("stream_negotiated", _on_negotiated)

    def _on_tls_required(self, _event=None) -> None:
        logger.error("Required STARTTLS is not supported by the server")
        self.emit("tls_required")

    def connection_info(self) -> dict:
        """Describe the active connection (mode, TLS, SASL, keep-alive)."""
        x = self.xmpp
        sock = getattr(x, "socket", None)
        features = getattr(x, "features", set())
        if 'starttls' in features:
            mode = "starttls"
        elif _is_tls(sock):
            mode = "direct"
        else:
            mode = "plain"
        info = {"mode": mode, "tls_version": "", "cipher": "",
                "sasl": "", "keepalive": self.keepalive,
                "sm": self.stream_management_state(),
                "csi": self.csi_state(),
                "host": "", "port": 0, "cert": {}}
        if _is_tls(sock):
            try:
                info["tls_version"] = sock.version() or ""
                cipher = sock.cipher()
                info["cipher"] = cipher[0] if cipher else ""
            except Exception:
                pass
            info["cert"] = _peer_certificate(sock)
        mech = getattr(x.plugin.get("feature_mechanisms", None), "mech", None)
        if mech is not None:
            info["sasl"] = getattr(mech, "name", "") or ""
        target = getattr(x, "_connected_target", None)
        custom = getattr(x, "custom_address", None)
        if target:
            info["host"], info["port"] = str(target[0]), int(target[1])
        elif custom:
            info["host"], info["port"] = str(custom[0]), int(custom[1])
        else:
            bound = getattr(x, "boundjid", None)
            info["host"] = str(bound.domain) if bound and bound.domain \
                else x.default_domain
            info["port"] = x.default_port
        return info

    def stream_management_state(self) -> str:
        """``off`` / ``enabled`` / ``resumed`` for the info icon."""
        if not self.stream_management or "xep_0198" not in self.xmpp.plugin:
            return "off"
        if getattr(self.xmpp.plugin["xep_0198"], "enabled_in", False):
            return "resumed" if self._sm_resumed else "enabled"
        return "off"

    def csi_state(self) -> str:
        """``off`` / ``active`` / ``inactive`` for the info icon."""
        if not self.csi or not self._csi_enabled:
            return "off"
        return "active" if self._client_active else "inactive"

    def set_client_active(self, active: bool) -> None:
        """Tell the server (XEP-0352) whether the client is in use."""
        active = bool(active)
        if active == self._client_active and self._csi_enabled:
            return
        self._client_active = active
        self._sync_csi()

    def set_csi_config(self, enabled: bool) -> None:
        """Apply the CSI preference to the live connection (no restart)."""
        enabled = bool(enabled)
        if enabled == self.csi:
            return
        self.csi = enabled
        plugin = self.xmpp.plugin.get("xep_0352", None)
        if enabled:
            if plugin is None:
                self.xmpp.register_plugin("xep_0352")
                plugin = self.xmpp.plugin.get("xep_0352", None)
            if not self._csi_handler_registered:
                self.xmpp.add_event_handler("csi_enabled", self._on_csi_enabled)
                self._csi_handler_registered = True
            if plugin is not None and "csi" in getattr(self.xmpp, "features", set()):
                plugin.enabled = True
                self._csi_enabled = True
            logger.info("CSI enabled live (server supports=%s)",
                        "csi" in getattr(self.xmpp, "features", set()))
            self._sync_csi()
            self.emit("csi_enabled")
        else:
            if plugin is not None and self._csi_enabled:
                try:
                    # Stop the server from buffering; it must think we are active.
                    plugin.send_active()
                except Exception:
                    logger.debug("CSI send_active failed", exc_info=True)
            self._csi_enabled = False
            if plugin is not None:
                try:
                    self.xmpp.unregister_plugin("xep_0352")
                except Exception:
                    logger.debug("CSI unregister failed", exc_info=True)
            logger.info("CSI disabled live")
            self.emit("connection_info", self.connection_info())

    def _sync_csi(self) -> None:
        """Send the current CSI state if the server supports it."""
        if not self.csi or "xep_0352" not in self.xmpp.plugin:
            return
        plugin = self.xmpp.plugin["xep_0352"]
        if not getattr(plugin, "enabled", False):
            return
        if not getattr(self.xmpp, "_session_started", False):
            return
        if self._client_active:
            plugin.send_active()
        else:
            plugin.send_inactive()

    def send_raw_xml(self, text: str) -> int:
        """Send XML entered in the console; returns the number of stanzas sent.

        Multiple top-level elements are accepted. An ``<iq>`` without an ``id``
        gets one so its reply can be matched by the normal IQ machinery.
        """
        payload = text.strip()
        if payload.startswith("<?xml"):
            payload = payload.split("?>", 1)[-1]
        root = ET.fromstring("<stanza-console>%s</stanza-console>" % payload)
        sent = 0
        for element in list(root):
            if element.tag == "iq" and not element.get("id"):
                element.set("id", "xmlc-%s" % uuid.uuid4().hex[:8])
            self.xmpp.send_raw(ET.tostring(element, encoding="unicode"))
            sent += 1
        return sent

    def discovered_services(self) -> dict | None:
        """Latest background discovery result (file proxy + STUN/TURN)."""
        return self._discovered

    async def discover_transfer_services(self, force: bool = False) -> dict:
        """Run/refresh file-proxy and STUN/TURN discovery and cache results."""
        from stanza_im.core.discovery import DiscoveryCache, refresh
        domain = self.jid_str.split("@")[-1]
        try:
            self._discovered = await refresh(self.xmpp, domain,
                                             DiscoveryCache(), force=force)
        except Exception:
            logger.exception("Service discovery failed")
            if self._discovered is None:
                self._discovered = {"file_proxy": None, "stun_turn": [],
                                    "ice_services": []}
        self.emit("services_discovered", self._discovered)
        return self._discovered

    async def refresh_services(self) -> dict:
        """Force a fresh discovery run (used by the preferences button)."""
        return await self.discover_transfer_services(force=True)

    def ice_servers(self) -> list[dict]:
        """Effective STUN/TURN list for Jingle ICE (aiortc RTCIceServer dicts).

        Priority: XEP-0215 credentials from the server, then the manually
        configured endpoint, then the SRV-derived auto endpoint.  The address
        comes from the connection settings' STUN/TURN section, as requested.
        """
        from stanza_im.core.discovery import (
            ice_servers_from_services, effective_endpoint)
        data = self._discovered or {}
        services = list(data.get("ice_services") or [])
        if services:
            servers = ice_servers_from_services(services)
            if servers:
                logger.info("CALL ICE servers from XEP-0215: %s",
                            [s.get("urls") for s in servers])
                return servers
        # Fallback: manual / auto settings (host:port), STUN only.
        mode = getattr(self, "stun_turn_mode", "auto")
        manual = getattr(self, "stun_turn_manual", "")
        auto = None
        for entry in (data.get("stun_turn") or []):
            if isinstance(entry, dict) and entry.get("host"):
                auto = {"host": entry.get("host"), "port": entry.get("port")}
                break
        endpoint = effective_endpoint(mode, manual, auto)
        if endpoint:
            host, _, port = endpoint.rpartition(":")
            try:
                port = int(port)
            except ValueError:
                port = 3478
            logger.info("CALL ICE server from settings: %s:%s", host, port)
            return [{"urls": "stun:%s:%s" % (host, port)}]
        logger.warning("CALL no STUN/TURN configured (direct/ICE host only)")
        return []

    def _install_socks_proxy(self, proxy_host: str, proxy_port: int) -> None:
        """Route the XMPP TCP connection through a SOCKS5 proxy.

        slixmpp has no native client-proxy support, so the direct
        ``_attempt_connection`` is replaced with one that opens the socket
        through the proxy and then hands it to slixmpp.
        """
        from stanza_im.xmpp import socks5

        xmpp = self.xmpp

        async def attempt(target_host: str, target_port: int, tls: bool,
                          server_hostname: str | None) -> bool:
            if xmpp._current_connection_attempt is None:
                return False
            xmpp.event_when_connected = "connected"
            xmpp._connect_loop_wait += 1
            try:
                sock = await socks5.connect_via_socks5(
                    xmpp.loop, proxy_host, proxy_port,
                    target_host or xmpp.default_domain, target_port)
                kwargs: dict = {"sock": sock}
                if tls:
                    kwargs["ssl"] = xmpp.get_ssl_context()
                    kwargs["server_hostname"] = server_hostname
                await xmpp.loop.create_connection(lambda: xmpp, **kwargs)
                xmpp._connect_loop_wait = 0
                target = getattr(xmpp, "_dns_hosts", {}).get(
                    (target_host, target_port), target_host)
                xmpp._connected_target = (target, target_port, tls)
                return True
            except Exception as exc:
                logger.warning("SOCKS5 connection attempt failed: %s", exc)
                xmpp.event("connection_failed", exc)
                return False

        xmpp._attempt_connection = attempt
        logger.info("Routing the XMPP connection through SOCKS5 %s:%s",
                    proxy_host, proxy_port)

    async def disconnect(self) -> None:
        """Gracefully disconnect: go offline and close the stream."""
        # Stop any reconnect attempts (an explicit logout must not reconnect).
        self._reconnect_enabled = False
        self._shutting_down = True
        self._cancel_reconnect()
        try:
            self.file_transfer.close()
        except Exception:
            logger.debug("Closing file transfers failed", exc_info=True)
        if not self.xmpp.is_connected():
            return
        try:
            self.send_presence("offline")
        except Exception:
            logger.debug("Sending unavailable presence failed", exc_info=True)
        try:
            # XMLStream.disconnect() returns a future that drains the send
            # queue (flushing the unavailable presence), sends the stream
            # footer and closes the transport.  It must be awaited: otherwise
            # the shutdown cancels it and the server keeps the session (and the
            # account appears online) until the resumption window expires.
            await asyncio.wait_for(self.xmpp.disconnect(wait=1.0),
                                   timeout=2.5)
        except Exception:
            logger.debug("XMPP disconnect did not finish cleanly",
                         exc_info=True)

    def send_message(self, jid: str, body: str, mtype: str = "chat",
                     mhtml: str | None = None, reply_to: str = "",
                     reply_id: str = "", reply_ref_sender: str = "",
                     reply_ref_body: str = "",
                     replace_id: str = "",
                     media: dict | None = None) -> str:
        """Send a message.

        With *reply_to* + *reply_id* a XEP-0461 ``<reply/>`` is attached as
        the first child of ``<message>`` (so the recipient's client can render
        the referenced message).  When *reply_ref_body* is given (the quoted
        original text) the body is prefixed with a XEP-0393 ``> `` quote and a
        XEP-0421 ``<fallback for='urn:xmpp:reply:0'>`` is added so clients
        without reply support still see the context.
        """
        if not isinstance(jid, str) or not jid.strip():
            logger.warning("Skipping message with empty target: %r", jid)
            return ""
        jid = jid.strip()
        msg, message_id = self._compose_message(
            jid, body, mtype, mhtml, reply_to, reply_id, reply_ref_sender,
            reply_ref_body, replace_id, media)
        logger.debug("Sending %s message to %s (reply_id=%s): %r",
                     mtype, jid, reply_id, str(msg["body"])[:200])
        msg.send()
        return message_id

    def _compose_message(self, jid: str, body: str, mtype: str = "chat",
                         mhtml: str | None = None, reply_to: str = "",
                         reply_id: str = "", reply_ref_sender: str = "",
                         reply_ref_body: str = "", replace_id: str = "",
                         media: dict | None = None):
        """Build an outgoing ``<message>`` stanza (not sent yet)."""
        msg = self.xmpp.Message()
        msg["to"] = jid
        msg["type"] = mtype
        body = str(body)
        quote = ""
        if reply_ref_body and reply_ref_sender:
            prefix = f"{reply_ref_sender} wrote:\n{reply_ref_body}"
            quote = compose_reply_body(prefix)
            body = quote + body
        msg["body"] = body
        message_id = uuid.uuid4().hex
        msg["id"] = message_id
        if reply_to and reply_id:
            self._attach_reply(msg, reply_to, reply_id, prefix_len=len(quote))
        if replace_id:
            self._attach_replace(msg, replace_id)
        if mtype == "chat":
            msg["request_receipt"] = True  # XEP-0184
        if mtype in ("chat", "groupchat") and not replace_id:
            # XEP-0333: mark the message so the peer may return a <displayed/>.
            ET.SubElement(msg.xml, "{%s}markable" % NS_CHAT_MARKERS)
        if mhtml:
            msg["html"]["body"] = mhtml
        if media:
            self._attach_media_sharing(msg, media)
        return msg, message_id

    async def send_omemo_message(self, jid: str, body: str, mtype: str = "chat",
                                 recipients=None, mhtml: str | None = None,
                                 reply_to: str = "", reply_id: str = "",
                                 reply_ref_sender: str = "",
                                 reply_ref_body: str = "",
                                 replace_id: str = "",
                                 media: dict | None = None) -> str:
        """Encrypt and send a message with OMEMO (XEP-0384).

        *recipients* is the set of bare JIDs to encrypt for (defaults to *jid*,
        i.e. a 1:1 chat).  Returns the message id, or "" when nothing was sent.
        """
        if not isinstance(jid, str) or not jid.strip():
            return ""
        if not getattr(self.omemo, "available", False):
            raise RuntimeError("OMEMO is not available")
        jid = jid.strip()
        msg, message_id = self._compose_message(
            jid, body, mtype, mhtml, reply_to, reply_id, reply_ref_sender,
            reply_ref_body, replace_id, media)
        targets = set(recipients) if recipients else {jid}
        encrypted, errors = await self.omemo.encrypt(
            msg, targets, identifier=jid)
        if errors:
            logger.warning("OMEMO encryption had errors: %s", errors)
        if encrypted is None:
            logger.warning("OMEMO produced no message for %s", jid)
            return ""
        encrypted.send()
        return message_id

    async def send_omemo_muc_message(self, room: str, body: str,
                                     reply_to: str = "", reply_id: str = "",
                                     reply_ref_sender: str = "",
                                     reply_ref_body: str = "") -> str:
        """Encrypt and send a groupchat message with OMEMO (XEP-0384 §5.8)."""
        if not getattr(self.omemo, "available", False):
            raise RuntimeError("OMEMO is not available")
        room = str(room).split("/")[0]
        msg, message_id = self._compose_message(
            room, body, "groupchat", None, reply_to, reply_id,
            reply_ref_sender, reply_ref_body, "", None)
        recipients = self.omemo.muc_recipients(room)
        encrypted, errors = await self.omemo.encrypt(
            msg, recipients, identifier=room)
        if errors:
            logger.warning("OMEMO MUC encryption errors: %s", errors)
        if encrypted is None:
            return ""
        encrypted.send()
        return message_id

    async def send_omemo_file(self, jid: str, path: str, caption: str = "",
                              mtype: str = "chat", recipients=None) -> None:
        """Encrypt *path* (XEP-0454) and share it as an OMEMO message.

        The file is AES-GCM encrypted in memory, the ciphertext is uploaded via
        HTTP Upload and the resulting ``aesgcm://…#iv+key`` URL is sent inside
        an OMEMO message.
        """
        from pathlib import Path
        from slixmpp.plugins.xep_0454 import XEP_0454

        if not getattr(self.omemo, "available", False):
            raise RuntimeError("OMEMO is not available")
        self.emit("file_upload_progress", jid, "start", "", path)
        try:
            payload, fragment = await asyncio.to_thread(
                XEP_0454.encrypt, None, Path(path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("OMEMO file encryption failed: %s", exc)
            self.emit("file_upload_progress", jid, "error", str(exc), str(path))
            return
        size = len(payload)
        ext = os.path.splitext(str(path))[1]
        upload_name = secrets.token_hex(12) + ext
        try:
            service = await self._http_upload_service()
            if not service:
                raise RuntimeError("HTTP Upload is not available")
            put_url, get_url, headers = await self._http_upload_slot(
                service, upload_name, size, "application/octet-stream")
        except Exception as exc:  # noqa: BLE001
            if self._is_upload_oversize(exc):
                self.emit("http_upload_oversize", jid, str(path))
                return
            logger.warning("OMEMO file upload failed for %s: %s", jid, exc)
            self.emit("file_upload_progress", jid, "error", str(exc), str(path))
            return
        try:
            progress = _UploadProgress()
            put_task = asyncio.create_task(self._http_upload_put(
                put_url, str(path), headers, progress, data=payload))
            last = -1
            while not put_task.done():
                await asyncio.sleep(0.05)
                pct = int(progress.pct * 100)
                if pct != last:
                    last = pct
                    self.emit("file_upload_progress", jid, "progress",
                              str(pct), str(path))
            await put_task
            url = XEP_0454.format_url(get_url, fragment)
            await self.send_omemo_message(jid, url, mtype=mtype,
                                          recipients=recipients)
            self.emit("file_upload_progress", jid, "done", url, str(path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("OMEMO file send failed for %s: %s", jid, exc)
            self.emit("file_upload_progress", jid, "error", str(exc), str(path))

    def send_attention(self, jid: str) -> bool:
        """Send a XEP-0224 attention request (a bodyless ``<attention/>``).

        Uses slixmpp's ``xep_0224`` plugin, which sends the request with the
        ``headline`` type so it is not stored as an offline message.
        """
        if not isinstance(jid, str) or not jid.strip():
            return False
        try:
            self.xmpp.plugin["xep_0224"].request_attention(jid.strip())
        except Exception:  # noqa: BLE001
            logger.debug("ATTENTION request failed", exc_info=True)
            return False
        logger.debug("ATTENTION request to %s", jid)
        return True

    def _build_reactions(self, target: str, target_id: str, emojis: list[str],
                         mtype: str = "", msg_id: str = ""):
        """Build (but do not send) a XEP-0444 reaction message; used by tests.

        Returns ``None`` for an invalid target/id.  *emojis* is the full current
        set of the sender (an empty list removes our entry).  The ``type``
        defaults to ``groupchat`` for a known room, else ``chat``.
        """
        if not isinstance(target, str) or not target.strip() or not target_id:
            return None
        target = target.strip()
        if not mtype:
            mtype = ("groupchat" if target.split("/")[0] in self.groupchats
                     else "chat")
        msg = self.xmpp.Message()
        msg["to"] = target
        msg["type"] = mtype
        msg["id"] = msg_id or uuid.uuid4().hex
        reactions = ET.SubElement(msg.xml, "{%s}reactions" % NS_REACTIONS)
        reactions.set("id", str(target_id))
        for emoji in emojis or []:
            emoji = str(emoji).strip()
            if emoji:
                ET.SubElement(reactions, "{%s}reaction" % NS_REACTIONS).text = emoji
        return msg

    def send_reactions(self, target: str, target_id: str, emojis: list[str],
                       mtype: str = "") -> str:
        """Send a XEP-0444 reaction set for *target_id* (return the new id).

        *emojis* is the full current set of the sender: it replaces any
        previous reactions by us for that stanza.  An empty list removes them.
        The ``type`` defaults to ``groupchat`` for a known room, else ``chat``.
        """
        msg = self._build_reactions(target, target_id, emojis, mtype)
        if msg is None:
            logger.warning("Skipping reactions (target=%r id=%r)",
                           target, target_id)
            return ""
        logger.debug("Sending %d reaction(s) to %s for %s (%s)",
                     len(emojis or []), target, target_id, msg["type"])
        msg.send()
        return str(msg["id"])

    def _build_retraction(self, jid: str, target_id: str, mtype: str = "chat",
                          msg_id: str = ""):
        """Build (but do not send) a XEP-0424 retraction; used by tests too."""
        msg = self.xmpp.Message()
        msg["to"] = jid
        msg["type"] = mtype
        msg["id"] = msg_id or uuid.uuid4().hex
        retract = ET.SubElement(msg.xml, "{%s}retract" % NS_RETRACT)
        retract.set("id", str(target_id))
        fallback = ET.SubElement(msg.xml, "{%s}fallback" % NS_FALLBACK)
        fallback.set("for", NS_RETRACT)
        msg["body"] = ("/me retracted a previous message, but it's "
                       "unsupported by your client.")
        ET.SubElement(msg.xml, "{%s}store" % NS_HINTS)
        return msg

    def send_retraction(self, jid: str, target_id: str,
                        mtype: str = "") -> str:
        """Retract the message *target_id* (XEP-0424) and return the new id."""
        if not isinstance(jid, str) or not jid.strip() or not target_id:
            logger.warning("Skipping retraction (jid=%r id=%r)", jid, target_id)
            return ""
        jid = jid.strip()
        if not mtype:
            mtype = ("groupchat" if jid.split("/")[0] in self.groupchats
                     else "chat")
        msg = self._build_retraction(jid, target_id, mtype)
        logger.debug("Sending retraction to %s for %s", jid, target_id)
        msg.send()
        return str(msg["id"])

    def _build_moderation(self, room: str, stanza_id: str, reason: str = ""):
        """Build (but do not send) a XEP-0425 moderation IQ; used by tests."""
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = room
        moderate = ET.SubElement(iq.xml, "{%s}moderate" % NS_MODERATE)
        moderate.set("id", str(stanza_id))
        ET.SubElement(moderate, "{%s}retract" % NS_RETRACT)
        if reason:
            ET.SubElement(moderate, "{%s}reason" % NS_MODERATE).text = reason
        return iq

    async def moderate_message(self, room: str, stanza_id: str,
                               reason: str = "") -> bool:
        """Retract *stanza_id* in *room* as a moderator (XEP-0425).

        The room broadcasts the retraction to every occupant, so the message
        is only updated when that echo arrives.  Returns ``True`` on an IQ
        result and emits ``moderation_failed`` on an error.
        """
        if not isinstance(room, str) or not room.strip() or not stanza_id:
            logger.warning("Skipping moderation (room=%r id=%r)",
                           room, stanza_id)
            return False
        room = room.strip()
        iq = self._build_moderation(room, stanza_id, reason)
        logger.debug("Moderating %s in %s (reason=%r)",
                     stanza_id, room, reason)
        try:
            await iq.send()
        except Exception as exc:
            logger.warning("Moderation request for %s in %s failed: %s",
                           stanza_id, room, exc)
            self.emit("moderation_failed", room, stanza_id, str(exc))
            return False
        self.emit("moderation_sent", room, stanza_id)
        return True

    def send_muc_invite(self, jid: str, room: str, reason: str = "",
                        password: str = "") -> None:
        """Send a XEP-0249 direct MUC invitation to *jid* for *room*."""
        if not isinstance(jid, str) or not jid.strip() or not room:
            logger.warning("Skipping MUC invite (jid=%r room=%r)", jid, room)
            return
        msg = self.xmpp.Message()
        msg["to"] = jid.strip()
        msg["type"] = "normal"
        x = ET.SubElement(msg.xml, "{%s}x" % NS_MUC_INVITE)
        x.set("jid", room)
        if password:
            x.set("password", password)
        if reason:
            x.set("reason", reason)
        logger.info("Sending MUC invite to %s for %s", jid.strip(), room)
        msg.send()

    @staticmethod
    def _attach_reply(msg, reply_to: str, reply_id: str,
                      prefix_len: int = 0) -> None:
        """Attach a XEP-0461 ``<reply/>`` as the first child of ``<message>``,
        plus an optional XEP-0421 compatibility fallback marking the quoted
        prefix (``prefix_len`` bytes of ``<body>``)."""
        xml = msg.xml
        reply = ET.SubElement(xml, "{%s}reply" % NS_REPLY)
        reply.set("to", reply_to)
        reply.set("id", reply_id)
        xml.remove(reply)
        xml.insert(0, reply)
        if prefix_len:
            fallback = ET.SubElement(xml, "{urn:xmpp:fallback:0}fallback")
            fallback.set("for", NS_REPLY)
            fb_body = ET.SubElement(fallback, "body")
            fb_body.set("start", "0")
            fb_body.set("end", str(prefix_len))

    @staticmethod
    def _attach_replace(msg, replace_id: str) -> None:
        """Attach a XEP-0308 ``<replace id='…'/>`` as the first child of
        ``<message>`` (the message replaces *replace_id*)."""
        xml = msg.xml
        replace = ET.SubElement(xml, "{%s}replace" % NS_CORRECT)
        replace.set("id", replace_id)
        xml.remove(replace)
        xml.insert(0, replace)

    @staticmethod
    def _attach_media_sharing(msg, media: dict) -> None:
        """Attach the XEP-0385 SIMS block, XEP-0372 reference, XEP-0066 OOB and
        the XEP-0428 fallbacks marking the URL inside the body.

        *media* carries at least ``url``; ``name``/``size``/``media_type``/
        ``width``/``height``/``hashes`` are optional.
        """
        url = str((media or {}).get("url") or "")
        if not url:
            return
        xml = msg.xml
        reference = ET.Element("{%s}reference" % NS_REFERENCE)
        reference.set("type", "data")
        sharing = ET.SubElement(reference, "{%s}media-sharing" % NS_SIMS)
        file_el = ET.SubElement(sharing, "{%s}file" % NS_FT)
        name = str(media.get("name") or "")
        if name:
            ET.SubElement(file_el, "{%s}name" % NS_FT).text = name
        for algo, value in (media.get("hashes") or {}).items():
            if algo and value:
                hash_el = ET.SubElement(file_el, "{%s}hash" % NS_HASHES)
                hash_el.set("algo", str(algo))
                hash_el.text = str(value)
        media_type = str(media.get("media_type") or "")
        if media_type:
            ET.SubElement(file_el, "{%s}media-type" % NS_FT).text = media_type
        size = _int_or_zero(media.get("size"))
        if size:
            ET.SubElement(file_el, "{%s}size" % NS_FT).text = str(size)
        width = _int_or_zero(media.get("width"))
        if width:
            ET.SubElement(file_el, "{%s}width" % NS_SCHEMA).text = str(width)
        height = _int_or_zero(media.get("height"))
        if height:
            ET.SubElement(file_el, "{%s}height" % NS_SCHEMA).text = str(height)
        sources = ET.SubElement(sharing, "{%s}sources" % NS_SIMS)
        src_ref = ET.SubElement(sources, "{%s}reference" % NS_REFERENCE)
        src_ref.set("type", "data")
        src_ref.set("uri", url)
        xml.insert(0, reference)
        oob = ET.SubElement(xml, "{%s}x" % NS_OOB)
        ET.SubElement(oob, "{%s}url" % NS_OOB).text = url
        body = str(msg["body"] or "")
        start = body.find(url)
        if start < 0:
            return
        end = start + len(url)
        for for_ns in (NS_SIMS, NS_OOB):
            fallback = ET.SubElement(xml, "{%s}fallback" % NS_FALLBACK)
            fallback.set("for", for_ns)
            fb_body = ET.SubElement(fallback, "{%s}body" % NS_FALLBACK)
            fb_body.set("start", str(start))
            fb_body.set("end", str(end))

    def send_presence(self, show: str | None = None, status: str = "",
                      priority: int | None = None) -> None:
        """Send presence to the server."""
        if show == "offline":
            p = self.xmpp.Presence()
            p["type"] = "unavailable"
            if status:
                p["status"] = status
            logger.debug("Sending presence: unavailable")
            p.send()
            return
        p = self.xmpp.Presence()
        if show and show not in ("online", "available"):
            p["type"] = "available"
            p["show"] = show
        else:
            p["type"] = "available"
        if status:
            p["status"] = status
        if priority is None:
            priority = self._effective_priority(show)
        if priority is not None:
            p["priority"] = priority
        logger.debug("Sending presence: %s", show or "available")
        p.send()

    def _effective_priority(self, show: str | None) -> int:
        """Resource priority for *show* (status map or the manual value)."""
        if self.priority_mode == "manual":
            return max(-128, min(127, int(self.priority)))
        return self._STATUS_PRIORITY.get(show or "online", 50)

    def send_chat_state(self, jid: str, state: str) -> None:
        """Send a XEP-0085 chat state notification."""
        if state in ("composing", "paused") and not self.send_typing_notifications:
            return
        if state in ("active", "inactive", "gone") and not self.send_activity_notifications:
            return
        msg = self.xmpp.Message()
        msg["to"] = jid
        msg["type"] = "chat"
        msg["chat_state"] = state
        logger.debug("Sending chat state %s to %s", state, jid)
        msg.send()

    def request_roster(self) -> None:
        """Request the roster from the server."""
        self.xmpp.get_roster()

    def get_roster_snapshot(self) -> list[dict]:
        """Return the current roster as a list of dicts:
        ``{jid, name, groups: list[str], subscription}``."""
        items: list[dict] = []
        cr = self.xmpp.client_roster
        for jid in cr:
            if jid in self._known_rooms:
                # slixmpp creates a pseudo roster item for a room's *own*
                # presence (``basexmpp._handle_available``); it is not a
                # contact and must never be shown in the roster.
                continue
            item = cr[jid]
            items.append({
                "jid": jid,
                "name": item["name"],
                "groups": list(item["groups"]),
                "subscription": item["subscription"],
            })
        return items

    def subscription(self, bare: str) -> str:
        """Roster subscription of *bare*: ``none``/``to``/``from``/``both``.

        Returns ``""`` when the JID is not in the roster.
        """
        jid = str(bare or "").split("/", 1)[0]
        item = self.roster.get(jid)
        return str(item.get("subscription") or "") if item else ""

    def get_roster_state(self) -> list[dict]:
        """Return the roster with the full subscription state (roster cache)."""
        items: list[dict] = []
        cr = self.xmpp.client_roster
        for jid in cr:
            if jid in self._known_rooms:
                continue  # a room's pseudo roster item (see snapshot)
            item = cr[jid]
            items.append({
                "jid": jid,
                "name": item["name"],
                "groups": list(item["groups"]),
                "from": bool(item["from"]),
                "to": bool(item["to"]),
                "whitelisted": bool(item["whitelisted"]),
                "pending_out": bool(item["pending_out"]),
                "pending_in": bool(item["pending_in"]),
            })
        return items

    # ── XEP-0237 roster versioning cache ─────────────────────────

    def _seed_roster_cache(self) -> None:
        """Preload the cached roster so the server can answer "no changes"."""
        try:
            cr = self.xmpp.client_roster
        except Exception:
            return
        if list(cr):
            return  # already populated (e.g. within a resumed session)
        self._roster_cache = self._roster_cache or roster_cache.load(self.jid_str)
        cache = self._roster_cache
        if not cache or not cache.get("items"):
            return
        seeded = 0
        for entry in cache["items"]:
            jid = str(entry.get("jid") or "")
            if not jid:
                continue
            if jid in self._known_rooms:
                # Never resurrect a room's pseudo roster item.
                continue
            item = cr[jid]
            if entry.get("name") is not None:
                item["name"] = entry.get("name")
            if entry.get("groups") is not None:
                item["groups"] = list(entry.get("groups") or [])
            item["from"] = bool(entry.get("from"))
            item["to"] = bool(entry.get("to"))
            item["whitelisted"] = bool(entry.get("whitelisted"))
            item["pending_out"] = bool(entry.get("pending_out"))
            item["pending_in"] = bool(entry.get("pending_in"))
            seeded += 1
        cr.version = str(cache.get("version") or "")
        logger.info("Seeded %d cached roster items (version=%r)",
                    seeded, cr.version)
        logger.debug("ROSTER[seed] ver=%r items=%s", cr.version,
                     [str(e.get("jid") or "") for e in cache["items"]])

    def _schedule_roster_save(self) -> None:
        """Coalesce roster-cache writes."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        handle = getattr(self, "_roster_save_handle", None)
        if handle is not None:
            handle.cancel()
        self._roster_save_handle = loop.call_later(
            1.0, self._save_roster_cache)

    def _save_roster_cache(self) -> None:
        self._roster_save_handle = None
        if not self.jid_str:
            return
        try:
            version = str(self.xmpp.client_roster.version or "")
            items = self.get_roster_state()
        except Exception:
            logger.debug("Could not snapshot the roster for caching",
                         exc_info=True)
            return
        logger.debug("ROSTER[save] ver=%r items=%s", version,
                     [i.get("jid") for i in items])
        try:
            cr = self.xmpp.client_roster
            for jid in [str(j) for j in cr]:
                logger.debug(
                    "ROSTER[state] jid=%s in_roster=%s in_contacts=%s "
                    "in_rooms=%s", jid, cr[jid]["subscription"],
                    jid in self.contacts, jid in self._known_rooms)
        except Exception:
            logger.debug("ROSTER[state] snapshot failed", exc_info=True)
        roster_cache.save(self.jid_str, version, items)

    def flush_roster_cache(self) -> None:
        """Persist the roster cache immediately (called on quit)."""
        handle = getattr(self, "_roster_save_handle", None)
        if handle is not None:
            handle.cancel()
        self._save_roster_cache()

    def get_contact(self, bare_jid: str) -> ContactInfo:
        """Return (creating if needed) the ContactInfo for a bare JID."""
        jid = str(bare_jid).split("/")[0]
        if jid not in self.contacts:
            logger.debug("ROSTER[contact] new=%s", jid)
            self.contacts[jid] = ContactInfo(jid)
        return self.contacts[jid]

    async def gateway_info(self, service: str) -> dict:
        """Return gateway description/prompt information from a service."""
        iq = await self.xmpp.plugin["xep_0030"].get_info(jid=service)
        is_gateway = any(
            str(node.get("category", "")).lower() == "gateway"
            for node in iq.xml.iter() if str(node.tag).endswith("identity")
        )
        if not is_gateway:
            raise ValueError("The selected service is not a gateway")
        query = next((node for node in iq.xml.iter()
                      if str(node.tag).endswith("query")
                      and node.get("xmlns") == "jabber:iq:gateway"), None)
        return {"gateway": True,
                "desc": (next((n.text or "" for n in query
                               if str(n.tag).endswith("desc")), "")
                         if query is not None else ""),
                "prompt": (next((n.text or "" for n in query
                                 if str(n.tag).endswith("prompt")), "")
                           if query is not None else "")}

    async def gateway_translate(self, service: str, prompt: str) -> str:
        """Translate an external service ID through an XMPP gateway."""
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = service
        query = iq.xml.makeelement("{jabber:iq:gateway}query", {})
        child = iq.xml.makeelement("{jabber:iq:gateway}prompt", {})
        child.text = prompt
        query.append(child)
        iq.xml.append(query)
        result = await iq.send()
        for node in result.xml.iter():
            if str(node.tag).endswith("jid") and node.text:
                return node.text.strip()
        raise ValueError("The gateway did not return an XMPP address")

    def add_contact(self, jid: str, name: str = "", groups: list[str] | None = None,
                    message: str = "", request_subscription: bool = True) -> None:
        """Add a contact and send a subscribe request."""
        if request_subscription:
            self.xmpp.send_presence_subscription(
                pto=jid, pfrom=self._full_jid, ptype="subscribe", pnick=name)
        if groups:
            self.xmpp.update_roster(jid, name=name, groups=groups)
        if message.strip():
            self.send_message(jid, message.strip())

    def remove_contact(self, jid: str) -> None:
        """Remove a contact from the roster."""
        self.xmpp.del_roster_item(jid)
        self.xmpp.send_presence_subscription(pto=jid, ptype="unsubscribe")

    def join_muc(self, room: str, nick: str, password: str = "",
                 save_bookmark: bool = False) -> None:
        """Join a Multi-User Chat room.

        The join is awaited inside a managed task (no orphan asyncio tasks):
        slixmpp's synchronous ``join_muc()`` schedules ``join_muc_wait()``
        without tracking its exceptions, surfacing as
        ``Task exception was never retrieved`` when a join fails or times
        out.  We drive ``join_muc_wait`` ourselves and map failures to the
        ``muc_join_error`` event; success emits ``muc_joined`` with the room
        subject and the initial occupant list.
        """
        self._known_rooms.add(room)
        gi = self.groupchats.setdefault(
            room, GroupChatInfo(room=room, nick=nick))
        gi.nick = nick
        gi.password = password or ""
        gi.joined = False
        loop = asyncio.get_event_loop()
        if save_bookmark:
            loop.create_task(self.save_bookmark(room, nick, password,
                                                autojoin=True))
        old_task = self._muc_join_tasks.get(room)
        if old_task is not None and not old_task.done():
            old_task.cancel()
        task = loop.create_task(
            self._join_muc_task(room, nick, password))
        self._muc_join_tasks[room] = task
        task.add_done_callback(lambda t, r=room: self._muc_task_done(r, t))

    async def _join_muc_task(self, room: str, nick: str, password: str) -> None:
        muc = self.xmpp.plugin["xep_0045"]
        try:
            result = await muc.join_muc_wait(room=room, nick=nick,
                                             password=password, timeout=90)
        except slixmpp.exceptions.PresenceError as exc:
            if self.groupchats.get(room, None) and self.groupchats[room].joined:
                return
            pres = getattr(exc, "presence", None)
            captcha = self._captcha_form(pres) if pres is not None else None
            if captcha is not None:
                # XEP-0158 §5: a CAPTCHA-protected room rejects the join until
                # the challenge is answered (the room continues on success).
                try:
                    body = str(pres["body"])
                except (KeyError, TypeError):
                    body = ""
                room_jid = str(pres["from"]) or room
                logger.info("MUC %s requires a CAPTCHA", room_jid)
                self.emit("captcha_challenge", room_jid, captcha,
                          _oob_url(pres), body)
                return
            error = exc.presence.get_error() if getattr(exc, "presence", None) else {}
            condition = (error or {}).get("condition", "") or "unknown"
            code = (error or {}).get("code", "") or ""
            logger.info("MUC join rejected for %s: %s (%s)", room, condition, code)
            self.emit("muc_join_error", room, condition, str(code))
            return
        except asyncio.TimeoutError:
            if self.groupchats.get(room, None) and self.groupchats[room].joined:
                return
            logger.info("MUC join timed out for %s", room)
            self.emit("muc_join_error", room, "timeout", "")
            return
        except Exception:
            if self.groupchats.get(room, None) and self.groupchats[room].joined:
                return
            logger.exception("Unexpected MUC join failure for %s", room)
            self.emit("muc_join_error", room, "unknown", "")
            return

        pres, subject_msg, occupants, _history = result
        # XEP-0045 §10.1.3: status code 201 marks a room we just created.
        created = False
        try:
            codes = pres["muc"]["status_codes"] or set()
            created = 201 in codes
        except Exception:
            created = False
        subjects = _message_subjects(subject_msg)
        subject = next((t for lang, t in subjects if not lang), "")
        if not subject and subjects:
            subject = subjects[0][1]
        gi = self.groupchats.get(room)
        if gi:
            gi.subject = subject
            gi.pending_history = _history or []
        self._muc_subjects[room] = subjects or [("", subject)]
        self._emit_muc_joined(room, subject, list(occupants or []),
                              created=created)

    def _emit_muc_joined(self, room: str, subject: str = "",
                         occupants: list | None = None,
                         created: bool = False) -> None:
        gi = self.groupchats.get(room)
        if not gi:
            return
        if gi.pending_history:
            self._store_muc_history(room, gi.pending_history)
            gi.pending_history = []
        if gi.joined:
            return
        gi.joined = True
        occupants = occupants if occupants is not None else list(gi.users)
        logger.info("Joined room %s as %s (%d occupants)%s",
                    room, gi.nick, len(occupants), " [created]" if created else "")
        self.emit("muc_joined", room, subject or gi.subject, occupants, created)
        subjects = self._muc_subjects.get(
            room, [("", subject or gi.subject)])
        self.emit("muc_subject_changed", room, list(subjects))

    def get_muc_info(self, room: str) -> None:
        """Request the advertised room name through XEP-0030."""
        asyncio.get_event_loop().create_task(self._fetch_muc_info(room))

    async def list_conference_rooms(self, server: str) -> list[dict]:
        """Return discoverable conference rooms on *server*."""
        if not server.strip():
            return []
        result = await self.xmpp.plugin["xep_0030"].get_items(jid=server)
        rooms = []
        for item in result.xml.iter():
            if not str(item.tag).endswith("item") or not item.get("jid"):
                continue
            jid = str(item.get("jid"))
            rooms.append({"jid": jid, "name": str(item.get("name") or jid.split("@", 1)[0]),
                          "private": False, "users": [], "occupants": ""})
        return rooms

    async def discover_conference_service(self) -> str:
        """Find the first conference service advertised by the account domain."""
        result = await self.xmpp.plugin["xep_0030"].get_items(
            jid=self.jid_str.split("@", 1)[-1])
        for item in result.xml.iter():
            service = str(item.get("jid") or "")
            if not service:
                continue
            try:
                info = await self.xmpp.plugin["xep_0030"].get_info(jid=service)
                if any(str(node.get("category", "")).lower() == "conference"
                       for node in info.xml.iter()
                       if str(node.tag).endswith("identity")):
                    return service
            except Exception:
                continue
        return ""

    async def discover_services(self, server: str) -> list[dict]:
        """Discover direct service items and classify their disco identities."""
        if not server.strip():
            return []
        result = await self.xmpp.plugin["xep_0030"].get_items(jid=server)
        services = []
        for node in result.xml.iter():
            if not str(node.tag).endswith("item") or not node.get("jid"):
                continue
            item = {"jid": str(node.get("jid")),
                    "node": str(node.get("node") or ""),
                    "name": str(node.get("name") or node.get("jid")),
                    "category": "", "type": "", "features": [], "items": []}
            try:
                info = await self.xmpp.plugin["xep_0030"].get_info(
                    jid=item["jid"], node=item["node"] or None)
                for identity in info.xml.iter():
                    if str(identity.tag).endswith("identity"):
                        item["category"] = str(identity.get("category") or "")
                        item["type"] = str(identity.get("type") or "")
                        break
                item["features"] = []
                for feature in info.xml.iter():
                    if str(feature.tag).endswith("feature"):
                        var = str(feature.get("var") or "")
                        if var:
                            item["features"].append(var)
            except Exception:
                pass
            services.append(item)
        return services

    async def discover_service_items(self, service: str, node: str = "") -> list[dict]:
        result = await self.xmpp.plugin["xep_0030"].get_items(
            jid=service, node=node or None)
        return [{"jid": str(item.get("jid")),
                 "node": str(item.get("node") or ""),
                 "name": str(item.get("name") or item.get("jid")),
                 "category": "", "type": "", "items": []}
                for item in result.xml.iter()
                if str(item.tag).endswith("item") and item.get("jid")]

    async def discover_service_info(self, service: str, node: str = "") -> dict:
        """Return the first disco identity and feature list of a service."""
        try:
            info = await self.xmpp.plugin["xep_0030"].get_info(
                jid=service, node=node or None)
        except Exception:
            return {"jid": service, "node": node, "name": service,
                    "category": "", "type": "", "features": []}
        features = [str(f.get("var") or "") for f in info.xml.iter()
                    if str(f.tag).endswith("feature") and f.get("var")]
        name = ""
        for element in info.xml.iter():
            if not str(element.tag).endswith("identity"):
                continue
            category = str(element.get("category") or "")
            type_ = str(element.get("type") or "")
            value = str(element.get("name") or "")
            if name == "" and value:
                name = value
            if category:
                return {"jid": service, "node": node, "name": name or service,
                        "category": category, "type": type_,
                        "features": features}
        return {"jid": service, "node": node, "name": name or service,
                "category": "", "type": "", "features": features}

    # ── Service actions: registration / search / ad-hoc commands ───────

    async def get_registration_form(self, jid: str) -> dict:
        """Return the XEP-0077 registration form of a service.

        Returns ``{"registered": bool, "form": ..., "fields": {...}}`` where
        *form* is an XEP-0004 form stanza (or None) and *fields* holds the
        legacy fields (username/password/...) when no data form is advertised.
        """
        iq = await self.xmpp["xep_0077"].get_registration(jid)
        reg = iq["register"]
        form = reg["form"] if reg["form"] and reg["form"].get_fields() else None
        # ``reg["fields"]`` is a set of field names (slixmpp), not pairs; build
        # the legacy {name: value} map and only when there is no data form.
        fields = None
        if form is None and reg["fields"]:
            fields = {str(name): str(reg[name] or "")
                      for name in reg["fields"]}
        instructions = str(reg["instructions"] or "")
        oob = ""
        try:
            oob = str(reg["oob"]["url"] or "")
        except (KeyError, TypeError):
            oob = ""
        if form is not None:
            _resolve_bob_media(form.xml, _bob_data_uris(iq.xml))
        return {"registered": bool(reg["registered"]), "form": form,
                "fields": fields, "instructions": instructions, "oob": oob}

    async def submit_registration(self, jid: str, values: dict[str, str],
                                  form=None) -> None:
        """Register (or update) an account at *jid* with *values*."""
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = jid
        if form is not None:
            self._fill_submit_form(iq["register"]["form"], form)
        else:
            allowed = getattr(type(iq["register"]), "form_fields", ())
            for key, value in values.items():
                if key in allowed:
                    iq["register"][key] = value
        await iq.send()
        return None

    @staticmethod
    def _fill_submit_form(submit, form) -> str:
        """Copy *form* fields (with current values) into a fresh submit form.

        Assigning a received form straight onto ``iq["search"]["form"]`` /
        ``iq["register"]["form"]`` does not serialize its fields (an empty
        ``<x type="form"/>`` goes on the wire), so each field is rebuilt on
        the target.  Returns the copied ``FORM_TYPE``.
        """
        submit.set_type("submit")
        form_type = ""
        for field in form["fields"]:
            var = str(field.get("var") or "")
            if not var:
                continue
            value = field.get("value")
            if var == "FORM_TYPE":
                if isinstance(value, list):
                    form_type = str(value[0]) if value else ""
                else:
                    form_type = str(value or "")
                continue
            if isinstance(value, bool):
                value = "1" if value else "0"
            target = submit.add_field(
                var, ftype=str(field.get("type") or "text-single"),
                required=bool(field.get("required", False)))
            if isinstance(value, list):
                target["value"] = [str(item) for item in value]
            elif value is not None:
                target["value"] = str(value)
        if form_type:
            submit.add_field("FORM_TYPE", value=form_type, ftype="hidden")
        return form_type

    async def unregister(self, jid: str) -> None:
        """Remove the current account registration at *jid* (XEP-0077)."""
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = jid
        iq["register"].set_remove(True)
        await iq.send()

    def _build_captcha_response(self, challenger: str, form):
        """Build (but do not send) a XEP-0158 CAPTCHA response IQ."""
        from slixmpp.plugins.xep_0004.stanza import Form
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = challenger
        captcha = ET.SubElement(iq.xml, "{%s}captcha" % NS_CAPTCHA)
        submit = Form()
        submit["type"] = "submit"
        self._fill_submit_form(submit, form)
        captcha.append(submit.xml)
        return iq

    async def answer_captcha(self, challenger: str, form) -> None:
        """Submit a solved XEP-0158 CAPTCHA form to *challenger*."""
        iq = self._build_captcha_response(challenger, form)
        logger.info("Answering CAPTCHA challenge from %s", challenger)
        await iq.send()

    async def change_password(self, new_password: str,
                              server: str | None = None) -> None:
        """Change the account password on the server (XEP-0077).

        Requires an authenticated session.  On success the in-memory password is
        updated so that an automatic reconnect authenticates with the new one.
        Raises on server errors (e.g. :class:`slixmpp.exceptions.IqError`).
        """
        await self.xmpp["xep_0077"].change_password(new_password, jid=server)
        self.xmpp.password = new_password

    async def get_search_form(self, jid: str) -> dict:
        """Return the XEP-0055 search form of a service.

        Returns ``{"form": Form|None, "fields": {name: default}}`` — the
        second form is used only for legacy (no data form) services.
        """
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        iq["to"] = jid
        iq.enable("search")
        result = await iq.send()
        search = result["search"]
        form = search["form"]
        if form and form.get_fields():
            return {"form": form, "fields": {}}
        fields: dict[str, str] = {}
        for child in search.xml:
            if not str(child.tag).startswith("{jabber:iq:search}"):
                continue
            key = str(child.tag).split("}")[-1]
            if key == "instructions":
                continue
            fields[key] = ""
        return {"form": None, "fields": fields}

    async def submit_search(self, jid: str, form=None,
                            values: dict[str, str] | None = None) -> dict:
        """Submit a XEP-0055 search.

        Returns ``{"rows": [{var: str}], "columns": [(var, label)]}``.
        """
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = jid
        if form is not None:
            self._fill_submit_form(iq["search"]["form"], form)
        else:
            for key, value in (values or {}).items():
                element = iq["search"].xml.makeelement(
                    f"{{jabber:iq:search}}{key}", {})
                element.text = str(value)
                iq["search"].xml.append(element)
        result = await iq.send()
        return self._parse_search_rows(result)

    @staticmethod
    def _parse_search_rows(result) -> dict:
        """Parse a XEP-0055 search response.

        Returns ``{"rows": [{var: str}], "columns": [(var, label)]}`` where
        columns describe the result table built from the reported fields.
        """
        rows: list[dict] = []
        for node in result.xml.iter():
            tag = str(node.tag)
            if tag.endswith("item") and "{jabber:iq:search}" in tag:
                jid_value = str(node.get("jid") or "")
                if jid_value:
                    rows.append({"jid": jid_value,
                                 "name": str(node.get("name") or "")})
        if rows:
            return {"rows": rows,
                    "columns": [("name", "name"), ("jid", "jid")]}
        columns: list[tuple[str, str]] = []
        form = result["search"]["form"]
        if form is not None and form["type"] == "result":
            for var, field in form.get_reported().items():
                label = str(field.get("label") or var)
                columns.append((str(var), label))
            if not columns:
                columns = [("jid", "JID")]
            for item in form["items"]:
                row = {}
                for var, value in item.items():
                    if var == "FORM_TYPE":
                        continue
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    else:
                        value = str(value or "")
                    row[str(var)] = value
                if row:
                    rows.append(row)
        return {"rows": rows, "columns": columns}

    async def get_entity_version(self, jid: str) -> dict:
        """Return software version info (XEP-0092) for *jid*.

        Returns ``{"software": str, "version": str, "os": str}`` with empty
        strings when the entity does not answer.
        """
        info = {"software": "", "version": "", "os": ""}
        try:
            result = await self.xmpp.plugin["xep_0092"].get_version(jid)
            version = result["software_version"]
            info["software"] = str(version.get("name", "") or "")
            info["version"] = str(version.get("version", "") or "")
            info["os"] = str(version.get("os", "") or "")
        except Exception:
            logger.debug("Software version unavailable for %s", jid)
        return info

    async def get_server_stats(self, jid: str) -> list[dict]:
        """XEP-0039 statistics of *jid*: ``[{name, units, value}]``.

        Asks the entity which statistics it supports and then requests their
        values in one query.  Returns ``[]`` when the entity does not answer.
        """
        names = await self._server_stat_names(jid)
        if not names:
            return []
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        iq["to"] = jid
        query = ET.SubElement(iq.xml, "{%s}query" % NS_STATS)
        for name in names:
            ET.SubElement(query, "{%s}stat" % NS_STATS).set("name", name)
        try:
            result = await iq.send(timeout=10)
        except Exception as exc:
            logger.debug("Statistics query failed for %s: %s", jid, exc)
            return []
        return [{"name": str(el.get("name") or ""),
                 "units": str(el.get("units") or ""),
                 "value": str(el.get("value") or "")}
                for el in result.xml.iter("{%s}stat" % NS_STATS)
                if el.get("name")]

    async def _server_stat_names(self, jid: str) -> list[str]:
        """The statistics names *jid* advertises (XEP-0039)."""
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        iq["to"] = jid
        ET.SubElement(iq.xml, "{%s}query" % NS_STATS)
        try:
            result = await iq.send(timeout=10)
        except Exception as exc:
            logger.debug("Statistics list failed for %s: %s", jid, exc)
            return []
        return [str(el.get("name") or "") for el in
                result.xml.iter("{%s}stat" % NS_STATS) if el.get("name")]

    async def get_server_uptime(self, jid: str) -> int | None:
        """XEP-0012: the entity's uptime in seconds (``None`` if unknown)."""
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        iq["to"] = jid
        ET.SubElement(iq.xml, "{%s}query" % NS_LAST)
        try:
            result = await iq.send(timeout=10)
        except Exception as exc:
            logger.debug("Last-activity query failed for %s: %s", jid, exc)
            return None
        for el in result.xml.iter("{%s}query" % NS_LAST):
            seconds = el.get("seconds")
            if seconds is not None:
                try:
                    return int(seconds)
                except (TypeError, ValueError):
                    return None
        return None

    async def get_commands_list(self, jid: str) -> list[dict]:
        """Return the XEP-0050 ad-hoc command list of a service."""
        node = "http://jabber.org/protocol/commands"
        result = await self.xmpp["xep_0030"].get_items(jid=jid, node=node)
        return [{"jid": str(item.get("jid") or jid),
                 "node": str(item.get("node") or ""),
                 "name": str(item.get("name") or item.get("node") or "")}
                for item in result.xml.iter()
                if str(item.tag).endswith("item") and item.get("node")]

    # ── Privacy lists / blocking (XEP-0016 / XEP-0191 / XEP-0377) ──

    def _server_feature(self, feature: str) -> bool:
        """Whether the account domain advertises *feature* (optimistic)."""
        features = getattr(self, "_server_features", None)
        if features is None:
            return True  # not probed yet — do not hide the UI
        return feature in features

    def supports_privacy(self) -> bool:
        """XEP-0016 privacy lists (`jabber:iq:privacy`)."""
        return self._server_feature(NS_PRIVACY)

    def supports_blocking(self) -> bool:
        """XEP-0191 blocking command (`urn:xmpp:blocking`)."""
        return self._server_feature(NS_BLOCKING)

    def supports_reports(self) -> bool:
        """XEP-0377 reports.

        Offered whenever blocking works: a report is a block with a nested
        ``<report/>``, and servers that support reports often do not announce
        ``urn:xmpp:reporting:1``.
        """
        return self.supports_blocking()

    async def refresh_server_features(self) -> None:
        """Cache the account domain's disco#info features for the gates."""
        domain = self.jid_str.split("@")[-1]
        try:
            info = await self.xmpp["xep_0030"].get_info(jid=domain)
            features = {str(el.get("var") or "") for el in info.xml.iter(
                "{%s}feature" % NS_DISCO_INFO)}
        except Exception:
            logger.debug("Server feature probe failed", exc_info=True)
            return
        self._server_features = features

    async def _privacy_iq(self, query, itype: str):
        iq = self.xmpp.Iq()
        iq["type"] = itype
        iq.xml.append(query)
        return await iq.send()

    async def get_privacy_lists(self) -> dict:
        """Return ``{"active", "default", "lists"}`` for the account."""
        result = await self._privacy_iq(privacy.lists_query(), "get")
        return privacy.parse_lists(result.xml)

    async def get_privacy_list(self, name: str) -> list[dict]:
        """Return the items of the privacy list *name*."""
        result = await self._privacy_iq(privacy.list_query(name, []), "get")
        return privacy.parse_list(result.xml, name)

    async def set_privacy_list(self, name: str, items: list[dict]) -> None:
        """Create or replace the privacy list *name*."""
        await self._privacy_iq(privacy.list_query(name, items), "set")

    async def remove_privacy_list(self, name: str) -> None:
        """Delete the privacy list *name* (an empty list removes it)."""
        await self._privacy_iq(privacy.list_query(name, []), "set")

    async def set_active_privacy_list(self, name: str) -> None:
        """Make *name* the active privacy list ("" deactivates)."""
        await self._privacy_iq(privacy.active_query(name), "set")

    async def set_default_privacy_list(self, name: str) -> None:
        """Make *name* the default privacy list ("" clears it)."""
        await self._privacy_iq(privacy.default_query(name), "set")

    async def get_blocked_jids(self) -> set[str]:
        """XEP-0191: fetch the blocklist and cache it.

        Uses ``get_blocked()`` and reads the items from the XML, because
        ``get_blocked_jids()`` only exists in newer slixmpp.
        """
        if not self.supports_blocking():
            return set()
        try:
            result = await self.xmpp["xep_0191"].get_blocked()
            blocked = _block_items(getattr(result, "xml", None))
        except Exception:
            logger.debug("Blocklist fetch failed", exc_info=True)
            return set(self._blocked)
        self._blocked = blocked
        return set(blocked)

    async def block_contact(self, jid: str) -> None:
        """XEP-0191: block *jid*."""
        await self.xmpp["xep_0191"].block(jid)
        self._blocked.add(str(jid))
        self.emit("blocklist_updated", set(self._blocked))

    async def unblock_contact(self, jid: str) -> None:
        """XEP-0191: unblock *jid*."""
        await self.xmpp["xep_0191"].unblock(jid)
        self._blocked.discard(str(jid))
        self.emit("blocklist_updated", set(self._blocked))

    async def report_contact(self, jid: str, reason: str = "spam",
                             text: str = "") -> None:
        """XEP-0377: block *jid* while attaching a spam/abuse report."""
        report_reason = ("urn:xmpp:reporting:abuse" if reason == "abuse"
                         else "urn:xmpp:reporting:spam")
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        block = ET.SubElement(iq.xml, "{%s}block" % NS_BLOCKING)
        item = ET.SubElement(block, "{%s}item" % NS_BLOCKING)
        item.set("jid", jid)
        report = ET.SubElement(item, "{%s}report" % NS_REPORTING)
        report.set("reason", report_reason)
        text = str(text or "").strip()
        if text:
            node = ET.SubElement(report, "{%s}text" % NS_REPORTING)
            node.set("{http://www.w3.org/XML/1998/namespace}lang",
                     _current_language())
            node.text = text
        await iq.send()
        self._blocked.add(str(jid))
        self.emit("blocklist_updated", set(self._blocked))

    def _on_blocked_push(self, iq) -> None:
        self._apply_block_push(iq, "block")

    def _on_unblocked_push(self, iq) -> None:
        self._apply_block_push(iq, "unblock")

    def _apply_block_push(self, iq, tag: str) -> None:
        """XEP-0191 §5: a push carries the full blocklist."""
        xml = getattr(iq, "xml", None)
        if xml is None:
            return
        self._blocked = _block_items(xml)
        self.emit("blocklist_updated", set(self._blocked))

    async def _load_blocklist(self) -> None:
        """Probe the domain features and fetch the XEP-0191 blocklist."""
        try:
            await self.refresh_server_features()
        except Exception:
            logger.debug("Server feature probe failed", exc_info=True)
        if not self.supports_blocking():
            return
        blocked = await self.get_blocked_jids()
        self.emit("blocklist_updated", set(blocked))

    async def start_command(self, jid: str, node: str) -> dict:
        """Start an ad-hoc command and await its first response."""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        session = {"next": self._command_handle(fut),
                   "error": self._command_error(fut),
                   "payload": None}
        self.xmpp["xep_0050"].start_command(jid, node, session)
        iq = await asyncio.wait_for(fut, timeout=30)
        return self._parse_command_result(iq, session)

    async def continue_command(self, session: dict, action: str = "next",
                               form=None) -> dict:
        """Continue an ad-hoc command with *form* data or *action*."""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        session["next"] = self._command_handle(fut)
        session["error"] = self._command_error(fut)
        session["payload"] = [form.xml] if form is not None else None
        plugin = self.xmpp["xep_0050"]
        if action == "cancel":
            plugin.cancel_command(session)
        elif action == "complete":
            plugin.complete_command(session)
        else:
            plugin.continue_command(session, action)
        iq = await asyncio.wait_for(fut, timeout=30)
        return self._parse_command_result(iq, session)

    def _parse_command_result(self, iq, session: dict) -> dict:
        if iq["type"] == "error":
            return {"session": session, "error": self._command_error_text(iq),
                    "form": None, "actions": [], "notes": [], "status": ""}
        command = iq["command"]
        form = command["form"]
        return {"session": session,
                "sessionid": command["sessionid"],
                "status": command["status"],
                "form": form if form and form.get_fields() else None,
                "actions": sorted(command["actions"] or ()),
                "notes": list(command["notes"] or ()) or [],
                "error": ""}

    @staticmethod
    def _command_error_text(iq) -> str:
        if iq["type"] != "error":
            return ""
        return iq["error"]["text"] or iq["error"]["condition"] or "error"

    @classmethod
    def _command_error(cls, fut: asyncio.Future):
        def handler(iq, session):
            if not fut.done():
                cond = (iq["error"]["text"] or iq["error"]["condition"]
                        if iq["type"] == "error" else "command error")
                fut.set_exception(Exception(cond))
        return handler

    @staticmethod
    def _command_handle(fut: asyncio.Future):
        def handler(iq, session):
            if not fut.done():
                fut.set_result(iq)
        return handler

    async def _fetch_muc_info(self, room: str) -> None:
        try:
            iq = await self.xmpp.plugin["xep_0030"].get_info(jid=room)
            info = iq["disco_info"]
            name = ""
            for element in iq.xml.iter():
                if not str(element.tag).endswith("identity"):
                    continue
                category = str(element.get("category", ""))
                value = str(element.get("name", "") or "")
                if category == "conference" and value:
                    name = value
                    break
                if value and not name:
                    name = value
            for element in iq.xml.iter():
                if not str(element.tag).endswith("field"):
                    continue
                if element.get("var") != "muc#roomconfig_roomname":
                    continue
                value = next((child.text or "" for child in element
                              if str(child.tag).endswith("value")), "").strip()
                if value:
                    name = value
                    break
            features = {str(el.get("var") or "")
                        for el in iq.xml.iter()
                        if str(el.tag).endswith("feature")}
            if name:
                logger.info("MUC room name received for %s: %s", room, name)
            self.emit("muc_info_received", room, name, features)
        except Exception:
            logger.debug("Could not retrieve MUC info for %s",
                         room, exc_info=True)

    def probe_entity(self, jid: str) -> None:
        asyncio.get_event_loop().create_task(self._probe_entity(jid))

    async def _probe_entity(self, jid: str) -> None:
        info: dict[str, str] = {}
        try:
            result = await self.xmpp.plugin["xep_0092"].get_version(jid)
            version = result["software_version"]
            info["software"] = str(version.get("name", "") or "")
            info["version"] = str(version.get("version", "") or "")
            info["os"] = str(version.get("os", "") or "")
        except Exception:
            logger.debug("Software version unavailable for %s", jid)
        try:
            info["ping"] = f"{await self.xmpp.plugin['xep_0199'].ping(jid, timeout=5):.3f}s"
        except Exception:
            logger.debug("Ping unavailable for %s", jid)
        try:
            result = await self._get_entity_time(jid)
            utc = result.get("utc", "")
            tzo = result.get("tzo", "")
            info["client_time"] = (f"{utc} ({tzo})".strip()
                                   if tzo else utc)
        except Exception:
            logger.debug("Entity time unavailable for %s", jid)
        self.emit("entity_info_received", jid, info)

    def _store_muc_history(self, room: str, entries) -> None:
        """Persist messages returned by the MUC join handshake."""
        if not entries:
            return
        from stanza_im.core import history
        gi = self.groupchats.get(room)
        my_nick = gi.nick if gi else ""
        rows: list[dict] = []
        for entry in entries:
            try:
                forwarded = entry.get("forwarded") if hasattr(entry, "get") else None
                msg = _forwarded_stanza(forwarded) or entry
                body = str(_stanza_value(msg, "body") or "")
                if not body:
                    continue
                frm = str(_stanza_value(msg, "from") or "")
                nick = frm.split("/", 1)[1] if "/" in frm else frm
                direction = "outgoing" if nick == my_nick else "incoming"
                sender = "Me" if direction == "outgoing" else nick
                stamp = _stanza_value(_stanza_value(msg, "delay"), "stamp")
                if isinstance(stamp, datetime.datetime):
                    stamp = stamp.strftime("%Y-%m-%dT%H:%M:%S")
                rows.append({
                    "direction": direction,
                    "body": body,
                    "timestamp": _normalize_ts(str(stamp)) or None,
                    "sender": sender,
                    "origin_id": _stanza_id(msg, room) or "",
                    "reply_to": _reply_reference(msg)[0],
                    "reply_id": _reply_reference(msg)[1],
                })
            except Exception:
                logger.debug("Could not store MUC join history for %s",
                             room, exc_info=True)
        if rows:
            self._start_task(history.store_many_async(room, rows))

    def _muc_task_done(self, room: str, task) -> None:
        """Consume the join task's result so asyncio never warns about an
        unretrieved exception (the failure was already emitted/logged)."""
        if self._muc_join_tasks.get(room) is task:
            self._muc_join_tasks.pop(room, None)
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _bookmarks2_compat_mode(self) -> str:
        """Return ``"unified"`` when the server unifies bookmarks, else ``"dual"``.

        XEP-0402 §5.3/§6: ``urn:xmpp:bookmarks:1#compat`` (Private XML) and
        ``urn:xmpp:bookmarks:1#compat-pep`` (XEP-0223) are announced when the
        server keeps the legacy and PEP bookmark lists in sync.  Without them
        we publish to both stores.
        """
        if self._bookmarks2_compat is not None:
            return self._bookmarks2_compat
        mode = "dual"
        try:
            info = await self.xmpp["xep_0030"].get_info(jid=self.jid_str)
            features = {str(el.get("var") or "") for el in info.xml.iter()
                        if str(el.tag).endswith("feature")}
            if features & {NS_BOOKMARKS2_COMPAT, NS_BOOKMARKS2_COMPAT_PEP}:
                mode = "unified"
        except Exception:
            logger.debug("Bookmark compatibility disco#info failed",
                         exc_info=True)
        self._bookmarks2_compat = mode
        return mode

    async def _bookmarks2_get(self) -> list[dict] | None:
        """Fetch the XEP-0402 bookmark node; ``None`` when it is unavailable."""
        try:
            result = await self.xmpp["xep_0060"].get_items(
                self.jid_str, NS_BOOKMARKS2)
        except Exception:
            logger.debug("XEP-0402 bookmarks fetch failed", exc_info=True)
            return None
        xml = getattr(result, "xml", None)
        return _parse_bookmarks2(xml)

    # ── PEP manager (pubsub#owner / disco) ────────────────────────

    async def pep_list_nodes(self) -> list[dict] | None:
        """List our PEP nodes via ``disco#items`` on our own bare JID.

        Returns ``[{node, name, jid}]`` (items without a ``node`` attribute —
        the account's resources — are skipped), or ``None`` on failure.
        """
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        iq["to"] = self.jid_str
        ET.SubElement(iq.xml, "{%s}query" % NS_DISCO_ITEMS)
        try:
            result = await iq.send(timeout=10)
        except Exception:
            logger.debug("PEP disco#items failed", exc_info=True)
            return None
        nodes: list[dict] = []
        xml = getattr(result, "xml", None)
        if xml is not None:
            for item in xml.iter("{%s}item" % NS_DISCO_ITEMS):
                node = str(item.get("node") or "")
                if not node:
                    continue
                nodes.append({
                    "node": node,
                    "name": str(item.get("name") or ""),
                    "jid": str(item.get("jid") or ""),
                })
        return nodes

    async def pep_get_node_items(self, node: str):
        """Fetch the items of a PEP *node*; returns the result XML or ``None``."""
        if not node:
            return None
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        pubsub = ET.SubElement(iq.xml, "{%s}pubsub" % NS_PUBSUB)
        items = ET.SubElement(pubsub, "{%s}items" % NS_PUBSUB)
        items.set("node", node)
        try:
            result = await iq.send(timeout=10)
        except Exception:
            logger.debug("PEP items fetch for %s failed", node, exc_info=True)
            return None
        return getattr(result, "xml", None)

    async def pep_get_node_config(self, node: str):
        """Fetch a PEP node's configuration form (XEP-0060 §8.2).

        Returns a slixmpp ``Form`` (for ``DataFormWidget``) or ``None``.
        """
        if not node:
            return None
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        pubsub = ET.SubElement(iq.xml,
                               "{%s}pubsub" % NS_PUBSUB_OWNER)
        configure = ET.SubElement(pubsub,
                                  "{%s}configure" % NS_PUBSUB_OWNER)
        configure.set("node", node)
        try:
            result = await iq.send(timeout=10)
        except Exception:
            logger.debug("PEP config fetch for %s failed", node, exc_info=True)
            return None
        xml = getattr(result, "xml", None)
        if xml is None:
            return None
        from slixmpp.plugins.xep_0004.stanza import Form
        for child in xml.iter("{%s}x" % NS_DATA):
            if child.get("type") == "form":
                try:
                    return Form(xml=child)
                except Exception:
                    logger.debug("Could not parse PEP config form",
                                 exc_info=True)
                    return None
        return None

    async def pep_set_node_config(self, node: str, form) -> bool:
        """Submit a node configuration form (``pubsub#owner configure``)."""
        if not node or form is None:
            return False
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        pubsub = ET.SubElement(iq.xml, "{%s}pubsub" % NS_PUBSUB_OWNER)
        configure = ET.SubElement(pubsub,
                                  "{%s}configure" % NS_PUBSUB_OWNER)
        configure.set("node", node)
        try:
            configure.append(form.xml)
            await iq.send(timeout=10)
            return True
        except Exception:
            logger.debug("PEP config submit for %s failed", node, exc_info=True)
            return False

    async def pep_delete_node(self, node: str) -> bool:
        """Delete a PEP node (``pubsub#owner delete``)."""
        if not node:
            return False
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        pubsub = ET.SubElement(iq.xml, "{%s}pubsub" % NS_PUBSUB_OWNER)
        delete = ET.SubElement(pubsub, "{%s}delete" % NS_PUBSUB_OWNER)
        delete.set("node", node)
        try:
            await iq.send(timeout=10)
            return True
        except Exception:
            logger.debug("PEP delete of %s failed", node, exc_info=True)
            return False

    async def _bookmarks2_publish(self, room: str, nick: str, password: str,
                                  autojoin: bool, name: str) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        pubsub = ET.SubElement(iq.xml, "{%s}pubsub" % NS_PUBSUB)
        publish = ET.SubElement(pubsub, "{%s}publish" % NS_PUBSUB)
        publish.set("node", NS_BOOKMARKS2)
        item = ET.SubElement(publish, "{%s}item" % NS_PUBSUB)
        item.set("id", room)
        item.append(_build_bookmarks2_conference(nick, password, autojoin,
                                                 name))
        options = ET.SubElement(pubsub, "{%s}publish-options" % NS_PUBSUB)
        form = ET.SubElement(options, "{%s}x" % NS_DATA)
        form.set("type", "submit")
        _bookmarks2_publish_options(form)
        await iq.send()

    async def _bookmarks2_retract(self, room: str) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        pubsub = ET.SubElement(iq.xml, "{%s}pubsub" % NS_PUBSUB)
        retract = ET.SubElement(pubsub, "{%s}retract" % NS_PUBSUB)
        retract.set("node", NS_BOOKMARKS2)
        retract.set("notify", "true")
        item = ET.SubElement(retract, "{%s}item" % NS_PUBSUB)
        item.set("id", room)
        await iq.send()

    async def save_bookmark(self, room: str, nick: str, password: str = "",
                            autojoin: bool = True, name: str = "") -> None:
        """Save (or update) a conference bookmark.

        XEP-0402 (PEP Native Bookmarks) is the primary store; when the server
        does not unify bookmarks (no ``#compat``/``#compat-pep``) the legacy
        XEP-0048 storage is updated too, so older clients keep working.
        """
        saved = False
        try:
            await self._bookmarks2_publish(room, nick, password, autojoin,
                                           name)
            saved = True
        except Exception:
            logger.debug("XEP-0402 bookmark publish failed for %s", room,
                         exc_info=True)
        if not saved or await self._bookmarks2_compat_mode() == "dual":
            await self._save_bookmark_legacy(room, nick, password, autojoin,
                                             name)

    async def list_bookmarks(self) -> list[dict]:
        """Return conference bookmarks (XEP-0402, else XEP-0048).

        When the XEP-0402 node is empty but legacy bookmarks exist, they are
        migrated into the new node on first read.
        """
        bookmarks = await self._bookmarks2_get()
        if bookmarks:
            return bookmarks
        legacy = await self._list_bookmarks_legacy()
        if bookmarks is None:
            return legacy
        if legacy:
            for bookmark in legacy:
                try:
                    await self._bookmarks2_publish(
                        bookmark["jid"], bookmark["nick"],
                        bookmark["password"], bookmark["autojoin"],
                        bookmark["name"])
                except Exception:
                    logger.debug("Bookmark migration failed for %s",
                                 bookmark["jid"], exc_info=True)
        return legacy

    async def remove_bookmark(self, room: str) -> None:
        """Remove a conference bookmark (XEP-0402 and legacy when needed)."""
        removed = False
        try:
            await self._bookmarks2_retract(room)
            removed = True
        except Exception:
            logger.debug("XEP-0402 bookmark retract failed for %s", room,
                         exc_info=True)
        if not removed or await self._bookmarks2_compat_mode() == "dual":
            await self._remove_bookmark_legacy(room)

    # ── Private XML Storage notes (XEP-0049, Miranda format) ──────────

    async def get_notes(self) -> list[dict]:
        """Fetch the text notes stored in private storage.

        A single IQ gets the whole set; each ``<note tags title text>`` becomes
        ``{"title", "tags", "text"}``.  An empty/missing storage yields ``[]``.
        """
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        query = ET.SubElement(iq.xml, "{%s}query" % NS_PRIVATE)
        ET.SubElement(query, "{%s}storage" % NS_NOTES)
        result = await iq.send(timeout=15)
        return _parse_notes(result.xml)

    async def set_notes(self, notes: list[dict]) -> None:
        """Store the whole note set in private storage in one IQ."""
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        query = ET.SubElement(iq.xml, "{%s}query" % NS_PRIVATE)
        storage = ET.SubElement(query, "{%s}storage" % NS_NOTES)
        for note in notes:
            element = ET.SubElement(storage, "{%s}note" % NS_NOTES)
            element.set("tags", str(note.get("tags", "") or ""))
            ET.SubElement(element, "{%s}title" % NS_NOTES).text = str(
                note.get("title", "") or "")
            ET.SubElement(element, "{%s}text" % NS_NOTES).text = str(
                note.get("text", "") or "")
        await iq.send(timeout=15)

    async def _save_bookmark_legacy(self, room: str, nick: str,
                                    password: str = "", autojoin: bool = True,
                                    name: str = "") -> None:
        """Save (or update) a conference bookmark for *room* (XEP-0048)."""
        from slixmpp.plugins.xep_0048 import Bookmarks

        plugin = self.xmpp.plugin["xep_0048"]
        bookmarks: Bookmarks | None = None
        try:
            result = await plugin.get_bookmarks()
            if plugin.storage_method == "xep_0223":
                bookmarks = result["pubsub"]["items"]["item"]["bookmarks"]
            else:
                bookmarks = result["private"]["bookmarks"]
        except Exception:
            pass
        if bookmarks is None:
            bookmarks = Bookmarks()
        existing = [c for c in bookmarks["conferences"] if c["jid"] != room]
        bookmarks = Bookmarks()
        for conf in existing:
            bookmarks.add_conference(conf["jid"], conf["nick"], name=conf.get("name"),
                                      autojoin=conf["autojoin"],
                                     password=conf["password"])
        bookmarks.add_conference(room, nick, name=name or None,
                                  autojoin=bool(autojoin), password=password)
        if not name:
            # slixmpp would store the JID as the name; XEP-0048's name is
            # optional, so drop it entirely when the caller gave none.
            for conf in bookmarks["conferences"]:
                if str(conf["jid"]) == room:
                    try:
                        del conf["name"]
                    except Exception:
                        pass
                    break
        try:
            await plugin.set_bookmarks(bookmarks)
            logger.debug("Saved bookmark for room %s", room)
        except Exception:
            logger.exception("Failed to save bookmark for %s", room)

    async def _list_bookmarks_legacy(self) -> list[dict]:
        """Return conference bookmarks stored through XEP-0048."""
        plugin = self.xmpp.plugin["xep_0048"]
        try:
            result = await plugin.get_bookmarks()
            if plugin.storage_method == "xep_0223":
                bookmarks = result["pubsub"]["items"]["item"]["bookmarks"]
            else:
                bookmarks = result["private"]["bookmarks"]
            return [
                {
                    "jid": str(conf["jid"]),
                    "nick": str(conf["nick"] or ""),
                    "password": str(conf["password"] or ""),
                    "autojoin": bool(conf["autojoin"]),
                    "name": str(conf.get("name") or ""),
                }
                for conf in bookmarks["conferences"]
                if conf["jid"]
            ]
        except Exception:
            logger.debug("Could not read bookmarks", exc_info=True)
            return []

    async def _remove_bookmark_legacy(self, room: str) -> None:
        """Remove a conference bookmark from XEP-0048 storage."""
        from slixmpp.plugins.xep_0048 import Bookmarks

        plugin = self.xmpp.plugin["xep_0048"]
        try:
            result = await plugin.get_bookmarks()
            if plugin.storage_method == "xep_0223":
                old = result["pubsub"]["items"]["item"]["bookmarks"]
            else:
                old = result["private"]["bookmarks"]
            bookmarks = Bookmarks()
            for conf in old["conferences"]:
                if str(conf["jid"]) != room:
                    bookmarks.add_conference(
                        conf["jid"], conf["nick"], name=conf.get("name"),
                        autojoin=conf["autojoin"], password=conf["password"])
            await plugin.set_bookmarks(bookmarks)
        except Exception:
            logger.exception("Failed to remove bookmark for %s", room)

    def _handle_bookmarks2_event(self, jid: str, items) -> None:
        """XEP-0402: react to our own bookmark node changes (other resources)."""
        if jid and self.jid_str and jid != self.jid_str:
            return
        joins: list[tuple[str, str, str]] = []
        leaves: list[str] = []
        for child in items:
            if child.tag == "{%s}item" % NS_PUBSUB_EVENT:
                room = str(child.get("id") or "")
                conf = child.find("{%s}conference" % NS_BOOKMARKS2)
                if not room or conf is None:
                    continue
                if conf.get("autojoin", "") in ("1", "true"):
                    nick = conf.findtext("{%s}nick" % NS_BOOKMARKS2) or ""
                    password = (conf.findtext("{%s}password"
                                              % NS_BOOKMARKS2) or "")
                    joins.append((room, nick, password))
                else:
                    leaves.append(room)
            elif child.tag == "{%s}retract" % NS_PUBSUB_EVENT:
                room = str(child.get("id") or "")
                if room:
                    leaves.append(room)
        self._start_task(self._bookmarks2_apply(joins, leaves))

    async def _bookmarks2_apply(self, joins: list[tuple[str, str, str]],
                                leaves: list[str]) -> None:
        for room, nick, password in joins:
            if room in self.groupchats:
                continue
            logger.info("Bookmark notification: joining %s", room)
            self.autojoin_rooms.add(room)
            self.join_muc(room, nick or self.jid_str.split("@")[0],
                          password=password, save_bookmark=False)
        for room in leaves:
            if room in self.groupchats:
                logger.info("Bookmark notification: leaving %s", room)
                self.leave_muc(room)
        try:
            bookmarks = await self.list_bookmarks()
        except Exception:
            bookmarks = []
        self.emit("bookmarks_changed", bookmarks)

    def leave_muc(self, room: str, reason: str = "") -> None:
        """Leave a Multi-User Chat room."""
        muc = self.xmpp.plugin["xep_0045"]
        nick = self.groupchats[room].nick if room in self.groupchats else ""
        muc.leave_muc(room, nick, msg=reason)
        task = self._muc_join_tasks.pop(room, None)
        if task and not task.done():
            task.cancel()
        self.groupchats.pop(room, None)
        self._muc_last_activity.pop(room, None)
        self._muc_self_ping_busy.discard(room)

    # ── XEP-0410 MUC self-ping (Schrödinger's chat) ───────────────

    def _mark_muc_activity(self, room: str) -> None:
        """Record inbound traffic from *room* (self-ping idle timer)."""
        if not room:
            return
        activity = getattr(self, "_muc_last_activity", None)
        if activity is None:
            activity = self._muc_last_activity = {}
        activity[room] = time.monotonic()

    def _start_muc_self_ping(self) -> None:
        if (self._muc_self_ping_task is not None
                and not self._muc_self_ping_task.done()):
            return
        self._muc_self_ping_task = asyncio.get_event_loop().create_task(
            self._muc_self_ping_loop())

    def _stop_muc_self_ping(self) -> None:
        task, self._muc_self_ping_task = self._muc_self_ping_task, None
        if task is not None:
            task.cancel()

    async def _muc_self_ping_loop(self) -> None:
        """Periodically verify that silent rooms still know us (XEP-0410)."""
        while True:
            await asyncio.sleep(_MUC_SELF_PING_INTERVAL)
            if not self.xmpp.is_connected():
                continue
            now = time.monotonic()
            for room, gi in list(self.groupchats.items()):
                if not gi.joined or not gi.nick:
                    continue
                last = self._muc_last_activity.get(room)
                if last is None:
                    self._muc_last_activity[room] = now
                    continue
                if now - last < _MUC_SELF_PING_IDLE:
                    continue
                if room in self._muc_self_ping_busy:
                    continue
                self._muc_self_ping_busy.add(room)
                self._start_task(self._self_ping_room(room))

    async def _self_ping_room(self, room: str) -> None:
        """Ping our own occupant JID; rejoin when the room does not know us."""
        gi = self.groupchats.get(room)
        try:
            if gi is None or not gi.joined or not gi.nick:
                return
            iq = self.xmpp.Iq()
            iq["type"] = "get"
            iq["to"] = f"{room}/{gi.nick}"
            ET.SubElement(iq.xml, "{%s}ping" % NS_PING)
            try:
                await iq.send(timeout=30)
                logger.debug("MUC self-ping to %s succeeded", room)
                self._mark_muc_activity(room)
                return
            except slixmpp.exceptions.IqTimeout:
                # The MUC service (or another client) is unreachable: retry.
                logger.debug("MUC self-ping to %s timed out", room)
                return
            except slixmpp.exceptions.IqError as exc:
                condition = str(getattr(exc, "condition", "") or "")
                if condition in ("service-unavailable", "feature-not-implemented",
                                 "item-not-found", "remote-server-not-found",
                                 "remote-server-timeout"):
                    # Still joined (or undecidable): do not rejoin.
                    self._mark_muc_activity(room)
                    return
                logger.info("MUC %s self-ping failed (%s); rejoining",
                            room, condition or exc)
            except Exception:
                logger.debug("MUC self-ping to %s errored", room, exc_info=True)
                return
            # Any other error means we are no longer an occupant.
            self.join_muc(room, gi.nick, password=gi.password)
        finally:
            self._muc_self_ping_busy.discard(room)

    def send_muc_message(self, room: str, body: str, reply_to: str = "",
                         reply_id: str = "", reply_ref_sender: str = "",
                         reply_ref_body: str = "", replace_id: str = "",
                         media: dict | None = None) -> None:
        """Send a message to a MUC room, optionally replying or correcting."""
        self.send_message(room, body, mtype="groupchat",
                          reply_to=reply_to, reply_id=reply_id,
                          reply_ref_sender=reply_ref_sender,
                          reply_ref_body=reply_ref_body,
                          replace_id=replace_id, media=media)

    def edit_message(self, jid: str, body: str, replace_id: str,
                     mtype: str = "chat") -> str:
        """Send a XEP-0308 correction replacing *replace_id* with *body*."""
        return self.send_message(jid, body, mtype=mtype, replace_id=replace_id)

    def request_voice(self, room: str) -> bool:
        """Ask the room for voice (XEP-0045 §7.13).

        A visitor submits a ``muc#request`` data form (``muc#role`` =
        ``participant``) in a ``<message>`` addressed to the room; per the XEP
        the message carries **no** ``type`` (a ``groupchat`` type is treated as
        a broadcast and rejected with ``forbidden``) and no ``from`` (the
        server stamps it — a client-supplied ``from`` closes the stream with
        ``invalid-from``).
        """
        if not isinstance(room, str) or not room.strip():
            return False
        room = room.strip()
        from slixmpp.plugins.xep_0004.stanza import Form, FormField
        msg = self.xmpp.Message()
        msg["to"] = room
        form = Form()
        form["type"] = "submit"
        fmt = FormField()
        fmt["var"] = "FORM_TYPE"
        fmt["type"] = "hidden"  # XEP-0004: FORM_TYPE is always hidden
        fmt["value"] = "http://jabber.org/protocol/muc#request"
        role = FormField()
        role["var"] = "muc#role"
        role["type"] = "list-single"
        role["value"] = "participant"
        form.append(fmt)
        form.append(role)
        msg.append(form)
        msg_id = str(msg["id"] or "")
        if not msg_id:
            msg_id = uuid.uuid4().hex
            msg["id"] = msg_id
        # Remember the id so a server error reply (e.g. a throttled request)
        # can be attributed to this voice request.
        if len(self._voice_requests) > 64:
            self._voice_requests.clear()
        self._voice_requests.add(msg_id)
        logger.debug("VOICE request to %s (id=%s)", room, msg_id)
        msg.send()
        return True

    def _voice_request_error(self, msg) -> tuple[str, str, str] | None:
        """Return ``(room, condition, text)`` for a voice-request error reply."""
        if str(msg.get("type", "") or "") != "error":
            return None
        msg_id = str(msg["id"] or "")
        xml = getattr(msg, "xml", None)
        has_form = False
        if xml is not None:
            form = xml.find("{jabber:x:data}x")
            if form is not None:
                for field in form.iter("{jabber:x:data}field"):
                    if field.get("var") != "FORM_TYPE":
                        continue
                    value = next((c.text or "" for c in field
                                  if c.tag == "{jabber:x:data}value"), "")
                    has_form = value.strip() == NS_MUC_REQUEST
                    break
        if msg_id not in self._voice_requests and not has_form:
            return None
        self._voice_requests.discard(msg_id)
        frm = str(msg["from"] or "")
        room = frm.split("/", 1)[0]
        condition = ""
        err_text = ""
        if xml is not None:
            err = xml.find("{jabber:client}error")
            if err is not None:
                for child in err:
                    tag = str(child.tag).rsplit("}", 1)[-1]
                    if tag == "text":
                        text = (child.text or "").strip()
                        if text and not err_text:
                            err_text = text
                    elif tag not in ("text",) and not condition:
                        condition = tag
        return room, condition, err_text

    async def grant_voice(self, room: str, nick: str, jid: str = "") -> None:
        """Grant voice to an occupant (XEP-0045 §8.3).

        The moderator sends ``<iq type='set'><query xmlns='muc#admin'>
        <item nick='…' role='participant'/></query></iq>``.  *nick* is the
        occupant's room nickname; when it is unknown the bare/full *jid* is
        used instead (``<item jid=…>``).
        """
        muc = self.xmpp.plugin["xep_0045"]
        if nick:
            await muc.set_role(room, nick, "participant", reason="")
            return
        iq = self.xmpp.make_iq_set(ito=room)
        item = iq["mucadmin_query"]["item"]
        item["jid"] = jid
        item["role"] = "participant"
        await iq.send()

    def set_muc_role(self, room: str, nick: str, role: str) -> None:
        """Request a MUC role change for an occupant."""
        result = self.xmpp.plugin["xep_0045"].set_role(
            room, nick, role, reason="")
        if asyncio.iscoroutine(result):
            asyncio.get_event_loop().create_task(result)

    async def muc_get_config(self, room: str):
        """Fetch the room configuration form (XEP-0045 ``muc#owner``)."""
        muc = self.xmpp.plugin["xep_0045"]
        return await muc.get_room_config(room)

    async def muc_set_config(self, room: str, values: dict) -> None:
        """Submit a room configuration (XEP-0045 ``muc#owner``).

        *values* is a ``{var: value}`` mapping; a fresh ``type='submit'`` form
        is built so the server's own form (with labels/options) is never
        mutated by slixmpp's submit handling.
        """
        from slixmpp.plugins.xep_0004.stanza import Form, FormField
        form = Form()
        form["type"] = "submit"
        for var, value in values.items():
            field = FormField()
            field["var"] = var
            # slixmpp serialises form values as strings (it calls str methods
            # on them), so an int here raises "'int' object has no attribute
            # 'replace'" — always submit strings.
            field["value"] = value if isinstance(value, str) else str(value)
            form.append(field)
        muc = self.xmpp.plugin["xep_0045"]
        await muc.set_room_config(room, form)

    @staticmethod
    def muc_creation_values(opts: dict) -> dict:
        """Map the "create conference" options to XEP-0045 config values.

        * ``persistent``    → ``muc#roomconfig_persistentroom``
        * ``invisible``     → ``muc#roomconfig_publicroom`` (negated)
        * ``members_only``  → ``muc#roomconfig_membersonly``
        * ``anonymous``     → ``muc#roomconfig_whois`` (moderators/anyone)
        * ``name``          → ``muc#roomconfig_roomname`` (when non-empty)
        """
        opts = opts or {}
        # Boolean XEP-0045 fields are submitted as "1"/"0" strings (see
        # ``muc_set_config``); the whois selector is a value string.
        values: dict = {
            "muc#roomconfig_persistentroom": "1" if opts.get("persistent") else "0",
            "muc#roomconfig_publicroom": "0" if opts.get("invisible") else "1",
            "muc#roomconfig_membersonly": "1" if opts.get("members_only") else "0",
            "muc#roomconfig_whois": ("moderators" if opts.get("anonymous")
                                     else "anyone"),
        }
        name = str(opts.get("name") or "").strip()
        if name:
            values["muc#roomconfig_roomname"] = name
        return values

    async def muc_get_affiliations(self, room: str) -> dict:
        """Return ``{affiliation: [{"jid", "nick", "reason"}]}`` for *room*.

        slixmpp's ``get_affiliation_list`` keeps only the JIDs, so the admin
        IQ is built here to also read the optional ``<reason>`` (the
        "note" shown in the room-management dialog).  A failing category
        (e.g. an admin without access to the owner list) is left empty.
        """
        out: dict[str, list[dict]] = {
            aff: [] for aff in ("owner", "admin", "member", "outcast")}
        for aff in out:
            try:
                iq = self.xmpp.make_iq_get(ito=room)
                iq["mucadmin_query"]["item"]["affiliation"] = aff
                result = await iq.send()
                for item in result["mucadmin_query"]:
                    jid = str(item["jid"] or "")
                    if not jid:
                        continue
                    out[aff].append({
                        "jid": jid,
                        "nick": str(item["nick"] or ""),
                        "reason": str(item["reason"] or ""),
                    })
            except Exception:
                logger.debug("MUC %s list for %s failed", aff, room,
                             exc_info=True)
        return out

    async def muc_set_affiliation(self, room: str, jid: str,
                                  affiliation: str, reason: str = "") -> None:
        """Change *jid*'s affiliation; ``none`` removes it from the list."""
        muc = self.xmpp.plugin["xep_0045"]
        await muc.set_affiliation(room, affiliation, jid=jid, reason=reason)

    # ── XEP-0317 Hats ─────────────────────────────────────────────

    async def room_supports_hats(self, room: str) -> bool:
        """True when *room* advertises ``urn:xmpp:hats:0`` (cached)."""
        cached = self._hats_support.get(room)
        if cached is not None:
            return cached
        try:
            result = await self.xmpp["xep_0030"].get_info(jid=room)
            features = {str(el.get("var") or "") for el in result.xml.iter()
                        if str(el.tag).endswith("feature")}
        except Exception:
            logger.debug("Hats disco#info for %s failed", room, exc_info=True)
            return False
        supported = hats_mod.NS_HATS in features
        self._hats_support[room] = supported
        return supported

    async def room_supports_moderation(self, room: str) -> bool:
        """True when *room* advertises ``urn:xmpp:message-moderate:1``.

        The result is cached per room (XEP-0425 §2).
        """
        cached = self._moderation_support.get(room)
        if cached is not None:
            return cached
        try:
            result = await self.xmpp["xep_0030"].get_info(jid=room)
            features = {str(el.get("var") or "") for el in result.xml.iter()
                        if str(el.tag).endswith("feature")}
        except Exception:
            logger.debug("Moderation disco#info for %s failed", room,
                         exc_info=True)
            return False
        supported = NS_MODERATE in features
        self._moderation_support[room] = supported
        return supported

    def _hats_command(self, room: str, node: str, values: dict | None = None,
                      sessionid: str = "", action: str = "execute"):
        """Build a Hats ad-hoc command IQ (not sent), used by tests too."""
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = room
        iq.xml.append(
            hats_mod.build_command(node, values, sessionid, action))
        return iq

    @staticmethod
    def _hats_rows(root) -> list[dict]:
        rows = []
        for row in hats_mod.parse_result_form(root):
            uri = str(row.get("hats#uri") or "")
            rows.append({
                "uri": uri,
                "title": str(row.get("hats#title") or uri),
                "hue": hats_mod.parse_hue(row.get("hats#hue")),
                "jid": str(row.get("hats#jid") or ""),
            })
        return rows

    async def _hats_submit(self, room: str, node: str,
                           values: dict) -> None:
        """Execute a two-step Hats command (execute → complete form).

        The submit action is taken from the server's ``<actions/>`` (some
        servers, e.g. ejabberd, require the literal ``complete``), and the
        URI field is renamed to whatever var the server's form declares
        (``hat`` for destroy/assign/unassign on ejabberd).
        """
        first = await self._hats_command(room, node).send()
        sessionid, status = hats_mod.command_session(first.xml)
        if status == "completed":
            return
        data = dict(values)
        uri = data.pop("hats#uri", "")
        if uri:
            data[hats_mod.uri_field_var(first.xml)] = uri
        action = hats_mod.submit_action(first.xml)
        logger.debug("Hats %s submit action=%s fields=%s", node, action,
                     sorted(data))
        result = await self._hats_command(
            room, node, data, sessionid, action).send()
        error = hats_mod.command_error(result.xml)
        if error:
            raise Exception(error)

    async def hats_list(self, room: str) -> list[dict]:
        """Return the hats configured in *room* (title/uri/hue)."""
        result = await self._hats_command(room, hats_mod.CMD_LIST).send()
        return self._hats_rows(result.xml)

    async def hats_list_assigned(self, room: str) -> list[dict]:
        """Return the hats assigned in *room* (jid/uri/title/hue)."""
        result = await self._hats_command(
            room, hats_mod.CMD_LIST_ASSIGNED).send()
        return self._hats_rows(result.xml)

    async def hats_create(self, room: str, title: str, hue=None,
                          uri: str = "") -> str:
        """Create (or update, when *uri* is given) a hat and return its URI."""
        uri = uri or hats_mod.hat_uri(room, title)
        values = {"hats#title": title, "hats#uri": uri}
        if hue is not None:
            values["hats#hue"] = f"{float(hue):g}"
        await self._hats_submit(room, hats_mod.CMD_CREATE, values)
        return uri

    async def hats_update(self, room: str, uri: str, title: str,
                          hue=None) -> None:
        """Update an existing hat (create with the same URI)."""
        await self.hats_create(room, title, hue=hue, uri=uri)

    async def hats_destroy(self, room: str, uri: str) -> None:
        await self._hats_submit(room, hats_mod.CMD_DESTROY,
                                {"hats#uri": uri})

    async def hats_assign(self, room: str, jid: str, uri: str) -> None:
        await self._hats_submit(room, hats_mod.CMD_ASSIGN,
                                {"hats#jid": jid, "hats#uri": uri})

    async def hats_unassign(self, room: str, jid: str, uri: str) -> None:
        await self._hats_submit(room, hats_mod.CMD_UNASSIGN,
                                {"hats#jid": jid, "hats#uri": uri})

    def set_muc_subject(self, room: str, subject: str,
                        langs: list[tuple[str, str]] | None = None) -> None:
        """Set the subject/topic of a MUC room.

        *langs* is an optional list of ``(lang_code, text)`` variants sent as
        extra ``<subject xml:lang="...">`` elements per RFC 6121; the default
        subject goes to the primary ``<subject>`` element.
        """
        nick = self.groupchats[room].nick if room in self.groupchats else ""
        to = f"{room}/{nick}"
        msg = self.xmpp.Message()
        msg["to"] = to
        msg["type"] = "groupchat"
        msg["subject"] = subject
        for lang, text in (langs or []):
            el = ET.SubElement(msg.xml, "{jabber:client}subject")
            if lang:
                el.set(_XML_LANG, lang)
            el.text = text
        self._muc_subjects[room] = [("", subject)] + [
            (lang, text) for lang, text in (langs or []) if lang]
        gi = self.groupchats.get(room)
        if gi:
            gi.subject = subject
        msg.send()

    def get_muc_subjects(self, room: str) -> list[tuple[str, str]]:
        """All known ``(lang, text)`` subject variants for a room."""
        return list(self._muc_subjects.get(room, []))

    def get_vcard(self, jid: str, force: bool = False) -> None:
        """Request vCard for *jid*.  Fire-and-forget; result arrives via
        the ``vcard_received`` event as ``(jid, card_dict)``."""
        requested = _clean_jid(jid)
        if not requested:
            logger.debug("Skipping vCard request with empty JID: %r", jid)
            return
        bare = requested.split("/", 1)[0]
        cache_key = requested if "/" in requested else bare
        cached = None if force else self._vcard_cache.get(cache_key)
        if cached is not None:
            if "/" not in requested:
                contact = self.get_contact(bare)
                contact.vcard = cached
                if cached.get("avatar_path"):
                    contact.avatar_path = cached["avatar_path"]
            self.emit("vcard_received", requested, cached)
            return
        if cache_key in self._vcard_inflight:
            return
        self._vcard_inflight.add(cache_key)
        vcard = self.xmpp.plugin["xep_0054"]
        loop = asyncio.get_event_loop()
        loop.create_task(self._fetch_vcard(vcard, requested))

    async def _fetch_vcard(self, vcard, jid: str) -> None:
        try:
            iq = await vcard.get_vcard(jid)
        except Exception:
            logger.debug("vCard for %s unavailable", jid)
            self._vcard_inflight.discard(jid)
            self.emit("vcard_error", jid)
            return
        self._on_vcard(iq, jid)
        self._vcard_inflight.discard(jid)

    async def set_own_vcard(self, card: dict) -> bool:
        """Publish *card* (see :func:`stanza_im.include.vcard.parse_vcard`) as
        our own vCard.  Returns True on success."""
        vcard = self.xmpp.plugin["xep_0054"]
        stanza = _build_vcard(vcard, card)
        try:
            await vcard.publish_vcard(stanza)
        except Exception:
            logger.exception("Failed to publish own vCard")
            return False
        card["jid"] = self.jid_str
        contact = self.get_contact(self.jid_str)
        contact.vcard = card
        if card.get("photo"):
            try:
                from stanza_im.include.avatars import save_avatar
                card["avatar_path"] = save_avatar(self.jid_str, card["photo"])
                # XEP-0398: keep the PEP avatar and the XEP-0153 presence hash
                # in sync with the vCard PHOTO.
                self._avatar_ids[self.jid_str] = hashlib.sha1(
                    card["photo"]).hexdigest()
                self._publish_own_avatar(card["photo"])
            except Exception:
                pass
        self.emit("vcard_updated", self.jid_str, card)
        return True

    async def set_room_vcard(self, room: str, card: dict) -> bool:
        """Publish *card* as the room's vCard (XEP-0045 room + XEP-0054).

        Returns True on success; the local cache/contact are refreshed so the
        room avatar/title update immediately.
        """
        vcard = self.xmpp.plugin["xep_0054"]
        stanza = _build_vcard(vcard, card)
        try:
            await vcard.publish_vcard(stanza, jid=room)
        except Exception:
            logger.exception("Failed to publish room vCard for %s", room)
            return False
        card["jid"] = room
        contact = self.get_contact(room)
        contact.vcard = card
        self._vcard_cache.put(room, card)
        self.emit("vcard_received", room, card)
        return True

    def update_contact(self, jid: str, name: str = "",
                       groups: list[str] | None = None) -> None:
        """Rename *jid* and/or reassign it to *groups* on the roster."""
        try:
            self.xmpp.update_roster(jid, name=name, groups=list(groups or []))
        except Exception:
            logger.exception("Could not update roster item %s", jid)
            return
        self.request_roster()

    def rename_group(self, old: str, new: str) -> int:
        """Rename the roster group *old* to *new* for every member.

        Returns the number of roster items changed; the server roster push
        rebuilds the UI afterwards.
        """
        old = str(old or "").strip()
        new = str(new or "").strip()
        if not old or not new or old == new:
            return 0
        try:
            cr = self.xmpp.client_roster
        except Exception:
            return 0
        count = 0
        for jid in list(cr):
            item = cr[jid]
            groups = list(item["groups"])
            if old not in groups:
                continue
            groups = [new if g == old else g for g in groups]
            try:
                self.xmpp.update_roster(jid, groups=groups)
            except Exception:
                logger.exception("Could not rename group for %s", jid)
                continue
            count += 1
        if count:
            self.request_roster()
        return count

    def resend_subscription(self, jid: str) -> None:
        """Send a fresh presence subscribe request to *jid* (e.g. after a
        rejected or pending subscription)."""
        self.xmpp.send_presence_subscription(
            pto=jid, pfrom=self._full_jid, ptype="subscribe"
        )

    def request_subscription(self, jid: str) -> None:
        """Ask *jid* for our presence subscription (``subscribe``)."""
        self.xmpp.send_presence_subscription(
            pto=jid, pfrom=self._full_jid, ptype="subscribe"
        )
        logger.info("SUB[subscribe] sent 'subscribe' to %s", jid)

    def send_subscription(self, jid: str) -> None:
        """Grant *jid* our presence subscription (``subscribed``)."""
        self.xmpp.send_presence_subscription(
            pto=jid, pfrom=self._full_jid, ptype="subscribed"
        )
        logger.info("SUB[subscribed] sent 'subscribed' to %s", jid)

    def remove_subscription(self, jid: str) -> None:
        """Drop our presence subscription to *jid* (``unsubscribe``)."""
        self.xmpp.send_presence_subscription(
            pto=jid, pfrom=self._full_jid, ptype="unsubscribe"
        )
        logger.info("SUB[unsubscribe] sent 'unsubscribe' to %s", jid)

    def send_file(self, jid: str, filepath: str) -> None:
        """Send a file over Jingle SOCKS5 with IBB fallback (XEP-0234)."""
        self._start_task(self.send_file_p2p(jid, filepath, "p2p"))

    async def send_file_p2p(self, jid: str, path: str,
                            method: str = "p2p") -> None:
        """Send *path* to *jid* over Jingle.

        *method*: ``p2p`` (SOCKS5 with IBB fallback), ``p2p-ibb`` (IBB only).
        """
        await self.file_transfer.send_file(jid, path, method)

    def answer_file_offer(self, offer_id: str, accept: bool,
                          save_path: str = "") -> None:
        """Accept/reject an incoming Jingle file offer (see ``file_offer``)."""
        self.file_transfer.answer_offer(offer_id, accept, save_path)

    def cancel_file_offer(self, sid: str) -> None:
        self.file_transfer.cancel(sid)

    # ── XEP-0363 HTTP File Upload ────────────────────────────────

    def upload_http(self, jid: str, path: str, caption: str = ""):
        """Upload *path* via HTTP Upload and share the URL in *jid*'s chat.

        *caption* (optional) is not used here — callers send it once as a
        separate message via ``send_message``/``send_muc_message``.
        """
        return self._http_upload_flow(jid, path, caption)

    async def _http_upload_flow(self, jid: str, path: str, caption: str = "") -> None:
        self.emit("file_upload_progress", jid, "start", "", path)
        try:
            service = await self._http_upload_service()
            if not service:
                raise RuntimeError("HTTP Upload is not available")
            filename = os.path.basename(str(path))
            size = os.path.getsize(str(path))
            content_type = mimetypes.guess_type(filename)[0] \
                or "application/octet-stream"
            put_url, get_url, headers = await self._http_upload_slot(
                service, filename, size, content_type)
        except Exception as exc:  # noqa: BLE001 - size errors fall back to P2P
            if self._is_upload_oversize(exc):
                logger.info("HTTP Upload rejected %s for size; P2P fallback",
                            filename)
                self.emit("http_upload_oversize", jid, str(path))
                return
            logger.warning("HTTP Upload failed for %s: %s", jid, exc)
            self.emit("file_upload_progress", jid, "error", str(exc),
                      str(path))
            return
        try:
            progress = _UploadProgress()
            put_task = asyncio.create_task(
                self._http_upload_put(put_url, str(path), headers, progress))
            last = -1
            while not put_task.done():
                await asyncio.sleep(0.05)
                pct = int(progress.pct * 100)
                if pct != last:
                    last = pct
                    self.emit("file_upload_progress", jid, "progress",
                              str(pct), str(path))
            await put_task
            target = jid.split("/")[0] if "/" in jid else jid
            media = {
                "name": filename, "size": size, "media_type": content_type,
                "width": 0, "height": 0, "url": get_url,
                "hashes": await asyncio.to_thread(file_hashes_b64, str(path)),
                "hide_body": None,
            }
            if self.groupchats.get(target):
                self.send_muc_message(target, get_url, media=media)
            else:
                self.send_message(target, get_url, media=media)
            self.emit("file_upload_progress", jid, "done", get_url, str(path))
        except Exception as exc:  # noqa: BLE001 - surfaced as a status line
            logger.warning("HTTP Upload failed for %s: %s", jid, exc)
            self.emit("file_upload_progress", jid, "error", str(exc),
                      str(path))

    async def _http_upload_service(self) -> str:
        cached = getattr(self, "_upload_service_cache", None)
        if cached is not None:
            return cached
        domain = self.jid_str.split("@")[-1]
        candidates = [domain]
        try:
            discovered = await self.xmpp["xep_0030"].get_items(domain)
            xml = getattr(discovered, "xml", None)
            if xml is not None:
                for child in xml.iter("{%s}item" % NS_DISCO_ITEMS):
                    jid_candidate = (child.get("jid") or "").strip()
                    if jid_candidate and jid_candidate not in candidates:
                        candidates.append(jid_candidate)
        except Exception as exc:
            logger.debug("HTTP Upload disco items failed on %s: %s", domain, exc)
        for candidate in candidates:
            try:
                info = await self.xmpp["xep_0030"].get_info(candidate)
                xml = getattr(info, "xml", None)
                features = {el.get("var") or "" for el in xml.iter(
                    "{%s}feature" % NS_DISCO_INFO)} if xml is not None else set()
            except Exception:
                features = set()
            if NS_UPLOAD in features:
                self._upload_service_cache = candidate
                return candidate
        self._upload_service_cache = ""
        return ""

    async def http_upload_limit(self) -> int | None:
        """Return the XEP-0363 ``max-file-size`` of the upload service.

        ``None`` when there is no HTTP Upload service or it does not publish
        the limit.  The value is cached for the session.
        """
        if self._upload_limit is not None:
            return self._upload_limit or None
        limit = 0
        service = await self._http_upload_service()
        if service:
            try:
                info = await self.xmpp["xep_0030"].get_info(service)
                limit = _upload_max_file_size(getattr(info, "xml", None))
            except Exception:
                logger.debug("HTTP Upload disco#info failed on %s",
                             service, exc_info=True)
        self._upload_limit = limit
        return limit or None

    def _http_upload_request_iq(self, service: str, filename: str,
                                size: int, content_type: str):
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        iq["to"] = service
        request = ET.SubElement(iq.xml, "{%s}request" % NS_UPLOAD)
        request.set("filename", filename)
        request.set("size", str(int(size)))
        request.set("content-type", content_type)
        return iq

    @staticmethod
    def _parse_upload_slot(result):
        put_url = get_url = ""
        headers: dict[str, str] = {}
        for el in result.xml.iter():
            if el.tag == "{%s}put" % NS_UPLOAD:
                put_url = el.get("url") or ""
                for header in el:
                    if header.tag == "{%s}header" % NS_UPLOAD:
                        headers[str(header.get("name") or "")] = \
                            str(header.text or "")
            elif el.tag == "{%s}get" % NS_UPLOAD:
                get_url = el.get("url") or ""
        return put_url, get_url, headers

    @staticmethod
    def _is_upload_oversize(exc) -> bool:
        """True when an HTTP Upload slot request was rejected for size/quota."""
        condition = getattr(exc, "condition", "") or ""
        if condition in ("not-acceptable", "resource-constraint"):
            return True
        iq = getattr(exc, "iq", None)
        xml = getattr(iq, "xml", None)
        if xml is not None:
            for el in xml.iter():
                if el.tag.rsplit("}", 1)[-1] == "file-too-large":
                    return True
        return False

    async def _http_upload_slot(self, service: str, filename: str,
                                size: int, content_type: str):
        iq = self._http_upload_request_iq(service, filename, size, content_type)
        result = await iq.send()
        put_url, get_url, headers = self._parse_upload_slot(result)
        if not put_url or not get_url:
            raise RuntimeError("invalid HTTP Upload slot response")
        return put_url, get_url, headers

    @staticmethod
    async def _http_upload_put(url: str, path: str,
                               headers: dict[str, str],
                               progress: "_UploadProgress | None" = None,
                               data: bytes | None = None) -> None:
        """PUT *path* (or *data*) to *url* streaming the body in chunks.

        ``progress`` is updated by the worker thread with the upload fraction
        (0..1).  When *data* is given it is uploaded instead of the file (used
        by OMEMO file sharing, where the payload is encrypted in memory).
        """
        def _upload():
            import http.client as http_client
            import ssl
            from urllib.parse import urlsplit
            parts = urlsplit(url)
            scheme = parts.scheme or "https"
            host = str(parts.hostname)
            port = parts.port or (443 if scheme == "https" else 80)
            target = parts.path or "/"
            if parts.query:
                target += "?" + parts.query
            put_headers = {
                "Content-Type": headers.get("Content-Type")
                or "application/octet-stream",
            }
            for name, value in headers.items():
                if name.lower() not in ("content-type", "content-length",
                                        "transfer-encoding"):
                    put_headers[name] = value
            if data is not None:
                total = len(data)
                source = io.BytesIO(data)
            else:
                total = os.path.getsize(str(path))
                source = open(str(path), "rb")
            put_headers["Content-Length"] = str(total)
            if scheme == "https":
                conn = http_client.HTTPSConnection(
                    host, port, timeout=120,
                    context=ssl.create_default_context())
            else:
                conn = http_client.HTTPConnection(host, port, timeout=120)
            try:
                conn.putrequest("PUT", target)
                for name, value in put_headers.items():
                    conn.putheader(name, value)
                conn.endheaders()
                sent = 0
                try:
                    while True:
                        chunk = source.read(64 * 1024)
                        if not chunk:
                            break
                        conn.send(chunk)
                        sent += len(chunk)
                        if progress is not None:
                            progress.update(sent / total if total else 1.0)
                finally:
                    source.close()
                response = conn.getresponse()
                response.read()
                if not 200 <= response.status < 300:
                    raise RuntimeError(
                        "HTTP Upload PUT failed: %s %s"
                        % (response.status, response.reason))
            finally:
                conn.close()

        await asyncio.to_thread(_upload)

    def get_muc_list(self, service: str) -> None:
        """Discover MUC rooms on *service* via Service Discovery."""
        disco = self.xmpp.plugin["xep_0030"]
        if disco.supports(service, "http://jabber.org/protocol/muc"):
            logger.info("Service %s supports MUC", service)

    def approve_subscription(self, jid: str) -> None:
        """Approve a presence subscription request.

        Sends ``subscribed``; when we do not yet receive the peer's presence
        (no ``to`` subscription) a ``subscribe`` is sent too, so a bidirectional
        (``both``) subscription is established (needed e.g. for transports).
        """
        self.xmpp.send_presence_subscription(
            pto=jid, pfrom=self._full_jid, ptype="subscribed"
        )
        if self.subscription(jid) in ("none", "from", ""):
            self.xmpp.send_presence_subscription(
                pto=jid, pfrom=self._full_jid, ptype="subscribe"
            )
        logger.info("SUB[approve] sent 'subscribed' to %s", jid)

    def reject_subscription(self, jid: str) -> None:
        """Reject a presence subscription request."""
        self.xmpp.send_presence_subscription(
            pto=jid, pfrom=self._full_jid, ptype="unsubscribed"
        )
        logger.info("SUB[reject] sent 'unsubscribed' to %s", jid)

    def _on_subscription_request(self, pres) -> None:
        """A contact/transport requested a presence subscription (XEP-0045-ish).

        If we already receive the peer's presence (``to``/``both``) the request
        is a duplicate and is auto-approved; otherwise it is surfaced as a
        system event so the user can approve or reject it.
        """
        jid = str(pres["from"]).split("/", 1)[0]
        if not jid:
            return
        sub = self.subscription(jid)
        logger.info("SUB[request] from %s (current=%s)", jid, sub)
        if sub in ("to", "both"):
            self.approve_subscription(jid)
            return
        # A subscription request may carry the asker's nickname in a raw
        # ``<nick>`` element (not part of slixmpp's Presence interfaces).
        nick = ""
        xml = getattr(pres, "xml", None)
        if xml is not None:
            node = xml.find("nick")
            if node is not None and node.text:
                nick = node.text.strip()
        name, groups = "", []
        try:
            contact = self.get_contact(jid)
            name = getattr(contact, "name", "") or ""
            groups = list(getattr(contact, "groups", []) or [])
        except Exception:  # noqa: BLE001 - presentation only
            pass
        self.emit("subscription_requested", jid, nick, name, groups)

    def _on_unsubscribe_request(self, pres) -> None:
        """A contact asked us to stop our subscription to it.

        Standard behaviour is to answer ``unsubscribed`` (remove the ``to``
        subscription); the user is informed through a system event.
        """
        jid = str(pres["from"]).split("/", 1)[0]
        if not jid:
            return
        logger.info("SUB[unsubscribe] from %s", jid)
        self.reject_subscription(jid)
        self.emit("subscription_cancelled", jid)

    # ── Internal event handlers ───────────────────────────────────

    async def _on_session_start(self, event) -> None:
        logger.info("Session started, requesting roster...")
        self._seed_roster_cache()
        self.request_roster()
        self.send_presence()
        # Cache the domain features (privacy/blocking/report gating) and the
        # XEP-0191 blocklist for the roster's strikethrough state.
        loop = asyncio.get_event_loop()
        loop.create_task(self._load_blocklist())
        if self.message_carbons:
            try:
                await self.xmpp["xep_0280"].enable()
                logger.info("Enabled message carbons (XEP-0280)")
            except Exception as exc:
                logger.warning("Could not enable message carbons: %s", exc)
        if self.message_displayed_sync:
            loop = asyncio.get_event_loop()
            loop.create_task(self._mds_init())
        # PEP subscriptions survive a reconnect, so re-subscribe to the
        # currently known contacts (servers typically drop them on session end).
        for bare in self.contacts:
            self._ensure_pep_subscription(bare)
        self._start_pep_sweep()
        self._start_muc_self_ping()
        self.emit("session_started")
        self.emit("connection_info", self.connection_info())
        self._sync_csi()
        loop = asyncio.get_event_loop()
        loop.create_task(self._autojoin_bookmarks())
        # File-transfer proxy / STUN-TURN discovery is only needed for p2p
        # transfers and calls much later, so run it in the background and
        # never let it delay the session.
        loop.create_task(self.discover_transfer_services())

    async def _autojoin_bookmarks(self) -> None:
        """Join bookmarked MUC rooms flagged for auto-join (XEP-0048/0402).

        Implemented here (instead of the plugin's ``auto_join`` flag) because
        the shipped slixmpp ``_autojoin`` does not await the coroutine-returning
        ``get_bookmarks``.
        """
        if not self.auto_join_conferences:
            return
        bookmarks: list[dict] = []
        for attempt in range(3):
            bookmarks = await self.list_bookmarks()
            if bookmarks:
                break
            logger.debug("Bookmarks fetch failed (attempt %d)",
                         attempt + 1)
            await asyncio.sleep(1 + attempt)
        if not bookmarks:
            logger.debug("No bookmarks to auto-join")
            return
        for bookmark in bookmarks:
            try:
                room = bookmark["jid"]
                autojoin = bookmark["autojoin"]
                nick = bookmark["nick"] or self.jid_str.split("@")[0]
                password = bookmark["password"] or ""
            except Exception:
                continue
            gi = self.groupchats.get(room)
            # Skip only rooms that actually joined: a stale GroupChatInfo from
            # a failed attempt must not block the retry.
            if not autojoin or not room or (gi is not None and gi.joined):
                continue
            logger.info("Auto-joining bookmarked room %s", room)
            self.autojoin_rooms.add(room)
            try:
                self.join_muc(room, nick, password=password, save_bookmark=False)
            except Exception:
                logger.debug("Could not auto-join room %s", room, exc_info=True)

    # ── XEP-0490 Message Displayed Synchronization ───────────────

    def _mds_track(self, chat_jid: str, msg, server_sid: str) -> None:
        """Remember the latest server stanza-id (+ message id) of *chat_jid*."""
        self._mds_last_sid[chat_jid] = server_sid
        msg_id = str(msg.get("id") or "")
        if msg_id:
            self._mds_last_id[chat_jid] = msg_id

    def set_displayed_state(self, mapping: dict) -> None:
        """Seed the MDS bookkeeping with restored per-chat displayed sids.

        Keeps the startup XEP-0490 catch-up from re-applying our own stale
        state (which would clear unread messages that arrived after it), while
        a genuinely different remote state still clears them.
        """
        for jid, sid in (mapping or {}).items():
            if jid and isinstance(sid, str) and sid:
                self._mds_local[jid] = sid

    def mds_mark_displayed(self, chat_jid: str, sid: str = "",
                           msg_id: str = "") -> None:
        """Flag *chat_jid* as displayed up to the latest received message."""
        if not self.message_displayed_sync:
            return
        chat_jid = str(chat_jid or "").strip()
        if not chat_jid:
            return
        sid = sid or self._mds_last_sid.get(chat_jid)
        if not sid:
            logger.debug("MDS: nothing to mark displayed in %s", chat_jid)
            return
        msg_id = msg_id or self._mds_last_id.get(chat_jid, "")
        self._mds_local[chat_jid] = sid
        loop = asyncio.get_event_loop()
        if self._mds_server_assist and msg_id:
            task = self._mds_publish_message(chat_jid, sid, msg_id)
        else:
            task = self._mds_publish_pep(chat_jid, sid)
        loop.create_task(task)

    async def _mds_init(self) -> None:
        try:
            await self._mds_detect_server()
        except Exception as exc:
            logger.debug("MDS server detection failed: %s", exc)
        try:
            await self._mds_catch_up()
        except Exception as exc:
            logger.debug("MDS catch-up failed: %s", exc)

    async def _mds_detect_server(self) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        iq["to"] = self.jid_str
        ET.SubElement(iq.xml, "{%s}query" % NS_DISCO_INFO)
        result = await iq.send()
        features = {el.get("var") or "" for el in
                    result.xml.iter("{%s}feature" % NS_DISCO_INFO)}
        self._mds_server_assist = NS_MDS_ASSIST in features
        self._mds_pubsub_options = (
            "http://jabber.org/protocol/pubsub#publish-options" in features)
        logger.debug("MDS server assist=%s publish-options=%s",
                     self._mds_server_assist, self._mds_pubsub_options)

    async def _mds_catch_up(self) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        iq["to"] = ""
        pubsub = ET.SubElement(iq.xml, "{%s}pubsub" % NS_PUBSUB)
        ET.SubElement(pubsub, "{%s}items" % NS_PUBSUB).set("node", NS_MDS)
        result = await iq.send()
        for item_id, sid, by in self._mds_scan_result(result.xml):
            if by and by.split("/")[0] != self.jid_str:
                continue
            self._mds_apply_remote(item_id, sid)

    async def _mds_publish_pep(self, chat_jid: str, sid: str) -> None:
        await self._mds_build_pep(chat_jid, sid).send()

    def _mds_build_pep(self, chat_jid: str, sid: str):
        """Build the PEP publish IQ (not sent), used by tests too."""
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = ""
        pubsub = ET.SubElement(iq.xml, "{%s}pubsub" % NS_PUBSUB)
        publish = ET.SubElement(pubsub, "{%s}publish" % NS_PUBSUB)
        publish.set("node", NS_MDS)
        item = ET.SubElement(publish, "{%s}item" % NS_PUBSUB)
        item.set("id", chat_jid)
        disp = ET.SubElement(item, "{%s}displayed" % NS_MDS)
        sid_el = ET.SubElement(disp, "{urn:xmpp:sid:0}stanza-id")
        sid_el.set("by", self.jid_str)
        sid_el.set("id", sid)
        if self._mds_pubsub_options:
            options = ET.SubElement(pubsub, "{%s}publish-options" % NS_PUBSUB)
            form = ET.SubElement(options, "{%s}x" % NS_DATA)
            form.set("type", "submit")
            for var, val in (
                ("FORM_TYPE",
                 "http://jabber.org/protocol/pubsub#publish-options"),
                ("pubsub#persist_items", "true"),
                ("pubsub#max_items", "max"),
                ("pubsub#send_last_published_item", "never"),
                ("pubsub#access_model", "whitelist"),
            ):
                field = ET.SubElement(form, "{%s}field" % NS_DATA)
                field.set("var", var)
                if var == "FORM_TYPE":
                    field.set("type", "hidden")
                value = ET.SubElement(field, "{%s}value" % NS_DATA)
                value.text = val
        return iq

    async def _mds_publish_message(self, chat_jid: str, sid: str,
                                   msg_id: str) -> None:
        await self._mds_build_message(chat_jid, sid, msg_id).send()

    def _mds_build_message(self, chat_jid: str, sid: str, msg_id: str):
        msg = self.xmpp.Message()
        msg["to"] = chat_jid
        msg["type"] = "chat"
        marker = ET.SubElement(msg.xml, "{urn:xmpp:chat-markers:0}displayed")
        marker.set("id", msg_id)
        disp = ET.SubElement(msg.xml, "{%s}displayed" % NS_MDS)
        sid_el = ET.SubElement(disp, "{urn:xmpp:sid:0}stanza-id")
        sid_el.set("by", self.jid_str)
        sid_el.set("id", sid)
        return msg

    def _maybe_mds_event(self, msg) -> None:
        if str(msg["from"]).split("/")[0] != self.jid_str:
            return
        for item_id, sid, by in self._mds_scan_event(msg):
            if by and by.split("/")[0] != self.jid_str:
                continue
            self._mds_apply_remote(item_id, sid)

    @staticmethod
    def _mds_payload(container):
        for child in container:
            if child.tag == "{%s}displayed" % NS_MDS:
                sid_el = child.find("{urn:xmpp:sid:0}stanza-id")
                if sid_el is not None:
                    return sid_el.get("id") or "", sid_el.get("by") or ""
        return "", ""

    def _mds_scan_event(self, msg):
        for el in msg.xml:
            if el.tag != "{%s}event" % NS_PUBSUB_EVENT:
                continue
            items = el.find("{%s}items" % NS_PUBSUB_EVENT)
            if items is None or items.get("node") != NS_MDS:
                continue
            for item in items:
                if item.tag != "{%s}item" % NS_PUBSUB_EVENT:
                    continue
                sid, by = self._mds_payload(item)
                yield item.get("id") or "", sid, by

    def _mds_scan_result(self, root):
        for items in root.iter("{%s}items" % NS_PUBSUB):
            if items.get("node") != NS_MDS:
                continue
            for item in items.iter("{%s}item" % NS_PUBSUB):
                sid, by = self._mds_payload(item)
                yield item.get("id") or "", sid, by

    def _mds_apply_remote(self, chat_jid: str, sid: str) -> None:
        if not sid or not chat_jid:
            return
        if self._mds_local.get(chat_jid) == sid:
            return
        self._mds_local[chat_jid] = sid
        logger.debug("MDS: %s displayed up to %s", chat_jid, sid)
        self.emit("mds_displayed", chat_jid, sid)

    # ── Extended presence: XEP-0080/0107/0108/0118 ────────────────

    def _maybe_pep_event(self, msg) -> None:
        """Handle a PEP notification for mood/activity/tune/geoloc/avatar."""
        frm = _replyto_address(msg) or str(msg["from"]).split("/")[0]
        for el in msg.xml:
            if el.tag != "{%s}event" % NS_PUBSUB_EVENT:
                continue
            items = el.find("{%s}items" % NS_PUBSUB_EVENT)
            if items is None:
                continue
            node = items.get("node") or ""
            if node == NS_AVATAR_METADATA:
                self._handle_avatar_metadata(frm, items)
                continue
            if node == NS_BOOKMARKS2:
                self._handle_bookmarks2_event(frm, items)
                continue
            kind = pep.PEP_NODES.get(node)
            if not kind:
                continue
            for item in items:
                if item.tag != "{%s}item" % NS_PUBSUB_EVENT:
                    continue
                payload = next(iter(item), None)
                if payload is None:
                    continue
                self._store_pep(frm, kind, pep.parse_payload(node, payload))

    # ── XEP-0084 / XEP-0153 / XEP-0398 avatars ────────────────────

    def _handle_avatar_metadata(self, jid: str, items) -> None:
        """React to a contact's ``urn:xmpp:avatar:metadata`` (XEP-0084)."""
        if not jid:
            return
        info = None
        for item in items:
            if item.tag != "{%s}item" % NS_PUBSUB_EVENT:
                continue
            payload = next(iter(item), None)
            if payload is None:
                continue
            info = payload.find("{%s}info" % NS_AVATAR_METADATA)
            if info is not None:
                break
        if info is None:
            return
        avatar_id = str(info.get("id") or "")
        mtype = str(info.get("type") or "")
        if not avatar_id or avatar_id == self._avatar_ids.get(jid):
            return
        if (jid, avatar_id) in self._avatar_failed:
            return
        if jid in self._avatar_inflight:
            return
        self._avatar_inflight.add(jid)
        self._start_task(self._retrieve_avatar(jid, avatar_id, mtype))

    async def _retrieve_avatar(self, jid: str, avatar_id: str,
                               mtype: str = "") -> None:
        try:
            result = await asyncio.wait_for(
                self.xmpp["xep_0084"].retrieve_avatar(jid, avatar_id),
                timeout=20)
        except (slixmpp.exceptions.IqError, asyncio.TimeoutError) as exc:
            # Expected for a stale or absent node (e.g. item-not-found): report
            # briefly, without a traceback.
            logger.debug("Avatar retrieval for %s failed: %s", jid, exc)
            self._avatar_failed.add((jid, avatar_id))
            self._avatar_inflight.discard(jid)
            return
        except Exception:
            logger.debug("Avatar retrieval for %s failed", jid, exc_info=True)
            self._avatar_inflight.discard(jid)
            return
        self._avatar_inflight.discard(jid)
        raw = _avatar_data_from_iq(result)
        if raw:
            self._apply_avatar(jid, raw)

    def _apply_avatar(self, jid: str, raw: bytes) -> bool:
        """Cache the avatar *raw* for *jid* and notify the UI (XEP-0398).

        Returns ``False`` when the image is unchanged (same SHA-1), which
        keeps the XEP-0153 (vCard) and XEP-0084 (PEP) paths from flapping.
        """
        if not raw:
            return False
        bare = str(jid or "").split("/", 1)[0]
        if not bare:
            return False
        digest = hashlib.sha1(raw).hexdigest()
        if self._avatar_ids.get(bare) == digest:
            return False
        try:
            from stanza_im.include.avatars import save_avatar
            path = save_avatar(bare, raw)
        except Exception:
            logger.debug("Could not cache avatar for %s", bare, exc_info=True)
            return False
        self._avatar_ids[bare] = digest
        self.emit("avatar_updated", bare, path)
        return True

    def _on_vcard_avatar_update(self, pres) -> None:
        """XEP-0153: a contact changed the avatar hash in their presence."""
        try:
            bare = str(pres["from"]).split("/", 1)[0]
            photo = str(pres["vcard_temp_update"]["photo"] or "")
        except (KeyError, TypeError, AttributeError):
            return
        if not bare or not photo:
            return
        if self._avatar_ids.get(bare) == photo:
            return
        self.get_vcard(bare, force=True)

    def _publish_own_avatar(self, raw: bytes) -> None:
        """Publish our avatar to PEP (XEP-0084) and refresh the 0153 hash."""
        self._start_task(self._publish_own_avatar_async(raw))

    async def _publish_own_avatar_async(self, raw: bytes) -> None:
        if not raw:
            return
        digest = hashlib.sha1(raw).hexdigest()
        plugin = self.xmpp.plugin.get("xep_0084", None)
        if plugin is not None:
            try:
                await plugin.publish_avatar(raw)
            except Exception:
                logger.debug("PEP avatar publish failed", exc_info=True)
            else:
                try:
                    from stanza_im.include.avatars import image_mime, image_size
                    width, height = image_size(raw)
                    await plugin.publish_avatar_metadata([{
                        "id": digest,
                        "type": image_mime(raw),
                        "bytes": len(raw),
                        "width": width or None,
                        "height": height or None,
                    }])
                except Exception:
                    logger.debug("PEP avatar metadata publish failed",
                                 exc_info=True)
        self._set_vcard_avatar_hash(digest)

    def _set_vcard_avatar_hash(self, digest: str) -> None:
        """Update the XEP-0153 hash advertised in our presence."""
        plugin = self.xmpp.plugin.get("xep_0153", None)
        if plugin is None:
            return
        try:
            self.xmpp.plugin["xep_0153"].api["set_hash"](
                self.xmpp.boundjid, args=digest)
        except Exception:
            logger.debug("Could not update the vCard avatar hash",
                         exc_info=True)

    def _store_pep(self, jid: str, kind: str, data: dict) -> None:
        jid = str(jid or "").split("/")[0]
        if not jid:
            return
        entry = self.pep_data.setdefault(jid, {})
        entry[kind] = data
        self.emit("contact_pep_updated", jid, kind, data)
        logger.debug("PEP %s for %s = %r", kind, jid, data)

    # ── XEP-0163 subscriptions to contact PEP nodes ───────────────

    def _ensure_pep_subscription(self, bare: str) -> None:
        """Subscribe (XEP-0163) to the PEP nodes of *bare*, best-effort.

        The server only pushes ``<message type='headline'><event>``
        notifications to entities subscribed to the publisher's PEP nodes, so a
        pull-based client never sees live mood/activity/tune/geoloc changes.
        Like the pull path this is fire-and-forget with an in-flight guard;
        failures are cooldown-limited so an unsupported server is not spammed.
        """
        if not bare or not self.xmpp.is_connected():
            return
        if self.jid_str and self.jid_str == bare:
            return
        now = time.monotonic()
        last_fail = self._pep_subscribe_failed.get(bare, 0.0)
        if now - last_fail < self._pep_subscribe_cooldown:
            return
        for node in (*pep.PEP_NODES, NS_AVATAR_METADATA):
            key = (bare, node)
            if key in self._pep_subscribe_inflight:
                continue
            if node in self._pep_subscribed.get(bare, ()):
                continue
            self._pep_subscribe_inflight.add(key)
            self._start_task(self._pep_subscribe(key))

    async def _pep_subscribe(self, key: tuple[str, str]) -> None:
        bare, node = key
        try:
            result = await asyncio.wait_for(
                self.xmpp["xep_0060"].subscribe(bare, node, bare=True),
                timeout=8)
            status = ""
            for sub in result.xml.iter("{%s}subscription" % NS_PUBSUB):
                status = sub.get("subscription", "")
                break
            if status == "subscribed":
                self._pep_subscribed.setdefault(bare, set()).add(node)
                logger.debug("PEP subscription to %s %s", bare, node)
            elif status == "pending":
                logger.debug("PEP subscription to %s %s pending", bare, node)
            else:
                self._note_pep_subscribe_fail(bare, node,
                                              "state=%r" % status)
        except Exception as exc:  # noqa: BLE001 - best-effort subscription
            self._note_pep_subscribe_fail(bare, node, str(exc))
        finally:
            self._pep_subscribe_inflight.discard(key)

    def _note_pep_subscribe_fail(self, bare: str, node: str, detail: str) -> None:
        self._pep_subscribe_failed[bare] = time.monotonic()
        logger.debug("PEP subscription to %s %s failed (%s)",
                     bare, node, detail)

    def _unsubscribe_pep(self, bare: str) -> None:
        """Drop XEP-0163 subscriptions when a contact leaves the roster."""
        nodes = self._pep_subscribed.pop(bare, set())
        self._pep_subscribe_failed.pop(bare, None)
        if not nodes or not self.xmpp.is_connected():
            return
        for node in nodes:
            self._start_task(self._pep_unsubscribe(bare, node))

    async def _pep_unsubscribe(self, bare: str, node: str) -> None:
        try:
            await asyncio.wait_for(
                self.xmpp["xep_0060"].unsubscribe(bare, node, bare=True),
                timeout=8)
            logger.debug("PEP unsubscribed from %s %s", bare, node)
        except Exception:  # noqa: BLE001 - best-effort unsubscribe
            logger.debug("PEP unsubscribe from %s %s failed", bare, node,
                         exc_info=True)

    # ── Periodic PEP sweep (fallback when subscriptions are absent) ─

    def set_pep_sweep_paused(self, paused: bool) -> None:
        """Pause the periodic PEP sweep while the user is inactive."""
        self._pep_sweep_paused = bool(paused)

    def _start_pep_sweep(self) -> None:
        """Start/resume the periodic PEP sweep task (asyncio, no Qt).

        Only active when ``pep_sweep_interval > 0``; the sweep is a fallback
        for servers that do not forward XEP-0163 notifications, reusing the
        existing ``_maybe_refresh_pep`` rate-limit guards.
        """
        interval = self.pep_sweep_interval
        if interval <= 0:
            return
        self._stop_pep_sweep()
        self._pep_sweep_paused = False

        async def _loop() -> None:
            while True:
                await asyncio.sleep(interval)
                if self._pep_sweep_paused:
                    continue
                for contact in list(self.contacts.values()):
                    if contact.show != "offline":
                        self._maybe_refresh_pep(contact.jid, contact.show)

        self._pep_sweep_task = asyncio.get_event_loop().create_task(_loop())

    def _stop_pep_sweep(self) -> None:
        if self._pep_sweep_task is not None:
            self._pep_sweep_task.cancel()
            self._pep_sweep_task = None

    def publish_pep(self, node: str, payload) -> None:
        """Publish *payload* to the private PEP *node* (XEP-0163)."""
        self._start_task(self._publish_pep(node, payload))

    async def _publish_pep(self, node: str, payload) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = ""
        pubsub = ET.SubElement(iq.xml, "{%s}pubsub" % NS_PUBSUB)
        publish = ET.SubElement(pubsub, "{%s}publish" % NS_PUBSUB)
        publish.set("node", node)
        item = ET.SubElement(publish, "{%s}item" % NS_PUBSUB)
        item.set("id", "current")
        item.append(payload)
        try:
            await iq.send()
        except Exception as exc:  # noqa: BLE001 - best-effort PEP
            logger.warning("PEP publish to %s failed: %s", node, exc)
            self.emit("pep_publish_failed", node, str(exc))

    def publish_mood(self, key: str, text: str = "") -> None:
        self.publish_pep(pep.NS_MOOD, pep.build_mood(key, text))

    def publish_activity(self, group: str, sub: str = "") -> None:
        self.publish_pep(pep.NS_ACTIVITY, pep.build_activity(group, sub))

    def fetch_pep(self, jid: str) -> None:
        """Fetch the current mood/activity/tune/geoloc of *jid* (PEP items)."""
        self._start_task(self._fetch_pep(jid))

    def _pep_refresh(self, bare: str) -> None:
        """Pull the PEP nodes of a newly-present contact (presence-driven).

        A single in-flight fetch per bare JID is guaranteed; callers may fire
        this on every presence change without risking a fetch backlog. The
        pull never depends on the server pushing XEP-0163 notifications.
        """
        if bare in self._pep_inflight:
            logger.debug("PEP refresh for %s already in flight", bare)
            return
        self._pep_inflight.add(bare)
        self._start_task(self._pep_refresh_guard(bare))

    async def _pep_refresh_guard(self, bare: str) -> None:
        try:
            logger.debug("PEP refresh for %s", bare)
            await self._fetch_pep(bare)
        except Exception:
            logger.exception("PEP refresh failed for %s", bare)
        finally:
            self._pep_inflight.discard(bare)

    async def _fetch_pep(self, jid: str) -> None:
        bare = str(jid or "").split("/")[0]
        if not bare:
            return
        for node, kind in pep.PEP_NODES.items():
            try:
                payload = await self._pep_items(bare, node)
            except Exception:
                continue
            if payload is not None:
                self._store_pep(bare, kind, payload)

    async def _pep_items(self, jid: str, node: str):
        iq = self.xmpp.Iq()
        iq["type"] = "get"
        iq["to"] = jid
        pubsub = ET.SubElement(iq.xml, "{%s}pubsub" % NS_PUBSUB)
        items = ET.SubElement(pubsub, "{%s}items" % NS_PUBSUB)
        items.set("node", node)
        items.set("max_items", "1")
        result = await iq.send()
        for items_el in result.xml.iter("{%s}items" % NS_PUBSUB):
            if (items_el.get("node") or "") != node:
                continue
            for item in items_el:
                if item.tag != "{%s}item" % NS_PUBSUB:
                    continue
                child = next(iter(item), None)
                if child is not None:
                    return pep.parse_payload(node, child)
        return None

    def _on_attention_event(self, msg) -> None:
        """slixmpp ``xep_0224`` saw an incoming ``<attention/>`` (XEP-0224)."""
        frm = str(msg.get("from", "") or "")
        if frm:
            logger.debug("ATTENTION received from %s", frm)
            self.emit("attention_received", frm.split("/")[0])

    def _is_omemo_encrypted(self, msg) -> bool:
        omemo = getattr(self, "omemo", None)
        if omemo is None or not getattr(omemo, "available", False):
            return False
        try:
            return bool(omemo.is_encrypted(msg))
        except Exception:  # noqa: BLE001
            return False

    async def _decrypt_and_dispatch(self, msg) -> None:
        """Decrypt an incoming OMEMO stanza and hand it to the normal path."""
        try:
            decrypted, device = await self.omemo.decrypt(msg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OMEMO decryption failed: %s", exc)
            self.emit("omemo_decrypt_failed", str(msg["from"]), str(exc))
            return
        try:
            decrypted._omemo_encrypted = True
            decrypted._omemo_device = device
        except Exception:  # noqa: BLE001
            pass
        try:
            if device is not None:
                self.omemo.note_device_seen(device.bare_jid, device.device_id)
                resource = msg.get_from().resource
                if resource:
                    self.omemo.note_device_resource(
                        device.bare_jid, device.device_id, resource)
        except Exception:  # noqa: BLE001
            pass
        if str(decrypted["type"]) == "groupchat":
            self._on_groupchat_message(decrypted)
        elif getattr(msg, "_omemo_carbon", False):
            self._emit_1to1(decrypted, carbon=True)
        else:
            self._on_message(decrypted)

    def _emit_1to1(self, msg, carbon: bool = False) -> None:
        body = str(msg["body"])
        frm = str(msg["from"])
        unstyled, ts, reply_to, reply_id, stable_id = self._message_fields(msg)
        media = message_media(msg)
        markup = message_markup(msg)
        server_sid = _stanza_id(msg, self.jid_str)
        if server_sid:
            self._mds_track(frm.split("/")[0], msg, server_sid)
        self.emit("message_received", frm, body, ts, unstyled, stable_id,
                  frm, reply_to, reply_id, carbon, media=media,
                  encrypted=self._omemo_flag(msg), markup=markup)

    @staticmethod
    def _omemo_flag(msg) -> bool:
        return bool(getattr(msg, "_omemo_encrypted", False))

    def _on_message(self, msg) -> None:
        voice_err = self._voice_request_error(msg)
        if voice_err is not None:
            room, condition, text = voice_err
            logger.info("VOICE request error in %s: %s", room,
                        condition or "error")
            self.emit("voice_request_failed", room, condition, text)
            return
        if msg["type"] == "headline":
            self._maybe_mds_event(msg)
            self._maybe_pep_event(msg)
            return
        if self._is_omemo_encrypted(msg):
            self._start_task(self._decrypt_and_dispatch(msg))
            return
        if _is_muc_invite(msg):
            # A MUC invitation is surfaced by its own handler (dialog + OSD);
            # it must not turn into a 1:1 chat message.
            return
        if _is_captcha_message(msg):
            # A XEP-0158 challenge is surfaced by its own handler (dialog).
            return
        if _is_roster_exchange(msg):
            # A XEP-0144 roster exchange is surfaced by its own handler.
            return
        if msg["type"] in ("chat", "normal"):
            body = str(msg["body"])
            frm = str(msg["from"])
            reactions = _reactions(msg)
            if reactions is not None:
                # XEP-0444: reactions never render the (absent) body.
                target_id, emojis = reactions
                self.emit("message_reactions", frm, target_id, emojis)
                return
            retract_ref = _retract_reference(msg)
            if retract_ref:
                # XEP-0424: a retraction must never render its fallback body.
                self.emit("message_retracted", frm, retract_ref)
                return
            unstyled, ts, reply_to, reply_id, stable_id = \
                self._message_fields(msg)
            media = message_media(msg)
            markup = message_markup(msg)
            server_sid = _stanza_id(msg, self.jid_str)
            replace_ref = _replace_reference(msg)
            room, separator, nick = frm.partition("/")
            if separator and room in self.groupchats:
                if server_sid:
                    self._mds_track(frm, msg, server_sid)
                if replace_ref:
                    if self.allow_incoming_edits:
                        self.emit("message_corrected", frm, replace_ref,
                                  body, ts, unstyled, stable_id,
                                  reply_to, reply_id, media=media,
                                  markup=markup)
                        return
                    logger.debug("Incoming correction ignored (edits disabled)")
                self.emit("muc_private_message", room, nick, body, ts, unstyled,
                          stable_id, frm, reply_to, reply_id, media=media,
                          encrypted=self._omemo_flag(msg), markup=markup)
                return
            if server_sid:
                self._mds_track(frm.split("/")[0], msg, server_sid)
            if replace_ref:
                if self.allow_incoming_edits:
                    self.emit("message_corrected", frm, replace_ref,
                              body, ts, unstyled, stable_id,
                              reply_to, reply_id, media=media, markup=markup)
                    return
                logger.debug("Incoming correction ignored (edits disabled)")
            self.emit("message_received", frm, body, ts, unstyled,
                      stable_id, frm, reply_to, reply_id, media=media,
                      encrypted=self._omemo_flag(msg), markup=markup)

    @staticmethod
    def _message_fields(msg):
        """Extract (unstyled, ts, reply_to, reply_id, stable_id) from a
        1:1 message stanza (shared by direct messages and XEP-0280 carbons)."""
        unstyled = _has_stanza_element(msg, "unstyled")
        ts = msg.get("delay", {}).get("stamp", None)
        if isinstance(ts, datetime.datetime):
            ts = _normalize_ts(ts.strftime("%Y-%m-%dT%H:%M:%S"))
        elif ts:
            ts = _normalize_ts(str(ts))
        reply_to, reply_id = _reply_reference(msg)
        stable_id = _origin_id(msg) or str(msg.get("id") or "")
        return unstyled, ts, reply_to, reply_id, stable_id

    def _on_carbon_received(self, msg) -> None:
        """A 1:1 message received on another of our resources (XEP-0280)."""
        element = _carbon_inner(msg, "received")
        if element is None:
            return
        try:
            inner = slixmpp.Message(xml=element)
        except Exception:
            return
        if _is_muc_invite(inner):
            return
        if _is_roster_exchange(inner):
            self._start_task(self._on_roster_exchange_stanza(inner))
            return
        if self._is_omemo_encrypted(inner):
            try:
                inner._omemo_carbon = True
            except Exception:  # noqa: BLE001
                pass
            self._start_task(self._decrypt_and_dispatch(inner))
            return
        if inner["type"] not in ("chat", "normal"):
            return
        body = str(inner["body"])
        frm = str(inner["from"])
        reactions = _reactions(inner)
        if reactions is not None:
            target_id, emojis = reactions
            self.emit("message_reactions", frm, target_id, emojis)
            return
        retract_ref = _retract_reference(inner)
        if retract_ref:
            self.emit("message_retracted", frm, retract_ref)
            return
        unstyled, ts, reply_to, reply_id, stable_id = \
            self._message_fields(inner)
        media = message_media(inner)
        markup = message_markup(inner)
        server_sid = _stanza_id(inner, self.jid_str)
        if server_sid:
            self._mds_track(frm.split("/")[0], inner, server_sid)
        self.emit("message_received", frm, body, ts, unstyled,
                  stable_id, frm, reply_to, reply_id, True, media=media,
                  markup=markup)

    def _on_carbon_sent(self, msg) -> None:
        """A 1:1 message sent from another of our resources (XEP-0280)."""
        element = _carbon_inner(msg, "sent")
        if element is None:
            return
        try:
            inner = slixmpp.Message(xml=element)
        except Exception:
            return
        if inner["type"] not in ("chat", "normal"):
            return
        body = str(inner["body"])
        target = str(inner["to"] or "")
        bare = target.split("/")[0] if "/" in target else target
        if not bare:
            return
        retract_ref = _retract_reference(inner)
        if retract_ref:
            self.emit("message_retracted_own", bare, retract_ref)
            return
        unstyled, ts, reply_to, reply_id, stable_id = \
            self._message_fields(inner)
        media = message_media(inner)
        markup = message_markup(inner)
        self.emit("message_carbon_sent", bare, body, ts,
                  stable_id, reply_to, reply_id, media=media, markup=markup)

    def _on_groupchat_message(self, msg) -> None:
        frm = str(msg["from"])
        room = frm.split("/")[0]
        nick = frm.split("/", 1)[1] if "/" in frm else ""
        self._mark_muc_activity(room)
        if self._is_omemo_encrypted(msg):
            self._start_task(self._decrypt_and_dispatch(msg))
            return
        reactions = _reactions(msg)
        if reactions is not None:
            # XEP-0444: a bodyless reaction is never a chat message (and must
            # not count as unread); route it to the reactions handler.
            target_id, emojis = reactions
            logger.debug("MUC reaction(s) in %s from %s for %s",
                         room, nick, target_id)
            self.emit("groupchat_message_reactions", room, nick, frm,
                      target_id, emojis, _occupant_id(msg))
            return
        body = str(msg["body"])
        retract_ref = _retract_reference(msg)
        if retract_ref:
            # XEP-0424: never render the fallback body of a retraction.
            info = _moderation_info(msg)
            if info["moderated"] and (nick or room != frm.split("/")[0]):
                # XEP-0425 §5: a moderation message is only legitimate when it
                # comes from the MUC service itself, never from an occupant.
                logger.warning("Ignoring spoofed moderation retraction "
                               "from %s", frm)
                return
            self.emit("groupchat_message_retracted", room, nick, frm,
                      retract_ref, info["by"], info["reason"],
                      info["moderated"])
            return
        subjects = _message_subjects(msg)
        if not body and subjects:
            default = next((t for lang, t in subjects if not lang), "")
            if not default and subjects:
                default = subjects[0][1]
            gi = self.groupchats.get(room)
            if gi:
                gi.subject = default
            self._muc_subjects[room] = subjects
            self.emit("muc_subject_changed", room, list(subjects))
            return
        unstyled = _has_stanza_element(msg, "unstyled")
        ts = msg.get("delay", {}).get("stamp", None)
        if isinstance(ts, datetime.datetime):
            ts = _normalize_ts(ts.strftime("%Y-%m-%dT%H:%M:%S"))
        elif ts:
            ts = _normalize_ts(str(ts))
        # Live room echoes may also carry an archive marker. History replay
        # additionally has delayed delivery, which is the reliable signal.
        archived = _has_stanza_element(msg, "archived") and bool(ts)
        archive_id = _archive_result_id(msg) if archived else ""
        reply_to, reply_id = _reply_reference(msg)
        stable_id = _stanza_id(msg, room)
        if not stable_id and archived and archive_id:
            stable_id = archive_id
        if stable_id:
            self._mds_track(room, msg, stable_id)
        media = message_media(msg)
        markup = message_markup(msg)
        replace_ref = _replace_reference(msg)
        if replace_ref:
            if self.allow_incoming_edits:
                self.emit("groupchat_message_corrected",
                          room, replace_ref, body, ts, unstyled,
                          stable_id, frm, reply_to, reply_id, media=media,
                          markup=markup)
                return
            logger.debug("Incoming MUC correction ignored (edits disabled)")
        self.emit("groupchat_message", room, nick, body, ts, archived,
                  archive_id, unstyled, stable_id, frm, reply_to, reply_id,
                  media=media, encrypted=self._omemo_flag(msg), markup=markup)

    def _on_groupchat_subject(self, msg) -> None:
        """A MUC subject was set/announced (subject-only message).

        Servers deliver the current subject right after joining and on every
        change as a ``<message type="groupchat"><subject>…</subject></message>``
        stanza, which slixmpp routes to the ``groupchat_subject`` event.
        """
        room = str(msg["from"]).split("/")[0]
        if room not in self.groupchats:
            return
        self._mark_muc_activity(room)
        subjects = _message_subjects(msg)
        if not subjects:
            return
        default = next((t for lang, t in subjects if not lang), "")
        if not default:
            default = subjects[0][1]
        gi = self.groupchats.get(room)
        if gi:
            gi.subject = default
        self._muc_subjects[room] = subjects
        self.emit("muc_subject_changed", room, list(subjects))

    def _on_presence(self, pres) -> None:
        # Subscribed to the generic ``presence`` event, so it also fires for
        # ``subscribe``/``subscribed``/``probe``/``error`` (handled elsewhere)
        # and for show-only types; filter those out first.
        ptype = str(pres["type"])
        if ptype in ("subscribe", "subscribed", "unsubscribe", "unsubscribed",
                     "probe", "error"):
            return
        # MUC occupant presence is handled by ``_on_groupchat_presence``; the
        # generic handler also runs for it, and aggregating it here would give
        # a room the caps/client icon of a random participant.
        xml = getattr(pres, "xml", None)
        if xml is not None and xml.find("{%s}x" % NS_MUC_USER) is not None:
            return
        frm = str(pres["from"])
        bare, _, resource = frm.partition("/")
        # The room's *own* presence (``from="room@conf"`` with no resource) is
        # not a contact: skip it so it never becomes a roster/contact
        # pseudo-entry or gets PEP subscriptions.  (slixmpp itself would add a
        # pseudo roster item via ``basexmpp._handle_available``.)
        logger.debug("ROSTER[presence] frm=%s bare=%s res=%r type=%s",
                     frm, bare, resource, ptype)
        if not resource and bare in self._known_rooms:
            logger.debug("ROSTER[presence] ignored room presence %s", bare)
            return
        # slixmpp maps a bare <show> value into the ``type`` (chat/away/xa/dnd);
        # treat those as an available presence with that show.
        show = str(pres.get("show", ""))
        if ptype in ("chat", "away", "xa", "dnd"):
            if not show:
                show = ptype
            ptype = "available"
        if ptype == "available":
            if show in ("", "available", "None"):
                show = "online"
        else:
            show = "offline"
        status = str(pres.get("status", ""))
        try:
            priority = int(pres.get("priority", 0) or 0)
        except (TypeError, ValueError):
            priority = 0
        caps_node = _caps_node(pres)
        self.presences[frm] = {"show": show, "status": status, "type": ptype,
                               "priority": priority, "client": "",
                               "caps_node": caps_node}

        contact = self.get_contact(bare)
        if ptype != "available":
            if resource:
                contact.resources.pop(resource, None)
        else:
            previous_client = contact.resources.get(resource, {}).get("client", "")
            contact.resources[resource] = {
                "show": show, "status": status, "priority": priority,
                "client": previous_client, "caps_node": caps_node,
            }
            if resource and frm not in self._version_probed:
                self._version_probed.add(frm)
                self._start_task(self._prefetch_version(frm))
            if resource:
                self._start_task(self._load_caps(frm))

        # Aggregate presence across all resources of the same contact.
        best_show = "offline"
        best_status = ""
        for full, info in self.presences.items():
            if full.split("/")[0] != bare:
                continue
            if info["type"] != "available":
                continue
            s = info["show"]
            if SHOW_ORDER.get(s, 99) < SHOW_ORDER.get(best_show, 99) or best_show == "offline":
                best_show = s
                best_status = info["status"]

        contact.show = best_show
        contact.status = best_status
        self.emit("presence_changed", bare, best_show, best_status)
        if best_show != "offline":
            self._ensure_pep_subscription(bare)
        self._maybe_refresh_pep(bare, best_show)

    def _maybe_refresh_pep(self, bare: str, show: str) -> None:
        """Rate-limited PEP pull when a contact's presence arrives online.

        Mood/activity changes in other clients are usually accompanied by a
        (possibly byte-identical) presence re-send, so refreshing on any
        online presence — whatever the previous show/status tuple was — keeps
        the roster icons/tooltip fresh even when the server never pushes
        XEP-0163 notifications (the "PEP Event" matcher remains the fast push
        path). In-flight dedupe (one fetch per bare) plus a per-contact
        cooldown keep the fetch volume bounded.
        """
        if not bare or show == "offline":
            return
        if self.jid_str and bare == self.jid_str.split("/", 1)[0]:
            return
        now = time.monotonic()
        if now - self._pep_last_refresh.get(bare, 0.0) \
                < self._pep_refresh_interval:
            return
        self._pep_last_refresh[bare] = now
        self._pep_refresh(bare)

    async def _prefetch_version(self, full_jid: str) -> None:
        """Best-effort XEP-0092 lookup for a contact resource (for tooltips)."""
        try:
            info = await asyncio.wait_for(
                self.get_entity_version(full_jid), timeout=8)
        except Exception:
            return
        software = info.get("software") or ""
        bare, _, resource = full_jid.partition("/")
        try:
            self.presences[full_jid]["client"] = software
        except KeyError:
            return
        contact = self.get_contact(bare)
        if resource and resource in contact.resources:
            contact.resources[resource]["client"] = software

    # ── Capabilities (XEP-0115) for call gating ───────────────────

    async def _load_caps(self, full_jid: str) -> None:
        """Fetch and cache the entity-capabilities features for a resource.

        slixmpp resolves a presence's ``<c ver/>`` asynchronously (disco#info
        to the caps node), so ``get_caps`` can return nothing for a while after
        the presence arrives; retry with backoff until it resolves.
        """
        if not full_jid or full_jid in self._caps_inflight:
            return
        self._caps_inflight.add(full_jid)
        try:
            features: set[str] = set()
            for delay in (0.0, 0.5, 1.0, 2.0, 4.0):
                if delay:
                    await asyncio.sleep(delay)
                try:
                    caps = await self.xmpp.plugin["xep_0115"].get_caps(full_jid)
                except Exception as exc:
                    logger.debug("caps lookup failed for %s: %s", full_jid, exc)
                    caps = None
                features = self._features_from_caps(caps)
                if features:
                    break
            if not features:
                logger.debug("CAPS %s: no features resolved", full_jid)
                return
            self.contact_features[full_jid] = features
            bare = full_jid.split("/")[0]
            logger.debug("CAPS %s: %d features", full_jid, len(features))
            self.emit("contact_caps", bare)
        finally:
            self._caps_inflight.discard(full_jid)

    @staticmethod
    def _features_from_caps(caps) -> set[str]:
        if caps is None:
            return set()
        try:
            return set(caps.get_features())
        except AttributeError:
            try:
                return set(caps.get("features") or [])
            except Exception:
                return set()

    def client_icon(self, bare: str) -> str:
        """Absolute client icon path for *bare* (XEP-0115 caps), else ``""``.

        The best online resource wins; resources without a known caps node are
        skipped so a second resource can still provide an icon.
        """
        if not bare or bare in self.groupchats:
            return ""  # conferences never carry a client icon
        resources = self.get_contact(bare).resources
        candidates = sorted(
            resources.values(),
            key=lambda info: (SHOW_ORDER.get(info.get("show", "offline"), 99),
                              -int(info.get("priority", 0) or 0)))
        for info in candidates:
            node = str(info.get("caps_node") or "")
            if not node:
                continue
            path = clients_mod.client_icon_for(node, 16)
            if path:
                return path
        return ""

    def _on_entity_caps(self, pres) -> None:
        """slixmpp processed a caps presence — resolve our feature cache."""
        try:
            full_jid = str(pres["from"])
        except Exception:
            return
        if "/" not in full_jid:
            return
        self._start_task(self._load_caps(full_jid))

    def ensure_caps(self, bare: str) -> None:
        """Fallback: query a resource's disco#info if caps are still unknown."""
        if any(jid.split("/")[0] == bare for jid in self.contact_features):
            return
        best = ""
        for candidate, info in (self.presences or {}).items():
            if (candidate.split("/")[0] == bare
                    and info.get("type") == "available"):
                best = candidate
                break
        if best:
            self._start_task(self._load_caps_from_disco(best))

    async def _load_caps_from_disco(self, full_jid: str) -> None:
        try:
            info = await self.xmpp.plugin["xep_0030"].get_info(full_jid)
        except Exception:
            logger.debug("disco#info failed for %s", full_jid)
            return
        features: set[str] = set()
        xml = getattr(info, "xml", None)
        if xml is not None:
            features = {el.get("var") or "" for el in xml.iter(
                "{%s}feature" % NS_DISCO_INFO)}
        if features:
            self.contact_features[full_jid] = features
            logger.debug("CAPS(disco) %s: %d features", full_jid, len(features))
            self.emit("contact_caps", full_jid.split("/")[0])

    def supports_feature(self, bare: str, feature: str,
                         full_jid: str = "") -> bool:
        """True when any resource of *bare* advertises *feature* (XEP-0115)."""
        if full_jid and feature in self.contact_features.get(full_jid, set()):
            return True
        for jid, features in self.contact_features.items():
            if jid.split("/")[0] == bare and feature in features:
                return True
        return False

    CALL_FEATURES = ("urn:xmpp:jingle:1", "urn:xmpp:jingle:transports:ice-udp:1",
                     "urn:xmpp:jingle:apps:rtp:1",
                     "urn:xmpp:jingle:apps:dtls:0",
                     "urn:xmpp:jingle:apps:rtp:audio")

    async def get_omemo_aliases(self) -> list[dict]:
        from stanza_im.core import omemo_aliases
        return await omemo_aliases.fetch(self)

    async def set_omemo_aliases(self, entries: list[dict]) -> bool:
        from stanza_im.core import omemo_aliases
        return await omemo_aliases.publish(self, entries)

    def supports_omemo(self, bare: str) -> bool:
        """Whether *bare* advertises any OMEMO namespace in its caps."""
        if not getattr(self.omemo, "available", False):
            return False
        from stanza_im.xmpp.omemo import availability
        return (self.supports_feature(bare, availability.LEGACY_NAMESPACE)
                or self.supports_feature(bare, availability.OMEMO2_NAMESPACE))

    def supports_calls(self, bare: str, video: bool = False) -> bool:
        """Conversations-compatible check: does *bare* support A/V calls?"""
        required = list(self.CALL_FEATURES)
        if video:
            required.append("urn:xmpp:jingle:apps:rtp:video")
        for jid, features in self.contact_features.items():
            if jid.split("/")[0] != bare:
                continue
            if all(feature in features for feature in required):
                return True
        return False

    # ── Jingle RTP call API ───────────────────────────────────────

    def start_call(self, jid: str, video: bool = False) -> None:
        self._start_task(self.rtp_calls.start_call(jid, video))

    def answer_call(self, sid: str, accept: bool, video: bool = False) -> None:
        self._start_task(self.rtp_calls.answer_call(sid, accept, video))

    def answer_proposal(self, sid: str, accept: bool,
                        video: bool = False) -> None:
        """Accept/reject a XEP-0353 proposal (sends proceed/reject)."""
        self.rtp_calls.answer_proposal(sid, accept, video)

    def end_call(self, sid: str) -> None:
        self._start_task(self.rtp_calls.end_call(sid))

    def set_call_audio(self, sid: str, enabled: bool) -> None:
        """Mute/unmute the outgoing microphone (silence frames)."""
        self.rtp_calls.set_call_audio(sid, enabled)

    def set_call_audio_receive(self, sid: str, enabled: bool) -> None:
        """Mute/unmute playback of this session's remote audio."""
        self.rtp_calls.set_call_audio_receive(sid, enabled)

    def set_call_video(self, sid: str, enabled: bool) -> None:
        """Turn the local camera on/off (black frames to the peer)."""
        self.rtp_calls.set_call_video(sid, enabled)

    def set_call_local_preview(self, sid: str, enabled: bool = True) -> None:
        """Mark a session as the source of own-video preview frames."""
        self.rtp_calls.set_local_preview(sid, enabled)

    def start_muji_preview(self, room: str) -> None:
        """Open a standalone self-preview capture for a conference."""
        self.rtp_calls.start_local_preview(room)

    def stop_muji_preview(self, room: str) -> None:
        """Stop a conference's standalone self-preview capture."""
        self.rtp_calls.stop_local_preview(room)

    # ── Muji conference API (XEP-0272) ────────────────────────────

    def join_muji(self, room: str, nick: str, video: bool = False) -> None:
        self.muji.join(room, nick, video)

    def leave_muji(self, room: str) -> None:
        self.muji.leave(room)

    def _on_roster_update(self, iq) -> None:
        """A roster push or full roster response arrived.  slixmpp's internal
        handler has already updated ``client_roster`` by the time we run."""
        items = self.get_roster_snapshot()
        new_keys = {item["jid"] for item in items}
        old_keys = set(self.roster.keys())

        added = [item for item in items if item["jid"] not in old_keys]
        removed = [jid for jid in old_keys - new_keys]

        self.roster = {item["jid"]: item for item in items}

        logger.debug("ROSTER[update] got=%d added=%s removed=%s total=%d",
                     len(items), [i["jid"] for i in added], removed,
                     len(self.roster))
        for item in added:
            self.emit("roster_item_added", item)
            self._ensure_pep_subscription(str(item["jid"]))
        for jid in removed:
            self.emit("roster_item_removed", jid)
            self._unsubscribe_pep(jid)
        self.emit("roster_received", items)
        self._schedule_roster_save()

    def _on_groupchat_presence(self, pres) -> None:
        frm = str(pres["from"])
        room = frm.split("/")[0]
        nick = frm.split("/", 1)[1] if "/" in frm else ""
        if room:
            self._known_rooms.add(room)
        self._mark_muc_activity(room)
        ptype = str(pres["type"])

        # Error presences (nick conflict, kick, ban, ...) are delivered by
        # the join task via ``muc_join_error`` or by error callbacks — do not
        # treat them as participants.
        if ptype == "error":
            self.emit("groupchat_presence_error", room, str(room), ptype, "")
            return
        # Muji conference coordination (XEP-0272) piggybacks on MUC presence.
        try:
            self.muji.handle_presence(pres)
        except Exception:
            logger.debug("Muji presence handling failed", exc_info=True)
        if ptype == "unavailable":
            show = "unavailable"
        else:
            show = str(pres.get("show", "")) or "online"
            if show in ("available", "None", ""):
                show = "online"
        status = str(pres.get("status", ""))

        role = ""
        affiliation = ""
        real_jid = ""
        try:
            muc = pres.get("muc")
            if muc is None:
                muc = pres["muc"]
            if muc is not None:
                role = str(muc.get("role", ""))
                affiliation = str(muc.get("affiliation", ""))
                item = muc.get("item")
                if item is None:
                    item = muc["item"]
                if item is not None:
                    real_jid = _clean_jid(item.get("jid", "") or item["jid"])
        except Exception:
            pass

        hats = hats_mod.parse_hats(pres)

        gi = self.groupchats.setdefault(room, GroupChatInfo(room=room, nick=nick))
        if show == "unavailable":
            gi.users.pop(nick, None)
        else:
            previous_client = gi.users.get(nick, {}).get("client", "")
            gi.users[nick] = {
                "show": show,
                "status": status,
                "role": role,
                "affiliation": affiliation,
                "real_jid": real_jid,
                "client": previous_client,
                "caps_node": _caps_node(pres),
                "occupant_id": _occupant_id(pres),
                "hats": hats,
            }
            if real_jid and (room, nick) not in self._muc_version_probed:
                self._muc_version_probed.add((room, nick))
                self._start_task(self._prefetch_muc_version(room, nick, real_jid))
        if nick == gi.nick and show != "unavailable":
            # The self-presence arrives before ``join_muc_wait`` returns; read
            # the XEP-0045 status code here so a room we just created (201) is
            # flagged even on this earlier path.
            created = False
            try:
                created = 201 in (pres["muc"]["status_codes"] or set())
            except Exception:
                created = False
            self._emit_muc_joined(room, gi.subject, list(gi.users),
                                  created=created)
        self.emit("groupchat_presence", room, nick, show, status, role,
                  affiliation, real_jid, hats)

    async def _prefetch_muc_version(self, room: str, nick: str,
                                    jid: str) -> None:
        """Best-effort XEP-0092 lookup for a MUC participant's client."""
        try:
            info = await asyncio.wait_for(
                self.get_entity_version(jid), timeout=8)
        except Exception:
            return
        software = info.get("software") or ""
        gi = self.groupchats.get(room)
        if gi and nick in gi.users:
            gi.users[nick]["client"] = software
        self.emit("groupchat_presence_details", room, nick)

    def _on_subscribed(self, pres) -> None:
        frm = str(pres["from"])
        logger.info("Subscribed to %s", frm)
        self.emit("subscribed", frm)

    def _on_unsubscribed(self, pres) -> None:
        frm = str(pres["from"])
        logger.info("SUB[unsubscribed] from %s", frm)
        self.emit("unsubscribed", frm)
        self.emit("subscription_cancelled", frm.split("/", 1)[0])

    def _on_got_online(self, pres) -> None:
        frm = str(pres["from"])
        self.emit("got_online", frm)

    def _on_auth_failed(self, event=None) -> None:
        # slixmpp passes the SASL failure stanza (with a ``condition`` such as
        # ``not-authorized``); legacy auth raises the event without one.
        condition = ""
        try:
            condition = str(event["condition"] or "") if event is not None else ""
        except (KeyError, TypeError, AttributeError):
            condition = ""
        logger.error("Authentication failed (%s)", condition or "unknown")
        self.emit("auth_failed", condition)

    def _on_disconnected(self, event) -> None:
        logger.info("Disconnected from server")
        self._stop_pep_sweep()
        self._stop_muc_self_ping()
        self._pep_subscribed.clear()
        self.emit("disconnected")
        self._maybe_schedule_reconnect()

    # ── Reconnect (XEP-0198 window, then our own backoff loop) ────────

    _RESUME_WINDOW_S = 10.0
    _RECONNECT_BACKOFF = (1.0, 2.0, 5.0, 15.0, 30.0)

    def resume_expected(self) -> bool:
        """Whether a dropped connection is likely to be resumed (XEP-0198)."""
        if not self.stream_management or "xep_0198" not in self.xmpp.plugin:
            return False
        plugin = self.xmpp.plugin["xep_0198"]
        return bool(getattr(plugin, "sm_id", None))

    def _maybe_schedule_reconnect(self) -> None:
        """Wait briefly for an SM resume, then start our reconnect loop."""
        if not self._reconnect_enabled or self._shutting_down:
            return
        if self._reconnect_handle is not None:
            return
        if self.resume_expected():
            # Give the server a short window to resume the stream; if the
            # ``session_resumed`` event arrives it cancels the reconnect.
            try:
                loop = asyncio.get_event_loop()
                self._reconnect_handle = loop.call_later(
                    self._RESUME_WINDOW_S, self._start_reconnect_loop)
            except RuntimeError:
                self._start_reconnect_loop()
        else:
            self._start_reconnect_loop()

    async def manual_reconnect(self) -> None:
        """User-requested reconnect: reset the backoff and try once."""
        self._reconnect_enabled = True
        self._shutting_down = False
        self._cancel_reconnect()
        self.emit("reconnecting", 1, 0.0)
        try:
            await self.connect_async()
        except Exception as exc:
            logger.info("Manual reconnect failed: %r", exc)
            self.emit("reconnect_failed", 1)
            self._maybe_schedule_reconnect()
            return
        if self.xmpp.is_connected():
            self.emit("reconnected")

    def _cancel_reconnect(self) -> None:
        if self._reconnect_handle is not None:
            try:
                self._reconnect_handle.cancel()
            except Exception:
                pass
            self._reconnect_handle = None
        if self._reconnect_task is not None and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        self._reconnect_task = None
        self._reconnect_attempt = 0

    def _start_reconnect_loop(self) -> None:
        self._reconnect_handle = None
        if not self._reconnect_enabled or self._shutting_down:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = self._start_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Retry ``connect_async`` with exponential backoff (no attempt cap)."""
        while self._reconnect_enabled and not self._shutting_down:
            if self.xmpp.is_connected():
                return
            delay = self._RECONNECT_BACKOFF[
                min(self._reconnect_attempt, len(self._RECONNECT_BACKOFF) - 1)]
            self._reconnect_attempt += 1
            logger.info("Reconnect attempt %d in %.0fs", self._reconnect_attempt,
                        delay)
            self.emit("reconnecting", self._reconnect_attempt, delay)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return
            if not self._reconnect_enabled or self._shutting_down:
                return
            try:
                await self.connect_async()
            except Exception as exc:
                logger.info("Reconnect attempt %d failed: %r",
                            self._reconnect_attempt, exc)
                self.emit("reconnect_failed", self._reconnect_attempt)
                continue
            # ``connect_async`` resolves once the transport is up; the full
            # session (roster/presence/PEP/autojoin) re-runs in
            # ``_on_session_start``.
            if self.xmpp.is_connected():
                self._reconnect_attempt = 0
                self.emit("reconnected")
                return

    def _on_sm_enabled(self, _event=None) -> None:
        logger.info("Stream management enabled")
        self._sm_resumed = False
        self.emit("sm_enabled")

    def _on_session_resumed(self, _event=None) -> None:
        logger.info("Stream resumed (XEP-0198)")
        self._sm_resumed = True
        self._cancel_reconnect()
        self._sync_csi()
        for bare in self.contacts:
            self._ensure_pep_subscription(bare)
        self._start_pep_sweep()
        self._start_muc_self_ping()
        self.emit("stream_resumed")

    def _on_sm_failed(self, _event=None) -> None:
        logger.warning("Stream management resumption failed")
        self._sm_resumed = False
        self.emit("sm_failed")
        # The server refused to resume — start the reconnect loop now.
        self._start_reconnect_loop()

    def _on_sm_disabled(self, _event=None) -> None:
        self._sm_resumed = False
        self.emit("sm_disabled")

    def _on_csi_enabled(self, _event=None) -> None:
        logger.info("Client state indication enabled")
        self._csi_enabled = True
        self._sync_csi()
        self.emit("csi_enabled")

    def _on_presence_error(self, pres) -> None:
        frm = str(pres["from"])
        error = pres.get("error", {})
        code = error.get("code", "unknown")
        self.emit("presence_error", frm, code)

    def _on_disco_info(self, event) -> None:
        jid = str(event.get("from", ""))
        self.emit("disco_info_received", jid)

    def _on_vcard(self, iq, requested_jid: str = "") -> None:
        jid = _clean_jid(iq.get("from", "")) or _clean_jid(requested_jid)
        bare = jid.split("/")[0]
        card = _parse_vcard(iq)
        card["jid"] = jid
        photo = card.get("photo")
        if photo:
            try:
                from stanza_im.include.avatars import save_avatar
                card["avatar_path"] = save_avatar(jid or bare, photo)
                self._avatar_ids[bare] = hashlib.sha1(photo).hexdigest()
            except Exception:
                pass
        if "/" not in jid:
            contact = self.get_contact(bare)
            if not card.get("avatar_path") and contact.avatar_path:
                card["avatar_path"] = contact.avatar_path
            contact.vcard = card
        card["fetched_at"] = time.time()
        self._vcard_cache.put(jid or bare, card)
        logger.debug("vCard received for %s", jid or bare)
        self.emit("vcard_received", jid or bare, card)

    async def fetch_history_mam(self, jid: str, since: str | None = None,
                                limit: int = 200) -> int | None:
        """Fetch older messages for *jid* from the server archive (MAM,
        XEP-0313) and store them locally.

        Queries only the range strictly before the locally stored ``since``
        timestamp so overlapping messages are not re-fetched.  Returns the
        number of messages stored, or ``None`` when another query for the
        same JID is in flight.
        """
        if jid in self._mam_inflight:
            return None
        if since is None:
            self._mam_cursors.pop(jid, None)
        self._mam_inflight.add(jid)
        try:
            return await self._fetch_history_mam_impl(jid, since, limit)
        finally:
            self._mam_inflight.discard(jid)

    @staticmethod
    def _mam_query_modes(is_muc: bool, end) -> list[tuple[bool, object]]:
        """Return the ordered list of ``(use_archive_jid, query_end)`` pairs
        for :meth:`_fetch_history_mam_impl`.

        For 1:1 chats ``use_archive_jid`` is always ``False`` — the query
        is sent to the *user's own* archive with ``<with>jid</with>``.
        Sending the IQ ``to`` a 1:1 contact (``jid`` mode, ``use_archive_jid``
        ``True``) returns the *contact's* full archive, mixing other
        contacts' messages into the local history.  For MUC rooms ``jid``
        mode is correct (the room archive lives on the room's JID).
        """
        modes: list[tuple[bool, object]] = [(is_muc, end)]
        if is_muc:
            if end is not None:
                modes.append((True, None))
        else:
            if end is not None:
                modes.append((False, None))
        return modes

    @staticmethod
    def _mam_belongs_to(jid: str, frm: str, is_muc: bool,
                        own_jid: str) -> bool:
        """True when a MAM result stanza belongs to the *jid* conversation.

        For 1:1 chats only the two parties are accepted: the contact (its
        bare JID must equal ``jid``) and our own bare JID (outgoing copies).
        Anything else — a server that ignored the ``<with>`` filter or
        returned another account's archive — is rejected.  MUC results are
        accepted as-is because their senders are room nicks.
        """
        if is_muc:
            return True
        bare = frm.split("/", 1)[0].lower()
        return bare == jid.lower() or bare == own_jid.lower()

    async def _fetch_history_mam_impl(self, jid: str, since: str | None,
                                       limit: int) -> int:
        mam = self.xmpp.plugin["xep_0313"]
        end = None
        if since:
            try:
                ts = since
                end = datetime.datetime.fromisoformat(
                    ts.replace("Z", "+00:00"))
                if end.tzinfo is None:
                    end = end.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                end = None
        cursor = self._mam_cursors.get(jid)
        if cursor:
            end = None
        rsm = {"max": int(limit)}
        if cursor:
            rsm["before"] = cursor
        elif since is None:
            # slixmpp serializes True as an empty <before/> element. An empty
            # string is omitted, which makes ejabberd return the oldest page.
            rsm["before"] = True
        modes = self._mam_query_modes(jid in self.groupchats, end)
        results = []
        last_error = None
        for index, (use_archive_jid, query_end) in enumerate(modes, 1):
            mode = "jid" if use_archive_jid else "with_jid"
            logger.info("MAM query %d for %s: mode=%s end=%s before=%s max=%s",
                        index, jid, mode, query_end, rsm.get("before"), limit)
            try:
                task = (mam.retrieve(jid=jid, end=query_end, rsm=rsm)
                        if use_archive_jid
                        else mam.retrieve(with_jid=jid, end=query_end, rsm=rsm))
                iq = await asyncio.wait_for(task, timeout=25.0)
                if str(iq.get("type", "result")) == "error":
                    last_error = iq
                    logger.warning("MAM IQ error for %s (%s): %s",
                                   jid, mode, str(iq))
                    continue
                last_error = None
                results = iq.get("mam", {}).get("results") or []
                logger.info("MAM query %d for %s returned %d results",
                            index, jid, len(results))
                if results:
                    break
            except asyncio.TimeoutError:
                last_error = "timeout"
                logger.info("MAM query timed out for %s", jid)
            except Exception as exc:
                last_error = exc
                logger.debug("MAM query %d for %s failed: %r",
                             index, jid, exc)
        if not results and last_error is not None:
            logger.debug("MAM returned no usable results for %s: %r",
                         jid, last_error)
            self.emit("mam_unavailable", jid)
            return 0

        if results:
            archive_ids = []
            for result in results:
                archive_id = _archive_result_id(result)
                if archive_id:
                    archive_ids.append(str(archive_id))
            if archive_ids:
                try:
                    self._mam_cursors[jid] = min(archive_ids, key=int)
                except ValueError:
                    self._mam_cursors[jid] = archive_ids[0]
                logger.info("MAM cursor for %s advanced to before=%s",
                            jid, self._mam_cursors[jid])
            else:
                logger.warning("MAM results for %s have no archive cursor", jid)

        me = self.jid_str.split("@")[0]
        my_nick = ""
        gi = self.groupchats.get(jid)
        if gi:
            my_nick = gi.nick
        stored = 0
        parsed = 0
        skipped = 0
        duplicates = 0
        skip_reasons: dict[str, int] = {}
        rows: list[dict] = []
        for result in results:
            try:
                fwd = _stanza_value(result, "forwarded")
                msg = _forwarded_stanza(fwd) or result
                if msg is None or not hasattr(msg, "get"):
                    logger.warning("MAM result %d for %s has no message stanza: %r",
                                   results.index(result), jid, result)
                    skipped += 1
                    skip_reasons["no_stanza"] = skip_reasons.get("no_stanza", 0) + 1
                    continue
                tomb_id, _tomb_stamp = _retracted_tombstone(msg)
                mod_info = _moderation_info(msg)
                body = str(_stanza_value(msg, "body") or "")
                if not body and not tomb_id:
                    skipped += 1
                    skip_reasons["empty_body"] = skip_reasons.get("empty_body", 0) + 1
                    continue
                parsed += 1
                frm = str(_stanza_value(msg, "from") or "")
                stamp = _message_timestamp(msg, result)
                if not stamp:
                    skipped += 1
                    skip_reasons["missing_timestamp"] = (
                        skip_reasons.get("missing_timestamp", 0) + 1)
                    logger.warning("MAM result for %s has no server timestamp",
                                   jid)
                    continue
                ts = _normalize_ts(stamp)
                direction = "incoming"
                sender = ""
                if jid in self.groupchats:
                    sender = frm.split("/", 1)[1] if "/" in frm else frm
                    if sender == my_nick:
                        direction = "outgoing"
                        sender = "Me"
                else:
                    sender = frm.split("/", 1)[0]
                    if sender == self.jid_str:
                        direction = "outgoing"
                        sender = "Me"
                    elif not self._mam_belongs_to(jid, frm, False,
                                                  self.jid_str):
                        # A misbehaving server (e.g. one that ignores the
                        # <with> filter and returns another account's whole
                        # archive) can yield stanzas addressed to other
                        # contacts.  Never let them pollute this chat's
                        # local history.
                        skipped += 1
                        skip_reasons["wrong_sender"] = (
                            skip_reasons.get("wrong_sender", 0) + 1)
                        continue
                from stanza_im.core import history
                if jid in self.groupchats:
                    stable = _stanza_id(msg, jid) or _archive_result_id(result)
                else:
                    stable = _origin_id(msg) or str(msg.get("id") or "")
                rows.append({
                    "direction": direction,
                    "body": body,
                    "timestamp": ts or None,
                    "sender": sender,
                    "archive_id": _archive_result_id(result),
                    "origin_id": stable,
                    "reply_to": _reply_reference(msg)[0],
                    "reply_id": _reply_reference(msg)[1],
                    "retracted": bool(tomb_id),
                    "retract_reason": mod_info["reason"],
                    "retract_by": mod_info["by"],
                    "markup": message_markup(msg),
                })
            except Exception:
                skipped += 1
                skip_reasons["exception"] = skip_reasons.get("exception", 0) + 1
                logger.debug("Could not parse MAM result for %s",
                             jid, exc_info=True)
                continue
        if rows:
            inserted = await history.store_many_async(jid, rows)
            stored = inserted
            duplicates = len(rows) - inserted
        logger.info("MAM returned %d results for %s: parsed=%d skipped=%d "
                    "duplicates=%d stored=%d", len(results), jid, parsed,
                    skipped, duplicates, stored)
        if skip_reasons:
            logger.info("MAM skip reasons for %s: %s", jid, skip_reasons)
        if results and parsed and not stored and not duplicates:
            self.emit("mam_parse_error", jid, len(results), parsed, skipped)
            return -1
        return stored + duplicates

    def _on_chatstate(self, msg) -> None:
        # Chat states (XEP-0085) apply to 1:1 messaging only — ignore
        # groupchat messages so a conference never appears "active".
        if str(msg["type"]) == "groupchat":
            return
        frm = str(msg["from"]).split("/")[0]
        state = str(msg["chat_state"])
        self.emit("chatstate_received", frm, state)
        if state in ("composing", "paused"):
            self.emit("typing", frm, state == "composing")

    def _on_receipt_received(self, msg) -> None:
        frm = str(msg["from"]).split("/")[0]
        logger.debug("Message receipt delivered to %s", frm)
        receipt_id = str(msg.get("receipt", "") or msg.get("id", ""))
        self.emit("receipt_delivered", frm, receipt_id)


def _normalize_ts(ts: str) -> str:
    """Normalize an XEP-0082 timestamp to canonical UTC ISO-8601."""
    value = str(ts or "").strip()
    if not value:
        return ""
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    parsed = parsed.astimezone(datetime.timezone.utc)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _message_timestamp(message, result=None) -> str:
    """Extract the original server timestamp from a MAM result."""
    for stanza in (message, result):
        delay = _stanza_value(stanza, "delay")
        stamp = _stanza_value(delay, "stamp")
        if isinstance(stamp, datetime.datetime):
            return stamp.strftime("%Y-%m-%dT%H:%M:%S")
        if stamp:
            value = str(stamp).strip()
            if value:
                return value
    return ""


def _archive_result_id(result) -> str:
    """Return the stable archive id from a forwarded MAM result."""
    # Prefer the archive markers in the raw XML. The slixmpp MAM result
    # wrapper does not always expose its outer ``result`` attributes through
    # the normal stanza mapping interface.
    for xml in (getattr(result, "xml", None), result):
        if xml is None or not hasattr(xml, "iter"):
            continue
        for node in xml.iter():
            tag = str(node.tag).rsplit("}", 1)[-1]
            if tag in ("archived", "stanza-id", "result"):
                value = node.attrib.get("id")
                if value:
                    return str(value)
    forwarded = _stanza_value(result, "forwarded")
    message = _forwarded_stanza(forwarded)
    if message is not None:
        for key in ("stanza-id", "archived"):
            marker = _stanza_value(message, key)
            value = _stanza_value(marker, "id")
            if value:
                return str(value)
    value = _stanza_value(result, "id")
    return str(value) if value else ""


def _has_stanza_element(stanza, tag: str) -> bool:
    """Return whether a stanza contains an XML child named *tag*."""
    xml = getattr(stanza, "xml", None)
    if xml is None and hasattr(stanza, "iter"):
        xml = stanza
    if xml is None:
        return False
    return any(str(node.tag).rsplit("}", 1)[-1] == tag
               for node in xml.iter())


def _clean_jid(value) -> str:
    """Normalize stanza values so None never becomes the JID ``"None"``."""
    if value is None:
        return ""
    result = str(value).strip()
    return "" if result.lower() in ("", "none", "null") else result


def _forwarded_stanza(forwarded):
    """Extract the inner stanza from slixmpp's XEP-0297 object."""
    if forwarded is None:
        return None
    xml = getattr(forwarded, "xml", None)
    if xml is None and hasattr(forwarded, "iter"):
        xml = forwarded
    if xml is not None:
        for node in xml.iter():
            if str(node.tag).rsplit("}", 1)[-1] == "message":
                return node
    getter = getattr(forwarded, "get_stanza", None)
    if getter is not None:
        stanza = getter()
        if stanza:
            return stanza
    try:
        stanza = forwarded.get("stanza")
        if stanza:
            return stanza
    except (AttributeError, KeyError, TypeError):
        pass
    try:
        return forwarded["stanza"]
    except (KeyError, TypeError, AttributeError):
        return None


def _stanza_value(stanza, key: str, default=""):
    """Read a slixmpp stanza field through both public interfaces."""
    if stanza is None:
        return default
    xml = getattr(stanza, "xml", None)
    if xml is None and hasattr(stanza, "iter"):
        xml = stanza
    if xml is not None:
        if key in xml.attrib:
            return xml.attrib[key]
        for node in xml.iter():
            if str(node.tag).rsplit("}", 1)[-1] != key:
                continue
            if key in node.attrib:
                return node.attrib[key]
            return node if key in ("delay", "forwarded") else (node.text or "")
    try:
        value = stanza.get(key)
        if value not in (None, ""):
            return value
    except (AttributeError, KeyError, TypeError):
        pass
    try:
        value = stanza[key]
        return default if value is None else value
    except (KeyError, TypeError, AttributeError):
        return default


# ── Data classes ──────────────────────────────────────────────────


class ContactInfo:
    """Lightweight contact data object."""

    __slots__ = ("jid", "name", "groups", "subscription", "show", "status",
                 "avatar_path", "vcard", "resources")

    def __init__(self, jid: str, name: str = "", groups: list[str] | None = None,
                 subscription: str = "both"):
        self.jid = jid
        self.name = name or jid.split("@")[0]
        self.groups = groups or []
        self.subscription = subscription
        self.show = "offline"
        self.status = ""
        self.avatar_path: str | None = None
        self.vcard: dict | None = None
        self.resources: dict[str, dict] = {}  # {resource: {show, status, priority}}


class GroupChatInfo:
    """Lightweight groupchat data object."""

    __slots__ = ("room", "nick", "password", "subject", "users", "joined",
                 "pending_history")

    def __init__(self, room: str, nick: str):
        self.room = room
        self.nick = nick
        self.password = ""
        self.subject = ""
        self.users: dict[str, dict] = {}  # {nick: {show, status, role, affiliation}}
        self.joined = False
        self.pending_history: list = []
