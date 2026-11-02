"""Offscreen tests for OMEMO XEP-0280 sent carbons and SCE affixes.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_omemo_carbons.py
"""
import asyncio
import os
import sys
import tempfile
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


if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll OMEMO carbon tests passed.")
