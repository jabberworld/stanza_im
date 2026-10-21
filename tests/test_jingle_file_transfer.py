"""Offscreen tests for Jingle file transfer (XEP-0234/0260/0261).

Covers the stanza builders/parsers, the SOCKS5 bytestream loopback, the IBB
receive path, the HTTP-Upload→P2P fallback trigger, config defaults, the send
menus and sequential P2P batching.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_jingle_file_transfer.py
"""
import asyncio
import base64
import hashlib
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_jingle_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

import slixmpp

from stanza_im.core.client import JabberClient
from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.xmpp import bytestream
from stanza_im.xmpp import jingle

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# ``asyncio.run`` clears the current loop on Python 3.11, while slixmpp needs
# one whenever a client or a Future is created; run every coroutine on one
# shared loop instead.
_LOOP = asyncio.new_event_loop()


def _run(coro):
    asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


asyncio.set_event_loop(_LOOP)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def iq_with(xml_tag: str):
    iq = slixmpp.Iq()
    iq["type"] = "set"
    return iq


# ── 1. <file> description round-trip --------------------------------------
meta = jingle.FileMeta(name="hello world.txt", size=6144,
                       media_type="text/plain", date="1969-07-21T02:56:15Z",
                       desc="test", hash_algo="sha-1", hash_value="abc=")
el = jingle.build_file_element(meta)
parsed = jingle.parse_file_element(el)
check("file element round-trip",
      parsed.name == "hello world.txt" and parsed.size == 6144
      and parsed.media_type == "text/plain"
      and parsed.hash_algo == "sha-1" and parsed.hash_value == "abc=")
hash_el = el.find("{%s}hash" % jingle.NS_HASHES)
check("hash in urn:xmpp:hashes:2", hash_el is not None
      and hash_el.get("algo") == "sha-1")
check("size present", el.find("{%s}size" % jingle.NS_FT).text == "6144")

# ── 2. SOCKS5 candidate build/parse ---------------------------------------
candidates = [jingle.Candidate(cid="c1", host="192.168.1.2", port=5086,
                               jid="me@x/r", priority=8257636, type="direct"),
              jingle.Candidate(cid="c2", host="proxy.x", port=7625,
                               jid="proxy.x", priority=655361, type="proxy")]
tr = jingle.build_s5b_transport("bsid1", candidates, dstaddr="deadbeef")
info = jingle.parse_s5b_transport(tr)
check("s5b transport parsed",
      info["sid"] == "bsid1" and info["dstaddr"] == "deadbeef"
      and len(info["candidates"]) == 2
      and info["candidates"][0].host == "192.168.1.2"
      and info["candidates"][1].type == "proxy")

# ── 3. DST hash ------------------------------------------------------------
expected = hashlib.sha1(b"sid1a@x/rb@y/r").hexdigest()
check("sha1_dst both orders",
      bytestream.sha1_dst("sid1", "a@x/r", "b@y/r") == expected
      and bytestream.sha1_dst("sid1", "b@y/r", "a@x/r") != expected)

# ── 4. SOCKS5 bytestream loopback -----------------------------------------
async def _loopback():
    dst = bytestream.sha1_dst("sid1", "a@x/r", "b@y/r")
    got = asyncio.get_running_loop().create_future()

    async def _on_conn(reader, writer):
        got.set_result(await reader.readexactly(5))
        writer.close()

    server, port = await bytestream.listen_for_bytestream(
        {dst}, _on_conn, host="127.0.0.1")
    reader, writer = await bytestream.connect_bytestream("127.0.0.1", port, dst)
    writer.write(b"hello")
    await writer.drain()
    data = await got
    writer.close()
    server.close()
    await server.wait_closed()
    return data


check("bytestream loopback", _run(_loopback()) == b"hello")


async def _reject():
    dst = bytestream.sha1_dst("sid2", "a@x/r", "b@y/r")

    async def _on_conn(reader, writer):
        writer.close()

    server, port = await bytestream.listen_for_bytestream(
        {dst}, _on_conn, host="127.0.0.1")
    try:
        await bytestream.connect_bytestream("127.0.0.1", port, "nope")
        return False
    except bytestream.BytestreamError:
        return True
    finally:
        server.close()
        await server.wait_closed()


check("bytestream rejects wrong DST", _run(_reject()))

# ── 5. IBB receive path ----------------------------------------------------
client = JabberClient("me@example.com/res", "pw")
manager = client.file_transfer
tmp_path = os.path.join(_SCRATCH, "recv.bin")
session = jingle.JingleSession(
    sid="s1", peer_bare="bob@example.com", peer_full="bob@example.com/r",
    self_full="me@example.com/r", initiator=False, content_name="file-x",
    meta=jingle.FileMeta(name="recv.bin", size=6), method="ibb",
    ibb_sid="ibbsid", path=tmp_path)
manager.sessions["s1"] = session

open_iq = iq_with("open")
open_el = ET.SubElement(open_iq.xml, "{%s}open" % jingle.NS_IBB_OLD)
open_el.set("sid", "ibbsid")
open_el.set("block-size", "4096")
_run(manager._on_ibb_open(open_iq))
check("IBB open creates the file", session.ibb_reader is not None)

for seq, chunk in enumerate((b"abc", b"def")):
    data_iq = iq_with("data")
    data_el = ET.SubElement(data_iq.xml, "{%s}data" % jingle.NS_IBB_OLD)
    data_el.set("seq", str(seq))
    data_el.set("sid", "ibbsid")
    data_el.text = base64.b64encode(chunk).decode("ascii")
    manager._on_ibb_data(data_iq)

# An out-of-sequence chunk must be ignored.
bad_iq = iq_with("data")
bad_el = ET.SubElement(bad_iq.xml, "{%s}data" % jingle.NS_IBB_OLD)
bad_el.set("seq", "7")
bad_el.set("sid", "ibbsid")
bad_el.text = base64.b64encode(b"XXX").decode("ascii")
manager._on_ibb_data(bad_iq)

session.ibb_reader.flush()
with open(tmp_path, "rb") as fh:
    received = fh.read()
check("IBB data assembled in order", received == b"abcdef")


async def _noop(*_a, **_k):
    return None


manager._send_received = _noop
manager._terminate = _noop
close_iq = iq_with("close")
close_el = ET.SubElement(close_iq.xml, "{%s}close" % jingle.NS_IBB_OLD)
close_el.set("sid", "ibbsid")
_run(manager._on_ibb_close(close_iq))
check("IBB close finalizes", session.ibb_reader is None)

# ── 6. incoming offer event ------------------------------------------------
offer_client = JabberClient("me@example.com/res", "pw")
offers = []
offer_client.on("file_offer", lambda *a: offers.append(a))
iq = slixmpp.Iq()
iq["type"] = "set"
iq["from"] = "bob@example.com/phone"
jingle_el = ET.SubElement(iq.xml, "{%s}jingle" % jingle.NS_JINGLE)
jingle_el.set("action", "session-initiate")
jingle_el.set("sid", "offer1")
content = ET.SubElement(jingle_el, "{%s}content" % jingle.NS_JINGLE)
content.set("creator", "initiator")
content.set("name", "file-offer")
desc = ET.SubElement(content, "{%s}description" % jingle.NS_FT)
desc.append(jingle.build_file_element(jingle.FileMeta(
    name="photo.jpg", size=2048, media_type="image/jpeg")))
_run(offer_client.file_transfer._on_session_initiate(jingle_el, iq))
check("file_offer emitted",
      bool(offers) and offers[0][0] == "offer1"
      and offers[0][1] == "bob@example.com/phone"
      and offers[0][2]["name"] == "photo.jpg"
      and offers[0][2]["size"] == 2048)

# ── 7. HTTP Upload oversize fallback --------------------------------------
class _Oversize(Exception):
    condition = "not-acceptable"
    iq = None


fb_client = JabberClient("me@example.com/res", "pw")
fb_events = []
fb_client.on("http_upload_oversize", lambda *a: fb_events.append(a))

async def _fake_service():
    return "upload.example.com"


async def _fake_slot(*_a, **_k):
    raise _Oversize()


fb_client._http_upload_service = _fake_service
fb_client._http_upload_slot = _fake_slot
big = os.path.join(_SCRATCH, "big.bin")
with open(big, "wb") as fh:
    fh.write(b"x" * 32)
_run(fb_client._http_upload_flow("bob@example.com", big))
check("oversize falls back to P2P",
      fb_events == [("bob@example.com", big)])

check("_is_upload_oversize condition",
      JabberClient._is_upload_oversize(_Oversize()) is True)


class _PlainError(Exception):
    condition = "remote-server-timeout"


check("_is_upload_oversize ignores other errors",
      JabberClient._is_upload_oversize(_PlainError()) is False)


class _IqHolder:
    def __init__(self, xml):
        self.xml = xml


class _FtError(Exception):
    condition = "cancel"

    def __init__(self):
        iq = slixmpp.Iq()
        err = ET.SubElement(iq.xml, "error")
        ET.SubElement(err, "{%s}file-too-large" % jingle.NS_FT_ERRORS)
        self.iq = _IqHolder(iq.xml)


check("_is_upload_oversize file-too-large element",
      JabberClient._is_upload_oversize(_FtError()) is True)

# ── 8. config defaults + preferences controls ------------------------------
cfg = Config()
check("files defaults",
      cfg.files.auto_accept is False
      and cfg.files.download_notifications is True
      and cfg.files.download_dir == "")

from stanza_im.ui.preferences import PreferencesDialog

prefs = PreferencesDialog(cfg, chat_themes.ChatThemeFactory())
check("prefs file controls exist",
      "file_auto_accept" in prefs._controls
      and "file_download_notifications" in prefs._controls
      and "file_download_dir" in prefs._controls)
check("auto accept checkbox enabled",
      prefs._controls["file_auto_accept"].isEnabled())
prefs._controls["file_auto_accept"].setChecked(True)
prefs._controls["file_download_dir"].setText("/tmp/dl")
prefs._apply_settings()
check("prefs persist file settings",
      cfg.files.auto_accept is True and cfg.files.download_dir == "/tmp/dl")
prefs.close()

# ── 9. send menu gains P2P IBB ---------------------------------------------
cw = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
actions = [a.text() for a in cw._send_file_btn.menu().actions()]
check("send menu has P2P IBB", "P2P" in actions and "P2P IBB" in actions
      and "HTTP Upload" in actions)

# ── 10. sequential P2P batching -------------------------------------------
order = []


class _SerialManager(jingle.JingleFileTransferManager):
    async def _send_one(self, jid, path, method):
        order.append("start:%s" % path)
        await asyncio.sleep(0.02)
        order.append("end:%s" % path)


serial = _SerialManager(client)


async def _batch():
    await asyncio.gather(
        serial.send_file("bob@example.com", "a", "p2p"),
        serial.send_file("bob@example.com", "b", "p2p"))


_run(_batch())
check("P2P batch is sequential",
      order == ["start:a", "end:a", "start:b", "end:b"])

# ── 11. JET-OMEMO: policy, content security, refusal, stream ---------------
from types import SimpleNamespace

from stanza_im.xmpp import jet as jet_mod

check("JET policy defaults to prefer",
      JabberClient("me@example.com/res", "pw").file_encryption == "prefer")
check("files.encryption defaults to prefer",
      Config().files.encryption == "prefer")
check("a custom policy is normalized",
      JabberClient("me@example.com/res", "pw",
                   file_encryption="bogus").file_encryption == "prefer")

# The <security/> element is added to an outgoing initiate.
enc_client = JabberClient("me@example.com/res", "pw")
enc_client.file_encryption = "require"
enc_client.supports_feature = lambda bare, feature: True


async def _fake_key(peer):
    envelope = ET.Element("{%s}encrypted" % jet_mod.NS_LEGACY_OMEMO)
    return b"k" * 16, b"i" * 12, envelope


enc_client.omemo = SimpleNamespace(available=True,
                                   encrypt_transport_key=_fake_key)
enc_mgr = enc_client.file_transfer
enc_session = jingle.JingleSession(
    sid="enc1", peer_bare="bob@example.com", peer_full="bob@example.com/r",
    self_full="me@example.com/r", initiator=True, content_name="file-enc",
    meta=jingle.FileMeta(name="a.bin", size=10), method="ibb",
    ibb_sid="bsid", encrypted=True, transport_key=b"k" * 16,
    transport_iv=b"i" * 12)
enc_session.security_el = jet_mod.build_security(
    "file-enc", ET.Element("{%s}encrypted" % jet_mod.NS_LEGACY_OMEMO))

_sent_iqs = []
_orig_send = slixmpp.Iq.send


def _capture_send(self, *args, **kwargs):
    _sent_iqs.append(self)

    async def _done():
        return None
    return _done()


slixmpp.Iq.send = _capture_send
try:
    _run(enc_mgr._send_session_initiate(enc_session, ibb=True))
finally:
    slixmpp.Iq.send = _orig_send
_sec = (_sent_iqs[-1].xml.find(".//{%s}security" % jet_mod.NS_JET)
        if _sent_iqs else None)
check("an outgoing initiate carries the JET security",
      _sec is not None
      and _sec.get("cipher") == jet_mod.CIPHER_AES_128_GCM
      and _sec.get("type") == jet_mod.NS_LEGACY_OMEMO
      and _sec.get("name") == "file-enc"
      and _sec.find("{%s}encrypted" % jet_mod.NS_LEGACY_OMEMO) is not None)

# A require policy refuses when no key can be produced.
refuse_client = JabberClient("me@example.com/res", "pw")
refuse_client.file_encryption = "require"
refuse_client.supports_feature = lambda bare, feature: False
refuse_events = []
refuse_client.on("file_transfer_progress",
                 lambda *a: refuse_events.append(a))
_run(refuse_client.file_transfer.send_file(
    "bob@example.com", os.path.join(_SCRATCH, "source.bin")))
check("require refuses when the peer has no JET",
      bool(refuse_events) and refuse_events[-1][1] == "error")

# A strict policy rejects a plain incoming offer; an unsupported envelope too.
async def _offer(path_client, security_type=None):
    client = JabberClient("me@example.com/res", "pw")
    client.file_encryption = path_client
    refused = []
    client.on("file_offer_rejected", lambda *a: refused.append(a))
    iq = slixmpp.Iq()
    iq["type"] = "set"
    iq["from"] = "bob@example.com/phone"
    jingle_el = ET.SubElement(iq.xml, "{%s}jingle" % jingle.NS_JINGLE)
    jingle_el.set("action", "session-initiate")
    jingle_el.set("sid", "strict1")
    content = ET.SubElement(jingle_el, "{%s}content" % jingle.NS_JINGLE)
    content.set("creator", "initiator")
    content.set("name", "file-strict")
    desc = ET.SubElement(content, "{%s}description" % jingle.NS_FT)
    desc.append(jingle.build_file_element(jingle.FileMeta(
        name="x.bin", size=1)))
    ET.SubElement(content, "{%s}transport" % jingle.NS_IBB).set("sid", "b")
    if security_type:
        sec = ET.SubElement(content, "{%s}security" % jet_mod.NS_JET)
        sec.set("name", "file-strict")
        sec.set("cipher", jet_mod.CIPHER_AES_128_GCM)
        sec.set("type", security_type)
        ET.SubElement(sec, "{%s}encrypted" % security_type)
    await client.file_transfer._on_session_initiate(jingle_el, iq)
    return refused


check("strict rejects a plain offer",
      _run(_offer("strict")) == [("bob@example.com", "strict")])
check("an unsupported envelope is refused",
      _run(_offer("prefer", "urn:xmpp:omemo:2"))
      == [("bob@example.com", "unsupported")])
check("require accepts a plain offer",
      _run(_offer("require")) == [])


# The encrypted S5B stream round-trips through the real helpers.
async def _encrypted_stream():
    payload = b"jet payload " * 5000
    source = os.path.join(_SCRATCH, "source.bin")
    target = os.path.join(_SCRATCH, "target.bin")
    with open(source, "wb") as fh:
        fh.write(payload)
    for name in (target, target + ".part"):
        try:
            os.remove(name)
        except OSError:
            pass
    transfer = JabberClient("me@example.com/res", "pw").file_transfer
    secret = jet_mod.TransportSecret(b"k" * 16, b"i" * 12)
    sender = jingle.JingleSession(
        sid="st1", peer_bare="bob@example.com", peer_full="bob@example.com/r",
        self_full="me@example.com/r", initiator=True, content_name="file-st",
        meta=jingle.FileMeta(name="source.bin", size=len(payload)),
        path=source, encrypted=True, transport_key=secret.key,
        transport_iv=secret.iv)
    receiver = jingle.JingleSession(
        sid="st1", peer_bare="bob@example.com", peer_full="me@example.com/r",
        self_full="bob@example.com/r", initiator=False,
        content_name="file-st",
        meta=jingle.FileMeta(name="source.bin", size=len(payload)),
        path=target, encrypted=True, transport_key=secret.key,
        transport_iv=secret.iv)

    async def _on_conn(reader, writer):
        await transfer._stream_out(sender, (reader, writer))

    server = await asyncio.start_server(_on_conn, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    await transfer._stream_in(receiver, (reader, writer))
    server.close()
    await server.wait_closed()
    with open(target, "rb") as fh:
        got = fh.read()
    return payload, got, os.path.exists(target + ".part"), receiver.part_path


_payload, _got, _leftover, _part = _run(_encrypted_stream())
check("an encrypted S5B transfer round-trips", _got == _payload)
check("no unverified .part file is left behind",
      not _leftover and not _part)

# The encrypted IBB path assembles the file from the ciphertext blocks.
async def _encrypted_ibb():
    payload = b"ibb jet data " * 3000
    source = os.path.join(_SCRATCH, "ibb-source.bin")
    target = os.path.join(_SCRATCH, "ibb-target.bin")
    with open(source, "wb") as fh:
        fh.write(payload)
    for name in (target, target + ".part"):
        try:
            os.remove(name)
        except OSError:
            pass
    secret = jet_mod.TransportSecret(b"z" * 16, b"y" * 12)
    sender_client = JabberClient("me@example.com/res", "pw")
    sender = jingle.JingleSession(
        sid="ibt1", peer_bare="bob@example.com", peer_full="bob@example.com/r",
        self_full="me@example.com/res", initiator=True, content_name="file-ibt",
        meta=jingle.FileMeta(name="ibb-source.bin", size=len(payload)),
        path=source, method="ibb", ibb_sid="ibs", encrypted=True,
        transport_key=secret.key, transport_iv=secret.iv)
    blocks = []

    async def _collect(session, chunk):
        blocks.append(chunk)

    async def _noop_close(session):
        return None

    sender_client.file_transfer._ibb_send_block = _collect
    sender_client.file_transfer._ibb_send_close = _noop_close
    await sender_client.file_transfer._ibb_send_file(sender)

    receiver_client = JabberClient("bob@example.com/res", "pw")
    receiver = jingle.JingleSession(
        sid="ibt1", peer_bare="me@example.com", peer_full="me@example.com/res",
        self_full="bob@example.com/res", initiator=False,
        content_name="file-ibt",
        meta=jingle.FileMeta(name="ibb-source.bin", size=len(payload)),
        path=target, method="ibb", ibb_sid="ibs", encrypted=True,
        transport_key=secret.key, transport_iv=secret.iv)
    rmgr = receiver_client.file_transfer
    rmgr.sessions["ibt1"] = receiver
    open_iq = iq_with("open")
    open_el = ET.SubElement(open_iq.xml, "{%s}open" % jingle.NS_IBB_OLD)
    open_el.set("sid", "ibs")
    open_el.set("block-size", "4096")
    await rmgr._on_ibb_open(open_iq)
    for seq, block in enumerate(blocks):
        data_iq = iq_with("data")
        data_el = ET.SubElement(data_iq.xml, "{%s}data" % jingle.NS_IBB_OLD)
        data_el.set("seq", str(seq))
        data_el.set("sid", "ibs")
        data_el.text = base64.b64encode(block).decode("ascii")
        rmgr._on_ibb_data(data_iq)

    async def _noop(*_a, **_k):
        return None

    rmgr._send_received = _noop
    rmgr._terminate = _noop
    close_iq = iq_with("close")
    close_el = ET.SubElement(close_iq.xml, "{%s}close" % jingle.NS_IBB_OLD)
    close_el.set("sid", "ibs")
    await rmgr._on_ibb_close(close_iq)
    with open(target, "rb") as fh:
        got = fh.read()
    return (payload, got, sum(len(b) for b in blocks),
            os.path.exists(target + ".part"))


_ib_payload, _ib_got, _ib_wire, _ib_part = asyncio.get_event_loop().run_until_complete(
    _encrypted_ibb())
check("an encrypted IBB transfer round-trips", _ib_got == _ib_payload)
check("the IBB wire carries only the tag overhead",
      _ib_wire == len(_ib_payload) + jet_mod.TAG_SIZE)
check("the IBB receiver leaves no .part file", not _ib_part)

# Preferences expose the four modes.
prefs2 = PreferencesDialog(Config(), chat_themes.ChatThemeFactory())
_combo = prefs2._controls.get("file_encryption")
check("the encryption selector exists with four modes",
      _combo is not None and _combo.count() == 4)
prefs2._controls["file_encryption"].setCurrentIndex(3)
prefs2._apply_settings()
check("the strict mode persists",
      prefs2._config.files.encryption == "strict")
prefs2.close()

print("\nAll tests passed" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
