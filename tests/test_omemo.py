"""Offscreen tests for the OMEMO core helpers (availability/storage/SCE).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_omemo.py
"""
import asyncio
import os
import stat
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_omemo_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.xmpp.omemo import availability
from stanza_im.xmpp.omemo import sce
from stanza_im.xmpp.omemo.storage import OmemoStorage, storage_path

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. availability ------------------------------------------------------------
check("OMEMO stack detected as available", availability.AVAILABLE)
check("both backends detected",
      availability.BACKEND_LEGACY in availability.BACKENDS
      and availability.BACKEND_OMEMO2 in availability.BACKENDS)
check("no missing packages", availability.MISSING == [])
check("summary mentions both backends",
      "legacy" in availability.summary()
      and "omemo2" in availability.summary())


# 2. storage -----------------------------------------------------------------
store = OmemoStorage(storage_path(os.path.join(_SCRATCH, "profile")))


async def _storage_roundtrip():
    from omemo.storage import Just, Nothing
    empty = await store._load("missing")
    ok_empty = isinstance(empty, Nothing)
    await store._store("k", {"a": 1, "b": [1, 2, 3]})
    loaded = await store._load("k")
    ok_just = isinstance(loaded, Just) and loaded.from_just() == {
        "a": 1, "b": [1, 2, 3]}
    await store._delete("k")
    gone = await store._load("k")
    return ok_empty, ok_just, isinstance(gone, Nothing)


ok_empty, ok_just, ok_gone = asyncio.run(_storage_roundtrip())
check("storage returns Nothing for a missing key", ok_empty)
check("storage round-trips a JSON value", ok_just)
check("storage deletes a key", ok_gone)
check("OMEMO store file is 0600",
      stat.S_IMODE(os.stat(store._path).st_mode) == 0o600)

store.set_app("chat_modes", {"bob@example.com": "omemo"})
check("app-level key round-trips",
      store.get_app("chat_modes") == {"bob@example.com": "omemo"})
reopened = OmemoStorage(store._path)
check("app-level key persists across reopen",
      reopened.get_app("chat_modes") == {"bob@example.com": "omemo"})


# 3. SCE envelope ------------------------------------------------------------
body = ET.Element("{jabber:client}body")
body.text = "Hello World!"
reply = ET.Element("{urn:xmpp:reply:0}reply")
reply.set("id", "m1")
hints = ET.Element("{urn:xmpp:hints}store")
eme = ET.Element("{urn:xmpp:eme:0}encryption")
message = ET.Element("{jabber:client}message")
for elt in (body, reply, hints, eme):
    message.append(elt)

content = sce.collect_content(message)
check("collect_content keeps body and reply, drops hints/eme",
      body in content and reply in content
      and hints not in content and eme not in content)

envelope = sce.build_envelope(content, "romeo@montague.lit")
payload = sce.serialize(envelope)
parsed = sce.parse(payload)
check("envelope round-trips through serialize/parse",
      parsed.tag == "{urn:xmpp:sce:1}envelope")
check("envelope carries a from affix",
      sce.affix(parsed, "from") is not None
      and sce.affix(parsed, "from").get("jid") == "romeo@montague.lit")
check("envelope carries an rpad affix",
      sce.affix(parsed, "rpad") is not None
      and len(sce.affix(parsed, "rpad").text or "") >= 100)
check("no to affix for a 1:1 envelope", sce.affix(parsed, "to") is None)

extracted = sce.extract_content(parsed)
tags = [e.tag for e in extracted]
check("extract_content returns body and reply",
      "{jabber:client}body" in tags and "{urn:xmpp:reply:0}reply" in tags)
check("extracted body text survives",
      next(e for e in extracted if e.tag == "{jabber:client}body").text
      == "Hello World!")

muc_env = sce.build_envelope(content, "romeo@montague.lit",
                             "room@conference.montague.lit")
check("MUC envelope carries a to affix",
      sce.affix(muc_env, "to").get("jid") == "room@conference.montague.lit")

try:
    sce.parse(b"not xml")
    check("malformed payload is rejected", False)
except ValueError:
    check("malformed payload is rejected", True)

try:
    sce.parse(b"<nope/>")
    check("non-envelope root is rejected", False)
except ValueError:
    check("non-envelope root is rejected", True)


# 4. config section ----------------------------------------------------------
from stanza_im.core.storage import Config

cfg = Config()
check("omemo config defaults",
      cfg.omemo.enabled is True and cfg.omemo.blind_trust is True
      and cfg.omemo.alias_sync is False)
cfg.omemo.blind_trust = False
cfg.save()
check("omemo config round-trips", Config().omemo.blind_trust is False)


# 5. history encryption flag + render ----------------------------------------
from stanza_im.core import history
from stanza_im.ui.chat_themes import ChatThemeFactory

history.store_message("omemo@example.com", "incoming", "secret",
                      origin_id="e1", encrypted=True, encryption="omemo")
entry = history.entry_by_ref("omemo@example.com", "e1")
check("history stores the encrypted flag", entry is not None
      and entry["encrypted"] is True and entry["encryption"] == "omemo")

html = ChatThemeFactory().render_message(
    sender="Bob", body="secret", timestamp="10:00", direction="incoming",
    encrypted=True)
check("encrypted messages render a lock", "stanza-lock" in html)
html_plain = ChatThemeFactory().render_message(
    sender="Bob", body="hi", timestamp="10:00", direction="incoming")
check("plain messages have no lock", "stanza-lock" not in html_plain)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All OMEMO tests passed.")
