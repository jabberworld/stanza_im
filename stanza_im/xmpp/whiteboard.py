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

import asyncio
import copy
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from stanza_im.include import svg_transform
from stanza_im.include.constants import WHITEBOARD_HEIGHT, WHITEBOARD_WIDTH
from stanza_im.include.enumerators import SHOW_ORDER
from stanza_im.xmpp import jmi
from stanza_im.xmpp import sxe
from stanza_im.xmpp.sxe import NS_SXE, NS_SXE_TRANSPORT, SxeDocument

logger = logging.getLogger("stanza_im.whiteboard")

NS_WHITEBOARD = "urn:xmpp:jingle:apps:svg-whiteboard:0"
NS_JINGLE = "urn:xmpp:jingle:1"
NS_SVG = "http://www.w3.org/2000/svg"
NS_XLINK = "http://www.w3.org/1999/xlink"

#: Fixed root record id of the shared SVG document.  Every participant uses the
#: same value (``"0"``, the value the specification's examples use), so an
#: incremental ``<new parent="…"/>`` edit refers to a record that exists locally
#: without needing a full snapshot first.  A foreign host's own root RID is
#: adopted from the snapshot (XEP-0284 §10.3), so interop does not depend on it.
WHITEBOARD_ROOT_RID = "0"

#: The ``prolog`` attribute of a ``<document-begin/>``: the XML prolog including
#: the SVG DOCTYPE, carried as a ``data:`` URI (XEP-0284 §7.3).
DOC_PROLOG = ("data:text/xml,%3C%3Fxml%20version%3D%271.0%27%3F%3E%0A"
              "%3C%21DOCTYPE%20svg%20PUBLIC%20%27-%2F%2FW3C%2F%2FDTD%20SVG%20"
              "1.1%2F%2FEN%27%20%27http%3A%2F%2Fwww.w3.org%2FGraphics%2FSVG%2F"
              "1.1%2FDTS%2Fsvg11.dtd%27%3E")


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
    host: str = ""              # the session host (the initiator in a 1:1)
    synced: bool = False        # the host's state has been received
    pending: list = field(default_factory=list)  # edits waiting for the state
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
        # XEP-0353 JMI: incoming proposals (sid -> proposer full JID), pending
        # proceed futures for our own proposals, and sids we accepted as a
        # joiner (so the following session-initiate auto-joins).
        self._proposals: dict[str, str] = {}
        self._proceed_futures: dict[str, asyncio.Future] = {}
        self._proceeded: set[str] = set()
        # Pending <connect/> requests of the sessions we joined.  The request
        # goes out once the session-accept is acknowledged and is retried while
        # the host has not offered its state yet.
        self._connect_tasks: dict[str, asyncio.Task] = {}
        self._connect_retry_delays = (2.0, 5.0, 10.0)

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
        """The current drawable objects of the session document (for the canvas).

        Both ``<path/>`` and ``<image/>`` children are returned; each carries its
        element ``tag`` so the canvas can render it.
        """
        session = self.sessions.get(sid)
        if session is None:
            return []
        doc = session.doc
        out: list[dict] = []
        self._collect_shapes(doc, doc.root_rid, out, "", "")
        return out

    def _collect_shapes(self, doc: SxeDocument, parent_rid: str,
                        out: list[dict], group: str, group_tf: str) -> None:
        """Flatten the drawables under *parent_rid* into *out*.

        A ``<g/>``'s children are flattened and carry the group's record id and
        transform (the profile §8.5); nesting is one level deep.
        """
        for child in doc.children(parent_rid):
            record = doc.records.get(child)
            if record is None or record.type != "element":
                continue
            attrs = {doc.records[a].name: doc.records[a].chdata
                     for a in doc.children(child)
                     if doc.records[a].type == "attr"}
            if record.name == "g":
                self._collect_shapes(doc, child, out, child,
                                     attrs.get("transform", ""))
                continue
            if record.name not in ("path", "image"):
                continue
            item = {"rid": child, "id": attrs.get("id", ""),
                    "tag": record.name, "group": group,
                    "group-transform": group_tf,
                    "stroke": attrs.get("stroke", "#1a1a1a"),
                    "stroke-width": attrs.get("stroke-width", "2"),
                    "fill": attrs.get("fill", ""),
                    "fill-opacity": attrs.get("fill-opacity", ""),
                    "stroke-linecap": attrs.get("stroke-linecap", ""),
                    "stroke-linejoin": attrs.get("stroke-linejoin", ""),
                    "fill-rule": attrs.get("fill-rule", ""),
                    "transform": attrs.get("transform", "")}
            if record.name == "image":
                item.update({
                    "x": attrs.get("x", "0"), "y": attrs.get("y", "0"),
                    "width": attrs.get("width", "0"),
                    "height": attrs.get("height", "0"),
                    "href": attrs.get("xlink:href", "")})
            else:
                item["d"] = attrs.get("d", "")
            out.append(item)

    def view_box(self, sid: str) -> tuple[int, int]:
        """The canvas size from the document's ``viewBox``.

        The host's ``viewBox`` is authoritative (the spec's Section 10), so a
        joiner renders the shared document at the host's size.  Falls back to our
        default when the document carries no usable ``viewBox``.
        """
        session = self.sessions.get(sid)
        if session is None:
            return WHITEBOARD_WIDTH, WHITEBOARD_HEIGHT
        doc = session.doc
        rid = doc.find_attr(doc.root_rid, "viewBox")
        if rid:
            parts = str(doc.records[rid].chdata or "").replace(",", " ").split()
            if len(parts) == 4:
                try:
                    w, h = float(parts[2]), float(parts[3])
                except (TypeError, ValueError):
                    w = h = 0.0
                if w > 0 and h > 0:
                    return int(round(w)), int(round(h))
        return WHITEBOARD_WIDTH, WHITEBOARD_HEIGHT

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
            session.synced = True
            self._advertise(session)
            self._send(session, self._sxe(session, "connect"))
            self.client.emit("whiteboard_ready", sid)
            self._announce_active(peer)
            return sid
        sid = uuid.uuid4().hex
        session = WhiteboardSession(sid=sid, peer=peer, is_muc=False,
                                    is_host=True, name=name)
        self._seed_document(session.doc)
        session.synced = True
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
            if self._peer_supports_jmi(peer) \
                    and getattr(self.client, "_start_task", None):
                # XEP-0353: propose first, initiate the Jingle session once the
                # peer proceeds (a reject/retract fails the share).
                logger.info("Whiteboard: propose %s -> %s (sid=%s)", peer, full,
                            sid)
                self.client._start_task(self._propose_and_initiate(session))
            else:
                logger.info("Whiteboard: invite %s -> %s (sid=%s)", peer, full,
                            sid)
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
            # A MUC board has no initial-state handshake: every occupant keeps
            # its own document and the room relays the edits.
            session.synced = is_muc
            self.sessions[sid] = session
        self._by_peer[peer] = sid
        if not is_muc:
            self._connect_after_accept(session)
        else:
            self._send(session, self._sxe(session, "connect"))

    def _connect_after_accept(self, session: WhiteboardSession) -> None:
        """Accept the session, then request its state once that is acknowledged.

        The host offers the shared state on a ``<connect/>`` only when its own
        payload channel is ready.  Iris (Psi) starts the accepted content on the
        next event-loop turn after the ``session-accept`` reply, so a request
        that arrives together with the accept is silently dropped and the host
        never offers again.  Sending the request after the acknowledgement
        avoids that race; the retries cover a host that was still busy.
        """

        def send_connect(result=None) -> None:
            if self.sessions.get(session.sid) is not session or session.ready:
                return
            try:
                failed = str(result.get("type") or "") == "error"
            except AttributeError:
                failed = False
            if failed:
                logger.info("Whiteboard: session-accept failed for %s",
                            session.sid[:8])
                return
            self._send(session, self._sxe(session, "connect"))

        self._send_jingle(session, "session-accept", on_result=send_connect)
        # Even a lost acknowledgement must not leave the joiner without the
        # state: the host may have received the accept after all.
        self._schedule_connect_retries(session)

    def _schedule_connect_retries(self, session: WhiteboardSession) -> None:
        self._cancel_connect(session.sid)
        task = self._spawn(self._retry_connect(session))
        if task is not None:
            self._connect_tasks[session.sid] = task

    async def _retry_connect(self, session: WhiteboardSession) -> None:
        try:
            for delay in self._connect_retry_delays:
                await asyncio.sleep(delay)
                if self.sessions.get(session.sid) is not session:
                    return
                if session.ready:
                    return
                logger.info("Whiteboard: no state for %s yet, re-sending "
                            "connect", session.sid[:8])
                self._send(session, self._sxe(session, "connect"))
        finally:
            if self._connect_tasks.get(session.sid) is asyncio.current_task():
                self._connect_tasks.pop(session.sid, None)

    def _cancel_connect(self, sid: str) -> None:
        task = self._connect_tasks.pop(sid, None)
        if task is not None and not task.done():
            task.cancel()

    def _spawn(self, coro):
        """Schedule *coro* on the client's event loop (when there is one)."""
        start = getattr(self.client, "_start_task", None)
        if callable(start):
            try:
                return start(coro)
            except Exception:  # noqa: BLE001
                logger.debug("Whiteboard: could not schedule a task",
                             exc_info=True)
                coro.close()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                coro.close()
                return None
        return loop.create_task(coro)

    def refuse_session(self, sid: str,
                       reason: str = "unsupported-applications") -> None:
        """Refuse an incoming session and drop it (XEP-0166 §6.2.4.4).

        A responder that will not take part answers the ``session-initiate`` with
        a ``session-terminate``; the specification's example uses the
        ``unsupported-applications`` reason (the default here).
        """
        session = self.sessions.pop(sid, None)
        if session is None:
            return
        self._cancel_connect(sid)
        if self._by_peer.get(session.peer) == sid:
            self._by_peer.pop(session.peer, None)
        self._announce_inactive(session.peer)
        if not session.is_muc:
            try:
                self._send_jingle(session, "session-terminate", reason=reason)
            except Exception:  # noqa: BLE001
                logger.debug("Whiteboard: could not refuse session",
                             exc_info=True)
        self.client.emit("whiteboard_ended", sid)

    # ── XEP-0353 Jingle Message Initiation ────────────────────────

    def owns_jmi(self, sid: str) -> bool:
        """True when *sid* belongs to a whiteboard JMI exchange."""
        return (sid in self.sessions or sid in self._proposals
                or sid in self._proceeded)

    def _peer_supports_jmi(self, bare: str) -> bool:
        try:
            return bool(self.client.supports_feature(
                bare.split("/", 1)[0], jmi.NS_JINGLE_MSG))
        except Exception:  # noqa: BLE001
            return False

    def _send_jmi(self, action: str, to_jid: str, sid: str,
                  descriptions=()) -> None:
        try:
            jmi.build(self.client, action, to_jid, sid, descriptions).send()
        except Exception:  # noqa: BLE001
            logger.debug("Whiteboard: could not send jingle-message %s", action,
                         exc_info=True)

    async def _propose_and_initiate(self, session: WhiteboardSession) -> None:
        """Propose the session (XEP-0353) and initiate it on proceed."""
        try:
            future = asyncio.get_event_loop().create_future()
        except RuntimeError:
            self._send_jingle(session, "session-initiate")
            return
        self._proceed_futures[session.sid] = future
        self._send_jmi("propose", session.peer, session.sid,
                       [(NS_WHITEBOARD, {})])
        accepted = True
        try:
            accepted = bool(await asyncio.wait_for(future, timeout=30))
        except asyncio.TimeoutError:
            logger.info("Whiteboard: no proceed for %s, continuing",
                        session.sid)
        except Exception:  # noqa: BLE001
            accepted = False
        self._proceed_futures.pop(session.sid, None)
        if not accepted:
            self.sessions.pop(session.sid, None)
            if self._by_peer.get(session.peer) == session.sid:
                self._by_peer.pop(session.peer, None)
            self._announce_inactive(session.peer)
            self.client.emit("whiteboard_failed", session.sid, "rejected")
            return
        if session.failure or session.ready or session.local_only:
            return
        self._send_jingle(session, "session-initiate")

    def handle_jingle_message(self, msg) -> None:
        """Route an incoming whiteboard JMI message (propose/proceed/reject)."""
        action = jmi.action_of(msg)
        element = jmi.action_element(msg)
        if not action or element is None:
            return
        sid = str(element.get("id") or "")
        if not sid:
            return
        if action == "propose":
            frm = str(msg["from"] or "")
            self._proposals[sid] = frm
            self.client.emit("whiteboard_proposed", sid, frm.split("/", 1)[0],
                             frm)
            return
        future = self._proceed_futures.get(sid)
        if action in ("proceed", "accept"):
            if future is not None and not future.done():
                future.set_result(True)
        elif action in ("reject", "retract"):
            if future is not None and not future.done():
                future.set_result(False)

    def answer_proposal(self, sid: str, accept: bool) -> None:
        """Answer a whiteboard proposal (sends proceed/reject to the proposer)."""
        full = self._proposals.pop(sid, "")
        if not full:
            return
        if accept:
            self._proceeded.add(sid)
            self._send_jmi("proceed", full, sid)
        else:
            self._send_jmi("reject", full, sid)

    def end_session(self, sid: str) -> None:
        session = self.sessions.pop(sid, None)
        if session is None:
            return
        self._cancel_connect(sid)
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
        """Add a drawable object (``path`` or ``image``) and broadcast ``<new>``."""
        session = self.sessions.get(sid)
        if session is None:
            return ""
        doc = session.doc
        tag = str(attrs.get("tag") or "path")
        if tag not in ("path", "image"):
            tag = "path"
        rid = doc.add_element(doc.root_rid, tag)
        for key in ("id", "stroke", "stroke-width", "fill",
                    "stroke-linecap", "stroke-linejoin", "fill-rule",
                    "transform"):
            value = attrs.get(key)
            if value:
                doc.add_attr(rid, key, str(value))
        if tag == "image":
            for key in ("x", "y", "width", "height"):
                value = attrs.get(key)
                if value is not None and value != "":
                    doc.add_attr(rid, key, str(value))
            href = attrs.get("href")
            if href:
                # The embedded source lives in xlink:href (the profile §8.7).
                doc.add_attr(rid, "xlink:href", str(href), ns=NS_XLINK)
        else:
            value = attrs.get("d")
            if value:
                doc.add_attr(rid, "d", str(value))
        new = doc.new_elements_for(rid)
        self._send_edits(session, new=new)
        self._record(sid, {"new": new, "set": [], "remove": []},
                     {"new": [], "set": [], "remove": [self._remove_element(rid)]})
        return rid

    def update_shape(self, sid: str, rid: str, attrs: dict) -> None:
        """Change an existing shape's attributes and broadcast the edits."""
        session = self.sessions.get(sid)
        if session is None:
            return
        doc = session.doc
        if rid not in doc.records:
            return
        new: list[ET.Element] = []
        sets: list[ET.Element] = []
        inv_sets: list[ET.Element] = []
        inv_removes: list[ET.Element] = []
        for key in ("d", "stroke", "stroke-width", "fill",
                    "stroke-linecap", "stroke-linejoin", "fill-rule",
                    "transform", "x", "y", "width", "height"):
            if key not in attrs:
                continue
            existing = doc.find_attr(rid, key)
            old = doc.records[existing] if existing else None
            # Capture the old values before set_attr mutates the record in place.
            old_chdata = old.chdata if old is not None else ""
            old_version = old.version if old is not None else 0
            attr_rid = doc.set_attr(rid, key, str(attrs[key] or ""))
            if old is not None:
                sets.append(self._set_element(attr_rid, doc))
                inv_sets.append(self._set_element_values(
                    attr_rid, old_chdata, old_version))
            else:
                # A brand-new attribute record (e.g. the ``transform`` created by
                # the first move): the peer must learn its RID first — a
                # ``<set>`` for an unknown target is silently ignored, so the
                # move/transform would never reach it.
                new.extend(doc.new_elements_for(attr_rid))
                inv_removes.append(self._remove_element(attr_rid))
        if new or sets:
            self._send_edits(session, new=new, sets=sets)
            self._record(sid, {"new": new, "set": sets, "remove": []},
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

    # ── Grouping (the profile §8.5) ───────────────────────────────

    def group_shapes(self, sid: str, rids: list[str]) -> str:
        """Group drawables under a new ``<g/>``; returns the group record id."""
        session = self.sessions.get(sid)
        if session is None:
            return ""
        doc = session.doc
        rids = [r for r in rids if r in doc.records]
        if len(rids) < 2:
            return ""
        group_rid = doc.add_element(doc.root_rid, "g")
        doc.add_attr(group_rid, "id", self._next_id())
        new = doc.new_elements_for(group_rid)
        sets: list[ET.Element] = []
        inverse: list[ET.Element] = []
        for rid in rids:
            record = doc.records[rid]
            old_parent = record.parent
            parent_set = self._parent_set(rid, group_rid, record.version)
            sets.append(parent_set)
            inverse.append(self._parent_set(rid, old_parent, record.version))
            doc.apply_set(parent_set)
        self._send_edits(session, new=new, sets=sets)
        # Undo: reparent the children back and drop the group.
        self._record(sid, {"new": new, "set": sets, "remove": []},
                     {"new": [], "set": inverse,
                      "remove": [self._remove_element(group_rid)]})
        self.client.emit("whiteboard_state", sid)
        return group_rid

    def ungroup(self, sid: str, group_rid: str) -> bool:
        """Dissolve a ``<g/>``.

        The group's transform is composed into each child and the children are
        reparented to the group's parent, then the group is removed (the profile
        §8.5).
        """
        session = self.sessions.get(sid)
        if session is None:
            return False
        doc = session.doc
        group = doc.records.get(group_rid)
        if group is None or group.name != "g":
            return False
        g_attr = doc.find_attr(group_rid, "transform")
        g_matrix = svg_transform.parse_matrix(
            doc.records[g_attr].chdata if g_attr else "")
        parent = group.parent or doc.root_rid
        members = [c for c in doc.children(group_rid)
                   if doc.records[c].type == "element"]
        if not members:
            return False
        new: list[ET.Element] = []
        sets: list[ET.Element] = []
        inverse_new: list[ET.Element] = [group.new_element()]
        inverse_sets: list[ET.Element] = []
        inverse_removes: list[ET.Element] = []
        for child in doc.children(group_rid):   # recreate the group for undo
            if doc.records[child].type == "attr":
                inverse_new.append(doc.records[child].new_element())
        compose = not svg_transform.is_identity(g_matrix)
        for rid in members:
            record = doc.records[rid]
            parent_set = self._parent_set(rid, parent, record.version)
            sets.append(parent_set)
            inverse_sets.append(
                self._parent_set(rid, group_rid, record.version))
            doc.apply_set(parent_set)
            if not compose:
                continue
            existing = doc.find_attr(rid, "transform")
            old = doc.records[existing] if existing else None
            old_value = old.chdata if old is not None else ""
            old_version = old.version if old is not None else 0
            child_matrix = svg_transform.parse_matrix(old_value)
            composed = (svg_transform.compose(g_matrix, child_matrix)
                        if child_matrix is not None else g_matrix)
            attr_rid = doc.set_attr(rid, "transform",
                                    svg_transform.to_str(composed))
            new.extend(doc.new_elements_for(attr_rid))
            if old is not None:
                inverse_sets.append(
                    self._set_element_values(attr_rid, old_value, old_version))
            else:
                inverse_removes.append(self._remove_element(attr_rid))
        removes = [self._remove_element(group_rid)]
        doc.remove(group_rid)
        self._send_edits(session, new=new, sets=sets, removes=removes)
        self._record(sid, {"new": new, "set": sets, "remove": removes},
                     {"new": inverse_new, "set": inverse_sets,
                      "remove": inverse_removes})
        self.client.emit("whiteboard_state", sid)
        return True

    def set_group_transform(self, sid: str, group_rid: str,
                            transform: str) -> bool:
        """Set a ``<g/>``'s transform (its children move with it)."""
        session = self.sessions.get(sid)
        if session is None or not transform:
            return False
        doc = session.doc
        if doc.records.get(group_rid) is None:
            return False
        existing = doc.find_attr(group_rid, "transform")
        old = doc.records[existing] if existing else None
        old_value = old.chdata if old is not None else ""
        old_version = old.version if old is not None else 0
        attr_rid = doc.set_attr(group_rid, "transform", transform)
        if old is None:
            new = doc.new_elements_for(attr_rid)
            sets: list[ET.Element] = []
            inverse = {"new": [], "set": [],
                       "remove": [self._remove_element(attr_rid)]}
        else:
            new = []
            sets = [self._set_element(attr_rid, doc)]
            inverse = {"new": [],
                       "set": [self._set_element_values(attr_rid, old_value,
                                                        old_version)],
                       "remove": []}
        self._send_edits(session, new=new, sets=sets)
        self._record(sid, {"new": new, "set": sets, "remove": []}, inverse)
        self.client.emit("whiteboard_state", sid)
        return True

    @staticmethod
    def _parent_set(rid: str, parent: str, version: int) -> ET.Element:
        """A ``<set>`` reparenting a record (the grouping edit)."""
        el = ET.Element(_q(NS_SXE, "set"))
        el.set("target", rid)
        el.set("version", str(version))
        el.set("parent", parent)
        return el

    #: Stacking-order operations (the profile §8.6, via ``primary-weight``).
    _REORDER = ("front", "back", "forward", "backward")

    def reorder(self, sid: str, rid: str, op: str) -> bool:
        """Change a drawable's stacking order and broadcast the ``<set>`` edits.

        Sibling order is the document's ``primary-weight`` (XEP-0284), so a
        reorder renumbers the changed siblings to their new position.
        """
        session = self.sessions.get(sid)
        if session is None or op not in self._REORDER:
            return False
        doc = session.doc
        children = doc.children(doc.root_rid)
        drawables = [r for r in children
                     if doc.records[r].type == "element"
                     and doc.records[r].name in ("path", "image")]
        if rid not in drawables or len(drawables) < 2:
            return False
        index = drawables.index(rid)
        if op == "front":
            drawables.append(drawables.pop(index))
        elif op == "back":
            drawables.insert(0, drawables.pop(index))
        elif op == "forward":
            if index >= len(drawables) - 1:
                return False
            drawables[index], drawables[index + 1] = (
                drawables[index + 1], drawables[index])
        else:  # backward
            if index <= 0:
                return False
            drawables[index], drawables[index - 1] = (
                drawables[index - 1], drawables[index])
        # Renumber only the drawables, keeping them above the metadata records.
        base = max((doc.records[r].primary_weight for r in children
                    if r not in drawables), default=0.0)
        sets: list[ET.Element] = []
        inverse: list[ET.Element] = []
        for pos, record_rid in enumerate(drawables):
            record = doc.records[record_rid]
            weight = base + pos + 1
            if abs(record.primary_weight - weight) < 1e-9:
                continue
            sets.append(self._weight_set(record_rid, weight, record.version))
            inverse.append(self._weight_set(record_rid, record.primary_weight,
                                            record.version))
            doc.apply_set(sets[-1])
        if not sets:
            return False
        self._send_edits(session, sets=sets)
        self._record(sid, {"new": [], "set": sets, "remove": []},
                     {"new": [], "set": inverse, "remove": []})
        # A reorder has no canvas-level signal, so refresh from the document.
        self.client.emit("whiteboard_state", sid)
        return True

    def set_view_box(self, sid: str, width: int, height: int) -> bool:
        """Resize the canvas by updating the document's ``viewBox`` (the §8.8 op)."""
        session = self.sessions.get(sid)
        if session is None:
            return False
        doc = session.doc
        value = "0 0 %d %d" % (max(1, int(width)), max(1, int(height)))
        existing = doc.find_attr(doc.root_rid, "viewBox")
        old = doc.records[existing] if existing else None
        # Capture the old values before set_attr mutates the record in place.
        old_chdata = old.chdata if old is not None else ""
        old_version = old.version if old is not None else 0
        attr_rid = doc.set_attr(doc.root_rid, "viewBox", value)
        sets = [self._set_element(attr_rid, doc)]
        inverse = ([self._set_element_values(attr_rid, old_chdata, old_version)]
                   if old is not None else [self._remove_element(attr_rid)])
        self._send_edits(session, sets=sets)
        self._record(sid, {"new": [], "set": sets, "remove": []},
                     {"new": [], "set": inverse, "remove": []})
        return True

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
            # The offered transport names the host: in a 1:1 session it is the
            # initiator (XEP-0284 §4.1) and the accept echoes it (§4.2).
            session.host = self._offer_host(jingle, frm)
            self._seed_document(session.doc)
            self.sessions[sid] = session
            self._by_peer[peer] = sid
            self._announce_active(peer)
            if sid in self._proceeded:
                # We already accepted the XEP-0353 proposal: join silently.
                self._proceeded.discard(sid)
                self.join_session(peer, sid, False)
                self.client.emit("whiteboard_ready", sid)
            else:
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
                self._cancel_connect(sid)
                self._announce_inactive(session.peer)
                self.client.emit("whiteboard_ended", sid)
        else:
            logger.debug("Whiteboard: unhandled Jingle action %s", action)

    @staticmethod
    def _offer_host(jingle: ET.Element, fallback: str) -> str:
        """The host named by an incoming Jingle offer's SXE transport."""
        for transport in jingle.iter(_q(NS_SXE_TRANSPORT, "transport")):
            for host in transport.iter(_q(NS_SXE_TRANSPORT, "host")):
                text = (host.text or "").strip()
                if text:
                    return text
        initiator = (jingle.get("initiator") or "").strip()
        return initiator or fallback

    def _send_jingle(self, session: WhiteboardSession, action: str,
                     reason: str = "", on_result=None) -> None:
        iq = self.client.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.full_peer or session.peer
        jingle = ET.SubElement(iq.xml, _q(NS_JINGLE, "jingle"))
        jingle.set("action", action)
        jingle.set("sid", session.sid)
        if action == "session-initiate":
            jingle.set("initiator", self.client._full_jid)
        elif action == "session-accept":
            # XEP-0166 §6.2.4.2: the accept names the responder.
            jingle.set("responder", self.client._full_jid)
        if action != "session-terminate":
            content = ET.SubElement(jingle, _q(NS_JINGLE, "content"))
            content.set("creator", "initiator")
            content.set("name", "whiteboard")
            ET.SubElement(content, _q(NS_WHITEBOARD, "description"))
            transport = ET.SubElement(content,
                                      _q(NS_SXE_TRANSPORT, "transport"))
            host = ET.SubElement(transport, _q(NS_SXE_TRANSPORT, "host"))
            if session.is_muc:
                host_text = session.peer
            elif action == "session-accept":
                # XEP-0284 §4.2: the accept repeats the offered host (the
                # initiator in a 1:1 session), never ourselves.
                host_text = (session.host or session.full_peer
                             or session.peer)
            else:
                host_text = self.client.jid_str
            host.text = host_text
        else:
            reason_el = ET.SubElement(jingle, _q(NS_JINGLE, "reason"))
            ET.SubElement(reason_el, _q(NS_JINGLE, reason or "success"))
        try:
            future = iq.send(callback=on_result)
        except TypeError:
            # A lightweight stanza stub (tests) has a plain send().
            iq.send()
            future = None
            if on_result is not None:
                try:
                    on_result(None)
                except Exception:  # noqa: BLE001
                    logger.debug("Whiteboard: result handler failed",
                                 exc_info=True)
        if future is not None:
            future.add_done_callback(self._log_iq_result)

    @staticmethod
    def _log_iq_result(future) -> None:
        """Consume the Jingle IQ future so an error is not left unretrieved."""
        if future.cancelled():
            return
        try:
            exc = future.exception()
        except Exception:  # noqa: BLE001
            return
        if exc is not None:
            logger.debug("Whiteboard: Jingle IQ failed: %s", exc)

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
        tag_name = tag.rsplit("}", 1)[-1]
        if tag_name == "state":
            logger.debug("Whiteboard: SXE state from %s in %s", frm, sid[:8])
        else:
            logger.info("Whiteboard: SXE %s from %s in %s", tag_name, frm,
                        sid[:8])
        if tag == _q(NS_SXE, "close"):
            # A peer ended the session (MUC client extension): notify and drop.
            self._cancel_connect(sid)
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
        # A repeated connect (a joiner that lost its channel) gets a fresh
        # offer even when an earlier one was already accepted.
        session.accepted = False
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
        # as a replace: the host's root RID is adopted (our own default is "0",
        # but a foreign host may use another GUID) and the drawable records are
        # unioned — a peer that joined later gains the existing shapes without
        # the active peers losing theirs.  A snapshot is a join, not an action,
        # so it is not recorded for undo; an incremental edit is.
        is_snapshot = state.find(_q(NS_SXE, "document-begin")) is not None
        forward = self._batch()
        inverse = self._batch()
        for child in state:
            if child.tag == _q(NS_SXE, "new"):
                if not (child.get("parent") or ""):
                    # The snapshot's root element: adopt the host's root RID
                    # (XEP-0284 §10.3).  Never an undoable edit.
                    doc.apply_new(child)
                    continue
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
        if (state.find(_q(NS_SXE, "document-end")) is not None
                or is_snapshot):
            session.ready = True
            if not session.synced:
                session.synced = True
                logger.info("Whiteboard: state received for %s", session.sid[:8])
                self._flush_pending(session)
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
        kind = (element[0].tag.rsplit("}", 1)[-1]
                if len(element) else "sxe")
        logger.debug("Whiteboard: SXE out %s to %s in %s", kind, target,
                     session.sid[:8])
        try:
            msg.send()
        except Exception:  # noqa: BLE001
            logger.debug("Whiteboard: could not send SXE", exc_info=True)

    def _send_state(self, session: WhiteboardSession, to: str) -> None:
        el = self._sxe(session)
        state = ET.SubElement(el, _q(NS_SXE, "state"))
        begin = ET.SubElement(state, _q(NS_SXE, "document-begin"))
        begin.set("prolog", DOC_PROLOG)
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
        if not session.is_host and not session.synced:
            # A joiner may edit only after it received the initial state
            # (XEP-0284 §9) — the host already ignores edits from an
            # unsynchronized peer.  Keep them and send them in order once the
            # snapshot has been applied.
            session.pending.extend(
                copy.deepcopy(item)
                for item in (*(new or []), *(sets or []), *(removes or [])))
            logger.debug("Whiteboard: buffered an edit for %s (%d pending)",
                         session.sid[:8], len(session.pending))
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

    def _flush_pending(self, session: WhiteboardSession) -> None:
        """Send the edits buffered while the initial state was awaited."""
        pending = session.pending
        session.pending = []
        if not pending:
            return
        logger.info("Whiteboard: flushing %d buffered edit(s) for %s",
                    len(pending), session.sid[:8])
        self._send_edits(
            session,
            new=[e for e in pending if e.tag == _q(NS_SXE, "new")],
            sets=[e for e in pending if e.tag == _q(NS_SXE, "set")],
            removes=[e for e in pending if e.tag == _q(NS_SXE, "remove")])

    @staticmethod
    def _set_element(rid: str, doc: SxeDocument) -> ET.Element:
        record = doc.records[rid]
        el = ET.Element(_q(NS_SXE, "set"))
        el.set("target", rid)
        el.set("version", str(record.version))
        el.set("chdata", record.chdata)
        return el

    @staticmethod
    def _weight_set(rid: str, weight: float, version: int) -> ET.Element:
        """A ``<set>`` changing a record's ``primary-weight`` (sibling order)."""
        el = ET.Element(_q(NS_SXE, "set"))
        el.set("target", rid)
        el.set("version", str(version))
        el.set("primary-weight", "%g" % weight)
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
