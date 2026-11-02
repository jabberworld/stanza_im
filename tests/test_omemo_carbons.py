"""Offscreen tests for OMEMO XEP-0280 sent carbons and SCE affixes.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_omemo_carbons.py
"""
import asyncio
import os
import sys
import tempfile
import unittest.mock
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_omemo_carbon_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp

from stanza_im.core import history
from stanza_im.core.client import JabberClient
from stanza_im.xmpp.omemo import sce
from stanza_im.xmpp.omemo.manager import OmemoManager

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


LEGACY = "eu.siacs.conversations.axolotl"


def make_sent_carbon(to="bob@example.com", body="This message is OMEMO encrypted.",
                     mid="m-1", encrypted=True):
    outer = slixmpp.Message()
    outer["from"] = "me@example.com/other"
    outer["to"] = "me@example.com/res1"
    outer["type"] = "chat"
    inner = slixmpp.Message()
    inner["from"] = "me@example.com/other"
    inner["to"] = to
    inner["type"] = "chat"
    inner["body"] = body
    inner["id"] = mid
    if encrypted:
        ET.SubElement(inner.xml, f"{{{LEGACY}}}encrypted")
    sent = ET.SubElement(outer.xml, "{urn:xmpp:carbons:2}sent")
    fw = ET.SubElement(sent, "{urn:xmpp:forward:0}forwarded")
    fw.append(inner.xml)
    return outer


class _FakeOmemo:
    available = True

    def __init__(self, decrypt_error=None):
        self.calls = []
        self.decrypt_error = decrypt_error

    def is_encrypted(self, msg):
        return True

    async def decrypt(self, msg):
        self.calls.append(str(msg["to"]))
        if self.decrypt_error is not None:
            raise RuntimeError(self.decrypt_error)
        out = slixmpp.Message()
        out["from"] = str(msg["from"])
        out["to"] = str(msg["to"])
        out["type"] = str(msg["type"])
        out["id"] = str(msg["id"])
        out["body"] = "hello"
        return out, None

    def note_device_seen(self, *_args):
        pass

    def note_device_resource(self, *_args):
        pass


def _drain():
    try:
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.01))
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.01))


# 1. A sent carbon with our key is decrypted and routed as outgoing ----------
c = JabberClient("me@example.com/res1", "pw")
c.omemo = _FakeOmemo()
sent_events = []
c.on("message_carbon_sent", lambda *a, **k: sent_events.append(a))
c._on_carbon_sent(make_sent_carbon())
_drain()
check("an encrypted sent carbon is decrypted", c.omemo.calls == ["bob@example.com"])
check("the decrypted sent carbon is our outgoing message",
      len(sent_events) == 1 and sent_events[0][0] == "bob@example.com"
      and sent_events[0][1] == "hello")
check("the OMEMO fallback body never reaches the chat",
      all(e[1] != "This message is OMEMO encrypted." for e in sent_events))


# 2. A per-device self copy is ignored, not rendered as a self-chat ----------
c2 = JabberClient("me@example.com/res1", "pw")
c2.omemo = _FakeOmemo()
self_events = []
c2.on("message_carbon_sent", lambda *a, **k: self_events.append(a))
c2._on_carbon_sent(make_sent_carbon(to="me@example.com"))
_drain()
check("a per-device self carbon is not decrypted", c2.omemo.calls == [])
check("a per-device self carbon is not rendered", self_events == [])


# 3. A not-for-us copy of our own message is ignored silently ----------------
c3 = JabberClient("me@example.com/res1", "pw")
c3.omemo = _FakeOmemo(
    decrypt_error="The message to decrypt does not contain key material for us.")
failed = []
received = []
c3.on("omemo_decrypt_failed", lambda *a: failed.append(a))
c3.on("message_received", lambda *a, **k: received.append(a))
inner = slixmpp.Message()
inner["from"] = "me@example.com/other"
inner["to"] = "me@example.com"
inner["type"] = "chat"
inner["body"] = "This message is OMEMO encrypted."
ET.SubElement(inner.xml, f"{{{LEGACY}}}encrypted")
asyncio.get_event_loop().run_until_complete(c3._decrypt_and_dispatch(inner))
check("an expected not-for-us self copy is not an error", failed == [])
check("an expected not-for-us self copy is not rendered", received == [])


# 3b. A direct bodyless per-device copy never becomes a self-chat ------------
c4 = JabberClient("me@example.com/res1", "pw")
c4.omemo = _FakeOmemo()
c4_received = []
c4.on("message_received", lambda *a, **k: c4_received.append(a))
direct = slixmpp.Message()
direct["from"] = "me@example.com/other"
direct["to"] = "me@example.com"
direct["type"] = "chat"
ET.SubElement(direct.xml, f"{{{LEGACY}}}encrypted")
c4._on_message(direct)
_drain()
check("a bodyless direct self copy is not decrypted", c4.omemo.calls == [])
check("a bodyless direct self copy is not rendered", c4_received == [])


# 4. SCE affixes accept the peer in a sent carbon ----------------------------
mgr = OmemoManager.__new__(OmemoManager)
mgr._own_bare = "me@example.com"
stanza = slixmpp.Message()
stanza["from"] = "me@example.com/other"
stanza["to"] = "bob@example.com"
stanza["type"] = "chat"
envelope = sce.build_envelope([], "me@example.com", "bob@example.com")
try:
    mgr._verify_affixes(envelope, "me@example.com", stanza)
    ok = True
except Exception:
    ok = False
check("a sent carbon's SCE <to> may be the peer", ok)
envelope2 = sce.build_envelope([], "me@example.com")
try:
    mgr._verify_affixes(envelope2, "me@example.com", stanza)
    ok2 = True
except Exception:
    ok2 = False
check("an envelope without <to> is still accepted", ok2)


# 4c. The MAM parser marks encrypted rows and keeps the raw stanza ----------
_mam_client = JabberClient("me@example.com/res1", "pw")
_mam_client.omemo = _FakeOmemo()
_raw = slixmpp.Message()
_raw["from"] = "bob@example.com/res"
_raw["to"] = "me@example.com/res1"
_raw["type"] = "chat"
_raw["body"] = "This message is OMEMO encrypted."
_raw["id"] = "mam-raw-1"
ET.SubElement(_raw.xml, "{urn:xmpp:delay}delay").set(
    "stamp", "2026-11-02T10:00:00Z")
ET.SubElement(_raw.xml, f"{{{LEGACY}}}encrypted")
_parsed, _p, _s, _r = _mam_client._mam_rows("bob@example.com", [_raw])
check("the MAM parser keeps the encrypted stanza for decryption",
      len(_parsed) == 1 and _parsed[0].get("_omemo_stanza") is not None)


# 4d. A raw XML forwarded MAM result is normalized to a Message -------------
class _StrictOmemo(_FakeOmemo):
    def is_encrypted(self, msg):
        # Mimic slixmpp-omemo: it needs the stanza's .xml attribute.
        xml = getattr(msg, "xml", None)
        if xml is None:
            return set()
        return set(xml.findall(f"{{{LEGACY}}}encrypted"))


def make_mam_result(frm="bob@example.com/res", to="me@example.com/res1",
                    mid="mam-element-1", stamp="2026-11-02T22:35:00Z",
                    omemo=True):
    # A real slixmpp MAM result: outer <message><result><forwarded>…
    # The inner payload is a raw XML element, as the MAM plugin delivers it.
    outer = slixmpp.Message()
    outer["to"] = "me@example.com/res1"
    result = ET.SubElement(outer.xml, "{urn:xmpp:mam:2}result", {
        "id": "archive-element-1",
    })
    forwarded = ET.SubElement(result, "{urn:xmpp:forward:0}forwarded")
    ET.SubElement(forwarded, "{urn:xmpp:delay}delay", {"stamp": stamp})
    inner = ET.SubElement(forwarded, "{jabber:client}message", {
        "from": frm, "to": to, "type": "chat", "id": mid,
    })
    ET.SubElement(inner, "{jabber:client}body").text = (
        "This message is OMEMO encrypted." if omemo else "plain")
    if omemo:
        ET.SubElement(inner, f"{{{LEGACY}}}encrypted")
    return outer


_mam_element = JabberClient("me@example.com/res1", "pw")
_mam_element.omemo = _StrictOmemo()
_element_rows, _ep, _es, _er = _mam_element._mam_rows(
    "bob@example.com", [make_mam_result()])
check("a raw XML forwarded MAM stanza is recognized as encrypted",
      len(_element_rows) == 1
      and _element_rows[0].get("_omemo_stanza") is not None)
check("a raw XML forwarded MAM stanza keeps the server timestamp",
      len(_element_rows) == 1
      and _element_rows[0].get("timestamp") == "2026-11-02T22:35:00.000000Z")
_element_rows = asyncio.get_event_loop().run_until_complete(
    _mam_element._decrypt_mam_rows("bob@example.com", _element_rows))
check("a raw XML forwarded MAM stanza is decrypted",
      _element_rows[0]["body"] == "hello"
      and _element_rows[0]["encrypted"] is True
      and _element_rows[0]["encryption"] == "omemo")

_plain_rows, _pp, _ps, _pr = _mam_element._mam_rows(
    "bob@example.com", [make_mam_result(mid="mam-plain-1", omemo=False)])
check("a plain forwarded MAM stanza keeps the server timestamp",
      len(_plain_rows) == 1
      and _plain_rows[0].get("body") == "plain"
      and _plain_rows[0].get("timestamp") == "2026-11-02T22:35:00.000000Z")


# 4e. An outgoing own-device MAM row is not mistaken for a self copy --------
_mam_out = JabberClient("me@example.com/res1", "pw")
_mam_out.omemo = _StrictOmemo()
_out_rows, _op, _os, _or = _mam_out._mam_rows(
    "bob@example.com",
    [make_mam_result(frm="me@example.com/walkbook",
                     to="bob@example.com", mid="mam-out-1")])
_out_rows = asyncio.get_event_loop().run_until_complete(
    _mam_out._decrypt_mam_rows("bob@example.com", _out_rows))
check("an outgoing own-device MAM OMEMO row is decrypted",
      _out_rows[0]["direction"] == "outgoing"
      and _out_rows[0]["body"] == "hello"
      and _mam_out.omemo.calls == ["bob@example.com"])


# 5. MAM rows are decrypted before storage --------------------------------
_mam = JabberClient("me@example.com/res1", "pw")
_mam.omemo = _FakeOmemo()
_mam_stanza = slixmpp.Message()
_mam_stanza["from"] = "bob@example.com/res"
_mam_stanza["to"] = "me@example.com/res1"
_mam_stanza["type"] = "chat"
_mam_stanza["body"] = "This message is OMEMO encrypted."
_mam_stanza["id"] = "mam-1"
ET.SubElement(_mam_stanza.xml, f"{{{LEGACY}}}encrypted")
_mam_rows = [{
    "direction": "incoming", "body": _mam_stanza["body"],
    "timestamp": "2026-11-02T10:00:00Z", "sender": "bob@example.com",
    "archive_id": "mam-1", "stanza_id": "mam-1", "origin_id": "mam-1",
    "reply_to": "", "reply_id": "", "retracted": False,
    "retract_reason": "", "retract_by": "", "replace_id": "",
    "markup": None, "_omemo_stanza": _mam_stanza,
}]
_mam_rows = asyncio.get_event_loop().run_until_complete(
    _mam._decrypt_mam_rows("bob@example.com", _mam_rows))
check("a 1:1 MAM OMEMO row is decrypted",
      _mam_rows[0]["body"] == "hello"
      and _mam_rows[0]["encrypted"] is True
      and _mam_rows[0]["encryption"] == "omemo")

_fail = JabberClient("me@example.com/res1", "pw")
_fail.omemo = _FakeOmemo(
    decrypt_error="The message to decrypt does not contain key material for us.")
_stanza2 = slixmpp.Message()
_stanza2["from"] = "bob@example.com/res"
_stanza2["to"] = "me@example.com/res1"
_stanza2["type"] = "chat"
_stanza2["body"] = "This message is OMEMO encrypted."
ET.SubElement(_stanza2.xml, f"{{{LEGACY}}}encrypted")
_fail_rows = [{
    "direction": "incoming", "body": "This message is OMEMO encrypted.",
    "timestamp": "2026-11-02T10:00:00Z", "sender": "bob@example.com",
    "archive_id": "mam-2", "stanza_id": "mam-2", "origin_id": "mam-2",
    "reply_to": "", "reply_id": "", "retracted": False,
    "retract_reason": "", "retract_by": "", "replace_id": "",
    "markup": None, "_omemo_stanza": _stanza2,
}]
_fail_rows = asyncio.get_event_loop().run_until_complete(
    _fail._decrypt_mam_rows("bob@example.com", _fail_rows))
check("an undecryptable MAM row keeps its fallback",
      _fail_rows[0]["body"] == "This message is OMEMO encrypted."
      and _fail_rows[0]["encrypted"] is True)


# 6. An old fallback row is upgraded by a later plaintext copy -------------
_upgrade = "upgrade@example.com"
history.store_message(
    _upgrade, "incoming", "This message is OMEMO encrypted.",
    "2026-11-02T10:00:00Z", sender="bob@example.com",
    archive_id="up-1", stanza_id="up-1", origin_id="up-1",
    message_id="up-1")
history.store_message(
    _upgrade, "incoming", "plaintext", "2026-11-02T10:00:00Z",
    sender="bob@example.com", archive_id="up-1", stanza_id="up-1",
    origin_id="up-1", message_id="up-1", encrypted=True,
    encryption="omemo")
_up_rows = history.load_history(_upgrade, limit=10)
check("a fallback row is upgraded to the plaintext without a duplicate",
      len(_up_rows) == 1 and _up_rows[0]["body"] == "plaintext"
      and bool(_up_rows[0].get("encrypted")))

# 6b. A local URL echo blocks the later MAM fallback duplicate ---------------
_echo = "echo@example.com"
history.store_message(
    _echo, "outgoing", "aesgcm://upload.example/file#key",
    "2026-11-02T10:00:00Z", sender="Me",
    origin_id="omemo-file-id", message_id="omemo-file-id",
    encrypted=True, encryption="omemo")
history.store_many(_echo, [{
    "direction": "outgoing", "body": "This message is OMEMO encrypted.",
    "timestamp": "2026-11-02T10:00:01Z", "sender": "Me",
    "archive_id": "arc-file", "stanza_id": "arc-file",
    "origin_id": "omemo-file-id", "reply_to": "", "reply_id": "",
    "retracted": False, "retract_reason": "", "retract_by": "",
    "replace_id": "", "markup": None, "encrypted": True,
    "encryption": "omemo",
}])
_echo_rows = history.load_history(_echo, limit=10)
check("a local file echo suppresses the later MAM fallback",
      len(_echo_rows) == 1
      and _echo_rows[0]["body"] == "aesgcm://upload.example/file#key")


# 7. An OMEMO file echo reuses the sent stanza id --------------------------
def _run_omemo_file():
    from slixmpp.plugins.xep_0454 import XEP_0454

    c = JabberClient("me@example.com/res1", "pw")
    sent = []

    async def _service():
        return "upload.example.com"

    async def _slot(service, name, size, ctype):
        return ("https://upload.example.com/put",
                "https://upload.example.com/get", {})

    async def _put(url, path, headers, progress, data=None):
        return None

    async def _send(jid, url, mtype="chat", recipients=None):
        sent.append((jid, url))
        return "omemo-file-id"

    c._http_upload_service = _service
    c._http_upload_slot = _slot
    c._http_upload_put = _put
    c.send_omemo_message = _send
    fd, path = tempfile.mkstemp(suffix=".png")
    os.write(fd, b"png")
    os.close(fd)
    try:
        with unittest.mock.patch.object(
                XEP_0454, "encrypt",
                return_value=(b"ciphertext", "iv+key")):
            result = asyncio.get_event_loop().run_until_complete(
                c.send_omemo_file("bob@example.com", path))
    finally:
        os.unlink(path)
    return result, sent, c.take_upload_result("bob@example.com", path)


_file_id, _file_sent, _file_result = _run_omemo_file()
check("an OMEMO file returns the sent stanza id", _file_id == "omemo-file-id")
check("the local echo stashes the real stanza id",
      _file_result[0] == "omemo-file-id")
check("the local echo gets aesgcm media metadata",
      (_file_result[1] or {}).get("url", "").startswith("aesgcm://"))


if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll OMEMO carbon tests passed.")
