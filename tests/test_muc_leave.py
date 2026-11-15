"""Offscreen tests for a best-effort MUC leave.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_leave.py
"""
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


class _Muc:
    def leave_muc(self, room, nick, msg=""):
        raise KeyError(
            f"Unable to find the room {room} in the currently joined rooms")


class _Xmpp:
    def __init__(self):
        self.plugin = {"xep_0045": _Muc()}

    @staticmethod
    def is_connected():
        return True


client = JabberClient.__new__(JabberClient)
client.xmpp = _Xmpp()
client.groupchats = {"room@conf.example": SimpleNamespace(nick="me")}
client._muc_join_tasks = {}
client._muc_room_features = {"room@conf.example": {"urn:xmpp:mam:2"}}
client._muc_last_activity = {"room@conf.example": 1.0}
client._muc_self_ping_busy = {"room@conf.example"}
sent = []
client.send_directed_presence = lambda *args, **kwargs: sent.append(args)

try:
    JabberClient.leave_muc(client, "room@conf.example", "bye")
    raised = False
except Exception:
    raised = True

check("a slixmpp KeyError does not escape leave_muc", not raised)
check("the local room state is cleared",
      "room@conf.example" not in client.groupchats
      and "room@conf.example" not in client._muc_room_features
      and "room@conf.example" not in client._muc_last_activity
      and "room@conf.example" not in client._muc_self_ping_busy)
check("a directed unavailable presence is attempted",
      sent == [("room@conf.example/me", "unavailable", "bye")])

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All MUC-leave tests passed")
