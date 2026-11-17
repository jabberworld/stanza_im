"""The unread divider is removed by the user's scroll, not by opening.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_unread_divider.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from types import SimpleNamespace

from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.main_window import MainWindow


FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


cw = ChatWidget.__new__(ChatWidget)
cw._released = False
cw.jid = "room@example"
cw._unread_boundary = {"ref": "m-1", "ts": "", "sid": ""}
marks = []
cw.mark_read = lambda: marks.append(1)
ChatWidget._on_divider_passed(cw)
check("a user scroll past the divider clears it", marks == [1])

cw2 = ChatWidget.__new__(ChatWidget)
cw2._released = False
cw2.jid = "room@example"
cw2._unread_boundary = {}
marks2 = []
cw2.mark_read = lambda: marks2.append(1)
ChatWidget._on_divider_passed(cw2)
check("a read chat has no divider to clear", marks2 == [])


class _Chat:
    _unread_resolving = False
    _view = SimpleNamespace(_scroll_suspended=False, _deferred_scroll=None)

    def mark_visible_unread(self):
        return 0

    def mark_visible_mentions(self):
        return 0

    def seen_anchor(self):
        return {}


class _Window:
    def get_chat(self, _jid):
        return _Chat()

    def current_jid(self):
        return "room@example"


calls = []
probe = SimpleNamespace(
    _unread_chats={"room@example": {"unread": 1, "mentions": 0}},
    _chat_window=_Window(),
    _chat_area_available=lambda: True,
    _history_sync_pending=set(),
    _history_reload_pending=set(),
    _mds_reconciling=set(),
    _mds_pending_sid="",
    _mds_pending_jid="",
    _mds_throttle_ms=3000,
    _mds_throttle_timer=SimpleNamespace(start=lambda *_a: None),
    _recount_unread=lambda: None,
    _refresh_unread_badge=lambda _jid: None,
    _push_unread_to_chat=lambda _jid: None,
    _schedule_unread_save=lambda: None,
    _mark_chat_read=lambda jid: calls.append(jid),
)
MainWindow._apply_visible_unread(probe, "room@example", 16)
check("visible unread may become read without clearing the divider",
      probe._unread_chats["room@example"]["unread"] == 0 and calls == [])

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All unread-divider tests passed.")
