"""Offscreen test: seeding the roster cache fills the event-diff snapshot."""
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_roster_seed_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import JabberClient


class _FakeRoster(dict):
    version = ""

    def __missing__(self, key):
        value = {
            "name": "", "groups": [], "subscription": "both",
            "from": False, "to": False, "whitelisted": False,
            "pending_out": False, "pending_in": False,
        }
        self[key] = value
        return value


async def _case():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    client = JabberClient("me@example.com/res", "pw")
    fake = _FakeRoster()
    client.xmpp.client_roster = fake
    client._roster_cache = {
        "version": "v1",
        "items": [
            {"jid": "a@example.com", "name": "A", "groups": ["Friends"],
             "from": True, "to": True},
            {"jid": "b@example.com", "name": "B", "groups": [],
             "from": False, "to": True},
        ],
    }
    client._seed_roster_cache()
    return client, fake


client, fake = asyncio.run(_case())
checks = [
    ("the fake roster received both cached items", len(fake) == 2),
    ("the version was restored", fake.version == "v1"),
    ("the event-diff snapshot contains the cached JIDs",
     set(client.roster) == {"a@example.com", "b@example.com"}),
    ("the snapshot keeps the roster groups",
     client.roster["a@example.com"]["groups"] == ["Friends"]),
]
failures = []
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + ": " + name)
    if not ok:
        failures.append(name)
if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print("All roster-seed tests passed.")
