"""Offscreen tests for client branding and graceful shutdown.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_client_branding.py
"""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_brand_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import JabberClient
from stanza_im.include.constants import (APP_NAME, GIT_COMMIT, VERSION,
                                         VERSION_DISPLAY)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


c = JabberClient("me@example.com/r", "pw")

# 1. caps node + software version branding ------------------------------------
caps = c.xmpp.plugin["xep_0115"]
check("caps node is branded",
      caps.caps_node == f"{APP_NAME} {VERSION_DISPLAY}")
check("the version carries the git commit in a checkout",
      (VERSION_DISPLAY == f"{VERSION} ({GIT_COMMIT})" if GIT_COMMIT
       else VERSION_DISPLAY == VERSION))
check("caps node is not slixmpp's",
      "slixmpp" not in (caps.caps_node or ""))

plugin = c.xmpp.plugin["xep_0092"]
check("xep_0092 name is Stanza IM", plugin.software_name == APP_NAME)
check("xep_0092 version is ours", plugin.version == VERSION_DISPLAY)
check("xep_0092 os is set", bool(plugin.os))

# 2. the advertised disco identity carries the name ---------------------------
_loop = asyncio.new_event_loop()


async def _identities():
    info = await c.xmpp["xep_0030"].get_info(jid=c.xmpp.boundjid, local=True)
    return list(info["identities"])


identities = _loop.run_until_complete(_identities())
named = [tuple(i) for i in identities]
check("named client identity advertised",
      any(t[:2] == ("client", "pc") and APP_NAME in t for t in named))
check("no nameless bot identity",
      not any(t[:2] == ("client", "bot") for t in named))

# 2b. the disco features survive the server-assigned bind ----------------------
from slixmpp import JID  # noqa: E402

c2 = JabberClient("me@example.com/r", "pw")


async def _after_bind():
    c2.xmpp.boundjid = JID("me@example.com/walkbook")
    pre = await c2.xmpp["xep_0030"].get_info(
        c2.xmpp.boundjid.full, None, local=True)
    c2._register_disco()
    post = await c2.xmpp["xep_0030"].get_info(
        c2.xmpp.boundjid.full, None, local=True)
    return set(pre["features"]), set(post["features"]), list(post["identities"])


_pre_feats, _post_feats, _post_ids = _loop.run_until_complete(_after_bind())
check("a fresh bind drops the __init__ disco features",
      "urn:xmpp:jingle:1" not in _pre_feats)
check("re-registering after the bind restores the call features",
      "urn:xmpp:jingle:apps:rtp:audio" in _post_feats)
check("re-registering restores the named identity",
      any(tuple(i)[:2] == ("client", "pc") for i in _post_ids))


# 3. graceful disconnect: unavailable + awaited stream close ------------------
class _FakeXmpp:
    def __init__(self, connected=True):
        self.auto_reconnect = True
        self.connected = connected
        self.closed = False
        self.wait = None

    def is_connected(self):
        return self.connected

    def disconnect(self, wait=2.0):
        self.wait = wait

        async def _do():
            self.closed = True

        return _do()


sent = []
c.xmpp = _FakeXmpp()
c.send_presence = lambda show=None, status="", priority=None: sent.append(show)
_loop.run_until_complete(c.disconnect())
check("reconnect disabled on shutdown", c.xmpp.auto_reconnect is False)
check("unavailable presence sent", sent == ["offline"])
check("stream close awaited", c.xmpp.closed is True)
check("bounded wait passed to slixmpp", c.xmpp.wait == 1.0)

c2 = JabberClient("me@example.com/r", "pw")
c2.xmpp = _FakeXmpp(connected=False)
sent2 = []
c2.send_presence = lambda show=None, status="", priority=None: sent2.append(show)
_loop.run_until_complete(c2.disconnect())
check("nothing sent when already offline", sent2 == []
      and c2.xmpp.closed is False)

# 3. a stale (call-less) caps entry is verified with a live disco#info -------
cc = JabberClient("me@example.com/r", "pw")
_checked = []
cc._start_task = lambda coro: (_checked.append(coro), coro.close())
cc.presences = {"bob@example.com/pc": {"type": "available"},
                "carol@example.com/pc": {"type": "available"}}
cc.contact_features["bob@example.com/pc"] = {
    "http://jabber.org/protocol/disco#info"}
cc.ensure_caps("bob@example.com")
check("a call-less caps entry is verified live", len(_checked) == 1)
cc.ensure_caps("bob@example.com")
check("the live verification runs once per resource", len(_checked) == 1)
cc.contact_features["carol@example.com/pc"] = {
    "http://jabber.org/protocol/disco#info", "urn:xmpp:jingle:apps:rtp:audio"}
cc.ensure_caps("carol@example.com")
check("a call-capable caps entry needs no verification", len(_checked) == 1)

_loop.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All client-branding tests passed.")
