"""The account's own JID is hidden by default and shown on demand.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_roster_self.py
"""
import os
import sys
import tempfile
from types import SimpleNamespace

_SCRATCH = tempfile.mkdtemp(prefix="stanza_rosterself_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.i18n import load as load_i18n  # noqa: E402
from stanza_im.i18n import tr  # noqa: E402
from stanza_im.ui.main_window import MainWindow  # noqa: E402
from stanza_im.ui.roster_style import UserItem  # noqa: E402
from stanza_im.ui.roster_widget import RosterWidget  # noqa: E402

load_i18n("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


GROUP = tr("roster_group_self")


class _Contact:
    name = "Me"
    show = "online"
    status = ""
    avatar_path = None


class _Client:
    jid_str = "me@example.com"

    def get_contact(self, jid):
        return _Contact()


def make_win(show_self):
    win = MainWindow.__new__(MainWindow)
    win._client = _Client()
    win._config = SimpleNamespace(
        appearance=SimpleNamespace(roster_show_self=show_self))
    win._roster = RosterWidget()
    win._roster.set_leading_groups({GROUP})
    win._roster.set_trailing_groups({tr("roster_group_conferences")})
    win._schedule_roster_repaint = lambda: None
    return win


def _self_row(win):
    return next((u for u in win._roster._users if u.jid == "me@example.com"),
                None)


# 1. hidden by default --------------------------------------------------------
win = make_win(show_self=False)
win._sync_self_roster()
check("the self-contact is hidden by default", _self_row(win) is None)
check("the empty self group is not created", GROUP not in win._roster._groups)

# 2. shown on demand, in a leading group -------------------------------------
win = make_win(show_self=True)
win._roster.add_user(UserItem(jid="bob@example.com", name="Bob",
                              group="Friends", status="online"))
win._sync_self_roster()
row = _self_row(win)
check("the self row appears when enabled", row is not None)
check("the self row uses the «Свой контакт» group", row.group == GROUP)
check("the self row shows the account name", row.name == "Me")
check("the self group sorts first", win._roster._sorted_groups[0] == GROUP)
check("the self group sorts before a contact group",
      win._roster._sorted_groups.index(GROUP)
      < win._roster._sorted_groups.index("Friends"))

# 3. the self JID is never an ordinary roster contact ------------------------
win = make_win(show_self=True)
win._add_roster_item({"jid": "me@example.com", "name": "Me",
                      "groups": ["Friends"], "subscription": "both"})
check("_add_roster_item skips the account's own JID",
      _self_row(win) is None and "Friends" not in win._roster._groups)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All roster-self tests passed.")
