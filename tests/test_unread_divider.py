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


class _View:
    def clear_unread_separator(self):
        return True

    def release_bottom_lock(self):
        pass


cw = ChatWidget.__new__(ChatWidget)
cw._released = False
cw.jid = "room@example"
cw._unread_boundary = {"ref": "m-1", "ts": "", "sid": ""}
cw._view = _View()
marks = []
cw.mark_read = lambda: marks.append(1)
ChatWidget._on_divider_passed(cw)
check("a user scroll past the divider keeps the unread boundary",
      marks == [] and bool(cw._unread_boundary)
      and cw._divider_dismissed is True)
ChatWidget.mark_read(cw)
check("marking read still clears the boundary",
      not cw._unread_boundary and cw._divider_dismissed is False)

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

    def mark_visible_unread(self, move_divider=True):
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



class _MoveView:
    def __init__(self):
        self.moved = []

    def visible_refs(self):
        return ["m1"]

    def move_unread_separator(self, ref):
        self.moved.append(ref)

    def clear_unread_separator(self):
        return True

    def release_bottom_lock(self):
        pass


cw3 = ChatWidget.__new__(ChatWidget)
cw3._released = False
cw3.jid = "room@example"
cw3.is_muc = False
cw3._unread_boundary = {"ref": "m0", "ts": "T0", "sid": ""}
cw3._unread_marker_shown = False
cw3._unread_armed = False
cw3._unread_passed = False
cw3._unread_resolving = False
cw3._seen_unread_refs = set()
cw3._seen_mention_refs = set()
cw3._seen_ref = ""
cw3._seen_ts = ""
cw3._seen_sid = ""
cw3._messages = []
cw3._history = [
    {"direction": "incoming", "sender": "A", "body": "read",
     "timestamp": "T0", "origin_id": "m0"},
    {"direction": "incoming", "sender": "A", "body": "visible",
     "timestamp": "T1", "origin_id": "m1"},
    {"direction": "incoming", "sender": "A", "body": "still unread",
     "timestamp": "T2", "origin_id": "m2"},
]
cw3._view = _MoveView()
remaining = ChatWidget.mark_visible_unread(cw3)
check("advancing the boundary moves the rendered divider",
      remaining == 1 and cw3._view.moved == ["m2"])

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All unread-divider tests passed.")
