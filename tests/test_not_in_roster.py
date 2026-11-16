"""Session-only «Не в списке» contacts."""
import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="stanza_not_in_roster_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(os.environ["XDG_DATA_HOME"], "c")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as load_i18n, tr
from stanza_im.ui.add_contact_dialog import AddContactDialog
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.roster_widget import RosterWidget

load_i18n("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


class _Contact:
    show = "offline"
    status = ""
    avatar_path = None


class _Client:
    jid_str = "me@example.com"
    roster = {}

    def get_contact(self, jid):
        return _Contact()


def _win():
    win = MainWindow.__new__(MainWindow)
    win._client = _Client()
    win._transport_jids = set()
    win._pm_targets = {}
    win._muc_self_nicks = {}
    win._known_conferences = set()
    win._conference_roster = set()
    win._muc_joined = set()
    win._bookmarks = {}
    win._config = SimpleNamespace(
        connection=SimpleNamespace(conference_servers=[]))
    win._unread_chats = {}
    win._roster = RosterWidget()
    win._roster.set_trailing_groups({tr("roster_group_not_in_list")})
    win._roster_name = lambda jid: ""
    win._schedule_roster_repaint = lambda: None
    win._not_in_roster = set()
    return win


win = _win()
jid = "1234060895@tg.example.com"
win._track_not_in_roster(jid, "Роман")
row = next((u for u in win._roster._users if u.jid == jid), None)
group = tr("roster_group_not_in_list")
checks = [
    ("an unknown contact gets a session row", row is not None),
    ("the session row is in «Не в списке»", row is not None and row.group == group),
    ("the session row is offline", row is not None and row.status == "offline"),
    ("the session set contains the JID", jid in win._not_in_roster),
]
win._roster.clear()
win._sync_not_in_roster()
checks.append(("a full roster rebuild restores the session row",
               any(u.jid == jid for u in win._roster._users)))
win._client.roster[jid] = {"jid": jid, "name": "Роман", "groups": [],
                           "subscription": "both"}
win._sync_not_in_roster()
checks.extend([
    ("a contact that entered the roster leaves the session group",
     all(u.jid != jid for u in win._roster._users)),
    ("the session set is pruned", jid not in win._not_in_roster),
])

# Server/transport JIDs (no localpart) never become unknown contacts.
server = "xmpp.example.org"
win._track_not_in_roster(server)
checks.extend([
    ("a transport JID is not a «Не в списке» contact",
     all(u.jid != server for u in win._roster._users)),
    ("a transport JID is not kept in the session set",
     server not in win._not_in_roster),
])

# The context-menu action reuses AddContactDialog with the JID/name prefilled.
_dlg = AddContactDialog([], None, jid=jid, name="Роман")
_data = _dlg.collect()
checks.extend([
    ("the add dialog receives the JID", _data["jid"] == jid),
    ("the add dialog receives the name", _data["name"] == "Роман"),
])
_dlg.close()

_src = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "stanza_im", "ui", "main_window.py"),
    encoding="utf-8").read()
checks.append(("the unknown-row menu offers «Add to list»",
               "ctx_add_to_roster" in _src
               and "_not_in_roster" in _src))
failures = []
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + ": " + name)
    if not ok:
        failures.append(name)
if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print("All not-in-roster tests passed.")
