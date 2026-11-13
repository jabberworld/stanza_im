"""XEP-0352 startup gating and the missing-presence probe.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_csi.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = os.path.join(
    tempfile.mkdtemp(prefix="stanza_csi_"), "config")
os.environ["XDG_DATA_HOME"] = os.path.join(
    tempfile.mkdtemp(prefix="stanza_csi_"), "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(
    tempfile.mkdtemp(prefix="stanza_csi_"), "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace

from PyQt6 import QtCore, QtWidgets

from stanza_im.core.client import JabberClient
from stanza_im.ui.main_window import MainWindow

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _FakeStateApp:
    def __init__(self, state):
        self._state = state

    def applicationState(self):
        return self._state


class _FakeClient:
    jid_str = "me@example.com/walkbook"

    def __init__(self):
        self.calls = []
        self.probes = []
        self.contacts = {
            "missing@example.com": SimpleNamespace(resources={}),
            "online@example.com": SimpleNamespace(resources={"r": {}}),
            "from@example.com": SimpleNamespace(resources={}),
            "rss.example.com": SimpleNamespace(resources={}),
        }

    def set_client_active(self, active):
        self.calls.append(bool(active))

    def get_roster_snapshot(self):
        return [
            {"jid": "missing@example.com"},
            {"jid": "online@example.com"},
            {"jid": "from@example.com"},
            {"jid": "rss.example.com"},
            {"jid": "me@example.com"},
        ]

    def subscription(self, jid):
        return {"missing@example.com": "both",
                "online@example.com": "both",
                "from@example.com": "from",
                "rss.example.com": "both",
                "me@example.com": "both"}.get(jid, "")

    def get_contact(self, jid):
        return self.contacts[jid]

    def probe_presence(self, jid):
        self.probes.append(jid)
        return True


mw = MainWindow.__new__(MainWindow)
mw._client = _FakeClient()
mw._csi_ready_at = time.monotonic() + 60
mw._csi_last_sent = None
mw._presence_probed = set()
mw.app = _FakeStateApp(QtWidgets.QApplication.applicationState())
mw._config = SimpleNamespace(
    connection=SimpleNamespace(csi_keep_active_for_typing_osd=False),
    notifications=SimpleNamespace(osd_enabled=False, osd_typing=False))

MainWindow._update_csi(mw)
check("CSI is suppressed before the initial roster settles",
      mw._client.calls == [])

mw._csi_ready_at = 0
mw.app = _FakeStateApp(QtCore.Qt.ApplicationState.ApplicationActive)
MainWindow._update_csi(mw)
MainWindow._update_csi(mw)
check("the first active transition is sent once",
      mw._client.calls == [True])
mw.app = _FakeStateApp(
    QtCore.Qt.ApplicationState.ApplicationInactive)
MainWindow._update_csi(mw)
check("an inactive transition is sent once",
      mw._client.calls == [True, False])

mw._client.calls.clear()
mw._presence_probed.clear()
MainWindow._probe_missing_presence(mw)
check("only subscribed contacts without resources are probed",
      set(mw._client.probes) == {"missing@example.com", "rss.example.com"})
MainWindow._probe_missing_presence(mw)
check("a contact is not probed twice in one session",
      mw._client.probes.count("missing@example.com") == 1
      and mw._client.probes.count("rss.example.com") == 1)


class _Presence:
    def __init__(self):
        self.values = {}

    def __setitem__(self, key, value):
        self.values[key] = value

    def send(self):
        self.values["sent"] = True


class _Xmpp:
    def __init__(self):
        self.presence = _Presence()

    def is_connected(self):
        return True

    def Presence(self):
        return self.presence


client = JabberClient.__new__(JabberClient)
client.xmpp = _Xmpp()
check("presence probe builds a probe stanza",
      client.probe_presence("missing@example.com/resource")
      and client.xmpp.presence.values["to"] == "missing@example.com"
      and client.xmpp.presence.values["type"] == "probe"
      and client.xmpp.presence.values["sent"])

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All CSI tests passed")
