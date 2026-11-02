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


if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll OMEMO carbon tests passed.")
