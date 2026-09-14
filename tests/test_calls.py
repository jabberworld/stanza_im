"""Offscreen tests for Jingle RTP calls, XEP-0215 and Muji.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_calls.py
"""
import asyncio
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_calls_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

import slixmpp

from stanza_im.core import discovery
from stanza_im.core.client import JabberClient
from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.xmpp import jingle_rtp as jr
from stanza_im.xmpp import muji

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── 1. RTP/ICE/DTLS XML round-trip ----------------------------------------
desc = jr.RtpDescription("audio", [
    jr.PayloadType(111, "opus", 48000, 2),
    jr.PayloadType(101, "telephone-event", 8000, 0)])
desc.sources.append(jr.RtpSource(12345, {"cname": "abc"}))
parsed = jr.parse_description(jr.build_description(desc))
check("rtp description round-trip",
      parsed.media == "audio" and parsed.payloads[0].name == "opus"
      and parsed.payloads[0].channels == 2
      and parsed.sources[0].ssrc == 12345)

transport = jr.IceTransport(
    ufrag="uf", pwd="pw",
    fingerprints=[jr.DtlsFingerprint("sha-256", "AA:BB", "actpass")],
    candidates=[jr.IceCandidate("f1", 1, "udp", 123, "10.0.0.1", 5000,
                                "host")])
tp = jr.parse_transport(jr.build_transport(transport))
check("ice transport round-trip",
      tp.ufrag == "uf" and tp.pwd == "pw"
      and tp.fingerprints[0].value == "AA:BB"
      and tp.candidates[0].ip == "10.0.0.1"
      and tp.candidates[0].type == "host")
check("ice transport xml has no mode attr",
      "mode" not in jr.build_transport(transport).attrib)

# parse_sdp must strip the attribute prefix exactly (off-by-one regression:
# the credentials must not keep a leading ':').
_sample_sdp = (
    "v=0\r\n"
    "m=audio 9 UDP/TLS/RTP/SAVPF 96\r\n"
    "a=mid:0\r\n"
    "a=ice-ufrag:abc123\r\n"
    "a=ice-pwd:secretpwd\r\n"
    "a=setup:actpass\r\n"
    "a=fingerprint:sha-256 AA:BB:CC\r\n"
)
_parsed = jr.parse_sdp(_sample_sdp)[0]["transport"]
check("parse_sdp ufrag/pwd without leading colon",
      _parsed.ufrag == "abc123" and _parsed.pwd == "secretpwd")
check("parse_sdp setup", _parsed.fingerprints[0].setup == "actpass")

# ── 2. SDP ↔ Jingle bridge with real aiortc peers -------------------------
try:
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.mediastreams import AudioStreamTrack
    HAS_AIORTC = True
except Exception:
    HAS_AIORTC = False


async def _sdp_roundtrip():
    pc1 = RTCPeerConnection()
    pc1.addTrack(AudioStreamTrack())
    await pc1.setLocalDescription(await pc1.createOffer())
    offer_sdp = pc1.localDescription.sdp
    contents = jr.jingle_contents_from_sdp(offer_sdp)
    # Credentials must survive parse→build without a leading ':'
    import re as _re
    orig_ufrag = _re.search(r"a=ice-ufrag:(\S+)", offer_sdp).group(1)
    if contents[0][2].ufrag != orig_ufrag:
        raise AssertionError("ufrag corrupted: %r != %r"
                             % (contents[0][2].ufrag, orig_ufrag))
    rebuilt = jr.sdp_from_jingle(contents, "sid1")
    pc2 = RTCPeerConnection()
    await pc2.setRemoteDescription(RTCSessionDescription(rebuilt, "offer"))
    pc2.addTrack(AudioStreamTrack())
    await pc2.setLocalDescription(await pc2.createAnswer())
    contents2 = jr.jingle_contents_from_sdp(pc2.localDescription.sdp)
    rebuilt2 = jr.sdp_from_jingle(contents2, "sid2")
    await pc1.setRemoteDescription(RTCSessionDescription(rebuilt2, "answer"))
    await pc1.close()
    await pc2.close()
    return contents[0]


if HAS_AIORTC:
    ok = False
    try:
        c0 = asyncio.run(_sdp_roundtrip())
        ok = True
    except Exception as exc:
        print("  sdp roundtrip error:", exc)
    check("SDP<->Jingle round-trip accepted by aiortc", ok)
    if ok:
        check("round-trip keeps ICE credentials",
              ":" not in c0[2].ufrag and ":" not in c0[2].pwd)
else:
    check("SDP<->Jingle round-trip accepted by aiortc (skipped)", True)

# ── 3. is_rtp_jingle ------------------------------------------------------
j = ET.Element("{%s}jingle" % jr.NS_JINGLE)
content = ET.SubElement(j, "{%s}content" % jr.NS_JINGLE)
ET.SubElement(content, "{%s}description" % jr.NS_RTP)
check("is_rtp_jingle detects RTP", jr.is_rtp_jingle(j))
ft = ET.Element("{%s}jingle" % jr.NS_JINGLE)
ET.SubElement(ft, "{%s}s5b" % "urn:xmpp:jingle:transports:s5b:1")
check("is_rtp_jingle ignores file transfer", not jr.is_rtp_jingle(ft))

# ── 3a. multi-content SDP: ICE/DTLS per media section ---------------------
_shared = jr.IceTransport(
    ufrag="uf", pwd="pw",
    fingerprints=[jr.DtlsFingerprint("sha-256", "AA:BB", "actpass")])
_multi = jr.sdp_from_jingle(
    [("0", jr.RtpDescription("video", [jr.PayloadType(97, "VP8", 90000, 0)]),
      _shared),
     ("1", jr.RtpDescription("audio", [jr.PayloadType(111, "opus", 48000, 2)]),
      _shared)], "sid")
_sections = _multi.split("m=")[1:]
check("ICE credentials in every media section",
      len(_sections) == 2 and all("a=ice-ufrag:uf" in ("m=" + s)
                                  for s in _sections))
if HAS_AIORTC:
    async def _multi_accept():
        pc = RTCPeerConnection()
        try:
            await pc.setRemoteDescription(RTCSessionDescription(_multi, "offer"))
            await pc.createAnswer()
            return True
        finally:
            await pc.close()

    try:
        _multi_ok = asyncio.run(_multi_accept())
    except Exception as exc:
        _multi_ok = False
        print("  multi-content sdp error:", exc)
    check("multi-content SDP accepted by aiortc", _multi_ok)

# ── 3b. camera failure degrades gracefully (no traceback) -----------------
from stanza_im.xmpp import media as media_mod
if media_mod.HAS_AIORTC and media_mod.av is not None:
    _cam = media_mod._VideoCaptureTrack("/dev/video_does_not_exist_xyz")
    check("camera open failure degrades to black frames",
          _cam._container is None)
    _cam.stop()

# ── 4. XEP-0215 normalisation ---------------------------------------------
servers = discovery.ice_servers_from_services([
    {"type": "stun", "host": "s.example", "port": 3478, "transport": "udp"},
    {"type": "turn", "host": "t.example", "port": 443, "transport": "udp",
     "username": "u", "password": "p"},
    {"type": "turn", "host": "t.example", "port": 443, "transport": "tcp",
     "username": "u", "password": "p"},
    {"type": "stun", "host": "s.example", "port": 3478, "transport": "tcp"},
    {"type": "stun", "host": "2a07:c801::", "port": 3478, "transport": "udp"},
])
check("extdisco normalisation (IPv6/transport filtered)",
      servers == [{"urls": "stun:s.example:3478"},
                  {"urls": "turn:t.example:443?transport=udp",
                   "username": "u", "credential": "p"}])

# ── 5. client.ice_servers() priority --------------------------------------
client = JabberClient("me@example.com/res", "pw")
client._discovered = {"ice_services": [
    {"type": "turn", "host": "relay.example", "port": 3478,
     "transport": "udp", "username": "x", "password": "y"}]}
check("ice_servers uses XEP-0215",
      client.ice_servers()[0]["urls"] == "turn:relay.example:3478?transport=udp")
client._discovered = {"ice_services": [], "stun_turn": []}
client.stun_turn_mode = "manual"
client.stun_turn_manual = "stun.example:3478"
check("ice_servers falls back to manual",
      client.ice_servers()[0]["urls"] == "stun:stun.example:3478")

# ── 6. call gating (XEP-0115 caps) ----------------------------------------
features = {"urn:xmpp:jingle:1", "urn:xmpp:jingle:transports:ice-udp:1",
            "urn:xmpp:jingle:apps:rtp:1", "urn:xmpp:jingle:apps:dtls:0",
            "urn:xmpp:jingle:apps:rtp:audio"}
client.contact_features = {"bob@example.com/phone": set(features)}
check("supports audio calls", client.supports_calls("bob@example.com"))
check("no video without feature",
      not client.supports_calls("bob@example.com", video=True))
check("unknown contact unsupported",
      not client.supports_calls("alice@example.com"))

# ── 7. chat widget call menu gating ---------------------------------------
cw = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
check("call menu present",
      cw._call_btn is not None and not cw._call_btn.isEnabled())
cw.set_call_support(True, True)
actions = [a.text() for a in cw._call_btn.menu().actions()]
check("call menu items", cw._call_btn.isEnabled()
      and any(a.startswith("Audio") for a in actions)
      and any(a.startswith("Video") for a in actions))
cw.set_call_support(False, False)
check("call menu disabled again", not cw._call_btn.isEnabled())

# ── 8. call window + incoming dialog --------------------------------------
from stanza_im.ui.call_window import CallWindow, IncomingCallDialog
win = CallWindow("sid1", "bob@example.com", video=True)
check("call window", win.sid == "sid1" and win._video_view is not None)
win.close()
dlg = IncomingCallDialog("bob@example.com", "video")
decisions = []
dlg.decision.connect(lambda a, v: decisions.append((a, v)))
dlg._on_accept()
check("incoming dialog accept", decisions == [(True, True)])
dlg.close()

# ── 9. Muji presence + invites --------------------------------------------
pres = slixmpp.Presence()
pres["from"] = "room@conf.example/Alice"
pres["to"] = "me@example.com/res"
pres["type"] = "available"
muji_el = ET.SubElement(pres.xml, "{%s}muji" % muji.NS_MUJI)
content = ET.SubElement(muji_el, "{%s}content" % muji.NS_MUJI)
content.set("name", "voice")
desc_el = ET.SubElement(content, "{%s}description" % muji.NS_RTP)
desc_el.set("media", "audio")
client.muji.handle_presence(pres)
conf = client.muji.conferences.get("room@conf.example")
check("muji presence parsed",
      conf is not None and conf.participants["Alice"].contents == {"voice": "audio"})

inv = slixmpp.Message()
inv["from"] = "bob@example.com/phone"
inv["type"] = "chat"
invitel = ET.SubElement(inv.xml, "{%s}invite" % muji.NS_CALL_INVITES)
muji_inv = ET.SubElement(invitel, "{%s}muji" % muji.NS_MUJI)
muji_inv.set("room", "room@conf.example")
captured = []
client.on("muji_invite", lambda *a: captured.append(a))
check("muji invite parsed", client.muji.handle_invite_message(inv)
      and captured == [("bob@example.com", "room@conf.example")])

# ── 10. XEP-0353 bodyless messages ---------------------------------------
from slixmpp.xmlstream.matcher.xpath import MatchXPath

propose_msg = slixmpp.Message()
propose_msg["from"] = "bob@example.com/phone"
propose_msg["type"] = "chat"
propose_el = ET.SubElement(
    propose_msg.xml, "{%s}propose" % jr.NS_JINGLE_MSG)
propose_el.set("id", "sid42")
ET.SubElement(propose_el, "{%s}description" % jr.NS_RTP).set("media", "audio")
matcher = MatchXPath("{jabber:client}message/{urn:xmpp:jingle-message:0}*")
check("bodyless jingle-message matcher", matcher.match(propose_msg))

call_client = JabberClient("me@example.com/res", "pw")
proposed = []
call_client.on("call_proposed", lambda *a: proposed.append(a))
call_client.rtp_calls.handle_message(propose_msg)
check("incoming propose handled",
      proposed == [("sid42", "bob@example.com/phone", "audio")])

proceeded = []


async def _fake_action(action, to_jid, sid, video=False, extra=None):
    proceeded.append((action, to_jid, sid))


async def _noop(_sid):
    return None


call_client.rtp_calls._send_message_action = _fake_action
call_client.rtp_calls._proceed_session_timeout = _noop


async def _answer():
    call_client.rtp_calls.answer_proposal("sid42", True, False)
    await asyncio.sleep(0)


asyncio.run(_answer())
check("proceed sent to full JID on accept",
      proceeded == [("proceed", "bob@example.com/phone", "sid42")])
check("session marked proceeded",
      "sid42" in call_client.rtp_calls._proceeded)


# propose builder uses the RTP namespace + both media
captured_xml = []


class _FakeMessage:
    def __init__(self):
        self.xml = ET.Element("{jabber:client}message")

    def __setitem__(self, key, value):
        pass

    def send(self):
        captured_xml.append(self.xml)


call_client.xmpp.Message = _FakeMessage
builder_client = JabberClient("me@example.com/res", "pw")
builder_client.xmpp.Message = _FakeMessage


async def _send_propose():
    await builder_client.rtp_calls._send_message_action(
        "propose", "bob@example.com", "sidX", video=True)


asyncio.run(_send_propose())
descs = [(el.get("media"), el.tag)
         for el in captured_xml[0].iter("{%s}description" % jr.NS_RTP)]
check("propose uses rtp ns with audio+video",
      descs == [("audio", "{%s}description" % jr.NS_RTP),
                ("video", "{%s}description" % jr.NS_RTP)])
check("jingle-message carries XEP-0334 store hint",
      captured_xml[0].find("{urn:xmpp:hints}store") is not None)


# proceed updates the outgoing session's target resource ------------------
async def _proceed_session():
    session = jr.CallSession(
        sid="sidP", peer_bare="bob@example.com",
        peer_full="bob@example.com/wrong", self_full="me@example.com/res",
        initiator=True, content_name="voice")
    client2 = JabberClient("me@example.com/res", "pw")
    client2.rtp_calls.sessions["sidP"] = session
    msg = slixmpp.Message()
    msg["from"] = "bob@example.com/phone"
    msg["type"] = "chat"
    el = ET.SubElement(msg.xml, "{%s}proceed" % jr.NS_JINGLE_MSG)
    el.set("id", "sidP")
    client2.rtp_calls.handle_message(msg)
    return session.peer_full


check("proceed selects the accepting resource",
      asyncio.run(_proceed_session()) == "bob@example.com/phone")

# ── 11. config defaults ---------------------------------------------------
cfg = Config()
check("devices defaults",
      cfg.devices.audio_input == "" and cfg.devices.video_input == ""
      and cfg.calls.auto_accept is False)

print("\nAll tests passed" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
