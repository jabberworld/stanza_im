"""Offscreen tests for PEP subscription gating and startup ordering."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import JabberClient

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


client = JabberClient.__new__(JabberClient)
client.xmpp = SimpleNamespace(is_connected=lambda: True)
client.jid_str = "me@example.org/res"
client._pep_subscribed = {}
client._pep_subscribe_inflight = set()
client._pep_subscribe_failed = {}
client._pep_subscribe_cooldown = 300.0
client._pep_subscribe_sem = None
tasks = []
client._start_task = lambda coro: (tasks.append(coro), coro.close())

allowed = set()
client.supports_feature = lambda bare, feature: feature in allowed
JabberClient._ensure_pep_subscription(client, "rss@example.org")
check("a contact without PEP caps gets no subscriptions", tasks == [])

allowed = {"http://jabber.org/protocol/mood+notify"}
tasks.clear()
JabberClient._ensure_pep_subscription(client, "friend@example.org")
check("only advertised PEP nodes are subscribed",
      len(tasks) == 1)
check("the mood node is the one requested",
      ("friend@example.org", "http://jabber.org/protocol/mood")
      in client._pep_subscribe_inflight)

src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "core", "client.py"), encoding="utf-8").read()
start = src.index("async def _on_session_start")
end = src.index("async def _subscribe_pep_contacts")
session = src[start:end]
check("initial presence is sent before the roster request",
      session.index("self.send_presence()")
      < session.index("self.request_roster()"))
check("bookmark auto-join is background work",
      "loop.create_task(self._autojoin_bookmarks())" in session)

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All PEP-gate tests passed")
