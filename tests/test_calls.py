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

from PyQt6 import QtGui, QtWidgets

import slixmpp

from stanza_im.core import discovery
from stanza_im.core.client import JabberClient
from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.main_window import MainWindow
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
    from aiortc import (RTCPeerConnection, RTCSessionDescription,
                        RTCIceCandidate)
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
check("no premature a=end-of-candidates (trickle)",
      "end-of-candidates" not in _multi)
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

    async def _trickle_after_offer():
        pc = RTCPeerConnection()
        try:
            _tr = jr.IceTransport(
                ufrag="uf", pwd="pw",
                fingerprints=[jr.DtlsFingerprint("sha-256", "AA:BB",
                                                "actpass")])
            _desc = jr.RtpDescription(
                "audio", [jr.PayloadType(111, "opus", 48000, 2)])
            _offer = jr.sdp_from_jingle([("0", _desc, _tr)], "sid")
            await pc.setRemoteDescription(RTCSessionDescription(_offer, "offer"))
            await pc.createAnswer()
            cand = RTCIceCandidate(
                component=1, foundation="1", ip="127.0.0.1", port=5000,
                priority=1, protocol="udp", type="host", sdpMid="0",
                sdpMLineIndex=0)
            await pc.addIceCandidate(cand)
            return True
        finally:
            await pc.close()

    try:
        _trickle_ok = asyncio.run(_trickle_after_offer())
    except Exception as exc:
        _trickle_ok = False
        print("  trickle error:", exc)
    check("trickled candidate accepted after setRemoteDescription", _trickle_ok)

# ── 3d. media-description fidelity (rtcp-mux/trickle/fmtp/fb/hdrext) ------
_fid_sdp = (
    "v=0\r\n"
    "m=audio 9 UDP/TLS/RTP/SAVPF 96 97\r\n"
    "a=mid:0\r\n"
    "a=rtcp-mux\r\n"
    "a=rtpmap:96 opus/48000/2\r\n"
    "a=fmtp:96 minptime=10;useinbandfec=1\r\n"
    "a=rtcp-fb:96 nack\r\n"
    "a=extmap:1 urn:ietf:params:rtp-hdrext:ssrc-audio-level\r\n"
    "a=ssrc:1111 cname:abc\r\n"
    "a=ssrc:2222 cname:abc\r\n"
    "a=ssrc-group:FID 1111 2222\r\n"
    "a=msid:stream1 track1\r\n"
)
_fid = jr.parse_sdp(_fid_sdp)[0]["desc"]
check("parse_sdp rtcp-mux", _fid.rtcp_mux)
_fid_opus = next(p for p in _fid.payloads if p.id == 96)
check("parse_sdp fmtp parameters",
      _fid_opus.parameters.get("minptime") == "10"
      and _fid_opus.parameters.get("useinbandfec") == "1")
check("parse_sdp rtcp-fb", ("nack", "") in _fid_opus.rtcp_fb)
check("parse_sdp extmap", _fid.rtp_hdrext == [
    (1, "urn:ietf:params:rtp-hdrext:ssrc-audio-level")])
check("parse_sdp ssrc-group", _fid.ssrc_groups == [("FID", [1111, 2222])])
check("parse_sdp msid", _fid.msid == "stream1 track1")

_bd = jr.RtpDescription(
    "audio",
    [jr.PayloadType(96, "opus", 48000, 2, {"minptime": "10"},
                    [("nack", "pli")])],
    [jr.RtpSource(1111, {"cname": "abc"})],
    rtcp_mux=True, ssrc_groups=[("FID", [1111, 2222])],
    rtp_hdrext=[(1, "urn:ietf:params:rtp-hdrext:ssrc-audio-level")])
_bd_el = jr.build_description(_bd)
check("build_description emits rtcp-mux",
      _bd_el.find("{%s}rtcp-mux" % jr.NS_RTP) is not None)
check("build_description emits rtcp-fb",
      _bd_el.find(".//{%s}rtcp-fb" % jr.NS_RTP_FB) is not None)
check("build_description emits rtp-hdrext",
      _bd_el.find("{%s}rtp-hdrext" % jr.NS_RTP_HDREXT) is not None)
check("build_description emits ssrc-group",
      _bd_el.find("{%s}ssrc-group" % jr.NS_RTP_SSMA) is not None)
_bd_rt = jr.parse_description(_bd_el)
check("rtcp-mux/fb/hdrext/ssrc-group round-trip",
      _bd_rt.rtcp_mux
      and _bd_rt.payloads[0].rtcp_fb == [("nack", "pli")]
      and _bd_rt.rtp_hdrext == [(1, "urn:ietf:params:rtp-hdrext:ssrc-audio-level")]
      and _bd_rt.ssrc_groups == [("FID", [1111, 2222])])

check("transport advertises trickle option",
      jr.build_transport(transport).find(
          "{%s}trickle" % jr.NS_ICE_OPTION) is not None)

_bj = ET.Element("{%s}jingle" % jr.NS_JINGLE)
jr.JingleRtpManager._append_bundle(_bj, [("0", None, None), ("1", None, None)])
_grp = _bj.find("{%s}group" % jr.NS_GROUPING)
check("BUNDLE group advertised",
      _grp is not None and _grp.get("semantics") == "BUNDLE"
      and [c.get("name") for c in _grp] == ["0", "1"])

if HAS_AIORTC:
    async def _offer_contents():
        pc = RTCPeerConnection()
        try:
            pc.addTrack(AudioStreamTrack())
            await pc.setLocalDescription(await pc.createOffer())
            return jr.jingle_contents_from_sdp(pc.localDescription.sdp)
        finally:
            await pc.close()

    _oc = asyncio.run(_offer_contents())
    check("aiortc offer -> Jingle advertises rtcp-mux",
          bool(_oc) and _oc[0][1].rtcp_mux)
    _opus_p = next((p for p in _oc[0][1].payloads if p.name == "opus"), None)
    check("aiortc offer -> opus payload has fmtp",
          _opus_p is not None and bool(_opus_p.parameters))

# ── 3e. audio encode pipeline / resampler compatibility -------------------
from stanza_im.xmpp import media as media_mod
_enc_ok, _enc_detail = media_mod.audio_encode_selftest()
check("audio encode self-test passes", _enc_ok)
if not _enc_ok:
    print("  audio encode error:", _enc_detail)

if media_mod.HAS_AIORTC:
    from fractions import Fraction
    from aiortc.codecs.opus import OpusEncoder as _OpusEncoder
    from aiortc.codecs.g711 import PcmEncoder as _PcmEncoder
    from aiortc.codecs.g722 import G722Encoder as _G722Encoder
    _enc = _OpusEncoder()
    _f = media_mod._silence(media_mod.AUDIO_SAMPLES_PER_FRAME, 2)
    _f.pts = 0
    _f.time_base = Fraction(1, media_mod.AUDIO_RATE)
    check("matching audio frame matches the encoder resampler",
          media_mod._frame_matches_resampler(_f, _enc.resampler))
    check("decode_ffmpeg_error unwraps UnicodeDecodeError",
          media_mod.decode_ffmpeg_error(
              UnicodeDecodeError("ascii", b"\xd0\x9d", 0, 1, "bad")
          ).startswith("\u041d"))
    check("PyAV AudioResampler is left untouched",
          not getattr(media_mod.av.AudioResampler, "_stanza_patched", False))
    check("aiortc audio encoders patched",
          _OpusEncoder._stanza_patched and _PcmEncoder._stanza_patched
          and _G722Encoder._stanza_patched)
    check("passthrough resampler yields the frame",
          media_mod._PassthroughResampler().resample(_f) == [_f])

    class _SpyResampler:
        def __init__(self, target):
            self._target = target
            self.calls = 0

        def __getattr__(self, name):
            if name in ("format", "layout", "rate", "frame_size"):
                return getattr(self._target, name)
            raise AttributeError(name)

        def resample(self, frame):
            self.calls += 1
            return [frame]

    _spy = _SpyResampler(_enc.resampler)
    _enc.resampler = _spy
    _enc.encode(_f)
    check("matching frame skips the encoder resampler", _spy.calls == 0)

# ── 3b. camera failure degrades gracefully (no traceback) -----------------
from stanza_im.xmpp import media as media_mod
if media_mod.HAS_AIORTC and media_mod.av is not None:
    _cam = media_mod._VideoCaptureTrack("/dev/video_does_not_exist_xyz")
    check("camera open failure degrades to black frames",
          _cam._container is None)
    _cam.stop()

# ── 3c. captured audio frames carry a usable pts --------------------------
if media_mod.HAS_AIORTC and media_mod.av is not None:
    async def _audio_frames():
        track = media_mod._AudioCaptureTrack("")
        try:
            from aiortc.codecs.opus import OpusEncoder
            encoder = OpusEncoder()
        except Exception:
            encoder = None
        first = await track.recv()
        second = await track.recv()
        monotonic = (first.pts is not None and second.pts is not None
                     and second.pts > first.pts)
        stereo = (first.layout.name == "stereo"
                  and first.samples == media_mod.AUDIO_SAMPLES_PER_FRAME)
        encode_ok = True
        if encoder is not None:
            try:
                encoder.encode(first)
                encoder.encode(second)
            except Exception as exc:
                encode_ok = False
                print("  opus encode error:", exc)
        track.stop()
        return monotonic, stereo, encode_ok

    _mono_ok, _stereo_ok, _encode_ok = asyncio.run(_audio_frames())
    check("captured audio frames have monotonic pts", _mono_ok)
    check("captured audio frames are stereo 20ms",
          _stereo_ok)
    check("Opus encoder accepts captured frames", _encode_ok)

    async def _recv_after_stop():
        track = media_mod._AudioCaptureTrack("")
        track.stop()
        frame = await track.recv()   # must not touch the stopped device
        return frame is not None and frame.pts is not None

    try:
        _stopped_ok = asyncio.run(_recv_after_stop())
    except Exception as exc:
        _stopped_ok = False
        print("  recv-after-stop error:", exc)
    check("recv after stop returns a frame (no teardown traceback)", _stopped_ok)

    async def _video_recv_after_stop():
        track = media_mod._VideoCaptureTrack("/dev/video_does_not_exist_xyz")
        track.stop()
        frame = await track.recv()
        return frame is not None and frame.pts is not None

    try:
        _vstopped_ok = asyncio.run(_video_recv_after_stop())
    except Exception as exc:
        _vstopped_ok = False
        print("  video recv-after-stop error:", exc)
    check("video recv after stop returns a frame", _vstopped_ok)

# ── 3d. mute/camera toggles mute capture (silence/black) -------------------
if media_mod.HAS_AIORTC and media_mod.av is not None:
    class _FakeIO:
        def __init__(self, payload: bytes):
            self.payload = payload
            self.read_calls = 0

        def read(self, n):
            self.read_calls += 1
            if not self.payload:
                return b""
            chunk, self.payload = self.payload[:n], self.payload[n:]
            return chunk

    _AUDIO_BYTES = (media_mod.AUDIO_SAMPLES_PER_FRAME
                    * media_mod.AUDIO_CHANNELS * 2)

    async def _muted_audio_never_reads_io():
        track = media_mod._AudioCaptureTrack("")
        track._io = _FakeIO(b"\x00" * _AUDIO_BYTES)
        track._enabled = False
        frame = await track.recv()
        return (track._io.read_calls == 0
                and frame is not None and frame.pts is not None)

    check("muted microphone sends silence without reading the device",
          asyncio.run(_muted_audio_never_reads_io()))

    async def _enabled_audio_reads_io():
        track = media_mod._AudioCaptureTrack("")
        io = _FakeIO(b"\x55" * _AUDIO_BYTES)
        track._io = io
        track._enabled = True
        frame = await track.recv()
        return io.read_calls > 0 and frame is not None

    check("unmuted microphone reads the device again",
          asyncio.run(_enabled_audio_reads_io()))

    class _FakeStream:
        pass

    class _FakeVideoContainer:
        streams = type("_S", (), {"video": [_FakeStream()]})()

        def __init__(self):
            self.decode_calls = 0

        def decode(self, stream):
            self.decode_calls += 1
            frame = media_mod.av.VideoFrame(160, 120, "yuv420p")
            for plane in frame.planes:
                plane.update(b"\x55" * plane.buffer_size)
            yield frame

        def close(self):
            pass

    async def _video_toggle_behavior():
        track = media_mod._VideoCaptureTrack("/dev/video_does_not_exist_xyz")
        container = _FakeVideoContainer()
        track._container = container
        track._stream = container.streams.video[0]
        track._enabled = False
        off_frame = await track.recv()
        off_ok = (off_frame is not None and off_frame.pts is not None
                  and container.decode_calls == 0)
        track._enabled = True
        on_frame = await track.recv()
        on_ok = (on_frame is not None and on_frame.pts is not None
                 and container.decode_calls > 0)
        return off_ok, on_ok

    try:
        _vb = asyncio.run(_video_toggle_behavior())
    except Exception as exc:
        _vb = (False, False)
        print("  video toggle error:", exc)
    check("camera off sends a muted frame without touching the device",
          _vb[0])
    check("camera on resumes real capture", _vb[1])

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

# ── 7b. MUC chat widget Muji call menu gating ------------------------------
cmuc = ChatWidget("room@conf.example", "Room", chat_themes.ChatThemeFactory(),
                  is_muc=True)
check("muc muji button gated off by default",
      cmuc._call_btn is not None and not cmuc._call_btn.isEnabled()
      and cmuc._call_btn.toolTip() == "Conference call")
# Muji support is a single aiortc-enabled switch, not per-capability.
cmuc.set_muji_support(True)
check("muc muji menu enabled by support switch",
      cmuc._call_btn.isEnabled()
      and cmuc._call_audio_action.isEnabled()
      and cmuc._call_video_action.isEnabled())
# On a MUC tab the call menu emits muji_call_requested, never call_requested.
muji_requests, call_requests = [], []
cmuc.muji_call_requested.connect(
    lambda jid, video: muji_requests.append((jid, video)))
cmuc.call_requested.connect(lambda jid, video: call_requests.append((jid, video)))
cmuc._call_audio_action.trigger()
check("muc audio menu emits muji_call_requested",
      muji_requests == [("room@conf.example", False)] and not call_requests)
cmuc._call_video_action.trigger()
check("muc video menu emits muji_call_requested",
      muji_requests == [("room@conf.example", False),
                        ("room@conf.example", True)] and not call_requests)
cmuc.set_muji_support(False)
check("muc muji menu disabled again", not cmuc._call_btn.isEnabled())
# set_muji_support is a no-op on 1:1 widgets.
cw.set_muji_support(True)
check("muji support ignored on 1:1 widget", not cw._call_btn.isEnabled())

from stanza_im.ui.chat_window import ChatWindow


def _chat_window_muji_result():
    cw6 = ChatWindow(chat_themes.ChatThemeFactory())
    muc_tab = cw6.open_groupchat("room@conf.example", "me", "Room")
    cw6.set_muji_support("room@conf.example", True)
    enabled = muc_tab._call_btn.isEnabled()
    reqs = []
    cw6.muji_call_requested.connect(
        lambda jid, video: reqs.append((jid, video)))
    muc_tab._call_video_action.trigger()
    cw6.close_chat("room@conf.example")
    return enabled, reqs


_support_ok, _cw_reqs = _chat_window_muji_result()
check("chat window muji support reaches muc tab", _support_ok)
check("chat window forwards muji_call_requested",
      _cw_reqs == [("room@conf.example", True)])

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

# ── 10a. controlled ICE nomination fallback -------------------------------
class _StubIceCall:
    def __init__(self, role="controlled", states=None):
        self._role = role
        self._states = list(states or ["checking"] * 50)
        self.forced = 0

    def ice_role(self):
        return self._role

    def ice_state(self):
        return self._states.pop(0) if self._states else "checking"

    def force_ice_controlling(self):
        self.forced += 1
        return True


async def _run_fallback(role="controlled", states=None):
    mgr = jr.JingleRtpManager(call_client)
    session = jr.CallSession(
        sid="sidF", peer_bare="bob@example.com", peer_full="bob@example.com/x",
        self_full="me@example.com/res", initiator=False)
    call = _StubIceCall(role, states)
    session.call = call
    mgr.sessions["sidF"] = session
    await mgr._nomination_fallback(session, delay=0.2)
    return call


check("controlled stalled ICE is forced to nominate",
      asyncio.run(_run_fallback()).forced == 1)
check("connected ICE is left alone",
      asyncio.run(_run_fallback(states=["connected"])).forced == 0)
check("controlling role is left alone",
      asyncio.run(_run_fallback(role="controlling")).forced == 0)
check("fallback default delay rescues stalled peers quickly",
      jr.JingleRtpManager._nomination_fallback.__defaults__ is not None
      and 4.0 <= jr.JingleRtpManager._nomination_fallback.__defaults__[0] < 8.0)

# ── 10b. forced nomination really re-runs the best succeeded pair ----------
_PairState = type("State", (), {"SUCCEEDED": "succeeded"})


class _FakePair:
    State = _PairState

    def __init__(self, component, state, inflight=False):
        self.component = component
        self.state = state
        self.inflight = inflight
        self.task = None
        self.started = False


class _FakeConnection:
    def __init__(self, pairs, nominating=(), nominated=()):
        self._check_list = list(pairs)
        self._nominating = set(nominating)
        self._nominated = dict(nominated)

    async def check_start(self, pair):
        pair.started = True


async def _run_nominate(pairs, nominating=(), nominated=()):
    conn = _FakeConnection(pairs, nominating, nominated)
    for p in pairs:
        if p.inflight:
            p.task = asyncio.ensure_future(asyncio.sleep(10))
    if media_mod.HAS_AIORTC:
        media_mod.AiortcCall._nominate_best_pair(conn)
    for p in pairs:
        if p.task is None or p.task.done():
            continue
        if p.inflight:
            p.task.cancel()
            try:
                await p.task
            except asyncio.CancelledError:
                pass
        else:
            await p.task
    return [(p.state, p.started) for p in pairs]


check("forced nomination starts the best succeeded pair",
      asyncio.run(_run_nominate(
          [_FakePair(1, "succeeded")])) == [("succeeded", True)])
check("already nominating components are skipped",
      asyncio.run(_run_nominate(
          [_FakePair(1, "succeeded")], nominating=(1,))) == [("succeeded", False)])
check("in-flight pair tasks are skipped",
      asyncio.run(_run_nominate(
          [_FakePair(1, "succeeded", inflight=True),
           _FakePair(1, "succeeded")])) == [("succeeded", False),
                                            ("succeeded", True)])
check("unchecked pairs are not nominated",
      asyncio.run(_run_nominate(
          [_FakePair(1, "frozen")])) == [("frozen", False)])

# ── 10c. forced controlling wins role conflicts via max tie-breaker --------
_MAX_TB = (1 << 64) - 1


class _FakeRoleConn:
    def __init__(self, controlling=False, tie_breaker=123):
        self.ice_controlling = controlling
        self._tie_breaker = tie_breaker
        self.switched = 0

    def switch_role(self, value):
        self.ice_controlling = value
        self.switched += 1


def _force_on(conn):
    if not media_mod.HAS_AIORTC:
        return False
    return media_mod.AiortcCall._force_controlling(conn)


def _force_result(controlling, tie_breaker):
    conn = _FakeRoleConn(controlling, tie_breaker)
    forced = _force_on(conn)
    return (forced, conn.ice_controlling, conn._tie_breaker, conn.switched)


check("forcing a controlled agent maximizes its tie-breaker",
      _force_result(False, 123) == (True, True, _MAX_TB, 1))
check("an already controlling agent is left untouched",
      _force_result(True, 999) == (False, True, 999, 0))

# ── 10d. propose media is detected across all <description> children --------
def _propose_el(*media):
    el = ET.Element(f"{{{jr.NS_JINGLE_MSG}}}propose")
    for kind in media:
        desc = ET.SubElement(el, f"{{{jr.NS_RTP}}}description")
        desc.set("media", kind)
    return el


check("audio+video proposal is detected as video",
      jr.JingleRtpManager._propose_media(
          _propose_el("audio", "video")) == "video")
check("video-only proposal is detected as video",
      jr.JingleRtpManager._propose_media(
          _propose_el("video")) == "video")
check("audio-only proposal is detected as audio",
      jr.JingleRtpManager._propose_media(
          _propose_el("audio")) == "audio")


def _propose_content_el():
    el = ET.Element(f"{{{jr.NS_JINGLE_MSG}}}propose")
    content = ET.SubElement(el, f"{{{jr.NS_JINGLE}}}content")
    ET.SubElement(content, f"{{{jr.NS_RTP}}}description").set(
        "media", "video")
    return el


check("description nested in content is detected as video",
      jr.JingleRtpManager._propose_media(
          _propose_content_el()) == "video")

# ── 10e. ringing windows carry the session video flag -----------------------
from stanza_im.ui.main_window import MainWindow


def _ringing_video(session_video):
    class _FakeSession:
        video = session_video

    class _FakeRtpCalls:
        sessions = {}

    if session_video is not None:
        _FakeRtpCalls.sessions["s1"] = _FakeSession()

    class _FakeClient:
        rtp_calls = _FakeRtpCalls()

    seen = []
    mw = MainWindow.__new__(MainWindow)
    mw._call_windows = {}
    mw._client = _FakeClient()
    mw._open_call_window = lambda sid, peer, video: seen.append(video)
    mw._on_call_state("s1", "peer", "ringing")
    return seen


check("outgoing video call preview shows the video surface",
      _ringing_video(True) == [True])
check("outgoing audio call preview keeps the video surface hidden",
      _ringing_video(False) == [False])
check("ringing with unknown session defaults to audio",
      _ringing_video(None) == [False])

# ── 10f. audio/camera toggles reach the media engine ------------------------
if media_mod.HAS_AIORTC:
    class _FakeLocalTrack:
        def __init__(self):
            self.calls = []

        def set_enabled(self, enabled):
            self.calls.append(enabled)

    def _engine_toggle_result(attr, method, values):
        call = media_mod.AiortcCall.__new__(media_mod.AiortcCall)
        track = _FakeLocalTrack()
        setattr(call, attr, track)
        for v in values:
            getattr(call, method)(v)
        return track.calls

    check("set_audio_enabled forwards to the local audio track",
          _engine_toggle_result("_local_audio", "set_audio_enabled",
                                [False, True]) == [False, True])
    check("set_video_enabled forwards to the local video track",
          _engine_toggle_result("_local_video", "set_video_enabled",
                                [True, False]) == [True, False])

    _bare_call = media_mod.AiortcCall.__new__(media_mod.AiortcCall)
    _bare_call._local_audio = None
    _bare_call._local_video = None
    _bare_call.set_audio_enabled(False)
    _bare_call.set_video_enabled(False)
    check("engine toggles tolerate missing tracks", True)


class _FakeEngineCall:
    def __init__(self):
        self.calls = []

    def set_audio_enabled(self, v):
        self.calls.append(("audio", v))

    def set_video_enabled(self, v):
        self.calls.append(("video", v))


def _manager_toggle_result():
    mgr = jr.JingleRtpManager.__new__(jr.JingleRtpManager)
    mgr.sessions = {"s1": type("_S", (), {"call": _FakeEngineCall()})()}
    mgr.set_call_audio("s1", False)
    mgr.set_call_video("s1", True)
    return mgr.sessions["s1"].call.calls


check("manager routes audio/camera toggles to the session engine",
      _manager_toggle_result() == [("audio", False), ("video", True)])

_mgr = jr.JingleRtpManager.__new__(jr.JingleRtpManager)
_mgr.sessions = {}
_mgr.set_call_audio("none", False)
_mgr.set_call_video("none", True)
check("manager toggles tolerate unknown sessions", True)


class _FakeRtpCallApi:
    def __init__(self):
        self.calls = []

    def set_call_audio(self, sid, enabled):
        self.calls.append(("a", sid, enabled))

    def set_call_video(self, sid, enabled):
        self.calls.append(("v", sid, enabled))


def _client_toggle_result():
    c = JabberClient.__new__(JabberClient)
    c.rtp_calls = _FakeRtpCallApi()
    c.set_call_audio("s1", False)
    c.set_call_video("s1", True)
    return c.rtp_calls.calls


check("client audio/camera toggles proxy to rtp_calls",
      _client_toggle_result() == [("a", "s1", False), ("v", "s1", True)])

# ── 10g. call-window controls toggle sending, not the remote view -----------
from stanza_im.i18n import tr


def _call_window_toggle_result():
    win = CallWindow("s1", "peer", video=True)
    seen_a, seen_c = [], []
    win.audio_toggled.connect(lambda sid, en: seen_a.append((sid, en)))
    win.camera_toggled.connect(lambda sid, en: seen_c.append((sid, en)))
    win._on_mute(True)
    win._on_camera(False)
    off_text = win._cam_btn.text()
    win._on_mute(False)
    win._on_camera(True)
    return (seen_a, seen_c,
            win._video_view.isVisibleTo(win), off_text)


_aw, _cw, _view_visible, _cam_text = _call_window_toggle_result()
check("mute emits audio_toggled for both ways",
      _aw == [("s1", False), ("s1", True)])
check("camera emits camera_toggled for both ways",
      _cw == [("s1", False), ("s1", True)])
check("turning the camera off keeps the remote video visible", _view_visible)
check("camera off relabels the button", _cam_text == tr("call_camera_off"))

_vw = CallWindow("s1", "peer", video=True)
_aw = CallWindow("s1", "peer", video=False)
check("video-call window shows the camera and remote video",
      _vw._cam_btn.isVisibleTo(_vw) and _vw._video_view.isVisibleTo(_vw))
check("audio-call window hides the camera and remote video",
      not _aw._cam_btn.isVisibleTo(_aw)
      and not _aw._video_view.isVisibleTo(_aw))
_vw.close()
_aw.close()

# ── 11. config defaults ---------------------------------------------------
cfg = Config()
check("devices defaults",
      cfg.devices.audio_input == "" and cfg.devices.video_input == ""
      and cfg.calls.auto_accept is False)

# ── 12. MUC call button → Muji conference routing ---------------------------
class _FakeMujiClient:
    def __init__(self):
        self.joins = []

        class _Rtp:
            available = True

        self.rtp_calls = _Rtp()

    def join_muji(self, room, nick, video):
        self.joins.append((room, nick, video))

    def set_client_active(self, active=True):
        pass


def _muji_routing_result():
    mw = MainWindow(app)
    mw._idle_timer.stop()
    mw._client = _FakeMujiClient()
    mw._muc_self_nicks["room@conf"] = "me"
    mw._on_muji_call_requested("room@conf", True)
    video_join = list(mw._client.joins)
    mw._on_muji_call_requested("room@conf", False)
    both_joins = list(mw._client.joins)
    mw._client.rtp_calls.available = False
    mw._client.joins.clear()
    mw._on_muji_call_requested("room@conf", True)
    blocked = not mw._client.joins
    mw.close()
    return video_join, both_joins, blocked


_video_route, _both_routes, _blocked = _muji_routing_result()
check("main window routes MUC call button to join_muji",
      _video_route == [("room@conf", "me", True)])
check("audio variant routed too",
      _both_routes == [("room@conf", "me", True),
                       ("room@conf", "me", False)])
check("MUC call button blocked without aiortc", _blocked)

# ── 13. Muji conference window: gating, session wiring, audio + mosaic -------
class _FakeMujiRtpSessions:
    def __init__(self):
        self.sessions = {}


class _FakeMujiConfClient:
    """Minimal client for the Muji window / MainWindow conference tests."""

    def __init__(self):
        self.events = []
        self.rtp_calls = _FakeMujiRtpSessions()
        self.muji = muji.MujiManager(self)
        self.sent_audio = []
        self.sent_receive = []
        self.started = []

    def emit(self, *args):
        self.events.append(args)

    def _start_task(self, coro):
        self.started.append(coro)

    def join_muji(self, *args):
        pass

    def leave_muji(self, *args):
        pass

    def end_call(self, *args):
        pass

    def set_call_audio(self, sid, enabled):
        self.sent_audio.append((sid, enabled))

    def set_call_audio_receive(self, sid, enabled):
        self.sent_receive.append((sid, enabled))

    def set_client_active(self, active=True):
        pass


class _MujiFakeSession:
    def __init__(self, sid, peer_bare, muji_room=""):
        self.sid = sid
        self.peer_bare = peer_bare
        self.peer_full = peer_bare + "/res"
        self.muji_room = muji_room
        self.video = False


def _muji_no_call_window_result():
    mw = MainWindow(app)
    mw._idle_timer.stop()
    client = _FakeMujiConfClient()
    mw._client = client
    client.rtp_calls.sessions["s1"] = _MujiFakeSession(
        "s1", "alice@host", muji_room="room@conf")
    mw._on_call_state("s1", "alice@host/res", "ringing")
    mw._on_call_state("s1", "alice@host/res", "active")
    muji_no_window = not mw._call_windows
    # a normal 1:1 call still opens a call window
    client.rtp_calls.sessions["s2"] = _MujiFakeSession("s2", "bob@host")
    mw._on_call_state("s2", "bob@host/res", "ringing")
    one_to_one_ok = "s2" in mw._call_windows
    mw.close()
    return muji_no_window, one_to_one_ok


_muji_no_w, _one2one_w = _muji_no_call_window_result()
check("muji sessions never open a 1:1 call window",
      _muji_no_w and _one2one_w)


def _muji_session_wiring_result():
    mw = MainWindow(app)
    mw._idle_timer.stop()
    client = _FakeMujiConfClient()
    mw._client = client
    client.muji.conferences["room@conf"] = muji.MujiConference(
        room="room@conf")
    mw._on_muji_session("sx", "carol@host/res", "room@conf")
    conf = client.muji.conferences["room@conf"]
    ok = ("res" in conf.participants
          and conf.participants["res"].real_jid == "carol@host")
    mw.close()
    return ok


check("muji_session records the incoming session peer as participant",
      _muji_session_wiring_result())


def _muji_audio_proxy_result():
    mw = MainWindow(app)
    mw._idle_timer.stop()
    client = _FakeMujiConfClient()
    mw._client = client
    conf = muji.MujiConference(room="room@conf")
    conf.participants["alice"] = muji.MujiParticipant(
        nick="alice", real_jid="alice@host")
    client.muji.conferences["room@conf"] = conf
    client.rtp_calls.sessions["sa"] = _MujiFakeSession(
        "sa", "alice@host", muji_room="room@conf")
    mw._on_muji_participant_audio("room@conf", "alice", False)
    mw._on_muji_participant_receive("room@conf", "alice", False)
    ok = (client.sent_audio == [("sa", False)]
          and client.sent_receive == [("sa", False)])
    # unknown nick resolves to no sid, no crash
    mw._on_muji_participant_audio("room@conf", "ghost", False)
    mw.close()
    return ok and client.sent_audio == [("sa", False)]


check("muji participant audio toggles proxy to the matching session",
      _muji_audio_proxy_result())


def _muji_window_ui_result():
    from stanza_im.ui.call_window import MujiCallWindow
    w = MujiCallWindow("room@conf")
    w.set_video(True)
    sent_audio, sent_recv = [], []
    w.participant_audio.connect(lambda *a: sent_audio.append(a))
    w.participant_receive.connect(lambda *a: sent_recv.append(a))
    w.set_participants(["alice", "bob"])
    item = w._rows["alice"]
    row = w._list.itemWidget(item)
    row_btns = row.findChildren(QtWidgets.QPushButton)
    row_btns[0].setChecked(False)   # mute mic toward alice
    row_btns[1].setChecked(False)   # stop hearing alice
    toggles_ok = (sent_audio == [("room@conf", "alice", False)]
                  and sent_recv == [("room@conf", "alice", False)]
                  and w._mic_state["alice"] is False
                  and w._recv_state["alice"] is False)
    # rebuild against the same set keeps the toggle states
    w.set_participants(["alice", "bob"])
    item = w._rows["alice"]
    row = w._list.itemWidget(item)
    row_btns = row.findChildren(QtWidgets.QPushButton)
    preserve = (row_btns[0].isChecked() is False
                and row_btns[1].isChecked() is False)

    img = QtGui.QImage(64, 48, QtGui.QImage.Format.Format_RGB888)
    img.fill(0)
    w.set_frame("alice", img)
    w.set_frame("bob", img)
    mosaic = w._video
    grid_first = mosaic._grid_holder.currentIndex() == 0
    mosaic._zoom_to("bob")
    zoom_ok = (mosaic._grid_holder.currentIndex() == 1
               and mosaic._big.nick == "bob"
               and set(mosaic._strip_tiles) == {"alice"})
    mosaic._show_grid()
    back_ok = mosaic._grid_holder.currentIndex() == 0
    w.close()
    return toggles_ok, preserve, grid_first, zoom_ok, back_ok


_togg, _pres, _grid, _zoom, _back = _muji_window_ui_result()
check("muji participant rows emit audio and receive toggles", _togg)
check("muji participant toggle state survives list rebuild", _pres)
check("muji mosaic starts in grid mode", _grid)
check("muji mosaic zooms one participant with a strip for the rest", _zoom)
check("muji mosaic back button restores the grid", _back)

print("\nAll tests passed" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
