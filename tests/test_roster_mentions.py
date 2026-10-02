"""Roster badges with mention counters + the virtual private-messages group."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core import unread_state
from stanza_im.i18n import tr
from stanza_im.ui.roster_style import RosterStyle, UserItem
from stanza_im.ui.roster_widget import RosterWidget

FAILURES = []


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    if not ok:
        FAILURES.append(label)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

# 1. badge label -------------------------------------------------------------
check("plain unread count", RosterStyle.badge_text(UserItem("a@x", "A", "G",
                                                            unread_count=5))
      == "5")
check("unread with mentions is composite",
      RosterStyle.badge_text(UserItem("a@x", "A", "G", unread_count=234,
                                      unread_mentions=2)) == "234 / 2")
check("mentions need unread",
      RosterStyle.badge_text(UserItem("a@x", "A", "G", unread_count=3,
                                      unread_mentions=0)) == "3")

# 2. the private-messages group ----------------------------------------------
from stanza_im.ui.main_window import MainWindow  # noqa: E402

GROUP = tr("roster_group_personal_messages")

win = MainWindow.__new__(MainWindow)
win._pm_roster = set()
win._pm_targets = {}
win._muc_users = {"room@conf.example": {
    "nick": {"nick": "Nick", "show": "away", "status": "hi",
             "real_jid": "", "avatar_path": ""}}}
win._unread_chats = {"room@conf.example/nick": unread_state.blank()}
win._unread_chats["room@conf.example/nick"].update(
    {"unread": 4, "mentions": 1})
win._roster = RosterWidget()
win._roster.set_trailing_groups({tr("roster_group_conferences"), GROUP})
win._client = None
win._chat_window = None
win._recount_unread()
# The repaint is a debounced QTimer on a real window; the model changes below
# are immediate, so the repaint itself is not interesting here.
win._schedule_roster_repaint = lambda: None

win._sync_pm_roster("room@conf.example/nick", "room@conf.example", "nick")
row = next(u for u in win._roster._users
           if u.jid == "room@conf.example/nick")
check("the PM row lands in the personal-messages group",
      row.group == GROUP and row.name == "Nick")
check("the PM row carries the unread counters",
      row.unread_count == 4 and row.unread_mentions == 1)
check("the PM row shows the occupant presence",
      row.status == "away" and row.icon_key == "away")
check("the PM group sorts last", win._roster._sorted_groups[-1] == GROUP)

win._maybe_drop_pm_roster("room@conf.example/nick")
check("an unread PM row is kept",
      "room@conf.example/nick" in win._pm_roster)

win._unread_chats["room@conf.example/nick"].update({"unread": 0,
                                                    "mentions": 0})
win._maybe_drop_pm_roster("room@conf.example/nick")
check("a read, closed PM row is dropped",
      "room@conf.example/nick" not in win._pm_roster
      and all(u.jid != "room@conf.example/nick" for u in win._roster._users))
check("the empty PM group disappears", GROUP not in win._roster._groups)


class _Tabbed:
    """Minimal ChatWindow stand-in remembering one open conversation."""

    def __init__(self, jid):
        self._open = {jid}

    def has_chat(self, jid):
        return jid in self._open

    def get_chat(self, jid):
        return None


win._chat_window = _Tabbed("room@conf.example/nick")
win._sync_pm_roster("room@conf.example/nick", "room@conf.example", "nick")
win._maybe_drop_pm_roster("room@conf.example/nick")
check("an open PM row is kept while the tab is open",
      "room@conf.example/nick" in win._pm_roster)

# 3. the PM group is never offered as a real contact group --------------------
_mw_src = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "stanza_im", "ui", "main_window.py"),
    encoding="utf-8").read()
check("the PM group is a virtual group",
      'tr("roster_group_personal_messages")' in _mw_src
      and _mw_src.count("_virtual_roster_groups()") >= 4)
check("the PM group is a trailing group",
      'self._roster.set_trailing_groups({' in _mw_src
      and 'tr("roster_group_personal_messages")})' in _mw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All roster-mention tests passed.")
