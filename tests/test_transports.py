"""Offscreen tests for the transports (gateways) tab.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_transports.py
"""
import asyncio
import os
import sys
import tempfile

os.environ["XDG_DATA_HOME"] = os.path.join(tempfile.mkdtemp(), "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tempfile.mkdtemp(), "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


GW = "xmpp.example.com"


class _Contact:
    def __init__(self, show):
        self.show = show
        self.status = ""
        self.avatar_path = None


class _FakeClient:
    jid_str = "me@example.com/res"
    pep_data: dict = {}

    def __init__(self):
        self.shows = {GW: "online"}
        self.removed = []
        self.presences = []

    def get_roster_snapshot(self):
        return [{"jid": GW, "name": "J2J", "groups": [], "subscription": "both"},
                {"jid": "bob@example.com", "name": "Bob", "groups": [],
                 "subscription": "both"}]

    async def discover_service_info(self, jid, node=""):
        return {"jid": jid, "node": "", "name": "",
                "category": "gateway" if jid == GW else "", "type": "",
                "features": []}

    def get_contact(self, jid):
        return _Contact(self.shows.get(jid, "offline"))

    def client_icon(self, jid):
        return ""

    def get_vcard(self, jid, force=False):
        pass

    def subscription(self, jid):
        return "both"

    async def remove_contact(self, jid):
        self.removed.append(jid)

    def send_directed_presence(self, to, ptype="", status="", priority=None):
        self.presences.append((to, ptype))


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
client = _FakeClient()
win._client = client
win._roster_name = lambda jid: "J2J" if jid == GW else jid

check("the transports tab is registered", "transports" in win._roster_tab_keys)
check("the transports roster exists", win._transport_roster is not None)

# Seed the ordinary roster with the gateway, then classify.
win._add_roster_item({"jid": GW, "name": "J2J", "groups": []})
win._add_roster_item({"jid": "bob@example.com", "name": "Bob", "groups": []})
check("the gateway starts as a normal contact",
      any(u.jid == GW for u in win._roster._users))

loop = asyncio.get_event_loop()
win._classify_transports()
loop.run_until_complete(asyncio.sleep(0.2))

check("the gateway is classified", GW in win._transport_jids)
check("the gateway left the contacts roster",
      all(u.jid != GW for u in win._roster._users))
check("the plain contact stays in the roster",
      any(u.jid == "bob@example.com" for u in win._roster._users))
check("the transports tab lists the gateway",
      any(u.jid == GW for u in win._transport_roster._users))
check("a classified transport is never re-added as a contact",
      win._add_roster_item({"jid": GW, "name": "J2J", "groups": []}) is None
      and all(u.jid != GW for u in win._roster._users))

# Connect / disconnect via a directed presence.
win._transport_roster._selected_jid = GW
win._on_transport_toggle()
check("an online transport is disconnected",
      client.presences and client.presences[-1] == (GW, "unavailable"))
client.shows[GW] = "offline"
win._on_transport_toggle()
check("an offline transport is connected",
      client.presences[-1] == (GW, ""))

# Remove (confirm) drops it from the tab.
_orig_question = QtWidgets.QMessageBox.question
QtWidgets.QMessageBox.question = lambda *a, **k: (
    QtWidgets.QMessageBox.StandardButton.Yes)
try:
    win._remove_transport_confirmed(GW)
    loop.run_until_complete(asyncio.sleep(0.05))
finally:
    QtWidgets.QMessageBox.question = _orig_question
check("removing a transport calls remove_contact", client.removed == [GW])
check("the removed transport leaves the tab",
      GW not in win._transport_jids
      and all(u.jid != GW for u in win._transport_roster._users))

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All transports tests passed.")
