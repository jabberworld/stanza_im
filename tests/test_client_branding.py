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
from stanza_im.include.constants import APP_NAME, VERSION

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


c = JabberClient("me@example.com/r", "pw")

# 1. caps node + software version branding ------------------------------------
caps = c.xmpp.plugin["xep_0115"]
check("caps node is branded",
      caps.caps_node == f"urn:stanza-im:ver:{VERSION}")
check("caps node is not slixmpp's",
      "slixmpp" not in (caps.caps_node or ""))

plugin = c.xmpp.plugin["xep_0092"]
check("xep_0092 name is Stanza IM", plugin.software_name == APP_NAME)
check("xep_0092 version is ours", plugin.version == VERSION)
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

_loop.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All client-branding tests passed.")
