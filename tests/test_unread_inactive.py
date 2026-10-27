"""Unread counters of non-running conferences are cleared on load.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_unread_inactive.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_inactive_unread_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.core import unread_state  # noqa: E402
from stanza_im.ui.main_window import MainWindow  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
win._unread_save_timer.stop()
win._unread_chats = {}
win._bookmarks = {
    "manual@conf.example": {"jid": "manual@conf.example", "autojoin": False},
    "auto@conf.example": {"jid": "auto@conf.example", "autojoin": True},
    "joined@conf.example": {"jid": "joined@conf.example", "autojoin": False},
}
win._bookmarks_loaded = True
win._known_conferences = set(win._bookmarks)
win._muc_self_nicks = {"joined@conf.example": "me"}
win._muc_joined = {"joined@conf.example"}
win._conference_roster = {"joined@conf.example"}


def entry(unread: int, anchor: str = "") -> dict:
    record = unread_state.blank()
    record["unread"] = unread
    record["mentions"] = 1 if unread else 0
    record["read_ts"] = anchor
    return record


win._unread_chats = {
    "manual@conf.example": entry(11, "2026-10-24T10:24:02Z"),
    "auto@conf.example": entry(4),
    "joined@conf.example": entry(5),
    "room@conf.example/nick": entry(6),
    "rss@example.com": entry(1),
}
win._recount_unread()

cleared = win._clear_inactive_conference_unread()
check("the inactive manual room is cleared",
      "manual@conf.example" in cleared
      and win._unread_chats["manual@conf.example"]["unread"] == 0)
check("its read anchor is preserved",
      win._unread_chats["manual@conf.example"]["read_ts"]
      == "2026-10-24T10:24:02Z")
check("a pending autojoin room is kept",
      win._unread_chats["auto@conf.example"]["unread"] == 4)
check("a joined room is kept",
      win._unread_chats["joined@conf.example"]["unread"] == 5)
check("a private message is kept",
      win._unread_chats["room@conf.example/nick"]["unread"] == 6)
check("an ordinary contact is kept",
      win._unread_chats["rss@example.com"]["unread"] == 1)
check("the aggregate total is recomputed", win._unread_total == 16)

# A failed autojoin is no longer "about to run": its unread is cleared.
failed = win._clear_inactive_conference_unread(
    "auto@conf.example", clear_autojoin=True, force=True)
check("a failed autojoin room is cleared",
      failed == ["auto@conf.example"]
      and win._unread_chats["auto@conf.example"]["unread"] == 0)
check("the remaining total is recomputed", win._unread_total == 12)

# Before the bookmark list is known nothing is cleared from a bulk pass.
win._bookmarks_loaded = False
win._unread_chats["manual@conf.example"] = entry(2)
check("a bulk clear without bookmarks is a no-op",
      win._clear_inactive_conference_unread() == []
      and win._unread_chats["manual@conf.example"]["unread"] == 2)

win._chat_window.close_all()
win.close()
win.deleteLater()

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All inactive-unread tests passed")
