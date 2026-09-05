"""XMPP client wrapper around slixmpp.

Provides a high-level async API and emits Qt-style callbacks that the UI
layer connects to.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import Any, Callable

import slixmpp

from jabbim.include.enumerators import SHOW_ORDER
from jabbim.include.vcard import parse_vcard as _parse_vcard, build_vcard as _build_vcard
from jabbim.core.vcard_cache import VCardCache

logger = logging.getLogger(__name__)


class JabberClient:
    """High-level XMPP client built on top of slixmpp.ClientXMPP."""

    def __init__(self, jid: str, password: str, resource: str = "Jabbim-next"):
        self.jid_str = jid
        self.resource = resource
        self._full_jid = f"{jid}/{resource}"

        self.xmpp = slixmpp.ClientXMPP(jid, password, sasl_mech="SCRAM-SHA-1")
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
        self.xmpp.register_plugin("xep_0049")  # Private XML Storage
        self.xmpp.register_plugin("xep_0128")  # Service Discovery Extensions
        self.xmpp.register_plugin("xep_0030")  # Service Discovery
        self.xmpp.register_plugin("xep_0092")  # Software version
        self.xmpp.register_plugin("xep_0199")  # Ping
        self.xmpp.register_plugin("xep_0202")  # Entity time
        self.xmpp.register_plugin("xep_0313")  # Message Archive Management (MAM)
        # xep_0313 pulls in xep_0059 (RSM) and xep_0297 (Forward) automatically

        # Callbacks: list of callables keyed by event name
        self._callbacks: dict[str, list[Callable]] = {}

        # Internal state
        self.roster: dict[str, Any] = {}  # {jid_str: roster_entry}
        self.contacts: dict[str, ContactInfo] = {}
        self.groupchats: dict[str, GroupChatInfo] = {}
        self.presences: dict[str, dict] = {}  # {full_jid: {show, status, ...}}
        self._mam_inflight: set[str] = set()  # JIDs with an active MAM query
        self._vcard_cache = VCardCache()
        self._vcard_inflight: set[str] = set()
        self._muc_join_tasks: dict[str, asyncio.Task] = {}

        # Hook up slixmpp events
        self.xmpp.add_event_handler("session_start", self._on_session_start)
        self.xmpp.add_event_handler("disco_info", self._on_disco_info)
        self.xmpp.add_event_handler("message", self._on_message)
        self.xmpp.add_event_handler("presence_available", self._on_presence)
        self.xmpp.add_event_handler("presence_unavailable", self._on_presence)
        self.xmpp.add_event_handler("presence_subscribed", self._on_subscribed)
        self.xmpp.add_event_handler("presence_unsubscribed", self._on_unsubscribed)
        self.xmpp.add_event_handler("groupchat_message", self._on_groupchat_message)
        self.xmpp.add_event_handler("groupchat_presence", self._on_groupchat_presence)
        self.xmpp.add_event_handler("got_online", self._on_got_online)
        self.xmpp.add_event_handler("failed_auth", self._on_auth_failed)
        self.xmpp.add_event_handler("disconnected", self._on_disconnected)
        self.xmpp.add_event_handler("presence_error", self._on_presence_error)
        self.xmpp.add_event_handler("roster_update", self._on_roster_update)
        self.xmpp.add_event_handler("chatstate", self._on_chatstate)
        self.xmpp.add_event_handler("receipt_received", self._on_receipt_received)

    # ── Public API ────────────────────────────────────────────────

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
        result = self.xmpp.connect()
        if asyncio.iscoroutine(result):
            await result
        elif isinstance(result, asyncio.Future):
            await result

    async def disconnect(self) -> None:
        """Gracefully disconnect."""
        if self.xmpp.is_connected():
            self.xmpp.disconnect()

    def send_message(self, jid: str, body: str, mtype: str = "chat",
                     mhtml: str | None = None) -> None:
        """Send a message."""
        if not isinstance(jid, str) or not jid.strip():
            logger.warning("Skipping message with empty target: %r", jid)
            return
        jid = jid.strip()
        msg = self.xmpp.Message()
        msg["to"] = jid
        msg["type"] = mtype
        msg["body"] = body
        if mtype == "chat":
            msg["request_receipt"] = True  # XEP-0184
        if mhtml:
            msg["html"]["body"] = mhtml
        logger.debug("Sending %s message to %s: %r", mtype, jid, body[:200])
        msg.send()

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

    def add_contact(self, jid: str, name: str = "", groups: list[str] | None = None,
                    message: str = "") -> None:
        """Add a contact and send a subscribe request."""
        self.xmpp.send_presence_subscription(
            pto=jid,
            pfrom=self._full_jid,
            ptype="subscribe",
            pnick=name,
        )
        if groups:
            self.xmpp.update_roster(jid, name=name, groups=groups)

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
        self.groupchats.setdefault(room, GroupChatInfo(room=room, nick=nick))
        self.groupchats[room].joined = False
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
        subject = str(subject_msg.get("subject", "")) if subject_msg else ""
        gi = self.groupchats.get(room)
        if gi:
            gi.subject = subject
            gi.pending_history = _history or []
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

    def get_muc_info(self, room: str) -> None:
        """Request the advertised room name through XEP-0030."""
        asyncio.get_event_loop().create_task(self._fetch_muc_info(room))

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
            info["software"] = str(result.get("software", "") or "")
            info["version"] = str(result.get("version", "") or "")
            info["os"] = str(result.get("os", "") or "")
        except Exception:
            logger.debug("Software version unavailable for %s", jid,
                         exc_info=True)
        try:
            info["ping"] = f"{await self.xmpp.plugin['xep_0199'].ping(jid, timeout=5):.3f}s"
        except Exception:
            logger.debug("Ping unavailable for %s", jid, exc_info=True)
        try:
            result = await self.xmpp.plugin["xep_0202"].get_entity_time(jid)
            info["client_time"] = str(result.get("time", "") or result.get("utc", ""))
        except Exception:
            logger.debug("Entity time unavailable for %s", jid, exc_info=True)
        self.emit("entity_info_received", jid, info)

    def _store_muc_history(self, room: str, entries) -> None:
        """Persist messages returned by the MUC join handshake."""
        if not entries:
            return
        from jabbim.core import history
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
                                      sender=sender, skip_existing=True)
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
                            autojoin: bool = True) -> None:
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
            bookmarks.add_conference(conf["jid"], conf["nick"],
                                     autojoin=conf["autojoin"],
                                     password=conf["password"])
        bookmarks.add_conference(room, nick,
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
                        conf["jid"], conf["nick"],
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

    def send_muc_message(self, room: str, body: str) -> None:
        """Send a message to a MUC room."""
        self.send_message(room, body, mtype="groupchat")

    def set_muc_role(self, room: str, nick: str, role: str) -> None:
        """Request a MUC role change for an occupant."""
        result = self.xmpp.plugin["xep_0045"].set_role(
            room, nick, role, reason="")
        if asyncio.iscoroutine(result):
            asyncio.get_event_loop().create_task(result)

    def set_muc_subject(self, room: str, subject: str) -> None:
        """Set the subject/topic of a MUC room."""
        nick = self.groupchats[room].nick if room in self.groupchats else ""
        to = f"{room}/{nick}"
        msg = self.xmpp.Message()
        msg["to"] = to
        msg["type"] = "groupchat"
        msg["subject"] = subject
        msg.send()

    def get_vcard(self, jid: str) -> None:
        """Request vCard for *jid*.  Fire-and-forget; result arrives via
        the ``vcard_received`` event as ``(jid, card_dict)``."""
        requested = _clean_jid(jid)
        if not requested:
            logger.debug("Skipping vCard request with empty JID: %r", jid)
            return
        bare = requested.split("/", 1)[0]
        cache_key = requested if "/" in requested else bare
        cached = self._vcard_cache.get(cache_key)
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
            logger.debug("vCard for %s unavailable", jid, exc_info=True)
            self._vcard_inflight.discard(jid)
            return
        self._on_vcard(iq, jid)
        self._vcard_inflight.discard(jid)

    async def set_own_vcard(self, card: dict) -> bool:
        """Publish *card* (see :func:`jabbim.include.vcard.parse_vcard`) as
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
                from jabbim.include.avatars import save_avatar
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
            try:
                self.join_muc(room, nick, password=password, save_bookmark=False)
            except Exception:
                logger.debug("Could not auto-join room %s", room, exc_info=True)

    def _on_message(self, msg) -> None:
        if msg["type"] in ("chat", "normal"):
            body = str(msg["body"])
            frm = str(msg["from"])
            ts = msg.get("delay", {}).get("stamp", None)
            if isinstance(ts, datetime.datetime):
                ts = _normalize_ts(ts.strftime("%Y-%m-%dT%H:%M:%S"))
            room, separator, nick = frm.partition("/")
            if separator and room in self.groupchats:
                self.emit("muc_private_message", room, nick, body, ts)
                return
            self.emit("message_received", frm, body, ts)

    def _on_groupchat_message(self, msg) -> None:
        room = str(msg["from"]).split("/")[0]
        nick = str(msg["from"]).split("/", 1)[1] if "/" in str(msg["from"]) else ""
        body = str(msg["body"])
        ts = msg.get("delay", {}).get("stamp", None)
        if isinstance(ts, datetime.datetime):
            ts = _normalize_ts(ts.strftime("%Y-%m-%dT%H:%M:%S"))
        self.emit("groupchat_message", room, nick, body, ts)

    def _on_presence(self, pres) -> None:
        frm = str(pres["from"])
        bare, _, _resource = frm.partition("/")
        ptype = str(pres["type"])
        show = str(pres.get("show", ""))
        if ptype != "available":
            show = "offline"
        elif show in ("", "available", "None"):
            show = "online"
        status = str(pres.get("status", ""))
        self.presences[frm] = {"show": show, "status": status, "type": ptype}

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

        contact = self.get_contact(bare)
        contact.show = best_show
        contact.status = best_status
        self.emit("presence_changed", bare, best_show, best_status)

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
            gi.users[nick] = {
                "show": show,
                "status": status,
                "role": role,
                "affiliation": affiliation,
                "real_jid": real_jid,
            }
        if nick == gi.nick and show != "unavailable":
            self._emit_muc_joined(room, gi.subject, list(gi.users))
        self.emit("groupchat_presence", room, nick, show, status, role,
                  affiliation, real_jid)

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
                from jabbim.include.avatars import save_avatar
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
                                limit: int = 200) -> int:
        """Fetch older messages for *jid* from the server archive (MAM,
        XEP-0313) and store them locally.

        Queries only the range strictly before the locally stored ``since``
        timestamp so overlapping messages are not re-fetched.  Returns the
        number of messages stored (0 on failure or while another query for
        the same JID is in flight).
        """
        if jid in self._mam_inflight:
            return 0
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
                if len(ts) >= 19 and ts[10] == "T":
                    ts = ts[:19]
                end = datetime.datetime.fromisoformat(ts)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                end = None
        rsm = {"max": int(limit)}
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
            logger.info("MAM query %d for %s: mode=%s end=%s max=%s",
                        index, jid, mode, query_end, limit)
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
                logger.debug("MAM query failed for %s", jid, exc_info=True)
        if not results and last_error is not None:
            logger.debug("MAM returned no usable results for %s: %r",
                         jid, last_error)
            self.emit("mam_unavailable", jid)
            return 0

        me = self.jid_str.split("@")[0]
        my_nick = ""
        gi = self.groupchats.get(jid)
        if gi:
            my_nick = gi.nick
        stored = 0
        parsed = 0
        skipped = 0
        for result in results:
            try:
                fwd = _stanza_value(result, "forwarded")
                msg = _forwarded_stanza(fwd) or result
                if msg is None or not hasattr(msg, "get"):
                    logger.warning("MAM result %d for %s has no message stanza: %r",
                                   results.index(result), jid, result)
                    skipped += 1
                    continue
                body = str(_stanza_value(msg, "body") or "")
                if not body:
                    skipped += 1
                    continue
                parsed += 1
                frm = str(_stanza_value(msg, "from") or "")
                delay = _stanza_value(msg, "delay") or {}
                stamp = _stanza_value(delay, "stamp")
                if isinstance(stamp, datetime.datetime):
                    stamp = stamp.strftime("%Y-%m-%dT%H:%M:%S")
                ts = _normalize_ts(str(stamp))
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
                from jabbim.core import history
                history.store_message(jid, direction, body,
                                      timestamp=ts or None, sender=sender,
                                      skip_existing=True)
                stored += 1
            except Exception:
                skipped += 1
                logger.debug("Could not parse MAM result for %s",
                             jid, exc_info=True)
                continue
        logger.info("MAM returned %d results for %s: parsed=%d skipped=%d stored=%d",
                    len(results), jid, parsed, skipped, stored)
        if results and parsed and not stored:
            self.emit("mam_parse_error", jid, len(results), parsed, skipped)
            return -1
        return stored

    def _on_chatstate(self, msg) -> None:
        frm = str(msg["from"]).split("/")[0]
        state = str(msg["chat_state"])
        if state == "composing":
            self.emit("typing", frm, True)
        else:
            self.emit("typing", frm, False)

    def _on_receipt_received(self, msg) -> None:
        frm = str(msg["from"]).split("/")[0]
        logger.debug("Message receipt delivered to %s", frm)
        self.emit("receipt_delivered", frm)


def _normalize_ts(ts: str) -> str:
    """Trim a XEP-0082 timestam to the storage format ``YYYY-MM-DDTHH:MM:SS``."""
    ts = ts.strip()
    if len(ts) >= 19 and ts[10] == "T":
        return ts[:19]
    return ts


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

    __slots__ = ("room", "nick", "subject", "users", "joined",
                 "pending_history")

    def __init__(self, room: str, nick: str):
        self.room = room
        self.nick = nick
        self.subject = ""
        self.users: dict[str, dict] = {}  # {nick: {show, status, role, affiliation}}
        self.joined = False
        self.pending_history: list = []
