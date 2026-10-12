"""Collaborative SVG whiteboard (Jingle application type + XEP-0284 SXE).

The whiteboard is a Jingle application (``urn:xmpp:jingle:apps:svg-whiteboard:0``)
whose transport is Shared XML Editing (``urn:xmpp:jingle:transports:sxe``).  The
shared document is an SVG document synchronized with the XEP-0284 record model
(see :mod:`stanza_im.xmpp.sxe`).  The host relays the SXE payloads: for a 1:1
session the initiator is the host, for a MUC session the room's JID is the host
and the payloads travel as ``groupchat`` messages.

Local drawing operations are turned into ``<new>``/``<set>``/``<remove>`` edits;
incoming edits are applied to the document and the UI is told to rebuild.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from stanza_im.xmpp import sxe
from stanza_im.xmpp.sxe import NS_SXE, NS_SXE_TRANSPORT, SxeDocument

logger = logging.getLogger("stanza_im.whiteboard")

NS_WHITEBOARD = "urn:xmpp:jingle:apps:svg-whiteboard:0"
NS_JINGLE = "urn:xmpp:jingle:1"
NS_SVG = "http://www.w3.org/2000/svg"


def _q(ns: str, tag: str) -> str:
    return "{%s}%s" % (ns, tag)


def is_whiteboard_jingle(jingle: ET.Element) -> bool:
    """True when a Jingle stanza carries the SVG-whiteboard description."""
    for el in jingle.iter():
        if el.tag == _q(NS_WHITEBOARD, "description"):
            return True
    return False


@dataclass
class WhiteboardSession:
    sid: str
    peer: str
    is_muc: bool = False
    is_host: bool = False
    name: str = ""
    full_peer: str = ""
    local_only: bool = False
    doc: SxeDocument = field(default_factory=SxeDocument)
    ready: bool = False
    offered: bool = False       # we sent a state offer
    accepted: bool = False      # our offer was accepted
    state_buffering: bool = False


class WhiteboardManager:
    """Owns the whiteboard sessions of one client."""

    def __init__(self, client):
        self.client = client
        self.sessions: dict[str, WhiteboardSession] = {}
        self._by_peer: dict[str, str] = {}

    @property
    def available(self) -> bool:
        return True

    # ── Lookups ───────────────────────────────────────────────────

    def session(self, sid: str) -> WhiteboardSession | None:
        return self.sessions.get(sid)

    def document(self, sid: str) -> SxeDocument | None:
        session = self.sessions.get(sid)
        return session.doc if session else None

    def shapes(self, sid: str) -> list[dict]:
        """The current shapes of the session document (for the canvas)."""
        session = self.sessions.get(sid)
        if session is None:
            return []
        doc = session.doc
        out: list[dict] = []
        for child in doc.children(doc.root_rid):
            record = doc.records.get(child)
            if record is None or record.type != "element" \
                    or record.name != "path":
                continue
            attrs = {doc.records[a].name: doc.records[a].chdata
                     for a in doc.children(child)
                     if doc.records[a].type == "attr"}
            out.append({"rid": child, "id": attrs.get("id", ""),
                        "d": attrs.get("d", ""),
                        "stroke": attrs.get("stroke", "#1a1a1a"),
                        "stroke-width": attrs.get("stroke-width", "2"),
                        "fill": attrs.get("fill", ""),
                        "transform": attrs.get("transform", "")})
        return out

    # ── Session lifecycle ─────────────────────────────────────────

    def start_session(self, peer: str, is_muc: bool = False,
                      name: str = "") -> str:
        """Create a new session hosted by us and invite/announce it."""
        sid = uuid.uuid4().hex
        session = WhiteboardSession(sid=sid, peer=peer, is_muc=is_muc,
                                    is_host=True, name=name)
        self._seed_document(session.doc)
        self.sessions[sid] = session
        self._by_peer[peer] = sid
        if is_muc:
            self._advertise(session)
            session.ready = True
            self._send(session, self._sxe(session, "connect"))
            self.client.emit("whiteboard_ready", sid)
        elif peer.split("/", 1)[0] == (self.client.jid_str or ""):
            # Sharing a board with our own JID is pointless (the invite would
            # loop back to us): keep the board local, never send an invite.
            session.local_only = True
            session.ready = True
            logger.info("Whiteboard: local-only board for %s", peer)
            self.client.emit("whiteboard_ready", sid)
        else:
            self._send_jingle(session, "session-initiate")
        return sid

    def join_session(self, peer: str, sid: str, is_muc: bool = False,
                     name: str = "") -> None:
        """Join an existing session (respond to an invite or connect)."""
        session = self.sessions.get(sid)
        if session is None:
            session = WhiteboardSession(sid=sid, peer=peer, is_muc=is_muc,
                                        is_host=False, name=name)
            self.sessions[sid] = session
        self._by_peer[peer] = sid
        if not is_muc:
            self._send_jingle(session, "session-accept")
        self._send(session, self._sxe(session, "connect"))

    def end_session(self, sid: str) -> None:
        session = self.sessions.pop(sid, None)
        if session is None:
            return
        if self._by_peer.get(session.peer) == sid:
            self._by_peer.pop(session.peer, None)
        if not session.is_muc:
            try:
                self._send_jingle(session, "session-terminate")
            except Exception:  # noqa: BLE001
                pass
        self.client.emit("whiteboard_ended", sid)

    def _advertise(self, session: WhiteboardSession) -> None:
        """Announce a MUC session in presence (XEP-0284 §4.2)."""
        try:
            pres = self.client.xmpp.Presence()
            pres["to"] = session.peer
            pres.xml.append(self._sxe(session))
            pres.send()
        except Exception:  # noqa: BLE001
            logger.debug("Whiteboard: could not advertise session",
                         exc_info=True)

    @staticmethod
    def _seed_document(doc: SxeDocument) -> None:
        doc.set_attr(doc.root_rid, "version", "1.2")
        doc.set_attr(doc.root_rid, "baseProfile", "tiny")
        doc.set_attr(doc.root_rid, "viewBox", "0 0 600 400")

    # ── Local edits ───────────────────────────────────────────────

    def add_shape(self, sid: str, attrs: dict) -> str:
        """Add a shape to the document and broadcast the ``<new>`` edits."""
        session = self.sessions.get(sid)
        if session is None:
            return ""
        doc = session.doc
        rid = doc.add_element(doc.root_rid, "path")
        for key in ("id", "d", "stroke", "stroke-width", "fill", "transform"):
            value = attrs.get(key)
            if value:
                doc.add_attr(rid, key, str(value))
        self._send_edits(session, new=doc.new_elements_for(rid))
        return rid

    def update_shape(self, sid: str, rid: str, attrs: dict) -> None:
        """Change an existing shape's attributes and broadcast ``<set>``."""
        session = self.sessions.get(sid)
        if session is None:
            return
        doc = session.doc
        if rid not in doc.records:
            return
        sets: list[ET.Element] = []
        for key in ("d", "stroke", "stroke-width", "fill", "transform"):
            if key not in attrs:
                continue
            attr_rid = doc.set_attr(rid, key, str(attrs[key] or ""))
            sets.append(self._set_element(attr_rid, doc))
        if sets:
            self._send_edits(session, sets=sets)

    def remove_shape(self, sid: str, rid: str) -> None:
        """Remove a shape and broadcast the ``<remove>`` edits (children first)."""
        session = self.sessions.get(sid)
        if session is None:
            return
        doc = session.doc
        removed = doc.remove(rid)
        removes = [self._remove_element(r) for r in removed]
        if removes:
            self._send_edits(session, removes=removes)

    # ── Jingle ────────────────────────────────────────────────────

    async def dispatch(self, action: str, jingle: ET.Element, iq) -> None:
        if str(iq["type"] or "") != "set":
            # Defensive: only a `set` Jingle IQ carries an action we must act
            # on (error replies echo the original action and must be ignored).
            return
        sid = jingle.get("sid", "")
        frm = str(iq["from"])
        peer = frm.split("/", 1)[0]
        if action == "session-initiate":
            session = WhiteboardSession(sid=sid, peer=peer, is_host=False,
                                        full_peer=frm)
            self._seed_document(session.doc)
            self.sessions[sid] = session
            self._by_peer[peer] = sid
            self.client.emit("whiteboard_invite", sid, peer, False)
        elif action == "session-accept":
            session = self.sessions.get(sid)
            if session is not None:
                session.peer = peer
                session.full_peer = frm
                self._by_peer[peer] = sid
        elif action == "session-terminate":
            session = self.sessions.pop(sid, None)
            if session is not None:
                self.client.emit("whiteboard_ended", sid)
        else:
            logger.debug("Whiteboard: unhandled Jingle action %s", action)

    def _send_jingle(self, session: WhiteboardSession, action: str) -> None:
        iq = self.client.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.full_peer or session.peer
        jingle = ET.SubElement(iq.xml, _q(NS_JINGLE, "jingle"))
        jingle.set("action", action)
        jingle.set("sid", session.sid)
        if action == "session-initiate":
            jingle.set("initiator", self.client._full_jid)
        if action != "session-terminate":
            content = ET.SubElement(jingle, _q(NS_JINGLE, "content"))
            content.set("creator", "initiator")
            content.set("name", "whiteboard")
            ET.SubElement(content, _q(NS_WHITEBOARD, "description"))
            transport = ET.SubElement(content,
                                      _q(NS_SXE_TRANSPORT, "transport"))
            host = ET.SubElement(transport, _q(NS_SXE_TRANSPORT, "host"))
            host.text = session.peer if session.is_muc else self.client.jid_str
        else:
            reason = ET.SubElement(jingle, _q(NS_JINGLE, "reason"))
            ET.SubElement(reason, _q(NS_JINGLE, "success"))
        iq.send()

    # ── SXE messages ──────────────────────────────────────────────

    async def handle_sxe(self, msg) -> None:
        frm = str(msg["from"] or "")
        bare = frm.split("/", 1)[0]
        el = msg.xml.find(_q(NS_SXE, "sxe"))
        if el is None:
            return
        sid = str(el.get("session") or "")
        nick = frm.split("/", 1)[1] if "/" in frm else ""
        # Ignore our own MUC reflections.
        if self._is_self_reflection(bare, nick):
            return
        session = self.sessions.get(sid)
        if session is None:
            session = WhiteboardSession(sid=sid, peer=bare, is_muc=True,
                                        is_host=False)
            self._seed_document(session.doc)
            self.sessions[sid] = session
        child = next(iter(el), None)
        if child is None:
            return
        tag = child.tag
        if tag == _q(NS_SXE, "connect"):
            self._on_connect(session, frm)
        elif tag == _q(NS_SXE, "state-offer"):
            self._on_state_offer(session, frm)
        elif tag == _q(NS_SXE, "accept-state"):
            self._on_accept_state(session, frm)
        elif tag == _q(NS_SXE, "refuse-state"):
            session.offered = False
        elif tag == _q(NS_SXE, "state"):
            self._apply_state(session, child)

    def _is_self_reflection(self, bare: str, nick: str) -> bool:
        if not nick:
            return False
        gi = self.client.groupchats.get(bare)
        return bool(gi is not None and gi.nick and nick == gi.nick)

    def _on_connect(self, session: WhiteboardSession, frm: str) -> None:
        """A participant connected; as the host we offer the state."""
        if not session.is_host:
            return
        session.offered = True
        self._send(session, self._sxe(session, "state-offer",
                                      {"description": True}), to=frm)

    def _on_state_offer(self, session: WhiteboardSession, frm: str) -> None:
        if session.accepted:
            self._send(session, self._sxe(session, "refuse-state"), to=frm)
            return
        session.accepted = True
        session.ready = True
        self._send(session, self._sxe(session, "accept-state"), to=frm)
        self.client.emit("whiteboard_ready", session.sid)

    def _on_accept_state(self, session: WhiteboardSession, frm: str) -> None:
        if not session.is_host:
            return
        session.ready = True
        self._send_state(session, frm)
        self.client.emit("whiteboard_ready", session.sid)

    def _apply_state(self, session: WhiteboardSession, state: ET.Element) -> None:
        doc = session.doc
        if state.find(_q(NS_SXE, "document-begin")) is not None:
            # A fresh snapshot: rebuild the drawable records.
            for rid in list(doc.records):
                if rid != doc.root_rid:
                    doc.records.pop(rid, None)
            doc.records[doc.root_rid].children = []
        for child in state:
            if child.tag == _q(NS_SXE, "new"):
                doc.apply_new(child)
            elif child.tag == _q(NS_SXE, "set"):
                doc.apply_set(child)
            elif child.tag == _q(NS_SXE, "remove"):
                doc.apply_remove(child)
        if state.find(_q(NS_SXE, "document-end")) is not None:
            session.ready = True
        self.client.emit("whiteboard_state", session.sid)

    # ── Sending ───────────────────────────────────────────────────

    def _next_id(self) -> str:
        return uuid.uuid4().hex

    def _sxe(self, session: WhiteboardSession, kind: str | None = None,
             extras: dict | None = None) -> ET.Element:
        el = ET.Element(_q(NS_SXE, "sxe"))
        el.set("session", session.sid)
        el.set("id", self._next_id())
        if kind:
            child = ET.SubElement(el, _q(NS_SXE, kind))
            if extras and extras.get("description"):
                ET.SubElement(child, _q(NS_WHITEBOARD, "description"))
        return el

    def _send(self, session: WhiteboardSession, element: ET.Element,
              to: str = "") -> None:
        if session.is_muc:
            # A groupchat message is always addressed to the room itself.
            target = session.peer
        else:
            target = to or session.full_peer or session.peer
        msg = self.client.xmpp.Message()
        msg["to"] = target
        msg["type"] = "groupchat" if session.is_muc else "chat"
        msg["id"] = self._next_id()
        msg.xml.append(element)
        try:
            msg.send()
        except Exception:  # noqa: BLE001
            logger.debug("Whiteboard: could not send SXE", exc_info=True)

    def _send_state(self, session: WhiteboardSession, to: str) -> None:
        el = self._sxe(session)
        state = ET.SubElement(el, _q(NS_SXE, "state"))
        begin = ET.SubElement(state, _q(NS_SXE, "document-begin"))
        begin.set("prolog",
                  "data:text/xml,%3C%3Fxml%20version%3D%271.0%27%3F%3E")
        for new in session.doc.all_new_elements():
            state.append(new)
        end = ET.SubElement(state, _q(NS_SXE, "document-end"))
        end.set("last-sender", "")
        end.set("last-id", "")
        self._send(session, el, to=to)

    def _send_edits(self, session: WhiteboardSession,
                    new: list | None = None, sets: list | None = None,
                    removes: list | None = None) -> None:
        if not (new or sets or removes):
            return
        el = self._sxe(session)
        state = ET.SubElement(el, _q(NS_SXE, "state"))
        for item in (new or []):
            state.append(item)
        for item in (sets or []):
            state.append(item)
        for item in (removes or []):
            state.append(item)
        self._send(session, el)

    @staticmethod
    def _set_element(rid: str, doc: SxeDocument) -> ET.Element:
        record = doc.records[rid]
        el = ET.Element(_q(NS_SXE, "set"))
        el.set("target", rid)
        el.set("version", str(record.version))
        el.set("chdata", record.chdata)
        return el

    @staticmethod
    def _remove_element(rid: str) -> ET.Element:
        el = ET.Element(_q(NS_SXE, "remove"))
        el.set("target", rid)
        return el
