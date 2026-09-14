"""Jingle RTP calls: XEP-0167 (RTP), XEP-0176 (ICE-UDP), DTLS (urn:…:dtls:0).

Signalling is implemented on the slixmpp stanza objects; the media/ICE/DTLS
path is delegated to :mod:`stanza_im.xmpp.media` (aiortc).  The Jingle
application/transport elements are converted to/from an SDP description that
aiortc understands (and back), so ICE candidates, the DTLS fingerprint and the
RTP payload map cross the XMPP wire.

Everything logs through ``stanza_im.call`` / ``stanza_im.call.rtp`` with
``CALL[…]`` markers so real-device tests can be diagnosed from the log file.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from stanza_im.xmpp import media

logger = logging.getLogger("stanza_im.call.rtp")

NS_JINGLE = "urn:xmpp:jingle:1"
NS_RTP = "urn:xmpp:jingle:apps:rtp:1"
NS_RTP_AUDIO = "urn:xmpp:jingle:apps:rtp:audio"
NS_RTP_VIDEO = "urn:xmpp:jingle:apps:rtp:video"
NS_RTP_SSMA = "urn:xmpp:jingle:apps:rtp:ssma:0"
NS_DTLS = "urn:xmpp:jingle:apps:dtls:0"
NS_ICE = "urn:xmpp:jingle:transports:ice-udp:1"
NS_JINGLE_MSG = "urn:xmpp:jingle-message:0"
NS_MUJI = "urn:xmpp:jingle:muji:0"

CALL_TIMEOUT = 45.0


def _q(ns: str, tag: str) -> str:
    return "{%s}%s" % (ns, tag)


# ── Data model ────────────────────────────────────────────────────

@dataclass
class PayloadType:
    id: int
    name: str
    clockrate: int = 0
    channels: int = 0
    parameters: dict = field(default_factory=dict)


@dataclass
class RtpSource:
    ssrc: int
    parameters: dict = field(default_factory=dict)


@dataclass
class RtpDescription:
    media: str = "audio"
    payloads: list = field(default_factory=list)
    sources: list = field(default_factory=list)


@dataclass
class IceCandidate:
    foundation: str = ""
    component: int = 1
    protocol: str = "udp"
    priority: int = 0
    ip: str = ""
    port: int = 0
    type: str = "host"
    rel_addr: str = ""
    rel_port: int = 0
    generation: int = 0
    network: int = 0


@dataclass
class DtlsFingerprint:
    hash: str = "sha-256"
    value: str = ""
    setup: str = "actpass"


@dataclass
class IceTransport:
    ufrag: str = ""
    pwd: str = ""
    fingerprints: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    mode: str = "tcp"


# ── Jingle XML build/parse (XEP-0167 / XEP-0176 / DTLS) ───────────

def build_description(desc: RtpDescription) -> ET.Element:
    el = ET.Element(_q(NS_RTP, "description"))
    el.set("media", desc.media)
    for payload in desc.payloads:
        pel = ET.SubElement(el, _q(NS_RTP, "payload-type"))
        pel.set("id", str(payload.id))
        if payload.name:
            pel.set("name", payload.name)
        if payload.clockrate:
            pel.set("clockrate", str(payload.clockrate))
        if payload.channels:
            pel.set("channels", str(payload.channels))
        for key, value in payload.parameters.items():
            par = ET.SubElement(pel, _q(NS_RTP, "parameter"))
            par.set("name", key)
            par.set("value", value)
    for source in desc.sources:
        sel = ET.SubElement(el, _q(NS_RTP_SSMA, "source"))
        sel.set("ssrc", str(source.ssrc))
        for key, value in source.parameters.items():
            par = ET.SubElement(sel, _q(NS_RTP_SSMA, "parameter"))
            par.set("name", key)
            par.set("value", value)
    return el


def parse_description(el: ET.Element) -> RtpDescription:
    desc = RtpDescription(media=el.get("media", "audio"))
    for child in el:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "payload-type":
            try:
                pid = int(child.get("id", "0") or 0)
                clock = int(child.get("clockrate", "0") or 0)
                channels = int(child.get("channels", "0") or 0)
            except ValueError:
                continue
            params = {}
            for par in child:
                if par.tag.rsplit("}", 1)[-1] == "parameter":
                    params[par.get("name", "")] = par.get("value", "")
            desc.payloads.append(PayloadType(
                pid, child.get("name", ""), clock, channels, params))
        elif tag == "source":
            try:
                ssrc = int(child.get("ssrc", "0") or 0)
            except ValueError:
                continue
            params = {}
            for par in child:
                if par.tag.rsplit("}", 1)[-1] == "parameter":
                    params[par.get("name", "")] = par.get("value", "")
            desc.sources.append(RtpSource(ssrc, params))
    return desc


def build_transport(transport: IceTransport) -> ET.Element:
    el = ET.Element(_q(NS_ICE, "transport"))
    el.set("ufrag", transport.ufrag)
    el.set("pwd", transport.pwd)
    if transport.mode:
        el.set("mode", transport.mode)
    for fp in transport.fingerprints:
        fel = ET.SubElement(el, _q(NS_DTLS, "fingerprint"))
        fel.set("hash", fp.hash)
        fel.set("setup", fp.setup)
        fel.text = fp.value
    for cand in transport.candidates:
        cel = ET.SubElement(el, _q(NS_ICE, "candidate"))
        cel.set("component", str(cand.component))
        cel.set("foundation", cand.foundation)
        cel.set("protocol", cand.protocol)
        cel.set("priority", str(int(cand.priority)))
        cel.set("ip", cand.ip)
        cel.set("port", str(int(cand.port)))
        cel.set("type", cand.type)
        if cand.rel_addr:
            cel.set("rel-addr", cand.rel_addr)
            cel.set("rel-port", str(int(cand.rel_port)))
        if cand.generation:
            cel.set("generation", str(cand.generation))
    return el


def parse_transport(el: ET.Element) -> IceTransport:
    transport = IceTransport(ufrag=el.get("ufrag", ""),
                             pwd=el.get("pwd", ""),
                             mode=el.get("mode", "tcp"))
    for child in el:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "fingerprint":
            transport.fingerprints.append(DtlsFingerprint(
                child.get("hash", "sha-256"), (child.text or "").strip(),
                child.get("setup", "actpass")))
        elif tag == "candidate":
            try:
                component = int(child.get("component", "1") or 1)
                priority = int(child.get("priority", "0") or 0)
                port = int(child.get("port", "0") or 0)
                rel_port = int(child.get("rel-port", "0") or 0)
                generation = int(child.get("generation", "0") or 0)
            except ValueError:
                continue
            transport.candidates.append(IceCandidate(
                foundation=child.get("foundation", ""), component=component,
                protocol=child.get("protocol", "udp"), priority=priority,
                ip=child.get("ip", ""), port=port,
                type=child.get("type", "host"),
                rel_addr=child.get("rel-addr", ""), rel_port=rel_port,
                generation=generation))
    return transport


# ── SDP ↔ Jingle ──────────────────────────────────────────────────

def _candidate_to_sdp(cand: IceCandidate) -> str:
    line = ("a=candidate:%s %d %s %d %s %d typ %s" % (
        cand.foundation or "0", cand.component, cand.protocol or "udp",
        int(cand.priority), cand.ip, int(cand.port), cand.type))
    if cand.rel_addr and cand.type == "srflx":
        line += " raddr %s rport %d" % (cand.rel_addr, int(cand.rel_port))
    return line


def sdp_from_jingle(contents: list, session_id: str = "") -> str:
    """Build an SDP offer/answer string from Jingle contents.

    *contents* is a list of ``(name, RtpDescription, IceTransport)``.
    All contents share the first content's ICE credentials (BUNDLE), which is
    what aiortc expects.
    """
    if not contents:
        raise ValueError("no contents")
    session_id = session_id or uuid.uuid4().hex
    mids = [name or str(i) for i, (name, _d, _t) in enumerate(contents)]
    first_transport = contents[0][2]
    fingerprint = first_transport.fingerprints[0] if first_transport.fingerprints else DtlsFingerprint()
    setup = fingerprint.setup or "actpass"
    lines = [
        "v=0",
        "o=- %d 2 IN IP4 0.0.0.0" % (abs(hash(session_id)) % 1000000000),
        "s=-",
        "t=0 0",
        "a=group:BUNDLE %s" % " ".join(mids),
        "a=msid-semantic:WMS *",
    ]
    for index, (name, desc, transport) in enumerate(contents):
        mid = mids[index]
        pts = " ".join(str(p.id) for p in desc.payloads)
        lines.append("m=%s 9 UDP/TLS/RTP/SAVPF %s" % (desc.media, pts))
        lines.append("c=IN IP4 0.0.0.0")
        lines.append("a=sendrecv")
        lines.append("a=mid:%s" % mid)
        lines.append("a=rtcp:9 IN IP4 0.0.0.0")
        lines.append("a=rtcp-mux")
        for payload in desc.payloads:
            rtpmap = "%s/%s" % (payload.name, payload.clockrate or 8000)
            if payload.channels:
                rtpmap += "/%d" % payload.channels
            lines.append("a=rtpmap:%d %s" % (payload.id, rtpmap))
        for source in desc.sources:
            cname = source.parameters.get("cname", session_id)
            lines.append("a=ssrc:%d cname:%s" % (source.ssrc, cname))
        for cand in transport.candidates:
            lines.append(_candidate_to_sdp(cand))
        lines.append("a=end-of-candidates")
    # ICE/DTLS attributes are shared (BUNDLE) — take them from the first one.
    lines.append("a=ice-ufrag:%s" % first_transport.ufrag)
    lines.append("a=ice-pwd:%s" % first_transport.pwd)
    lines.append("a=fingerprint:%s %s" % (fingerprint.hash, fingerprint.value))
    lines.append("a=setup:%s" % setup)
    sdp = "\r\n".join(lines) + "\r\n"
    logger.debug("CALL built SDP from Jingle:\n%s", sdp)
    return sdp


_M_LINE = re.compile(r"^m=(\w+) \d+ [^ ]+ (.*)$")


def parse_sdp(sdp: str) -> list:
    """Parse an SDP string into ``(name, RtpDescription, IceTransport)`` list."""
    contents: list = []
    current = None
    for raw in sdp.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _M_LINE.match(line)
        if match:
            media_type = match.group(1)
            pids = [int(p) for p in match.group(2).split() if p.isdigit()]
            desc = RtpDescription(media=media_type)
            for pid in pids:
                desc.payloads.append(PayloadType(pid, "", 0, 0, {}))
            current = {"name": "c%d" % len(contents), "desc": desc,
                       "transport": IceTransport()}
            contents.append(current)
            continue
        if current is None:
            continue
        desc = current["desc"]
        transport = current["transport"]
        if line.startswith("a=mid:"):
            current["name"] = line[6:] or current["name"]
        elif line.startswith("a=ice-ufrag:"):
            transport.ufrag = line[11:]
        elif line.startswith("a=ice-pwd:"):
            transport.pwd = line[9:]
        elif line.startswith("a=setup:"):
            setup = line[8:]
            if transport.fingerprints:
                transport.fingerprints[0].setup = setup
            else:
                transport.fingerprints.append(DtlsFingerprint(setup=setup))
        elif line.startswith("a=fingerprint:"):
            rest = line[14:]
            parts = rest.split(" ", 1)
            if len(parts) == 2:
                transport.fingerprints.append(
                    DtlsFingerprint(parts[0], parts[1].strip(), "actpass"))
        elif line.startswith("a=rtpmap:"):
            rest = line[9:]
            try:
                pid_s, mapping = rest.split(" ", 1)
                pid = int(pid_s)
                bits = mapping.split("/")
                name = bits[0]
                clock = int(bits[1]) if len(bits) > 1 and bits[1].isdigit() else 0
                channels = int(bits[2]) if len(bits) > 2 and bits[2].isdigit() else 0
            except ValueError:
                continue
            for payload in desc.payloads:
                if payload.id == pid:
                    payload.name, payload.clockrate, payload.channels = (
                        name, clock, channels)
        elif line.startswith("a=ssrc:"):
            rest = line[7:]
            try:
                ssrc_s, *attrs = rest.split(" ")
                ssrc = int(ssrc_s)
            except ValueError:
                continue
            params = {}
            for attr in attrs:
                if ":" in attr:
                    key, value = attr.split(":", 1)
                    params[key] = value
            desc.sources.append(RtpSource(ssrc, params))
        elif line.startswith("a=candidate:"):
            fields = line[len("a=candidate:"):].split()
            if len(fields) < 8:
                continue
            try:
                cand = IceCandidate(
                    foundation=fields[0], component=int(fields[1]),
                    protocol=fields[2], priority=int(fields[3]),
                    ip=fields[4], port=int(fields[5]),
                    type=fields[7] if len(fields) > 7 else "host")
            except (ValueError, IndexError):
                continue
            if "raddr" in fields:
                try:
                    cand.rel_addr = fields[fields.index("raddr") + 1]
                    cand.rel_port = int(fields[fields.index("rport") + 1])
                except (ValueError, IndexError):
                    pass
            transport.candidates.append(cand)
    logger.debug("CALL parsed SDP: %d content(s)", len(contents))
    for item in contents:
        logger.debug("  content %s: media=%s payloads=%s candidates=%d",
                     item["name"], item["desc"].media,
                     [(p.id, p.name) for p in item["desc"].payloads],
                     len(item["transport"].candidates))
    return contents


def jingle_contents_from_sdp(sdp: str) -> list:
    """SDP → Jingle contents, propagating ICE/DTLS to every content (BUNDLE)."""
    parsed = parse_sdp(sdp)
    if not parsed:
        return []
    shared = parsed[0]["transport"]
    for item in parsed:
        transport = item["transport"]
        if not transport.ufrag and shared.ufrag:
            transport.ufrag = shared.ufrag
            transport.pwd = shared.pwd
            transport.fingerprints = shared.fingerprints
        if not transport.candidates:
            transport.candidates = shared.candidates
    return [(item["name"], item["desc"], item["transport"]) for item in parsed]


# ── Session state ─────────────────────────────────────────────────

@dataclass
class CallSession:
    sid: str
    peer_bare: str
    peer_full: str
    self_full: str
    initiator: bool
    video: bool = False
    state: str = "initiating"
    call: object = None
    peer_transport: IceTransport = None
    my_transport: IceTransport = None
    contents: list = field(default_factory=list)
    content_name: str = "voice"
    video_content: str = "video"
    ringed: bool = False
    muji_room: str = ""


class JingleRtpManager:
    """1:1 Jingle RTP calls (XEP-0167/0176 + DTLS)."""

    def __init__(self, client):
        self.client = client
        self.sessions: dict[str, CallSession] = {}
        self.engine = media.get_engine()
        logger.info("CALL manager ready, engine=%s", self.engine.name)

    @property
    def available(self) -> bool:
        return self.engine.available

    # ── helpers ───────────────────────────────────────────────────
    def _devices(self) -> dict:
        return getattr(self.client, "call_devices", {}) or {}

    def _ice_servers(self) -> list:
        try:
            return self.client.ice_servers()
        except Exception:
            logger.exception("CALL ice_servers() failed")
            return []

    def _full_jid(self) -> str:
        return (getattr(self.client, "_full_jid", "")
                or self.client.jid_str or "")

    def _best_full_jid(self, bare: str) -> str:
        best, best_show = "", 99
        from stanza_im.include.enumerators import SHOW_ORDER
        for full, info in (self.client.presences or {}).items():
            if full.split("/")[0] != bare:
                continue
            if info.get("type") != "available":
                continue
            show = SHOW_ORDER.get(info.get("show", "online"), 99)
            if not best or show < best_show:
                best, best_show = full, show
        return best or bare

    def _content_name(self, media_type: str) -> str:
        return "voice" if media_type == "audio" else "video"

    # ── outgoing call ─────────────────────────────────────────────
    async def start_call(self, jid: str, video: bool = False,
                         use_message: bool = True, muji_room: str = "") -> None:
        if not self.available:
            logger.error("CALL cannot start: media engine unavailable")
            self.client.emit("call_failed", jid, "media engine unavailable")
            return
        peer_bare = str(jid).split("/")[0]
        sid = uuid.uuid4().hex
        session = CallSession(
            sid=sid, peer_bare=peer_bare,
            peer_full=self._best_full_jid(peer_bare),
            self_full=self._full_jid(), initiator=True, video=video,
            muji_room=muji_room)
        self.sessions[sid] = session
        logger.info("CALL start to %s (sid=%s video=%s muji=%s)",
                    session.peer_full, sid, video, muji_room)
        self.client.emit("call_state", sid, session.peer_full, "ringing")
        try:
            if (use_message and not muji_room
                    and self._peer_supports_messages(peer_bare)):
                await self._send_jingle_message("propose", session)
                session.ringed = True
                await self._wait_proceed(session, timeout=30)
            await self._send_session_initiate(session)
        except Exception as exc:
            logger.exception("CALL start failed")
            self.client.emit("call_failed", session.peer_full, str(exc))
            self._terminate(session, "connectivity-error", send=True)

    def _peer_supports_messages(self, bare: str) -> bool:
        support = getattr(self.client, "supports_feature", None)
        if callable(support):
            try:
                return bool(support(bare, NS_JINGLE_MSG))
            except Exception:
                return False
        return False

    async def _wait_proceed(self, session: CallSession, timeout: float) -> None:
        future = asyncio.get_event_loop().create_future()
        self._proceed_futures = getattr(self, "_proceed_futures", {})
        self._proceed_futures[session.sid] = future
        try:
            await asyncio.wait_for(future, timeout)
            logger.info("CALL proceed received for %s", session.sid)
        except asyncio.TimeoutError:
            logger.warning("CALL no proceed for %s, continuing anyway",
                           session.sid)

    async def _send_jingle_message(self, action: str, session: CallSession,
                                   extra: ET.Element | None = None) -> None:
        msg = self.client.xmpp.Message()
        msg["to"] = session.peer_bare
        msg["type"] = "chat"
        el = ET.SubElement(msg.xml, _q(NS_JINGLE_MSG, action))
        el.set("id", session.sid)
        if action == "propose":
            desc = ET.SubElement(el, _q(NS_JINGLE, "description"))
            desc.set("media", "video" if session.video else "audio")
        if extra is not None:
            el.append(extra)
        msg.send()
        logger.debug("CALL sent jingle-message %s (%s)", action, session.sid)

    async def _send_session_initiate(self, session: CallSession) -> None:
        call = self.engine.create_call(
            self._ice_servers(), self._devices(),
            on_ice_candidate=lambda cand: self._on_local_candidate(session, cand),
            on_remote_track=lambda *a: self._on_remote_track(session, *a),
            on_state=lambda *a: None)
        session.call = call
        call.add_audio()
        if session.video:
            call.add_video()
        sdp = await call.create_offer()
        contents = jingle_contents_from_sdp(sdp)
        iq = self.client.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        jingle = self._new_jingle("session-initiate", session)
        jingle.set("initiator", session.self_full)
        if session.muji_room:
            muji = ET.SubElement(jingle, _q(NS_MUJI, "muji"))
            muji.set("room", session.muji_room)
        iq.xml.append(jingle)
        for name, desc, transport in contents:
            content = self._content_el(name, desc)
            content.append(build_transport(transport))
            jingle.append(content)
        logger.debug("CALL session-initiate -> %s", session.peer_full)
        await iq.send(timeout=CALL_TIMEOUT)
        session.state = "initiating"
        session.contents = contents
        session.my_transport = contents[0][2] if contents else None

    def _on_local_candidate(self, session: CallSession, cand) -> None:
        logger.debug("CALL local candidate for %s: %s %s:%s", session.sid,
                     getattr(cand, "type", ""), getattr(cand, "host", ""),
                     getattr(cand, "port", ""))
        if session.state in ("accepted", "active"):
            self.client._start_task(self._send_transport_info(session, cand))

    async def _send_transport_info(self, session: CallSession, cand) -> None:
        if session.my_transport is None:
            session.my_transport = IceTransport()
        line = IceCandidate(
            foundation=getattr(cand, "foundation", "") or "0",
            component=getattr(cand, "component", 1),
            protocol=getattr(cand, "protocol", "udp"),
            priority=int(getattr(cand, "priority", 0) or 0),
            ip=getattr(cand, "host", ""), port=int(getattr(cand, "port", 0) or 0),
            type=getattr(cand, "type", "host"))
        session.my_transport.candidates.append(line)
        iq = self.client.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        jingle = self._new_jingle("transport-info", session)
        iq.xml.append(jingle)
        content = ET.SubElement(jingle, _q(NS_JINGLE, "content"))
        content.set("creator", "initiator")
        content.set("name", session.content_name)
        content.append(build_transport(IceTransport(
            ufrag=session.my_transport.ufrag, pwd=session.my_transport.pwd,
            fingerprints=session.my_transport.fingerprints,
            candidates=[line])))
        try:
            await iq.send(timeout=CALL_TIMEOUT)
        except Exception:
            logger.debug("CALL transport-info failed", exc_info=True)

    def _on_remote_track(self, session: CallSession, kind: str,
                         image=None) -> None:
        if kind in ("audio", "video"):
            logger.info("CALL %s track from %s", kind, session.peer_full)
            self.client.emit("call_remote_track", session.sid, kind)
        elif kind == "frame":
            self.client.emit("call_video_frame", session.sid, image)

    # ── incoming ──────────────────────────────────────────────────
    async def dispatch(self, action: str, jingle: ET.Element, iq) -> None:
        sid = jingle.get("sid", "")
        try:
            if action == "session-initiate":
                await self._on_session_initiate(jingle, iq)
            elif action == "session-accept":
                await self._on_session_accept(jingle)
            elif action == "transport-info":
                await self._on_transport_info(jingle)
            elif action == "session-terminate":
                await self._on_session_terminate(jingle)
            elif action == "transport-replace":
                logger.warning("CALL transport-replace unsupported (%s)", sid)
            elif action == "session-info":
                pass
            else:
                logger.debug("CALL unhandled action %s", action)
        except Exception:
            logger.exception("CALL action %s failed", action)

    async def _on_session_initiate(self, jingle: ET.Element, iq) -> None:
        sid = jingle.get("sid", "")
        peer_full = str(iq["from"])
        contents = self._contents_from_jingle(jingle)
        video = any(desc.media == "video" for _n, desc, _t in contents)
        session = CallSession(
            sid=sid, peer_bare=peer_full.split("/")[0], peer_full=peer_full,
            self_full=self._full_jid(), initiator=False, video=video)
        muji_el = jingle.find(_q(NS_MUJI, "muji"))
        if muji_el is not None:
            session.muji_room = muji_el.get("room", "")
        if contents:
            session.peer_transport = contents[0][2]
        self.sessions[sid] = session
        session.contents = contents
        logger.info("CALL incoming from %s (sid=%s video=%s muji=%s)",
                    peer_full, sid, video, session.muji_room)
        if session.muji_room:
            self.client.emit("muji_session", sid, peer_full,
                             session.muji_room)
            self.client._start_task(self.answer_call(sid, True, video))
            return
        self.client.emit("call_incoming", sid, peer_full,
                         "video" if video else "audio")

    async def answer_call(self, sid: str, accept: bool,
                          video: bool = False) -> None:
        session = self.sessions.get(sid)
        if session is None:
            return
        if not accept:
            await self._decline(session)
            return
        if not self.available:
            self.client.emit("call_failed", session.peer_full,
                             "media engine unavailable")
            await self._decline(session)
            return
        session.video = video or session.video
        try:
            await self._accept(session)
        except Exception as exc:
            logger.exception("CALL accept failed")
            self.client.emit("call_failed", session.peer_full, str(exc))
            self._terminate(session, "connectivity-error", send=True)

    async def _accept(self, session: CallSession) -> None:
        # Build a remote offer SDP from the stored peer transport/descriptions.
        offer = sdp_from_jingle(self._stored_contents(session), session.sid)
        call = self.engine.create_call(
            self._ice_servers(), self._devices(),
            on_ice_candidate=lambda cand: self._on_local_candidate(session, cand),
            on_remote_track=lambda *a: self._on_remote_track(session, *a),
            on_state=lambda *a: None)
        session.call = call
        await call.set_remote(offer, "offer")
        call.add_audio()
        if session.video:
            call.add_video()
        answer = await call.create_answer()
        contents = jingle_contents_from_sdp(answer)
        iq = self.client.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        jingle = self._new_jingle("session-accept", session)
        jingle.set("responder", session.self_full)
        iq.xml.append(jingle)
        for name, desc, transport in contents:
            content = self._content_el(name, desc)
            content.append(build_transport(transport))
            jingle.append(content)
        session.state = "accepted"
        session.my_transport = contents[0][2] if contents else None
        logger.info("CALL session-accept -> %s", session.peer_full)
        await iq.send(timeout=CALL_TIMEOUT)
        self.client.emit("call_state", session.sid, session.peer_full,
                         "active")

    async def _decline(self, session: CallSession) -> None:
        session.state = "declined"
        await self._send_jingle_message("reject", session)
        self._terminate(session, "decline", send=True)

    async def _on_session_accept(self, jingle: ET.Element) -> None:
        session = self.sessions.get(jingle.get("sid", ""))
        if session is None:
            return
        contents = self._contents_from_jingle(jingle)
        session.state = "accepted"
        logger.info("CALL session-accept from %s", session.peer_full)
        if session.call is not None and contents:
            try:
                answer = sdp_from_jingle(contents, session.sid)
                await session.call.set_remote(answer, "answer")
            except Exception:
                logger.exception("CALL set_remote(answer) failed")
        self.client.emit("call_state", session.sid, session.peer_full, "active")

    async def _on_transport_info(self, jingle: ET.Element) -> None:
        session = self.sessions.get(jingle.get("sid", ""))
        if session is None or session.call is None:
            return
        content = jingle.find(_q(NS_JINGLE, "content"))
        if content is None:
            return
        tel = content.find(_q(NS_ICE, "transport"))
        if tel is None:
            return
        transport = parse_transport(tel)
        for cand in transport.candidates:
            await session.call.add_ice(_candidate_to_sdp(cand))
        logger.debug("CALL transport-info: %d candidate(s)", len(transport.candidates))

    async def _on_session_terminate(self, jingle: ET.Element) -> None:
        session = self.sessions.get(jingle.get("sid", ""))
        if session is None:
            return
        reason = self._reason(jingle)
        logger.info("CALL terminated by peer: %s (%s)", session.sid, reason)
        self._close_session(session, "ended", reason)

    # ── jingle-message (XEP-0353) ─────────────────────────────────
    def handle_message(self, msg) -> bool:
        for action in ("propose", "proceed", "retract", "reject", "accept"):
            el = msg.xml.find(_q(NS_JINGLE_MSG, action))
            if el is None:
                continue
            sid = el.get("id", "")
            frm = str(msg["from"]).split("/")[0]
            logger.info("CALL jingle-message %s from %s (sid=%s)", action, frm,
                        sid)
            if action == "propose":
                self.client.emit("call_proposed", sid, frm,
                                 self._propose_media(el))
            elif action == "proceed":
                future = getattr(self, "_proceed_futures", {}).pop(sid, None)
                if future is not None and not future.done():
                    future.set_result(True)
            elif action in ("reject", "retract"):
                session = self.sessions.get(sid)
                if session is not None:
                    self._close_session(session, "ended", action)
            return True
        return False

    @staticmethod
    def _propose_media(el: ET.Element) -> str:
        desc = el.find(_q(NS_JINGLE, "description"))
        if desc is not None and desc.get("media") == "video":
            return "video"
        return "audio"

    # ── parse/build helpers ───────────────────────────────────────
    def _contents_from_jingle(self, jingle: ET.Element) -> list:
        contents = []
        for content in jingle.findall(_q(NS_JINGLE, "content")):
            name = content.get("name", "")
            desc_el = content.find(_q(NS_RTP, "description"))
            transport_el = content.find(_q(NS_ICE, "transport"))
            if desc_el is None:
                continue
            desc = parse_description(desc_el)
            transport = parse_transport(transport_el) if transport_el is not None else IceTransport()
            contents.append((name, desc, transport))
        return contents

    def _stored_contents(self, session: CallSession) -> list:
        if session.contents:
            return session.contents
        return [(session.content_name, RtpDescription("audio", [], []),
                 session.peer_transport or IceTransport())]

    def _content_el(self, name: str, desc: RtpDescription) -> ET.Element:
        el = ET.Element(_q(NS_JINGLE, "content"))
        el.set("creator", "initiator")
        el.set("name", name)
        el.set("senders", "both")
        el.append(build_description(desc))
        return el

    def _new_jingle(self, action: str, session: CallSession) -> ET.Element:
        return ET.Element(_q(NS_JINGLE, "jingle"),
                          {"action": action, "sid": session.sid})

    @staticmethod
    def _reason(jingle: ET.Element) -> str:
        reason = jingle.find(_q(NS_JINGLE, "reason"))
        if reason is None or len(reason) == 0:
            return ""
        return reason[0].tag.rsplit("}", 1)[-1]

    # ── termination ───────────────────────────────────────────────
    async def end_call(self, sid: str) -> None:
        session = self.sessions.get(sid)
        if session is not None:
            self._terminate(session, "success", send=True)
            self._close_session(session, "ended", "hangup")

    def _terminate(self, session: CallSession, reason: str,
                   send: bool = False) -> None:
        if send and session.sid in self.sessions:
            iq = self.client.xmpp.Iq()
            iq["type"] = "set"
            iq["to"] = session.peer_full
            jingle = self._new_jingle("session-terminate", session)
            iq.xml.append(jingle)
            rel = ET.SubElement(jingle, _q(NS_JINGLE, "reason"))
            ET.SubElement(rel, _q(NS_JINGLE, reason or "success"))
            try:
                iq.send()
            except Exception:
                logger.debug("CALL session-terminate send failed", exc_info=True)
        session.state = "ended"

    def _close_session(self, session: CallSession, state: str,
                       reason: str = "") -> None:
        if session.call is not None:
            try:
                session.call.close()
            except Exception:
                logger.debug("CALL close failed", exc_info=True)
            session.call = None
        self.sessions.pop(session.sid, None)
        self.client.emit("call_ended", session.sid, session.peer_full, reason)

    def close(self) -> None:
        for session in list(self.sessions.values()):
            self._close_session(session, "ended", "shutdown")

    # ── Muji (XEP-0272) helpers ───────────────────────────────────
    def end_muji(self, room: str) -> None:
        for session in list(self.sessions.values()):
            if session.muji_room == room:
                logger.info("MUJI ending session %s", session.sid)
                self._terminate(session, "success", send=True)
                self._close_session(session, "ended", "muji-leave")

    def add_muji_content(self, room: str, name: str, media: str) -> None:
        for session in list(self.sessions.values()):
            if session.muji_room == room:
                self.client._start_task(
                    self._send_content_action("content-add", session, name,
                                              media))

    def remove_muji_content(self, room: str, name: str) -> None:
        for session in list(self.sessions.values()):
            if session.muji_room == room:
                self.client._start_task(
                    self._send_content_action("content-remove", session, name,
                                              ""))

    async def _send_content_action(self, action: str, session: CallSession,
                                   name: str, media: str) -> None:
        iq = self.client.xmpp.Iq()
        iq["type"] = "set"
        iq["to"] = session.peer_full
        jingle = self._new_jingle(action, session)
        iq.xml.append(jingle)
        content = ET.SubElement(jingle, _q(NS_JINGLE, "content"))
        content.set("creator", "initiator")
        content.set("name", name)
        if media:
            desc = ET.SubElement(content, _q(NS_RTP, "description"))
            desc.set("media", media)
        try:
            await iq.send(timeout=CALL_TIMEOUT)
        except Exception:
            logger.debug("MUJI %s failed", action, exc_info=True)


def is_rtp_jingle(jingle: ET.Element) -> bool:
    """True when a Jingle stanza carries RTP/ICE (i.e. an A/V call)."""
    for el in jingle.iter():
        tag = el.tag
        if tag in (_q(NS_RTP, "description"), _q(NS_ICE, "transport")):
            return True
    return False
