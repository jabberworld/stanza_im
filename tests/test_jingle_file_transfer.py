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
from slixmpp.exceptions import IqTimeout

from stanza_im.core.client import JabberClient
from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.xmpp import bytestream
from stanza_im.xmpp import jingle
from stanza_im.xmpp import jmi

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

# A duplicate block is acknowledged but not written again.
dup_iq = iq_with("data")
dup_el = ET.SubElement(dup_iq.xml, "{%s}data" % jingle.NS_IBB_OLD)
dup_el.set("seq", "1")
dup_el.set("sid", "ibbsid")
dup_el.text = base64.b64encode(b"ZZZ").decode("ascii")
manager._on_ibb_data(dup_iq)

session.ibb_reader.flush()
with open(tmp_path, "rb") as fh:
    received = fh.read()
check("IBB data assembled in order", received == b"abcdef")
check("duplicate IBB data is ignored", session.ibb_in_seq == 2)

# A sequence gap aborts the receive instead of silently corrupting the file.
async def _noop(*_a, **_k):
    return None

gap_path = os.path.join(_SCRATCH, "gap.bin")
gap_session = jingle.JingleSession(
    sid="gap", peer_bare="bob@example.com", peer_full="bob@example.com/r",
    self_full="me@example.com/r", initiator=False, content_name="file-gap",
    meta=jingle.FileMeta(name="gap.bin", size=9), method="ibb",
    ibb_sid="ibbgap", path=gap_path)
manager.sessions["gap"] = gap_session
manager._terminate = _noop
gap_open = iq_with("open")
gap_open_el = ET.SubElement(gap_open.xml, "{%s}open" % jingle.NS_IBB_OLD)
gap_open_el.set("sid", "ibbgap")
gap_open_el.set("block-size", "4096")
_run(manager._on_ibb_open(gap_open))
for seq, chunk in ((0, b"abc"), (2, b"def")):
    gap_iq = iq_with("data")
    gap_el = ET.SubElement(gap_iq.xml, "{%s}data" % jingle.NS_IBB_OLD)
    gap_el.set("seq", str(seq))
    gap_el.set("sid", "ibbgap")
    gap_el.text = base64.b64encode(chunk).decode("ascii")
    manager._on_ibb_data(gap_iq)
_run(asyncio.sleep(0))
check("a gap aborts the IBB receive",
      gap_session.state == "failed" and gap_session.ibb_reader is None)
check("a failed IBB receive removes the partial file",
      not os.path.exists(gap_path))


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
    async def _send_one(self, jid, path, method, target=""):
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

# ── 10b. XEP-0353 file proposals + client selection ------------------------
jmi_client = JabberClient("me@example.com/res", "pw")
jmi_client.presences = {
    "bob@example.com/rbook": {"type": "available", "show": "online",
                              "priority": 50},
    "bob@example.com/monocles": {"type": "available", "show": "online",
                                  "priority": 50},
}
jmi_client.contact_features = {
    "bob@example.com/rbook": {jmi.NS_JINGLE_MSG},
    "bob@example.com/monocles": {jmi.NS_JINGLE_MSG},
}
jmi_client.resource_client_name = lambda bare, res: (
    "Stanza" if res == "rbook" else "Monocles")
jmi_mgr = jmi_client.file_transfer
labels = jmi_mgr.targets("bob@example.com")
check("JMI targets list every online resource",
      len(labels) == 2 and {full for full, _ in labels} == {
          "bob@example.com/rbook", "bob@example.com/monocles"})
check("JMI target labels name the client",
      any("Stanza" in label for _full, label in labels)
      and any("Monocles" in label for _full, label in labels))

_meta = jingle.FileMeta(name="hello.bin", size=7,
                        media_type="application/octet-stream")
_propose_msg = jmi_mgr._jmi_message(
    "propose", "sid-jmi", "bob@example.com/rbook", _meta, private=True)
_propose = jmi.action_element(_propose_msg)
_prop_desc = _propose.find("{%s}description" % jingle.NS_FT)
check("a file proposal carries the XEP-0234 description",
      _propose is not None and _prop_desc is not None
      and _prop_desc.find("{%s}file" % jingle.NS_FT) is not None)
check("a targeted proposal is private",
      _propose_msg.xml.find("{urn:xmpp:carbons:2}private") is not None
      and _propose_msg.xml.find("{urn:xmpp:hints}no-copy") is not None)

_jmi_calls = []
jmi_mgr._send_jmi_action = lambda action, sid, target, **kw:     _jmi_calls.append((action, target))


async def _fake_proceed(_session, _timeout=30.0):
    return "bob@example.com/monocles", "ok"


jmi_mgr._wait_proceed = _fake_proceed
jmi_session = jingle.JingleSession(
    sid="sid-jmi", peer_bare="bob@example.com",
    peer_full="bob@example.com/rbook", self_full="me@example.com/res",
    initiator=True, content_name="file-x", meta=_meta)
_run(jmi_mgr._propose_and_select(jmi_session))
check("the first proceeding resource is selected",
      jmi_session.peer_full == "bob@example.com/monocles")
check("every JMI resource is proposed and the other is retracted",
      ("propose", "bob@example.com/rbook") in _jmi_calls
      and ("propose", "bob@example.com/monocles") in _jmi_calls
      and ("retract", "bob@example.com/rbook") in _jmi_calls)

# Incoming proposal -> file_offer; accepting sends proceed and remembers the
# chosen path until the session-initiate arrives.
offer_client2 = JabberClient("me@example.com/res", "pw")
offer_client2.resource_client_name = lambda bare, res: ""
received_offers = []
offer_client2.on("file_offer", lambda *a: received_offers.append(a))
offer_mgr = offer_client2.file_transfer
incoming_msg = jmi_mgr._jmi_message(
    "propose", "sid-in", "me@example.com/res", _meta)
incoming_msg["from"] = "bob@example.com/phone"
offer_mgr.handle_jingle_message(incoming_msg)
check("a JMI proposal opens a file offer",
      len(received_offers) == 1
      and received_offers[0][0] == "sid-in"
      and received_offers[0][2]["name"] == "hello.bin")
accepted_calls = []
offer_mgr._send_jmi_action = lambda action, sid, target, **kw:     accepted_calls.append((action, target))
_run(offer_mgr._answer_offer(offer_mgr._proposals["sid-in"], True,
                             os.path.join(_SCRATCH, "hello.bin")))
check("accepting a proposal sends proceed",
      accepted_calls == [("proceed", "bob@example.com/phone")])
check("the accepted proposal waits for session-initiate",
      "sid-in" in offer_mgr._proposals
      and offer_mgr._proposal_paths["sid-in"].endswith("hello.bin"))

# A retract closes the other client's prompt.
retract_msg = jmi_mgr._jmi_message(
    "retract", "sid-in", "me@example.com/res")
retract_msg["from"] = "bob@example.com/phone"
cancelled = []
offer_client2.on("file_offer_cancelled", lambda sid: cancelled.append(sid))
offer_mgr.handle_jingle_message(retract_msg)
check("a retract cancels the pending proposal",
      cancelled == ["sid-in"] and "sid-in" not in offer_mgr._proposals)

# An accepted proposal is auto-accepted when the follow-up session-initiate
# arrives, and the initiator's IBB sid is adopted.
auto_client = JabberClient("me@example.com/res", "pw")
auto_mgr = auto_client.file_transfer
auto_msg = jmi_mgr._jmi_message(
    "propose", "sid-auto", "me@example.com/res", _meta)
auto_msg["from"] = "bob@example.com/phone"
auto_mgr.handle_jingle_message(auto_msg)
auto_calls = []
auto_mgr._send_jmi_action = lambda action, sid, target, **kw:     auto_calls.append((action, target))
_run(auto_mgr._answer_offer(auto_mgr._proposals["sid-auto"], True,
                            os.path.join(_SCRATCH, "auto.bin")))
auto_calls.clear()

async def _fake_auto_answer(session, accept, save_path):
    auto_calls.append(("answer", accept, save_path,
                       session.ibb_sid))

auto_mgr._answer_offer = _fake_auto_answer
auto_iq = slixmpp.Iq()
auto_iq["type"] = "set"
auto_iq["from"] = "bob@example.com/phone"
auto_jingle = ET.SubElement(auto_iq.xml,
                            "{%s}jingle" % jingle.NS_JINGLE)
auto_jingle.set("action", "session-initiate")
auto_jingle.set("sid", "sid-auto")
auto_content = ET.SubElement(auto_jingle,
                             "{%s}content" % jingle.NS_JINGLE)
auto_content.set("creator", "initiator")
auto_content.set("name", "file-auto")
auto_desc = ET.SubElement(auto_content,
                          "{%s}description" % jingle.NS_FT)
auto_desc.append(jingle.build_file_element(_meta))
auto_ibb = ET.SubElement(auto_content,
                         "{%s}transport" % jingle.NS_IBB)
auto_ibb.set("sid", "ibb-auto")
_run(auto_mgr._on_session_initiate(auto_jingle, auto_iq))
check("an accepted proposal auto-accepts its session-initiate",
      auto_calls == [("answer", True,
                      os.path.join(_SCRATCH, "auto.bin"), "ibb-auto")])

# The upload dialog exposes the recipient-resource selector and defaults to
# "all clients".
from stanza_im.ui.upload_dialog import FileTransferDialog
selector = FileTransferDialog(
    [os.path.join(_SCRATCH, "source.bin")],
    targets=[("bob@example.com/rbook", "Stanza · rbook"),
             ("bob@example.com/monocles", "Monocles · monocles")])
check("the target selector defaults to all clients",
      selector._target_combo is not None
      and selector._target_combo.count() == 3
      and selector.selected_target() == "")
selector._target_combo.setCurrentIndex(1)
check("the target selector returns the chosen full JID",
      selector.selected_target() == "bob@example.com/rbook")
selector.close()

# ── 10c. Sequential IBB under the ejabberd c2s shaper -------------------
check("IBB uses 4 KiB blocks",
      jingle.IBB_BLOCK_SIZE == 4096)
check("IBB has no pipelining window",
      not hasattr(jingle, "_IBB_WINDOW"))
check("Jingle accept timeout is generous",
      jingle._JINGLE_ACCEPT_TIMEOUT >= 120.0)


async def _sequential():
    source = os.path.join(_SCRATCH, "pipeline.bin")
    payload = b"z" * (jingle.IBB_BLOCK_SIZE * 10)
    with open(source, "wb") as fh:
        fh.write(payload)
    pclient = JabberClient("me@example.com/res", "pw")
    pmgr = pclient.file_transfer
    chunks = []
    active = 0
    max_active = 0

    async def _block(session, chunk):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        chunks.append(chunk)
        await asyncio.sleep(0.01)
        active -= 1

    async def _close(session):
        return None

    pmgr._ibb_send_block = _block
    pmgr._ibb_send_close = _close
    psession = jingle.JingleSession(
        sid="pipe", peer_bare="bob@example.com",
        peer_full="bob@example.com/r", self_full="me@example.com/res",
        initiator=True, content_name="file-pipe",
        meta=jingle.FileMeta(name="pipeline.bin", size=len(payload)),
        path=source, method="ibb", ibb_sid="ibsp")
    await pmgr._ibb_send_file(psession)
    return max_active, b"".join(chunks) == payload, len(chunks)


_seq_max, _seq_ok, _seq_blocks = _run(_sequential())
check("IBB sends one block at a time", _seq_max == 1)
check("sequential IBB keeps the bytes in order", _seq_ok)
check("IBB uses 4 KiB blocks", _seq_blocks == 10)

# Cancelling an IBB session stops the loop before the next block.
async def _cancel_ibb():
    source = os.path.join(_SCRATCH, "cancel.bin")
    payload = b"c" * (jingle.IBB_BLOCK_SIZE * 10)
    with open(source, "wb") as fh:
        fh.write(payload)
    cclient = JabberClient("me@example.com/res", "pw")
    cmgr = cclient.file_transfer
    chunks = []

    async def _block(session, chunk):
        chunks.append(chunk)
        session.cancelled = True

    async def _close(session):
        return None

    cmgr._ibb_send_block = _block
    cmgr._ibb_send_close = _close
    csession = jingle.JingleSession(
        sid="cancel", peer_bare="bob@example.com",
        peer_full="bob@example.com/r", self_full="me@example.com/res",
        initiator=True, content_name="file-cancel",
        meta=jingle.FileMeta(name="cancel.bin", size=len(payload)),
        path=source, method="ibb", ibb_sid="ibb-cancel")
    try:
        await cmgr._ibb_send_file(csession)
    except jingle.S5BFailed:
        pass
    return len(chunks)


check("cancelling IBB stops after the current block",
      _run(_cancel_ibb()) == 1)


# An incoming session-terminate is reported with the incoming direction.
async def _incoming_cancel():
    xclient = JabberClient("me@example.com/res", "pw")
    xmgr = xclient.file_transfer
    xs = jingle.JingleSession(
        sid="in-cancel", peer_bare="bob@example.com",
        peer_full="bob@example.com/r", self_full="me@example.com/res",
        initiator=False, content_name="file-in",
        meta=jingle.FileMeta(name="in.bin", size=10), method="ibb",
        ibb_sid="ibb-in", path=os.path.join(_SCRATCH, "in.bin"))
    xmgr.sessions[xs.sid] = xs
    xmgr._cleanup = lambda session: None
    events = []
    xclient.on("file_transfer_progress",
               lambda *a: events.append(a))
    term = ET.Element("{%s}jingle" % jingle.NS_JINGLE)
    term.set("sid", xs.sid)
    reason = ET.SubElement(term, "{%s}reason" % jingle.NS_JINGLE)
    ET.SubElement(reason, "{%s}cancel" % jingle.NS_JINGLE)
    await xmgr._on_session_terminate(term)
    return events


_in_cancel_events = _run(_incoming_cancel())
check("incoming cancel is reported with direction=in",
      bool(_in_cancel_events)
      and _in_cancel_events[-1][1] == "cancelled"
      and _in_cancel_events[-1][-1] == "in")

# A peer that rejects the larger open block falls back to 4096.
async def _open_fallback():
    fclient = JabberClient("me@example.com/res", "pw")
    fmgr = fclient.file_transfer
    calls = []

    async def _send(iq, *args, **kwargs):
        calls.append(iq)
        if len(calls) == 1:
            raise RuntimeError("block too large")

    _orig = slixmpp.Iq.send
    slixmpp.Iq.send = _send
    try:
        fsession = jingle.JingleSession(
            sid="fb", peer_bare="bob@example.com",
            peer_full="bob@example.com/r", self_full="me@example.com/res",
            initiator=True, content_name="file-fb",
            meta=jingle.FileMeta(name="x", size=1), method="ibb",
            ibb_sid="ibsfb", ibb_block=32768)
        await fmgr._ibb_send_open(fsession)
        return fsession.ibb_block, len(calls)
    finally:
        slixmpp.Iq.send = _orig


_fb_block, _fb_calls = _run(_open_fallback())
check("a rejected IBB block falls back to 4096",
      _fb_block == 4096 and _fb_calls == 2)

# A timed-out IBB data block is retried once with the same sequence number.
async def _ibb_retry():
    rclient = JabberClient("me@example.com/res", "pw")
    rmgr = rclient.file_transfer
    rsession = jingle.JingleSession(
        sid="retry", peer_bare="bob@example.com",
        peer_full="bob@example.com/r", self_full="me@example.com/res",
        initiator=True, content_name="file-retry",
        meta=jingle.FileMeta(name="x", size=1), method="ibb",
        ibb_sid="ibb-retry", ibb_block=32768)
    seqs = []

    async def _send(iq, *args, **kwargs):
        seqs.append(iq.xml.find(
            "{%s}data" % jingle.NS_IBB_OLD).get("seq"))
        if len(seqs) == 1:
            raise IqTimeout(iq)

    rmgr.xmpp.is_connected = lambda: True
    orig = slixmpp.Iq.send
    slixmpp.Iq.send = _send
    try:
        await rmgr._ibb_send_block(rsession, b"payload")
        return seqs, rsession.ibb_out_seq
    finally:
        slixmpp.Iq.send = orig


_retry_seqs, _retry_next = _run(_ibb_retry())
check("a timed-out IBB block retries with the same seq",
      _retry_seqs == ["0", "0"] and _retry_next == 1)
check("IqTimeout maps to a short timeout detail",
      jingle.JingleFileTransferManager._error_detail(
          IqTimeout(slixmpp.Iq())) == "timeout")

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
