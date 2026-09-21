"""Offscreen tests for XEP-0084 / XEP-0153 / XEP-0398 avatars.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_avatars.py
"""
import asyncio
import base64
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_avatars_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

asyncio.set_event_loop(asyncio.new_event_loop())

import slixmpp
from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.core.client import JabberClient, _avatar_data_from_iq
from stanza_im.include.avatars import image_mime, image_size

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAACXBIWXMAAA7EAAAOxAGV"
    "Kw4bAAAAFklEQVQImWP8z8DAwMDAxMDAwMDAAAANHQEDDMfniQAAAABJRU5ErkJggg==")
_PNG_B64 = base64.b64encode(_PNG).decode("ascii")


# ── image sniffing ───────────────────────────────────────────────
check("PNG mime sniffed", image_mime(_PNG) == "image/png")
check("JPEG mime sniffed", image_mime(b"\xff\xd8\xff\xe0rest") == "image/jpeg")
check("unknown mime", image_mime(b"nonsense") == "application/octet-stream")
check("image size read", image_size(_PNG) == (2, 2))
check("broken image size is zero", image_size(b"nonsense") == (0, 0))


# ── avatar data payload parsing ──────────────────────────────────
iq = slixmpp.Iq()
pubsub = ET.SubElement(iq.xml, "{http://jabber.org/protocol/pubsub}pubsub")
items = ET.SubElement(pubsub, "{http://jabber.org/protocol/pubsub}items")
item = ET.SubElement(items, "{http://jabber.org/protocol/pubsub}item")
data = ET.SubElement(item, "{urn:xmpp:avatar:data}data")
data.text = _PNG_B64
check("avatar data decoded from IQ", _avatar_data_from_iq(iq) == _PNG)


# ── client behaviour ─────────────────────────────────────────────
client = JabberClient("me@example.com/r", "pw")
check("xep_0153 registered", "xep_0153" in client.xmpp.plugin)
check("xep_0084 registered", "xep_0084" in client.xmpp.plugin)

updates = []
client.on("avatar_updated", lambda jid, path: updates.append((jid, path)))

check("avatar applied", client._apply_avatar("bob@example.com", _PNG) is True)
check("avatar_updated emitted", updates and updates[-1][0] == "bob@example.com")
check("avatar cached on disk", os.path.isfile(updates[-1][1]))
check("identical avatar is deduplicated",
      client._apply_avatar("bob@example.com", _PNG) is False)


# ── XEP-0153 presence hash ───────────────────────────────────────
fetched = []
client.get_vcard = lambda jid, force=False: fetched.append((jid, force))

pres = slixmpp.Presence()
pres["from"] = "bob@example.com/phone"
pres["vcard_temp_update"]["photo"] = "newhash"
client._on_vcard_avatar_update(pres)
check("changed vCard hash refetches the card",
      fetched == [("bob@example.com", True)])

fetched.clear()
client._avatar_ids["bob@example.com"] = "samehash"
pres["vcard_temp_update"]["photo"] = "samehash"
client._on_vcard_avatar_update(pres)
check("unchanged vCard hash is ignored", fetched == [])


# ── XEP-0084 metadata handling ───────────────────────────────────
scheduled = []
client._start_task = lambda coro: (scheduled.append(coro), coro.close())
items = ET.fromstring(
    "<items xmlns='http://jabber.org/protocol/pubsub#event' "
    "node='urn:xmpp:avatar:metadata'><item>"
    "<metadata xmlns='urn:xmpp:avatar:metadata'>"
    "<info id='sha1xyz' type='image/png' bytes='123'/></metadata>"
    "</item></items>")
client._avatar_ids.pop("carol@example.com", None)
client._handle_avatar_metadata("carol@example.com", items)
check("metadata schedules an avatar retrieval", len(scheduled) == 1)

scheduled.clear()
client._avatar_ids["carol@example.com"] = "sha1xyz"
client._handle_avatar_metadata("carol@example.com", items)
check("unchanged metadata id is ignored", scheduled == [])


# ── XEP-0084/0398 publishing our avatar ──────────────────────────
class _FakeAvatar:
    def __init__(self):
        self.published = []
        self.metadata = []

    async def publish_avatar(self, raw):
        self.published.append(raw)

    async def publish_avatar_metadata(self, items, **kwargs):
        self.metadata.append(items)


fake = _FakeAvatar()
plugin = client.xmpp.plugin["xep_0084"]
plugin.publish_avatar = fake.publish_avatar
plugin.publish_avatar_metadata = fake.publish_avatar_metadata
hashes = []
client._set_vcard_avatar_hash = lambda digest: hashes.append(digest)
asyncio.get_event_loop().run_until_complete(
    client._publish_own_avatar_async(_PNG))
check("own avatar published to PEP", fake.published == [_PNG])
check("own avatar metadata has dimensions",
      fake.metadata and fake.metadata[0][0]["width"] == 2
      and fake.metadata[0][0]["height"] == 2
      and fake.metadata[0][0]["type"] == "image/png")
check("XEP-0153 hash updated after publishing",
      hashes and hashes[0] == __import__("hashlib").sha1(_PNG).hexdigest())


# ── PEP event routing ────────────────────────────────────────────
msg = slixmpp.Message()
msg["from"] = "dave@example.com"
event = ET.SubElement(
    msg.xml, "{http://jabber.org/protocol/pubsub#event}event")
node = ET.SubElement(
    event, "{http://jabber.org/protocol/pubsub#event}items")
node.set("node", "urn:xmpp:avatar:metadata")
entry = ET.SubElement(
    node, "{http://jabber.org/protocol/pubsub#event}item")
metadata = ET.SubElement(entry, "{urn:xmpp:avatar:metadata}metadata")
info = ET.SubElement(metadata, "{urn:xmpp:avatar:metadata}info")
info.set("id", "sha1dave")
info.set("type", "image/png")
handled = []
client._handle_avatar_metadata = lambda jid, it: handled.append(jid)
client._maybe_pep_event(msg)
check("avatar metadata PEP event routed", handled == ["dave@example.com"])

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
