"""Jingle file transfer (XEP-0234) over Jingle SOCKS5 (XEP-0260) and Jingle
In-Band Bytestreams (XEP-0261, XEP-0047).

slixmpp ships no Jingle core plugin, so the session negotiation is built here
directly on top of the slixmpp stanza objects:

* outgoing offers (``session-initiate`` → ``session-accept`` → data →
  ``session-terminate``);
* the XEP-0260 SOCKS5 transport (candidate exchange, ``candidate-used`` /
  ``candidate-error``, proxy ``activate`` / ``activated``);
* the XEP-0261 In-Band transport used both as an explicitly selected method and
  as the fallback when SOCKS5 fails (``transport-replace`` / ``transport-accept``).

The manager is Qt-free; offers, progress and results are surfaced through the
``JabberClient.emit`` event bus.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import mimetypes
import os
import uuid
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from stanza_im.include.enumerators import SHOW_ORDER
from stanza_im.xmpp import bytestream

logger = logging.getLogger(__name__)

NS_JINGLE = "urn:xmpp:jingle:1"
NS_FT = "urn:xmpp:jingle:apps:file-transfer:5"
NS_FT_ERRORS = "urn:xmpp:jingle:apps:file-transfer:errors:0"
NS_S5B = "urn:xmpp:jingle:transports:s5b:1"
NS_IBB = "urn:xmpp:jingle:transports:ibb:1"
NS_IBB_OLD = "http://jabber.org/protocol/ibb"
NS_BYTESTREAMS = "http://jabber.org/protocol/bytestreams"
NS_HASHES = "urn:xmpp:hashes:2"

IBB_BLOCK_SIZE = 4096
_CHUNK = 16 * 1024
_S5B_CONNECT_TIMEOUT = 12.0
_IQ_TIMEOUT = 30


def _q(ns: str, tag: str) -> str:
    return "{%s}%s" % (ns, tag)


# ── File description (XEP-0234 §5) ────────────────────────────────

@dataclass
class FileMeta:
    name: str = ""
    size: int = 0
    media_type: str = "application/octet-stream"
    date: str = ""
    desc: str = ""
    hash_algo: str = ""
    hash_value: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "size": self.size,
                "media_type": self.media_type, "date": self.date,
                "desc": self.desc, "hash_algo": self.hash_algo}


def build_file_element(meta: FileMeta) -> ET.Element:
    """Build the ``<file/>`` child of a XEP-0234 ``<description/>``."""
    file_el = ET.Element(_q(NS_FT, "file"))
    if meta.media_type:
        ET.SubElement(file_el, _q(NS_FT, "media-type")).text = meta.media_type
    if meta.name:
        ET.SubElement(file_el, _q(NS_FT, "name")).text = meta.name
    if meta.date:
        ET.SubElement(file_el, _q(NS_FT, "date")).text = meta.date
    if meta.desc:
        ET.SubElement(file_el, _q(NS_FT, "desc")).text = meta.desc
    if meta.size:
        ET.SubElement(file_el, _q(NS_FT, "size")).text = str(int(meta.size))
    if meta.hash_algo:
        hash_el = ET.SubElement(file_el, _q(NS_HASHES, "hash"))
        hash_el.set("algo", meta.hash_algo)
        hash_el.text = meta.hash_value or ""
    return file_el


def parse_file_element(file_el: ET.Element) -> FileMeta:
    """Parse a XEP-0234 ``<file/>`` element into a :class:`FileMeta`."""
    meta = FileMeta()
    for child in file_el:
        tag = child.tag.rsplit("}", 1)[-1]
        text = (child.text or "").strip()
        if tag == "name":
            meta.name = text
        elif tag == "size":
            try:
                meta.size = int(text)
            except ValueError:
                meta.size = 0
        elif tag == "media-type":
            meta.media_type = text
        elif tag == "date":
            meta.date = text
        elif tag == "desc":
            meta.desc = text
        elif tag == "hash" and not meta.hash_algo:
            meta.hash_algo = child.get("algo", "")
            meta.hash_value = text
    return meta


def build_description(meta: FileMeta) -> ET.Element:
    desc = ET.Element(_q(NS_FT, "description"))
    desc.append(build_file_element(meta))
    return desc


def parse_description(el: ET.Element) -> FileMeta | None:
    file_el = el.find(_q(NS_FT, "file"))
    if file_el is None:
        return None
    return parse_file_element(file_el)


# ── SOCKS5 candidates (XEP-0260 §2.2) ─────────────────────────────

@dataclass
class Candidate:
    cid: str
    host: str
    port: int
    jid: str
    priority: int
    type: str = "direct"

    def element(self) -> ET.Element:
        el = ET.Element(_q(NS_S5B, "candidate"))
        el.set("cid", self.cid)
        el.set("host", self.host)
        el.set("jid", self.jid)
        el.set("port", str(int(self.port)))
        el.set("priority", str(int(self.priority)))
        el.set("type", self.type)
        return el


def build_s5b_transport(bsid: str, candidates: list[Candidate],
                        dstaddr: str = "", mode: str = "tcp") -> ET.Element:
    el = ET.Element(_q(NS_S5B, "transport"))
    el.set("sid", bsid)
    if mode:
        el.set("mode", mode)
    if dstaddr:
        el.set("dstaddr", dstaddr)
    for cand in candidates:
        el.append(cand.element())
    return el


def parse_s5b_transport(el: ET.Element) -> dict:
    """Parse a XEP-0260 ``<transport/>`` into a plain dict."""
    result = {
        "sid": el.get("sid", ""),
        "mode": el.get("mode", "tcp"),
        "dstaddr": el.get("dstaddr", ""),
        "candidates": [],
        "candidate_used": "",
        "activated": "",
        "candidate_error": False,
        "proxy_error": False,
    }
    for child in el:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "candidate":
            try:
                port = int(child.get("port", "0") or 0)
                priority = int(child.get("priority", "0") or 0)
            except ValueError:
                port, priority = 0, 0
            result["candidates"].append(Candidate(
                cid=child.get("cid", ""), host=child.get("host", ""),
                port=port, jid=child.get("jid", ""), priority=priority,
                type=child.get("type", "direct") or "direct"))
        elif tag == "candidate-used":
            result["candidate_used"] = child.get("cid", "")
        elif tag == "activated":
            result["activated"] = child.get("cid", "")
        elif tag == "candidate-error":
            result["candidate_error"] = True
        elif tag == "proxy-error":
            result["proxy_error"] = True
    return result


class S5BFailed(Exception):
    """Raised internally when the SOCKS5 negotiation cannot be completed."""


# ── Session state ─────────────────────────────────────────────────

@dataclass
class JingleSession:
    sid: str
    peer_bare: str
    peer_full: str
    self_full: str
    initiator: bool
    content_name: str
    meta: FileMeta
    method: str = "s5b"            # "s5b" or "ibb"
    state: str = "initiating"
    path: str = ""                 # outbound: file; inbound: save path
    bsid: str = ""                 # SOCKS5 bytestream SID
    ibb_sid: str = ""              # XEP-0047 session id
    ibb_block: int = IBB_BLOCK_SIZE
    ibb_out_seq: int = 0
    ibb_in_seq: int = 0
    ibb_reader: object = None
    peer_candidates: list[Candidate] = field(default_factory=list)
    my_candidates: list[Candidate] = field(default_factory=list)
    server: object = None
    accept_future: object = None
    transfer_future: object = None
    transport: object = None
    proxy_sockets: dict = field(default_factory=dict)
    inbound: dict = field(default_factory=dict)
    outgoing: dict = field(default_factory=dict)
    used_peer: str = ""
    used_self: str = ""
    activated: str = ""
    peer_candidate_error: bool = False


def _safe_filename(name: str) -> str:
    """Strip directory structure/control characters from a remote file name
    (XEP-0234 §12)."""
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = name.replace("\x00", "").strip().strip(".")
    cleaned = "".join(ch for ch in name
                      if ch.isprintable() and ch not in "/\\")
    return cleaned or "file"


def _sha1_b64(path: str) -> tuple[str, int]:
    digest = hashlib.sha1()
    size = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return base64.b64encode(digest.digest()).decode("ascii"), size


class JingleFileTransferManager:
    """Owns Jingle FT sessions for one :class:`JabberClient`."""

    def __init__(self, client):
        self.client = client
        self.sessions: dict[str, JingleSession] = {}
        self._offers: dict[str, JingleSession] = {}
        self._send_lock = asyncio.Lock()

    @property
    def xmpp(self):
        return self.client.xmpp

    def _emit(self, *args) -> None:
        self.client.emit(*args)

    def _loop(self) -> asyncio.AbstractEventLoop:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.get_event_loop()

    def _new_future(self):
        return self._loop().create_future()

    # ── Public API ────────────────────────────────────────────────

    async def send_file(self, jid: str, path: str,
                        method: str = "p2p") -> None:
        """Send *path* to *jid*; serialized so a batch runs sequentially."""
        async with self._send_lock:
            await self._send_one(jid, path, method)

    async def _send_one(self, jid: str, path: str, method: str) -> None:
        path = str(path)
        if not os.path.isfile(path):
            self._emit("file_transfer_progress", jid, "error",
                       "not a file", path, "out")
            return
        try:
            hash_b64, size = await asyncio.to_thread(_sha1_b64, path)
        except OSError as exc:
            self._emit("file_transfer_progress", jid, "error",
                       str(exc), path, "out")
            return
        meta = FileMeta(name=os.path.basename(path), size=size,
                        media_type=mimetypes.guess_type(path)[0]
                        or "application/octet-stream",
                        hash_algo="sha-1", hash_value=hash_b64)
        peer_bare = str(jid).split("/")[0]
        session = JingleSession(
            sid=uuid.uuid4().hex, peer_bare=peer_bare,
            peer_full=self._best_full_jid(peer_bare) or peer_bare,
            self_full=self._full_jid(), initiator=True,
            content_name="file-%s" % uuid.uuid4().hex[:8], meta=meta,
            path=path)
        session.accept_future = self._new_future()
        session.transfer_future = self._new_future()
        self.sessions[session.sid] = session
        self._emit("file_transfer_progress", jid, "start", "", path, "out")

        try:
            if method in ("ibb", "p2p-ibb"):
                await self._run_ibb_send(session)
                return
            try:
                await self._run_s5b(session)
            except S5BFailed:
                logger.info("S5B failed (%s), falling back to IBB", session.sid)
                if session.state in ("accepted", "transferring"):
                    await self._replace_with_ibb(session)
                await self._run_ibb_send(session, fallback=True)
        except S5BFailed as exc:
            session.state = "failed"
            self._emit("file_transfer_progress", peer_bare, "error",
                       str(exc) or "transfer failed", path, "out")
            self._cleanup(session)

    def answer_offer(self, offer_id: str, accept: bool,
                     save_path: str = "") -> None:
        """Accept or reject a file offer reported through ``file_offer``."""
        session = self._offers.pop(offer_id, None)
        if session is None:
            return
        self.client._start_task(self._answer_offer(session, accept, save_path))

    def cancel(self, sid: str) -> None:
        session = self.sessions.get(sid)
        if session is not None:
            self.client._start_task(self._terminate(session, "cancel"))

    def close(self) -> None:
        """Drop every session and close its listener/sockets (on disconnect)."""
        for session in list(self.sessions.values()):
            self._cleanup(session)
        self.sessions.clear()
        self._offers.clear()

    def active_offers(self) -> list[str]:
        return list(self._offers)

    # ── IQ entry points (registered by JabberClient) ──────────────

    async def handle_jingle_iq(self, iq) -> None:
        jingle = iq.xml.find(_q(NS_JINGLE, "jingle"))
        if jingle is None:
            return
        action = (jingle.get("action") or "").strip()
        self._reply(iq)
        self.client._start_task(self._dispatch(action, jingle, iq))

    async def handle_ibb_open(self, iq) -> None:
        self._reply(iq)
        self.client._start_task(self._on_ibb_open(iq))

    async def handle_ibb_close(self, iq) -> None:
        self._reply(iq)
        self.client._start_task(self._on_ibb_close(iq))

    async def handle_ibb_data(self, iq) -> None:
        self._reply(iq)
        self._on_ibb_data(iq)

    def _reply(self, iq) -> None:
        """Ack an incoming IQ-set (fire-and-forget; result IQs await nothing)."""
        try:
            self.xmpp.send(iq.reply())
        except Exception:
            logger.debug("Could not ack IQ", exc_info=True)

    # ── Jingle dispatch ───────────────────────────────────────────

    async def _dispatch(self, action: str, jingle: ET.Element, iq) -> None:
        try:
            if action == "session-initiate":
                await self._on_session_initiate(jingle, iq)
            elif action == "session-accept":
                await self._on_session_accept(jingle)
            elif action == "session-terminate":
                await self._on_session_terminate(jingle)
            elif action == "transport-info":
                await self._on_transport_info(jingle)
            elif action == "transport-replace":
                await self._on_transport_replace(jingle)
            elif action == "transport-accept":
                await self._on_transport_accept(jingle)
            elif action == "transport-reject":
                session = self.sessions.get(jingle.get("sid", ""))
                if session is not None:
                    session.state = "failed"
                    self._resolve(session.accept_future, False)
            elif action == "session-info":
                pass
            else:
                logger.debug("Unhandled Jingle action %s", action)
        except Exception:
            logger.exception("Jingle action %s failed", action)

    def _content_meta(self, jingle: ET.Element) -> tuple[str, FileMeta | None]:
        content = jingle.find(_q(NS_JINGLE, "content"))
        if content is None:
            return "", None
        name = content.get("name", "")
        desc = content.find(_q(NS_FT, "description"))
        meta = parse_description(desc) if desc is not None else None
        return name, meta

    async def _on_session_initiate(self, jingle: ET.Element, iq) -> None:
        sid = jingle.get("sid", "")
        peer_full = str(iq["from"])
        peer_bare = peer_full.split("/")[0]
        name, meta = self._content_meta(jingle)
        if meta is None:
            return
        content = jingle.find(_q(NS_JINGLE, "content"))
        s5b_el = content.find(_q(NS_S5B, "transport")) if content is not None else None
        ibb_el = content.find(_q(NS_IBB, "transport")) if content is not None else None
        method = "s5b" if s5b_el is not None else "ibb"
        session = JingleSession(
            sid=sid, peer_bare=peer_bare, peer_full=peer_full,
            self_full=self._full_jid(), initiator=False, content_name=name,
            meta=meta, method=method)
        if s5b_el is not None:
            info = parse_s5b_transport(s5b_el)
            session.bsid = info["sid"]
            session.peer_candidates = info["candidates"]
        elif ibb_el is not None:
            session.bsid = ibb_el.get("sid", "")
        session.accept_future = self._new_future()
        session.transfer_future = self._new_future()
        self.sessions[sid] = session
        self._offers[sid] = session
        self._emit("file_offer", sid, peer_full, meta.as_dict())

    async def _on_session_accept(self, jingle: ET.Element) -> None:
        session = self.sessions.get(jingle.get("sid", ""))
        if session is None:
            return
        content = jingle.find(_q(NS_JINGLE, "content"))
        s5b_el = content.find(_q(NS_S5B, "transport")) if content is not None else None
        if s5b_el is not None:
            info = parse_s5b_transport(s5b_el)
            session.peer_candidates = info["candidates"]
        session.state = "accepted"
        self._resolve(session.accept_future, True)

    async def _on_session_terminate(self, jingle: ET.Element) -> None:
        session = self.sessions.get(jingle.get("sid", ""))
        if session is None:
            return
        reason = self._terminate_reason(jingle)
        if session.state != "done":
            session.state = "failed"
            self._emit("file_transfer_progress", session.peer_bare, "error",
                       reason or "cancelled", session.path, "out")
        self._resolve(session.accept_future, False)
        self._cleanup(session)

    async def _on_transport_info(self, jingle: ET.Element) -> None:
        session = self.sessions.get(jingle.get("sid", ""))
        if session is None:
            return
        content = jingle.find(_q(NS_JINGLE, "content"))
        s5b_el = content.find(_q(NS_S5B, "transport")) if content is not None else None
        if s5b_el is None:
            return
        info = parse_s5b_transport(s5b_el)
        if info["candidate_used"]:
            session.used_self = info["candidate_used"]
            self._finish_transport_if_ready(session)
        if info["activated"]:
            session.activated = info["activated"]
        if info["candidate_error"]:
            session.peer_candidate_error = True

    async def _on_transport_replace(self, jingle: ET.Element) -> None:
        session = self.sessions.get(jingle.get("sid", ""))
        if session is None:
            return
        content = jingle.find(_q(NS_JINGLE, "content"))
        ibb_el = content.find(_q(NS_IBB, "transport")) if content is not None else None
        if ibb_el is None:
            return
        session.ibb_sid = ibb_el.get("sid", "") or uuid.uuid4().hex
        try:
            session.ibb_block = int(ibb_el.get("block-size", IBB_BLOCK_SIZE))
        except ValueError:
            session.ibb_block = IBB_BLOCK_SIZE
        session.method = "ibb"
        self._emit_status(session, "s5b_fallback")
        await self._send_transport_action("transport-accept", session,
                                          self._ibb_transport_el(session))

    async def _on_transport_accept(self, jingle: ET.Element) -> None:
        session = self.sessions.get(jingle.get("sid", ""))
        if session is None:
            return
        content = jingle.find(_q(NS_JINGLE, "content"))
        ibb_el = content.find(_q(NS_IBB, "transport")) if content is not None else None
        if ibb_el is not None and ibb_el.get("block-size"):
            try:
                session.ibb_block = int(ibb_el.get("block-size"))
            except ValueError:
                pass
        session.state = "accepted"
        self._resolve(session.accept_future, True)

    # ── SOCKS5 (XEP-0260) ─────────────────────────────────────────

    async def _run_s5b(self, session: JingleSession) -> None:
        session.bsid = uuid.uuid4().hex
        session.my_candidates = self._build_candidates(session)
        await self._setup_listener(session)
        await self._send_session_initiate(session)
        await self._await(session.accept_future, "session not accepted")
        await self._dial_candidates(session)
        transport = await self._await_transport(session)
        session.state = "transferring"
        await self._stream_out(session, transport)
        await self._send_received(session)
        await self._terminate(session, "success")

    def _build_candidates(self, session: JingleSession) -> list[Candidate]:
        candidates: list[Candidate] = []
        for host in bytestream.local_host_candidates():
            candidates.append(Candidate(
                cid=uuid.uuid4().hex, host=host, port=0,
                jid=session.self_full, priority=(126 << 16) | 1,
                type="direct"))
        proxy = self._resolve_proxy()
        if proxy:
            candidates.append(Candidate(
                cid=uuid.uuid4().hex, host=proxy["host"],
                port=int(proxy["port"]), jid=proxy["jid"],
                priority=(10 << 16) | 1, type="proxy"))
        return candidates

    def _resolve_proxy(self) -> dict | None:
        discovered = self.client.discovered_services() or {}
        proxy = discovered.get("file_proxy")
        return proxy if isinstance(proxy, dict) and proxy.get("port") else None

    def _dst(self, session: JingleSession) -> str:
        return bytestream.sha1_dst(session.bsid, session.self_full
                                   if session.initiator else session.peer_full,
                                   session.peer_full
                                   if session.initiator else session.self_full)

    def _expected_dsts(self, session: JingleSession) -> set[str]:
        return {
            bytestream.sha1_dst(session.bsid, session.self_full,
                                session.peer_full),
            bytestream.sha1_dst(session.bsid, session.peer_full,
                                session.self_full),
        }

    async def _setup_listener(self, session: JingleSession) -> None:
        direct = [c for c in session.my_candidates if c.type == "direct"]
        if not direct:
            return

        async def _on_inbound(reader, writer):
            for cand in direct:
                session.inbound[cand.cid] = (reader, writer)
            self._set_transport(session, (reader, writer))

        try:
            session.server, port = await bytestream.listen_for_bytestream(
                self._expected_dsts(session), _on_inbound)
        except OSError as exc:
            logger.debug("Could not listen for direct bytestream: %s", exc)
            return
        for cand in direct:
            cand.port = port

    async def _dial_candidates(self, session: JingleSession) -> None:
        ordered = sorted(session.peer_candidates,
                         key=lambda c: (-c.priority,
                                        0 if c.type == "direct" else 1))
        for cand in ordered:
            if cand.port:
                self.client._start_task(self._dial_candidate(session, cand))

    async def _dial_candidate(self, session: JingleSession,
                              cand: Candidate) -> None:
        try:
            reader, writer = await bytestream.connect_bytestream(
                cand.host, int(cand.port), self._dst(session),
                timeout=_S5B_CONNECT_TIMEOUT)
            if cand.type == "proxy":
                await self._activate_proxy(cand, session)
                await self._send_transport_info(
                    session, _q(NS_S5B, "activated"), cid=cand.cid)
            session.outgoing[cand.cid] = (reader, writer)
            session.used_peer = cand.cid
            await self._send_transport_info(
                session, _q(NS_S5B, "candidate-used"), cid=cand.cid)
            self._set_transport(session, (reader, writer))
        except Exception as exc:
            logger.debug("Candidate %s failed: %s", cand.cid, exc)

    async def _activate_proxy(self, cand: Candidate, session: JingleSession):
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = cand.jid
        query = ET.SubElement(iq.xml, _q(NS_BYTESTREAMS, "query"))
        query.set("sid", session.bsid)
        activate = ET.SubElement(query, _q(NS_BYTESTREAMS, "activate"))
        activate.text = session.peer_full
        try:
            await iq.send(timeout=_IQ_TIMEOUT)
        except Exception as exc:
            logger.debug("Proxy activation failed: %s", exc)

    def _finish_transport_if_ready(self, session: JingleSession) -> None:
        cand = next((c for c in session.my_candidates
                     if c.cid == session.used_self), None)
        if cand is None:
            return
        transport = (session.inbound.get(cand.cid)
                     or session.proxy_sockets.get(cand.cid))
        if transport is not None:
            self._set_transport(session, transport)

    def _set_transport(self, session: JingleSession, transport) -> None:
        if session.transport is None:
            session.transport = transport
        self._resolve(session.transfer_future, transport)

    async def _await_transport(self, session: JingleSession):
        await self._await(session.transfer_future, "no candidate connected")
        return session.transport

    async def _send_candidate_error(self, session: JingleSession) -> None:
        await self._send_transport_info(session,
                                        _q(NS_S5B, "candidate-error"))

    # ── IBB (XEP-0261 / XEP-0047) ─────────────────────────────────

    async def _replace_with_ibb(self, session: JingleSession) -> None:
        session.ibb_sid = session.ibb_sid or uuid.uuid4().hex
        session.method = "ibb"
        session.accept_future = self._new_future()
        logger.info("Replacing SOCKS5 transport with IBB for %s", session.sid)
        await self._send_transport_action(
            "transport-replace", session, self._ibb_transport_el(session))
        try:
            await self._await(session.accept_future, "transport-replace rejected")
        except S5BFailed as exc:
            raise S5BFailed("IBB fallback rejected") from exc

    def _ibb_transport_el(self, session: JingleSession) -> ET.Element:
        el = ET.Element(_q(NS_IBB, "transport"))
        el.set("block-size", str(int(session.ibb_block)))
        el.set("sid", session.ibb_sid or uuid.uuid4().hex)
        return el

    async def _run_ibb_send(self, session: JingleSession,
                            fallback: bool = False) -> None:
        if not fallback:
            session.ibb_sid = session.ibb_sid or uuid.uuid4().hex
            await self._send_session_initiate(session, ibb=True)
            await self._await(session.accept_future, "session not accepted")
        if session.state not in ("accepted", "transferring"):
            session.state = "failed"
            self._emit("file_transfer_progress", session.peer_bare, "error",
                       "session not accepted", session.path, "out")
            self._cleanup(session)
            return
        session.state = "transferring"
        session.accept_future = self._new_future()  # for a later replace
        await self._ibb_send_open(session)
        try:
            await self._ibb_send_file(session)
        except Exception as exc:  # noqa: BLE001 - surfaced as progress
            logger.warning("IBB send failed: %s", exc)
            self._emit("file_transfer_progress", session.peer_bare, "error",
                       str(exc), session.path, "out")
            await self._terminate(session, "media-error")
            return
        await self._send_received(session)
        await self._terminate(session, "success")

    async def _ibb_send_open(self, session: JingleSession) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        open_el = ET.SubElement(iq.xml, _q(NS_IBB_OLD, "open"))
        open_el.set("block-size", str(int(session.ibb_block)))
        open_el.set("sid", session.ibb_sid)
        open_el.set("stanza", "iq")
        await iq.send(timeout=_IQ_TIMEOUT)

    async def _ibb_send_file(self, session: JingleSession) -> None:
        total = os.path.getsize(session.path) or 1
        sent = 0
        with open(session.path, "rb") as fh:
            while True:
                chunk = fh.read(session.ibb_block)
                if not chunk:
                    break
                iq = self.xmpp.Iq()
                iq["type"] = "set"
                iq["to"] = session.peer_full
                data = ET.SubElement(iq.xml, _q(NS_IBB_OLD, "data"))
                data.set("seq", str(session.ibb_out_seq & 0xFFFF))
                data.set("sid", session.ibb_sid)
                data.text = base64.b64encode(chunk).decode("ascii")
                session.ibb_out_seq = (session.ibb_out_seq + 1) & 0xFFFF
                await iq.send(timeout=_IQ_TIMEOUT)
                sent += len(chunk)
                self._emit("file_transfer_progress", session.peer_bare,
                           "progress", str(int(sent * 100 / total)),
                           session.path, "out")
        await self._ibb_send_close(session)

    async def _ibb_send_close(self, session: JingleSession) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        close_el = ET.SubElement(iq.xml, _q(NS_IBB_OLD, "close"))
        close_el.set("sid", session.ibb_sid)
        try:
            await iq.send(timeout=_IQ_TIMEOUT)
        except Exception:
            logger.debug("IBB close failed", exc_info=True)

    async def _on_ibb_open(self, iq) -> None:
        open_el = iq.xml.find(_q(NS_IBB_OLD, "open"))
        if open_el is None:
            return
        session = self._find_ibb_session(open_el.get("sid", ""))
        if session is None or session.initiator or not session.path:
            return
        try:
            session.ibb_block = int(open_el.get("block-size", IBB_BLOCK_SIZE))
        except ValueError:
            session.ibb_block = IBB_BLOCK_SIZE
        session.ibb_in_seq = 0
        try:
            session.ibb_reader = open(session.path, "wb")
        except OSError as exc:
            logger.warning("Cannot save incoming file: %s", exc)
            session.state = "failed"
            self._emit("file_transfer_progress", session.peer_bare, "error",
                       str(exc), session.path, "in")
            return
        session.state = "transferring"
        self._emit("file_transfer_progress", session.peer_bare, "start",
                   "", session.path, "in")

    def _on_ibb_data(self, iq) -> None:
        data = iq.xml.find(_q(NS_IBB_OLD, "data"))
        if data is None:
            return
        session = self._find_ibb_session(data.get("sid", ""))
        if session is None or session.initiator or session.ibb_reader is None:
            return
        try:
            seq = int(data.get("seq", "0")) & 0xFFFF
        except ValueError:
            return
        if seq != (session.ibb_in_seq & 0xFFFF):
            logger.warning("Out-of-order IBB data (got %s, want %s)",
                           seq, session.ibb_in_seq)
            return
        session.ibb_in_seq = (session.ibb_in_seq + 1) & 0xFFFF
        try:
            chunk = base64.b64decode(data.text or "", validate=True)
        except Exception:
            return
        try:
            session.ibb_reader.write(chunk)
            session.ibb_reader.flush()
        except OSError as exc:
            logger.warning("IBB write failed: %s", exc)
            return
        total = session.meta.size or session.ibb_reader.tell() or 1
        self._emit("file_transfer_progress", session.peer_bare, "progress",
                   str(int(session.ibb_reader.tell() * 100 / total)),
                   session.path, "in")

    async def _on_ibb_close(self, iq) -> None:
        close_el = iq.xml.find(_q(NS_IBB_OLD, "close"))
        if close_el is None:
            return
        session = self._find_ibb_session(close_el.get("sid", ""))
        if session is None or session.initiator:
            return
        if session.ibb_reader is not None:
            try:
                session.ibb_reader.close()
            except OSError:
                pass
            session.ibb_reader = None
        session.state = "done"
        self._emit("file_transfer_progress", session.peer_bare, "done",
                   "", session.path, "in")
        await self._send_received(session)
        await self._terminate(session, "success")

    def _find_ibb_session(self, sid: str) -> JingleSession | None:
        for session in self.sessions.values():
            if session.ibb_sid == sid:
                return session
        return None

    # ── Incoming offer handling ───────────────────────────────────

    async def _answer_offer(self, session: JingleSession, accept: bool,
                            save_path: str) -> None:
        if not accept:
            await self._terminate(session, "decline")
            return
        if save_path:
            session.path = save_path
        if not session.path:
            await self._terminate(session, "decline")
            return
        if session.method == "s5b":
            session.bsid = session.bsid or uuid.uuid4().hex
            session.my_candidates = self._build_candidates(session)
            await self._setup_listener(session)
        else:
            session.ibb_sid = session.ibb_sid or uuid.uuid4().hex
        await self._send_session_accept(session)
        if session.method == "ibb":
            session.state = "accepted"       # wait for IBB <open>
            return
        # Open our proxy sockets (the proxy pairs both sides itself).
        for cand in session.my_candidates:
            if cand.type == "proxy":
                self.client._start_task(
                    self._open_proxy_socket(session, cand))
        try:
            transport = await self._await_transport(session)
        except S5BFailed:
            # Wait for the initiator's transport-replace to IBB.
            session.method = "ibb"
            session.ibb_sid = ""
            return
        session.state = "transferring"
        await self._stream_in(session, transport)
        await self._send_received(session)
        await self._terminate(session, "success")

    async def _open_proxy_socket(self, session: JingleSession,
                                 cand: Candidate) -> None:
        try:
            reader, writer = await bytestream.connect_bytestream(
                cand.host, int(cand.port), self._dst(session),
                timeout=_S5B_CONNECT_TIMEOUT)
            session.proxy_sockets[cand.cid] = (reader, writer)
        except Exception as exc:
            logger.debug("Proxy socket failed: %s", exc)

    # ── Data streaming ────────────────────────────────────────────

    async def _stream_out(self, session: JingleSession, transport) -> None:
        reader, writer = transport
        total = os.path.getsize(session.path) or 1
        sent = 0
        try:
            with open(session.path, "rb") as fh:
                while True:
                    chunk = fh.read(_CHUNK)
                    if not chunk:
                        break
                    writer.write(chunk)
                    await writer.drain()
                    sent += len(chunk)
                    self._emit("file_transfer_progress", session.peer_bare,
                               "progress", str(int(sent * 100 / total)),
                               session.path, "out")
        finally:
            await self._close_writer(writer)
        session.state = "done"
        self._emit("file_transfer_progress", session.peer_bare, "done",
                   "", session.path, "out")

    async def _stream_in(self, session: JingleSession, transport) -> None:
        reader, writer = transport
        total = session.meta.size or 0
        received = 0
        try:
            with open(session.path, "wb") as fh:
                while True:
                    chunk = await reader.read(_CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
                    received += len(chunk)
                    if total:
                        self._emit("file_transfer_progress",
                                   session.peer_bare, "progress",
                                   str(int(received * 100 / total)),
                                   session.path, "in")
                        if received >= total:
                            break
        except OSError as exc:
            logger.warning("Receiving file failed: %s", exc)
            session.state = "failed"
            self._emit("file_transfer_progress", session.peer_bare, "error",
                       str(exc), session.path, "in")
            await self._close_writer(writer)
            return
        await self._close_writer(writer)
        session.state = "done"
        self._emit("file_transfer_progress", session.peer_bare, "done",
                   "", session.path, "in")

    @staticmethod
    async def _close_writer(writer) -> None:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

    # ── Stanza builders / senders ─────────────────────────────────

    def _full_jid(self) -> str:
        return (getattr(self.client, "_full_jid", "")
                or self.client.jid_str or "")

    def _best_full_jid(self, bare: str) -> str:
        best = ""
        best_show = 99
        for full, info in (self.client.presences or {}).items():
            if full.split("/")[0] != bare:
                continue
            if info.get("type") != "available":
                continue
            show = SHOW_ORDER.get(info.get("show", "online"), 99)
            if not best or show < best_show:
                best, best_show = full, show
        return best

    def _new_jingle(self, action: str, session: JingleSession) -> ET.Element:
        return ET.Element(_q(NS_JINGLE, "jingle"),
                          {"action": action, "sid": session.sid})

    def _content_el(self, session: JingleSession) -> ET.Element:
        el = ET.Element(_q(NS_JINGLE, "content"))
        el.set("creator", "initiator")
        el.set("name", session.content_name)
        el.set("senders", "initiator")
        el.append(build_description(session.meta))
        return el

    async def _send_session_initiate(self, session: JingleSession,
                                     ibb: bool = False) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        jingle = self._new_jingle("session-initiate", session)
        jingle.set("initiator", session.self_full)
        iq.xml.append(jingle)
        content = self._content_el(session)
        jingle.append(content)
        if ibb:
            content.append(self._ibb_transport_el(session))
        else:
            content.append(build_s5b_transport(
                session.bsid, session.my_candidates,
                dstaddr=self._dst(session)))
        try:
            await iq.send(timeout=_IQ_TIMEOUT)
        except Exception as exc:
            raise S5BFailed(str(exc)) from exc

    async def _send_session_accept(self, session: JingleSession) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        jingle = self._new_jingle("session-accept", session)
        jingle.set("responder", session.self_full)
        iq.xml.append(jingle)
        content = self._content_el(session)
        jingle.append(content)
        if session.method == "ibb":
            content.append(self._ibb_transport_el(session))
        else:
            content.append(build_s5b_transport(
                session.bsid, session.my_candidates,
                dstaddr=self._dst(session)))
        try:
            await iq.send(timeout=_IQ_TIMEOUT)
        except Exception as exc:
            raise S5BFailed(str(exc)) from exc

    async def _send_transport_info(self, session: JingleSession,
                                   child_tag: str, cid: str = "") -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        jingle = self._new_jingle("transport-info", session)
        iq.xml.append(jingle)
        content = ET.SubElement(jingle, _q(NS_JINGLE, "content"))
        content.set("creator", "initiator")
        content.set("name", session.content_name)
        transport = ET.SubElement(content, _q(NS_S5B, "transport"))
        transport.set("sid", session.bsid)
        child = ET.SubElement(transport, child_tag)
        if cid:
            child.set("cid", cid)
        try:
            await iq.send(timeout=_IQ_TIMEOUT)
        except Exception:
            logger.debug("transport-info failed", exc_info=True)

    async def _send_transport_action(self, action: str,
                                     session: JingleSession,
                                     transport_el: ET.Element) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        jingle = self._new_jingle(action, session)
        iq.xml.append(jingle)
        content = ET.SubElement(jingle, _q(NS_JINGLE, "content"))
        content.set("creator", "initiator")
        content.set("name", session.content_name)
        content.append(transport_el)
        try:
            await iq.send(timeout=_IQ_TIMEOUT)
        except Exception:
            logger.debug("%s failed", action, exc_info=True)

    async def _send_received(self, session: JingleSession) -> None:
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        jingle = self._new_jingle("session-info", session)
        iq.xml.append(jingle)
        received = ET.SubElement(jingle, _q(NS_FT, "received"))
        received.set("creator", "initiator")
        received.set("name", session.content_name)
        try:
            await iq.send(timeout=_IQ_TIMEOUT)
        except Exception:
            logger.debug("session-info received failed", exc_info=True)

    async def _terminate(self, session: JingleSession, reason: str) -> None:
        if session.sid not in self.sessions:
            return
        iq = self.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        jingle = self._new_jingle("session-terminate", session)
        iq.xml.append(jingle)
        reason_el = ET.SubElement(jingle, _q(NS_JINGLE, "reason"))
        ET.SubElement(reason_el, _q(NS_JINGLE, reason or "success"))
        try:
            await iq.send(timeout=_IQ_TIMEOUT)
        except Exception:
            logger.debug("session-terminate failed", exc_info=True)
        if session.state != "done":
            session.state = "done" if reason == "success" else "failed"
        self._cleanup(session)

    @staticmethod
    def _terminate_reason(jingle: ET.Element) -> str:
        reason = jingle.find(_q(NS_JINGLE, "reason"))
        if reason is None or len(reason) == 0:
            return ""
        return reason[0].tag.rsplit("}", 1)[-1]

    # ── Helpers ───────────────────────────────────────────────────

    def _emit_status(self, session: JingleSession, key: str) -> None:
        self._emit("file_transfer_status", session.peer_bare, key)

    def _cleanup(self, session: JingleSession) -> None:
        if session.server is not None:
            try:
                session.server.close()
            except Exception:
                pass
            session.server = None
        writers = [t[1] for t in session.outgoing.values()]
        writers += [t[1] for t in session.proxy_sockets.values()]
        if session.transport is not None:
            writers.append(session.transport[1])
        for writer in writers:
            self.client._start_task(self._close_writer(writer))
        session.outgoing.clear()
        session.proxy_sockets.clear()
        session.inbound.clear()
        if session.ibb_reader is not None:
            try:
                session.ibb_reader.close()
            except OSError:
                pass
            session.ibb_reader = None
        self.sessions.pop(session.sid, None)
        self._offers.pop(session.sid, None)

    @staticmethod
    def _resolve(future, value) -> None:
        if future is not None and not future.done():
            future.set_result(value)

    async def _await(self, future, message: str) -> None:
        if future is None:
            raise S5BFailed(message)
        try:
            result = await asyncio.wait_for(asyncio.shield(future),
                                            _S5B_CONNECT_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise S5BFailed(message) from exc
        if result is False or result is None:
            raise S5BFailed(message)
