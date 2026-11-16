"""Error replies must not be mistaken for a peer's XEP-0085 activity."""
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="stanza_chat_activity_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(os.environ["XDG_DATA_HOME"], "c")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import JabberClient


class _Msg:
    def __init__(self, frm, mtype, state):
        self._values = {"from": frm, "to": "me@example.com/res",
                        "type": mtype, "chat_state": state}

    def __getitem__(self, key):
        return self._values.get(key, "")

    def get(self, key, default=None):
        return self._values.get(key, default)


async def _case():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    client = JabberClient("me@example.com/res", "pw")
    events = []
    client.on("chatstate_received", lambda *args: events.append(args))

    client._on_chatstate(_Msg("alex@example.com", "error", "active"))
    client._on_chatstate(_Msg("bob@example.com", "chat", "active"))
    return events


events = asyncio.run(_case())
checks = [
    ("an error chat state is ignored",
     all(frm != "alex@example.com" for frm, _ in events)),
    ("a normal chat state still reaches the UI",
     ("bob@example.com", "active") in events),
]
failures = []
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + ": " + name)
    if not ok:
        failures.append(name)
if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print("All chat-activity tests passed.")
