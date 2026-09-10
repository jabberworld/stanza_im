"""XMPP client wrapper around slixmpp.

Provides a high-level async API and emits Qt-style callbacks that the UI
layer connects to.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import platform
import time
import uuid
from typing import Any, Callable
from xml.etree import ElementTree as ET

import slixmpp
from slixmpp.jid import JID

from stanza_im.include.enumerators import SHOW_ORDER
from stanza_im.include.vcard import parse_vcard as _parse_vcard, build_vcard as _build_vcard
from stanza_im.core.vcard_cache import VCardCache
from stanza_im.include.constants import APP_NAME, VERSION

logger = logging.getLogger(__name__)

_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
NS_REPLY = "urn:xmpp:reply:0"      # XEP-0461 Message Replies
NS_SID = "urn:xmpp:sid:0"          # XEP-0359 Unique and Stable Stanza IDs
NS_CARBONS = "urn:xmpp:carbons:2"  # XEP-0280 Message Carbons
NS_FORWARD = "urn:xmpp:forward:0"  # XEP-0297 Stanza Forwarding


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


def _reply_reference(stanza) -> tuple[str, str]:
    """Return ``(to, id)`` of a XEP-0461 ``<reply/>`` on *stanza* ("" if none)."""
    xml = getattr(stanza, "xml", None)
    if xml is None:
        return ("", "")
    for el in xml:
        if el.tag == "{%s}reply" % NS_REPLY:
            return (str(el.get("to", "")), str(el.get("id", "")))
    return ("", "")


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


class JabberClient:
    """High-level XMPP client built on top of slixmpp.ClientXMPP."""

    def __init__(self, jid: str, password: str, resource: str = "jabbim",
                 host: str = "", port: int = 0,
                 auto_join_conferences: bool = True,
                 send_chatstates: bool = True,
                 send_typing_notifications: bool = True,
                 send_activity_notifications: bool = True,
                 send_software: bool = True,
                 message_carbons: bool = True):
        self.jid_str = jid
        self.resource = resource
        self.host = host
        self.port = int(port or 0)
        self.auto_join_conferences = auto_join_conferences
        self.autojoin_rooms: set[str] = set()
        self.message_carbons = message_carbons
        self.send_typing_notifications = send_typing_notifications if send_chatstates else False
        self.send_activity_notifications = send_activity_notifications if send_chatstates else False
        self.send_chatstates = (self.send_typing_notifications
                                or self.send_activity_notifications)
        self.send_software = send_software
        self._full_jid = f"{jid}/{resource}"

        self.xmpp = slixmpp.ClientXMPP(jid, password, sasl_mech="SCRAM-SHA-1")
        self.xmpp.requested_jid = JID(f"{jid}/{resource}")
        self.xmpp.auto_reconnect = True
        self.xmpp.reconnect_max_retries = 5

        # Register XEP plugins
        self.xmpp.register_plugin("xep_0054")  # vCard
        self.xmpp.register_plugin("xep_0045")  # MUC
        self.xmpp.register_plugin("xep_0066")  # OOB (file transfer)
        self.xmpp.register_plugin("xep_0085")  # Chat State Notifications
        self.xmpp.register_plugin("xep_0184")  # Message Receipts
        self.xmpp.register_plugin("xep_0224")  # Attention
        self.xmpp.register_plugin("xep_0048")  # Bookmarks
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
        self.xmpp.register_plugin("xep_0313")  # Message Archive Management (MAM)
        # xep_0313 pulls in xep_0059 (RSM) and xep_0297 (Forward) automatically
        self.xmpp.register_plugin("xep_0280")  # Message Carbons

        # XEP-0393 Message Styling (urn:xmpp:styling:0) — advertised in disco.
        self.xmpp["xep_0030"].add_feature("urn:xmpp:styling:0")
        # XEP-0461 Message Replies (urn:xmpp:reply:0) — advertised in disco.
        self.xmpp["xep_0030"].add_feature(NS_REPLY)

        # Callbacks: list of callables keyed by event name
        self._callbacks: dict[str, list[Callable]] = {}

        # Internal state
        self.roster: dict[str, Any] = {}  # {jid_str: roster_entry}
        self.contacts: dict[str, ContactInfo] = {}
        self.groupchats: dict[str, GroupChatInfo] = {}
        self.presences: dict[str, dict] = {}  # {full_jid: {show, status, ...}}
        self._muc_subjects: dict[str, list[tuple[str, str]]] = {}
        self._mam_inflight: set[str] = set()  # JIDs with an active MAM query
        self._mam_cursors: dict[str, str] = {}
        self._vcard_cache = VCardCache()
        self._vcard_inflight: set[str] = set()
        self._muc_join_tasks: dict[str, asyncio.Task] = {}
        self._version_probed: set[str] = set()        # full JIDs (XEP-0092)
        self._muc_version_probed: set[tuple[str, str]] = set()

        # Hook up slixmpp events
        self.xmpp.add_event_handler("session_start", self._on_session_start)
        self.xmpp.add_event_handler("disco_info", self._on_disco_info)
        self.xmpp.add_event_handler("message", self._on_message)
        self.xmpp.add_event_handler("presence_available", self._on_presence)
        self.xmpp.add_event_handler("presence_unavailable", self._on_presence)
        self.xmpp.add_event_handler("presence_subscribed", self._on_subscribed)
        self.xmpp.add_event_handler("presence_unsubscribed", self._on_unsubscribed)
        self.xmpp.add_event_handler("groupchat_message", self._on_groupchat_message)
        self.xmpp.add_event_handler("groupchat_subject", self._on_groupchat_subject)
        self.xmpp.add_event_handler("groupchat_presence", self._on_groupchat_presence)
        self.xmpp.add_event_handler("got_online", self._on_got_online)
        self.xmpp.add_event_handler("failed_auth", self._on_auth_failed)
        self.xmpp.add_event_handler("disconnected", self._on_disconnected)
        self.xmpp.add_event_handler("presence_error", self._on_presence_error)
        self.xmpp.add_event_handler("roster_update", self._on_roster_update)
        self.xmpp.add_event_handler("chatstate", self._on_chatstate)
        self.xmpp.add_event_handler("receipt_received", self._on_receipt_received)
        self.xmpp.add_event_handler("carbon_received", self._on_carbon_received)
        self.xmpp.add_event_handler("carbon_sent", self._on_carbon_sent)

    # ── Public API ────────────────────────────────────────────────

    def _start_task(self, coro) -> None:
        """Schedule *coro* on the current event loop (best-effort)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return
        loop.create_task(coro)

    def on(self, event: str, callback: Callable) -> None:
        """Register a callback for an internal event name."""
        self._callbacks.setdefault(event, []).append(callback)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Invoke all callbacks registered for *event*."""
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args, **kwargs)
            except Exception:
                logger.exception("Error in callback for %s", event)

    async def connect_async(self) -> None:
        """Connect to the XMPP server and start the session."""
        result = self.xmpp.connect(self.host or None, self.port or None)
        if asyncio.iscoroutine(result):
            await result
        elif isinstance(result, asyncio.Future):
            await result

    async def disconnect(self) -> None:
        """Gracefully disconnect."""
        if self.xmpp.is_connected():
            self.xmpp.disconnect()

    def send_message(self, jid: str, body: str, mtype: str = "chat",
                     mhtml: str | None = None, reply_to: str = "",
                     reply_id: str = "", reply_ref_sender: str = "",
                     reply_ref_body: str = "") -> str:
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
        if mtype == "chat":
            msg["request_receipt"] = True  # XEP-0184
        if mhtml:
            msg["html"]["body"] = mhtml
        logger.debug("Sending %s message to %s (reply_id=%s): %r",
                     mtype, jid, reply_id, body[:200])
        msg.send()
        return message_id

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
        if priority is not None:
            p["priority"] = priority
        logger.debug("Sending presence: %s", show or "available")
        p.send()

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
            item = cr[jid]
            items.append({
                "jid": jid,
                "name": item["name"],
                "groups": list(item["groups"]),
                "subscription": item["subscription"],
            })
        return items

    def get_contact(self, bare_jid: str) -> ContactInfo:
        """Return (creating if needed) the ContactInfo for a bare JID."""
        jid = str(bare_jid).split("/")[0]
        if jid not in self.contacts:
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
        gi = self.groupchats.setdefault(
            room, GroupChatInfo(room=room, nick=nick))
        gi.nick = nick
        gi.password = password or ""
        gi.joined = False
        loop = asyncio.get_event_loop()
        if save_bookmark:
            loop.create_task(self.save_bookmark(room, nick, password,
                                                autojoin=True))
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
        subjects = _message_subjects(subject_msg)
        subject = next((t for lang, t in subjects if not lang), "")
        if not subject and subjects:
            subject = subjects[0][1]
        gi = self.groupchats.get(room)
        if gi:
            gi.subject = subject
            gi.pending_history = _history or []
        self._muc_subjects[room] = subjects or [("", subject)]
        self._emit_muc_joined(room, subject, list(occupants or []))

    def _emit_muc_joined(self, room: str, subject: str = "",
                         occupants: list | None = None) -> None:
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
        logger.info("Joined room %s as %s (%d occupants)",
                    room, gi.nick, len(occupants))
        self.emit("muc_joined", room, subject or gi.subject, occupants)
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
        fields = dict(reg["fields"]) if reg["fields"] else None
        return {"registered": bool(reg["registered"]), "form": form,
                "fields": fields}

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

    async def get_commands_list(self, jid: str) -> list[dict]:
        """Return the XEP-0050 ad-hoc command list of a service."""
        node = "http://jabber.org/protocol/commands"
        result = await self.xmpp["xep_0030"].get_items(jid=jid, node=node)
        return [{"jid": str(item.get("jid") or jid),
                 "node": str(item.get("node") or ""),
                 "name": str(item.get("name") or item.get("node") or "")}
                for item in result.xml.iter()
                if str(item.tag).endswith("item") and item.get("node")]

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
            if name:
                logger.info("MUC room name received for %s: %s", room, name)
                self.emit("muc_info_received", room, name)
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
            result = await self.xmpp.plugin["xep_0202"].get_entity_time(jid)
            info["client_time"] = str(result.get("time", "") or result.get("utc", ""))
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
                history.store_message(room, direction, body,
                                      timestamp=_normalize_ts(str(stamp)) or None,
                                      sender=sender, skip_existing=True,
                                      origin_id=_stanza_id(msg, room) or "",
                                      reply_to=_reply_reference(msg)[0],
                                      reply_id=_reply_reference(msg)[1])
            except Exception:
                logger.debug("Could not store MUC join history for %s",
                             room, exc_info=True)

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

    async def save_bookmark(self, room: str, nick: str, password: str = "",
                            autojoin: bool = True, name: str = "") -> None:
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
        try:
            await plugin.set_bookmarks(bookmarks)
            logger.debug("Saved bookmark for room %s", room)
        except Exception:
            logger.exception("Failed to save bookmark for %s", room)

    async def list_bookmarks(self) -> list[dict]:
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

    async def remove_bookmark(self, room: str) -> None:
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

    def leave_muc(self, room: str, reason: str = "") -> None:
        """Leave a Multi-User Chat room."""
        muc = self.xmpp.plugin["xep_0045"]
        nick = self.groupchats[room].nick if room in self.groupchats else ""
        muc.leave_muc(room, nick, msg=reason)
        task = self._muc_join_tasks.pop(room, None)
        if task and not task.done():
            task.cancel()
        self.groupchats.pop(room, None)

    def send_muc_message(self, room: str, body: str, reply_to: str = "",
                         reply_id: str = "", reply_ref_sender: str = "",
                         reply_ref_body: str = "") -> None:
        """Send a message to a MUC room, optionally replying to *reply_id*."""
        self.send_message(room, body, mtype="groupchat",
                          reply_to=reply_to, reply_id=reply_id,
                          reply_ref_sender=reply_ref_sender,
                          reply_ref_body=reply_ref_body)

    def set_muc_role(self, room: str, nick: str, role: str) -> None:
        """Request a MUC role change for an occupant."""
        result = self.xmpp.plugin["xep_0045"].set_role(
            room, nick, role, reason="")
        if asyncio.iscoroutine(result):
            asyncio.get_event_loop().create_task(result)

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
            except Exception:
                pass
        self.emit("vcard_updated", self.jid_str, card)
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

    def resend_subscription(self, jid: str) -> None:
        """Send a fresh presence subscribe request to *jid* (e.g. after a
        rejected or pending subscription)."""
        self.xmpp.send_presence_subscription(
            pto=jid, pfrom=self._full_jid, ptype="subscribe"
        )

    def send_file(self, jid: str, filepath: str) -> None:
        """Send a file via SI file transfer (XEP-0066 / XEP-0096)."""
        # Placeholder — will be implemented in Phase 2
        logger.info("File transfer to %s: %s (not yet implemented)", jid, filepath)

    def get_muc_list(self, service: str) -> None:
        """Discover MUC rooms on *service* via Service Discovery."""
        disco = self.xmpp.plugin["xep_0030"]
        if disco.supports(service, "http://jabber.org/protocol/muc"):
            logger.info("Service %s supports MUC", service)

    def approve_subscription(self, jid: str) -> None:
        """Approve a presence subscription request."""
        self.xmpp.send_presence_subscription(
            pto=jid, pfrom=self._full_jid, ptype="subscribed"
        )

    def reject_subscription(self, jid: str) -> None:
        """Reject a presence subscription request."""
        self.xmpp.send_presence_subscription(
            pto=jid, pfrom=self._full_jid, ptype="unsubscribed"
        )

    # ── Internal event handlers ───────────────────────────────────

    async def _on_session_start(self, event) -> None:
        logger.info("Session started, requesting roster...")
        self.request_roster()
        self.send_presence()
        if self.message_carbons:
            try:
                await self.xmpp["xep_0280"].enable()
                logger.info("Enabled message carbons (XEP-0280)")
            except Exception as exc:
                logger.warning("Could not enable message carbons: %s", exc)
        self.emit("session_started")
        loop = asyncio.get_event_loop()
        loop.create_task(self._autojoin_bookmarks())

    async def _autojoin_bookmarks(self) -> None:
        """Join bookmarked MUC rooms flagged for auto-join (XEP-0048).

        Implemented here (instead of the plugin's ``auto_join`` flag) because
        the shipped slixmpp ``_autojoin`` does not await the coroutine-returning
        ``get_bookmarks``.
        """
        plugin = self.xmpp.plugin["xep_0048"]
        if not self.auto_join_conferences:
            return
        try:
            result = await plugin.get_bookmarks()
            if plugin.storage_method == "xep_0223":
                bookmarks = result["pubsub"]["items"]["item"]["bookmarks"]
            else:
                bookmarks = result["private"]["bookmarks"]
        except Exception:
            logger.debug("No bookmarks to auto-join", exc_info=True)
            return
        for conf in bookmarks["conferences"]:
            try:
                room = conf["jid"]
                autojoin = conf["autojoin"]
                nick = conf["nick"] or self.jid_str.split("@")[0]
                password = conf["password"] or ""
            except Exception:
                continue
            if not autojoin or not room or room in self.groupchats:
                continue
            logger.info("Auto-joining bookmarked room %s", room)
            self.autojoin_rooms.add(room)
            try:
                self.join_muc(room, nick, password=password, save_bookmark=False)
            except Exception:
                logger.debug("Could not auto-join room %s", room, exc_info=True)

    def _on_message(self, msg) -> None:
        if msg["type"] in ("chat", "normal"):
            body = str(msg["body"])
            frm = str(msg["from"])
            unstyled, ts, reply_to, reply_id, stable_id = \
                self._message_fields(msg)
            room, separator, nick = frm.partition("/")
            if separator and room in self.groupchats:
                self.emit("muc_private_message", room, nick, body, ts, unstyled,
                          stable_id, frm, reply_to, reply_id)
                return
            self.emit("message_received", frm, body, ts, unstyled,
                      stable_id, frm, reply_to, reply_id)

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
        if inner["type"] not in ("chat", "normal"):
            return
        body = str(inner["body"])
        frm = str(inner["from"])
        unstyled, ts, reply_to, reply_id, stable_id = \
            self._message_fields(inner)
        self.emit("message_received", frm, body, ts, unstyled,
                  stable_id, frm, reply_to, reply_id, True)

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
        unstyled, ts, reply_to, reply_id, stable_id = \
            self._message_fields(inner)
        self.emit("message_carbon_sent", bare, body, ts,
                  stable_id, reply_to, reply_id)

    def _on_groupchat_message(self, msg) -> None:
        frm = str(msg["from"])
        room = frm.split("/")[0]
        nick = frm.split("/", 1)[1] if "/" in frm else ""
        body = str(msg["body"])
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
        self.emit("groupchat_message", room, nick, body, ts, archived,
                  archive_id, unstyled, stable_id, frm, reply_to, reply_id)

    def _on_groupchat_subject(self, msg) -> None:
        """A MUC subject was set/announced (subject-only message).

        Servers deliver the current subject right after joining and on every
        change as a ``<message type="groupchat"><subject>…</subject></message>``
        stanza, which slixmpp routes to the ``groupchat_subject`` event.
        """
        room = str(msg["from"]).split("/")[0]
        if room not in self.groupchats:
            return
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
        frm = str(pres["from"])
        bare, _, resource = frm.partition("/")
        ptype = str(pres["type"])
        show = str(pres.get("show", ""))
        if ptype != "available":
            show = "offline"
        elif show in ("", "available", "None"):
            show = "online"
        status = str(pres.get("status", ""))
        try:
            priority = int(pres.get("priority", 0) or 0)
        except (TypeError, ValueError):
            priority = 0
        self.presences[frm] = {"show": show, "status": status, "type": ptype,
                               "priority": priority, "client": ""}

        contact = self.get_contact(bare)
        if ptype != "available":
            if resource:
                contact.resources.pop(resource, None)
        else:
            previous_client = contact.resources.get(resource, {}).get("client", "")
            contact.resources[resource] = {
                "show": show, "status": status, "priority": priority,
                "client": previous_client,
            }
            if resource and frm not in self._version_probed:
                self._version_probed.add(frm)
                self._start_task(self._prefetch_version(frm))

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

    def _on_roster_update(self, iq) -> None:
        """A roster push or full roster response arrived.  slixmpp's internal
        handler has already updated ``client_roster`` by the time we run."""
        items = self.get_roster_snapshot()
        new_keys = {item["jid"] for item in items}
        old_keys = set(self.roster.keys())

        added = [item for item in items if item["jid"] not in old_keys]
        removed = [jid for jid in old_keys - new_keys]

        self.roster = {item["jid"]: item for item in items}

        for item in added:
            self.emit("roster_item_added", item)
        for jid in removed:
            self.emit("roster_item_removed", jid)
        self.emit("roster_received", items)

    def _on_groupchat_presence(self, pres) -> None:
        frm = str(pres["from"])
        room = frm.split("/")[0]
        nick = frm.split("/", 1)[1] if "/" in frm else ""
        ptype = str(pres["type"])

        # Error presences (nick conflict, kick, ban, ...) are delivered by
        # the join task via ``muc_join_error`` or by error callbacks — do not
        # treat them as participants.
        if ptype == "error":
            self.emit("groupchat_presence_error", room, str(room), ptype, "")
            return
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
            }
            if real_jid and (room, nick) not in self._muc_version_probed:
                self._muc_version_probed.add((room, nick))
                self._start_task(self._prefetch_muc_version(room, nick, real_jid))
        if nick == gi.nick and show != "unavailable":
            self._emit_muc_joined(room, gi.subject, list(gi.users))
        self.emit("groupchat_presence", room, nick, show, status, role,
                  affiliation, real_jid)

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
        logger.info("Unsubscribed from %s", frm)
        self.emit("unsubscribed", frm)

    def _on_got_online(self, pres) -> None:
        frm = str(pres["from"])
        self.emit("got_online", frm)

    def _on_auth_failed(self, event) -> None:
        logger.error("Authentication failed")
        self.emit("auth_failed")

    def _on_disconnected(self, event) -> None:
        logger.info("Disconnected from server")
        self.emit("disconnected")

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
        modes = [(jid in self.groupchats, end)]
        if end is not None:
            modes.append((not (jid in self.groupchats), end))
            modes.append((jid in self.groupchats, None))
            modes.append((not (jid in self.groupchats), None))
        else:
            modes.append((not (jid in self.groupchats), None))
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
                body = str(_stanza_value(msg, "body") or "")
                if not body:
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
                    sender = frm.split("/")[0]
                    if frm.split("/")[0] == self.jid_str:
                        direction = "outgoing"
                        sender = "Me"
                from stanza_im.core import history
                if jid in self.groupchats:
                    stable = _stanza_id(msg, jid) or _archive_result_id(result)
                else:
                    stable = _origin_id(msg) or str(msg.get("id") or "")
                inserted = history.store_message(
                    jid, direction, body, timestamp=ts or None,
                    sender=sender, skip_existing=True,
                    archive_id=_archive_result_id(result),
                    origin_id=stable,
                    reply_to=_reply_reference(msg)[0],
                    reply_id=_reply_reference(msg)[1])
                if inserted:
                    stored += 1
                else:
                    duplicates += 1
            except Exception:
                skipped += 1
                skip_reasons["exception"] = skip_reasons.get("exception", 0) + 1
                logger.debug("Could not parse MAM result for %s",
                             jid, exc_info=True)
                continue
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
