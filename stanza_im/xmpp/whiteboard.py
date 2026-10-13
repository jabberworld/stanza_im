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

import copy
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from stanza_im.include.constants import WHITEBOARD_HEIGHT, WHITEBOARD_WIDTH
from stanza_im.include.enumerators import SHOW_ORDER
from stanza_im.xmpp import sxe
from stanza_im.xmpp.sxe import NS_SXE, NS_SXE_TRANSPORT, SxeDocument

logger = logging.getLogger("stanza_im.whiteboard")

NS_WHITEBOARD = "urn:xmpp:jingle:apps:svg-whiteboard:0"
NS_JINGLE = "urn:xmpp:jingle:1"
NS_SVG = "http://www.w3.org/2000/svg"

#: Fixed root record id of the shared SVG document.  Every participant uses the
#: same value, so an incremental ``<new parent="…"/>`` edit refers to a record
#: that exists locally without needing a full snapshot first.
WHITEBOARD_ROOT_RID = "svg-root"


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
    failure: str = ""
    doc: SxeDocument = field(
        default_factory=lambda: SxeDocument(root_rid=WHITEBOARD_ROOT_RID))
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
        # Peers (bare JID / room) with a currently active board, so the
        # start/end chat status line is emitted once per activity span.
        self._active_peers: set[str] = set()
        # Per-session undo/redo stacks of edit patches (forward + inverse), so a
        # shared board can undo the last operation whatever its author.
        self._undo: dict[str, list[dict]] = {}
        self._redo: dict[str, list[dict]] = {}

    @property
    def available(self) -> bool:
        return True

    def _announce_active(self, peer: str) -> None:
        if peer and peer not in self._active_peers:
            self._active_peers.add(peer)
            self.client.emit("whiteboard_activity", peer, True)

    def _announce_inactive(self, peer: str) -> None:
        if peer in self._active_peers:
            self._active_peers.discard(peer)
            self.client.emit("whiteboard_activity", peer, False)

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

    def _best_full_jid(self, bare: str) -> str:
        """The peer's best resource full JID for a 1:1 Jingle session.

        Prefers a resource whose XEP-0115 caps announce the whiteboard/SXE
        feature, then the best available resource (by ``show``), else the bare
        JID (no resource known).
        """
        bare = bare.split("/", 1)[0]
        caps = getattr(self.client, "contact_features", None) or {}
        presences = getattr(self.client, "presences", None) or {}

        def best(predicate) -> str:
            chosen, chosen_show = "", 99
            for full in presences:
                if full.split("/")[0] != bare:
                    continue
                info = presences.get(full) or {}
                if info.get("type") != "available":
                    continue
                if not predicate(full, info):
                    continue
                show = SHOW_ORDER.get(info.get("show", "online"), 99)
                if not chosen or show < chosen_show:
                    chosen, chosen_show = full, show
            return chosen

        chosen = best(lambda full, _info: (
            NS_WHITEBOARD in caps.get(full, ()) or NS_SXE in caps.get(full, ())))
        return chosen or best(lambda _full, _info: True) or bare

    @staticmethod
    def _muc_sid(room: str) -> str:
        """A deterministic session id shared by every participant of a room.

        A random sid per participant would give each its own session, so the
        peers would never see each other's edits; deriving it from the room JID
        makes everyone converge on the same shared document.
        """
        bare = room.split("/", 1)[0]
        return hashlib.sha1(
            ("urn:xmpp:sxe:0:" + bare).encode("utf-8")).hexdigest()

    def start_session(self, peer: str, is_muc: bool = False,
                      name: str = "") -> str:
        """Create (or, for a MUC, reuse) a session hosted by us and announce it."""
        if is_muc:
            sid = self._muc_sid(peer)
            session = self.sessions.get(sid)
            if session is None:
                session = WhiteboardSession(sid=sid, peer=peer, is_muc=True,
                                            is_host=True, name=name)
                self._seed_document(session.doc)
                self.sessions[sid] = session
            self._by_peer[peer] = sid
            session.ready = True
            self._advertise(session)
            self._send(session, self._sxe(session, "connect"))
            self.client.emit("whiteboard_ready", sid)
            self._announce_active(peer)
            return sid
        sid = uuid.uuid4().hex
        session = WhiteboardSession(sid=sid, peer=peer, is_muc=False,
                                    is_host=True, name=name)
        self._seed_document(session.doc)
        self.sessions[sid] = session
        self._by_peer[peer] = sid
        if peer.split("/", 1)[0] == (self.client.jid_str or ""):
            # Sharing a board with our own JID is pointless (the invite would
            # loop back to us): keep the board local, never send an invite.
            session.local_only = True
            session.ready = True
            logger.info("Whiteboard: local-only board for %s", peer)
            self.client.emit("whiteboard_ready", sid)
            self._announce_active(peer)
        else:
            full = self._best_full_jid(peer)
            if full == peer.split("/", 1)[0]:
                # No resource known: a bare-JID Jingle IQ is rejected by the
                # server (service-unavailable), so fail fast instead of sending.
                logger.info("Whiteboard: peer %s has no available resource",
                            peer)
                session.failure = "unavailable"
                return sid
            session.full_peer = full
            logger.info("Whiteboard: invite %s -> %s (sid=%s)", peer, full, sid)
            self._send_jingle(session, "session-initiate")
            self._announce_active(peer)
        return sid

    def handle_error(self, action: str, sid: str, condition: str = "") -> None:
        """A Jingle error reply arrived for *sid* (from the router)."""
        session = self.sessions.get(sid)
        if session is None:
            return
        logger.info("Whiteboard: Jingle %s failed for %s (%s)", action,
                    session.peer, condition or "error")
        if action == "session-initiate" and not session.ready:
            self.sessions.pop(sid, None)
            if self._by_peer.get(session.peer) == sid:
                self._by_peer.pop(session.peer, None)
            self.client.emit("whiteboard_failed", sid,
                             condition or "service-unavailable")

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
        if session.is_muc:
            # A MUC board has no Jingle session: broadcast an explicit close so
            # every occupant learns the session ended (a client extension).
            try:
                self._send(session, self._sxe(session, "close"))
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                self._send_jingle(session, "session-terminate")
            except Exception:  # noqa: BLE001
                pass
        self._announce_inactive(session.peer)
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
        doc.set_attr(doc.root_rid, "viewBox",
                     "0 0 %d %d" % (WHITEBOARD_WIDTH, WHITEBOARD_HEIGHT))

    # ── Undo / redo ───────────────────────────────────────────────

    _UNDO_MAX = 100

    @staticmethod
    def _batch() -> dict:
        return {"new": [], "set": [], "remove": []}

    def _record(self, sid: str, forward: dict, inverse: dict) -> None:
        """Push a patch (forward + inverse edits) onto the undo stack."""
        if not any(forward[k] or inverse[k]
                   for k in ("new", "set", "remove")):
            return
        stack = self._undo.setdefault(sid, [])
        stack.append({"forward": forward, "inverse": inverse})
        if len(stack) > self._UNDO_MAX:
            del stack[0]
        self._redo.pop(sid, None)  # a new operation invalidates the redo stack

    def can_undo(self, sid: str) -> bool:
        return bool(self._undo.get(sid))

    def can_redo(self, sid: str) -> bool:
        return bool(self._redo.get(sid))

    def undo(self, sid: str) -> bool:
        """Revert the last operation (own or remote); broadcast the inverse."""
        stack = self._undo.get(sid)
        if not stack:
            return False
        patch = stack.pop()
        self._apply_patch(sid, patch["inverse"])
        self._redo.setdefault(sid, []).append(patch)
        return True

    def redo(self, sid: str) -> bool:
        """Re-apply the last undone operation."""
        stack = self._redo.get(sid)
        if not stack:
            return False
        patch = stack.pop()
        self._apply_patch(sid, patch["forward"])
        self._undo.setdefault(sid, []).append(patch)
        return True

    def _apply_patch(self, sid: str, batch: dict) -> None:
        session = self.sessions.get(sid)
        if session is None:
            return
        doc = session.doc
        for el in batch.get("new", []):
            if not (el.get("parent") or ""):
                continue  # the root element already exists
            doc.apply_new(el)
        for el in batch.get("set", []):
            doc.apply_set(el)
        for el in batch.get("remove", []):
            doc.apply_remove(el)
        if not session.local_only:
            self._send_edits(
                session,
                new=[copy.deepcopy(e) for e in batch.get("new", [])],
                sets=[copy.deepcopy(e) for e in batch.get("set", [])],
                removes=[copy.deepcopy(e) for e in batch.get("remove", [])])
        self.client.emit("whiteboard_state", sid)

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
        new = doc.new_elements_for(rid)
        self._send_edits(session, new=new)
        self._record(sid, {"new": new, "set": [], "remove": []},
                     {"new": [], "set": [], "remove": [self._remove_element(rid)]})
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
        inv_sets: list[ET.Element] = []
        inv_removes: list[ET.Element] = []
        for key in ("d", "stroke", "stroke-width", "fill", "transform"):
            if key not in attrs:
                continue
            existing = doc.find_attr(rid, key)
            old = doc.records[existing] if existing else None
            attr_rid = doc.set_attr(rid, key, str(attrs[key] or ""))
            sets.append(self._set_element(attr_rid, doc))
            if old is not None:
                inv_sets.append(self._set_element_values(
                    attr_rid, old.chdata, old.version))
            else:
                inv_removes.append(self._remove_element(attr_rid))
        if sets:
            self._send_edits(session, sets=sets)
            self._record(sid, {"new": [], "set": sets, "remove": []},
                         {"new": [], "set": inv_sets, "remove": inv_removes})

    def remove_shape(self, sid: str, rid: str) -> None:
        """Remove a shape and broadcast the ``<remove>`` edits (children first)."""
        session = self.sessions.get(sid)
        if session is None:
            return
        doc = session.doc
        captured = doc.new_elements_for(rid) if rid in doc.records else []
        removed = doc.remove(rid)
        removes = [self._remove_element(r) for r in removed]
        if removes:
            self._send_edits(session, removes=removes)
            self._record(sid, {"new": [], "set": [], "remove": removes},
                         {"new": captured, "set": [], "remove": []})

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
            self._announce_active(peer)
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
                self._announce_inactive(session.peer)
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
        if tag == _q(NS_SXE, "close"):
            # A peer ended the session (MUC client extension): notify and drop.
            self._announce_inactive(session.peer)
            self.sessions.pop(sid, None)
            if self._by_peer.get(session.peer) == sid:
                self._by_peer.pop(session.peer, None)
            self.client.emit("whiteboard_ended", sid)
            return
        # Any other SXE from a peer means a board is active for that peer (this
        # is how a passive MUC occupant learns the room has a board).
        self._announce_active(session.peer)
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

    async def handle_sxe_presence(self, pres) -> None:
        """A MUC presence advertisement of a board (XEP-0284 §4.2).

        A late room joiner receives the existing occupants' presence, so this is
        how it learns the room already has an active board.
        """
        room = str(pres["from"] or "").split("/", 1)[0]
        if not room:
            return
        nick = str(pres["from"] or "").split("/", 1)[1] if "/" in str(
            pres["from"] or "") else ""
        if self._is_self_reflection(room, nick):
            return
        self._announce_active(room)

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
        self._announce_active(session.peer)
        self.client.emit("whiteboard_ready", session.sid)

    def _on_accept_state(self, session: WhiteboardSession, frm: str) -> None:
        if not session.is_host:
            return
        session.ready = True
        self._send_state(session, frm)
        self.client.emit("whiteboard_ready", session.sid)

    def _apply_state(self, session: WhiteboardSession, state: ET.Element) -> None:
        doc = session.doc
        # A snapshot (document-begin … document-end) is **merged**, not applied
        # as a replace: every peer shares the fixed WHITEBOARD_ROOT_RID (so the
        # root <new> is skipped) and the drawable records are unioned — a peer
        # that joined later gains the existing shapes without the active peers
        # losing theirs.  A snapshot is a join, not an action, so it is not
        # recorded for undo; an incremental edit is.
        is_snapshot = state.find(_q(NS_SXE, "document-begin")) is not None
        forward = self._batch()
        inverse = self._batch()
        for child in state:
            if child.tag == _q(NS_SXE, "new"):
                if not (child.get("parent") or ""):
                    continue  # the root element already exists locally
                rid = str(child.get("rid") or "")
                if rid and rid in doc.records:
                    inverse["new"].append(
                        copy.deepcopy(doc.records[rid].new_element()))
                elif rid:
                    inverse["remove"].append(self._remove_element(rid))
                forward["new"].append(copy.deepcopy(child))
                doc.apply_new(child)
            elif child.tag == _q(NS_SXE, "set"):
                rid = str(child.get("target") or "")
                if rid and rid in doc.records:
                    rec = doc.records[rid]
                    inverse["set"].append(self._set_element_values(
                        rid, rec.chdata, rec.version))
                forward["set"].append(copy.deepcopy(child))
                doc.apply_set(child)
            elif child.tag == _q(NS_SXE, "remove"):
                rid = str(child.get("target") or "")
                if rid and rid in doc.records:
                    inverse["new"].extend(doc.new_elements_for(rid))
                forward["remove"].append(copy.deepcopy(child))
                doc.apply_remove(child)
        if not is_snapshot:
            self._record(session.sid, forward, inverse)
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
    def _set_element_values(rid: str, chdata: str, version: int) -> ET.Element:
        """A ``<set>`` restoring an attribute to explicit *chdata*/*version*."""
        el = ET.Element(_q(NS_SXE, "set"))
        el.set("target", rid)
        el.set("version", str(version))
        el.set("chdata", str(chdata))
        return el

    @staticmethod
    def _remove_element(rid: str) -> ET.Element:
        el = ET.Element(_q(NS_SXE, "remove"))
        el.set("target", rid)
        return el
