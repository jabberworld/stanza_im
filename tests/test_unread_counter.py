"""Unread counting must be deduplicated and based on visible unread rows.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_unread_counter.py
"""
import inspect
import os
import sys
import tempfile
from types import SimpleNamespace

_SCRATCH = tempfile.mkdtemp(prefix="stanza_unread_counter_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.ui.chat_widget import ChatWidget  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _VisibleView:
    def __init__(self, refs=None):
        self.refs = list(refs or [])

    def visible_refs(self):
        return list(self.refs)


def _entry(index: int) -> dict:
    return {
        "direction": "incoming",
        "sender": "pravda",
        "body": f"message {index}",
        "timestamp": f"2026-10-02T10:{index:02d}:00Z",
        "origin_id": f"m-{index}",
        "message_id": f"m-{index}",
    }


def _widget(refs=None) -> ChatWidget:
    widget = ChatWidget.__new__(ChatWidget)
    widget.is_muc = False
    widget._self_nick = ""
    widget._unread_boundary = {"ts": "2026-10-02T09:59:59Z"}
    widget._unread_marker_shown = False
    widget._unread_armed = False
    widget._unread_passed = False
    widget._unread_resolving = False
    widget._released = False
    widget._unread_count = 0
    widget._mention_count = 0
    widget._seen_unread_refs = set()
    widget._seen_mention_refs = set()
    widget._seen_ref = ""
    widget._seen_ts = ""
    widget._seen_sid = ""
    widget._history = [_entry(i) for i in range(70)]
    # The same 70 rows are also present as live entries (the bug: history and
    # live copies were both counted by count_seen_since).
    widget._messages = [dict(entry) for entry in widget._history]
    widget._view = _VisibleView(refs)
    return widget


w = _widget()
seen = w.count_seen_since("2026-10-02T09:59:59Z",
                          "2026-10-02T10:69:00Z")
check("live+history copies are counted once", seen == 70)
check("the unread block is deduplicated", w.unread_total() == 70)
check("outgoing rows do not count", _widget().count_seen_since(
    "2026-10-02T09:59:59Z", "2026-10-02T10:69:00Z") == 70)

# only the first two messages are visible: 70 -> 68, never 66
w = _widget(["m-0", "m-1"])
check("only visible unread messages are removed",
      w.mark_visible_unread() == 68)
check("the same two messages are not removed twice",
      w.mark_visible_unread() == 68)

# all rows visible: the block must be emptied at once
w = _widget([f"m-{i}" for i in range(70)])
check("a fully visible unread block becomes zero",
      w.mark_visible_unread() == 0)

# A MUC row can render the server stanza-id while origin_id is a client UUID.
w = _widget()
w._messages = []
w._history = [{
    "direction": "incoming", "sender": "alice", "body": "server id",
    "timestamp": "2026-10-02T10:00:00Z",
    "origin_id": "client-uuid", "stanza_id": "123456",
    "archive_id": "123456", "message_id": "client-uuid",
}]
w._view = _VisibleView(["123456"])
check("visible server stanza-id removes the matching unread row",
      w.mark_visible_unread() == 0)

# outgoing messages are not part of the unread block
w = _widget()
w._history.insert(10, {
    "direction": "outgoing", "sender": "Me", "body": "mine",
    "timestamp": "2026-10-02T10:10:00Z", "origin_id": "out-1",
    "message_id": "out-1"})
check("outgoing messages are excluded from the unread block",
      w.unread_total() == 70)

# a delayed message older than the read point must not become unread
from stanza_im.ui.main_window import MainWindow  # noqa: E402


class _BumpProbe:
    def __init__(self):
        self._unread_chats = {"room@example": {"unread": 3, "mentions": 0,
                                               "read_ts": "2026-10-02T10:00:00Z",
                                               "seen_ts": "2026-10-02T10:05:00Z"}}
        self._read_state = lambda jid: dict(self._unread_chats[jid])


probe = _BumpProbe()
MainWindow._bump_unread(probe, "room@example",
                        ts="2026-10-02T09:00:00Z", ref="old-1")
check("a delayed older message is not counted unread",
      probe._unread_chats["room@example"]["unread"] == 3)

# An unread conversation with no read/seen anchor is not "already read":
# its whole loaded suffix is unread and set_history must place the separator.
w = _widget()
w._unread_boundary = {"ref": "", "ts": "", "sid": ""}
check("an unread block without an anchor is not empty",
      w.unread_total() == 70)

# The no-anchor sentinel must be truthy so set_history treats it as unread.
main = MainWindow.__new__(MainWindow)
main._unread_chats = {"room@example": {
    "unread": 5, "mentions": 0, "read_ts": "", "read_ref": "",
    "seen_ts": "", "seen_ref": "", "seen_sid": ""}}
anchor = MainWindow._restore_anchor_for(main, "room@example")
check("an unread room without an anchor returns a truthy sentinel",
      bool(anchor) and not anchor.get("ref") and not anchor.get("ts"))

# A background auto-joined tab must not reconcile/clear its stale counter.
class _BackgroundChat:
    def mark_visible_unread(self, move_divider=True):
        return 0

    def mark_visible_mentions(self):
        return 0

    def seen_anchor(self):
        return {}


class _BackgroundWindow:
    def get_chat(self, _jid):
        return _BackgroundChat()

    def current_jid(self):
        return "other@example"


background = MainWindow.__new__(MainWindow)
background._unread_chats = {"room@example": {"unread": 729, "mentions": 0}}
background._chat_window = _BackgroundWindow()
background._chat_area_visible = lambda: False
background._mark_chat_read = lambda _jid: None
MainWindow._apply_visible_unread(background, "room@example")
check("a background room keeps its counter until the user opens it",
      background._unread_chats["room@example"]["unread"] == 729)


class _FakeChat:
    def mark_visible_unread(self, move_divider=True):
        return 68

    def take_seen_move(self):
        return False

    def mark_visible_mentions(self):
        return 0

    def seen_anchor(self):
        return {"ref": "m-1", "ts": "2026-10-02T10:00:00Z",
                "sid": "m-1"}


class _FakeChatWindow:
    def get_chat(self, _jid):
        return _FakeChat()


main = MainWindow.__new__(MainWindow)
main._unread_chats = {"room@example": {
    "unread": 70, "mentions": 0, "read_ts": "2026-10-02T09:59:59Z",
    "seen_ts": ""}}
main._chat_window = _FakeChatWindow()
main._mds_pending_sid = ""
main._mds_pending_jid = ""
main._mds_throttle_ms = 3000
main._mds_throttle_timer = SimpleNamespace(start=lambda *_args: None)
main._recount_unread = lambda: None
main._refresh_unread_badge = lambda _jid: None
main._push_unread_to_chat = lambda _jid: None
main._schedule_unread_save = lambda: None
main._mark_chat_read = lambda _jid: None
MainWindow._on_chat_last_seen(
    main, "room@example", "m-1", "2026-10-02T10:00:00Z", "m-1")
check("the scroll report applies the visible unread count",
      main._unread_chats["room@example"]["unread"] == 68)

# While the read-anchor scroll is in flight the page still reports its
# transient bottom position; trusting it cleared the whole unread block on
# open (walkbook pravda: 13 -> 0 without scrolling).
from stanza_im.ui.chat_view import (  # noqa: E402
    anchor_scroll_guard_open, scroll_offset_changed,
)

check("a real scroll offset change is detected without a dirty flag",
      scroll_offset_changed(100.0, 140.0))
check("an idle poll is not a scroll change",
      not scroll_offset_changed(100.0, 100.5))
check("no previous offset means no scroll change",
      not scroll_offset_changed(None, 140.0))
from stanza_im.ui import chat_view as chat_view_module  # noqa: E402

_view_src = inspect.getsource(chat_view_module.ChatView)
check("the visible-ref cache is keyed by the scroll offset",
      "__stanzaVisibleCacheY" in _view_src)
check("the scroll listener is installed before the bridge setup",
      _view_src.index("addEventListener('scroll'")
      < _view_src.index("if (!window.bridge)"))
check("the first poll after showing a tab is deferred",
      "_show_poll" in _view_src)

_focus_src = inspect.getsource(MainWindow._focus_chat)
check("focus only reconciles chats that still have unread state",
      "needs_unread" in _focus_src)
check("focus only merges a tail when the tab marked one",
      "take_tail_refresh_on_focus" in _focus_src)
check("no anchor scroll means the guard is open",
      anchor_scroll_guard_open(None, [], 0.0))
check("the guard opens once the anchor target is visible",
      anchor_scroll_guard_open({"ref": "m-1", "until": 100.0},
                               ["m-1"], 1.0))
check("the guard stays while the anchor target is off-screen",
      not anchor_scroll_guard_open({"ref": "m-1", "until": 100.0},
                                   ["m-9"], 1.0))
check("a missing anchor target cannot wedge the guard forever",
      anchor_scroll_guard_open({"ref": "m-1", "until": 100.0},
                               [], 101.0))


class _SuspendedChat:
    def __init__(self, view, remaining=0):
        self._view = view
        self._remaining = remaining

    def mark_visible_unread(self, move_divider=True):
        return self._remaining

    def mark_visible_mentions(self):
        return 0

    def seen_anchor(self):
        return {}


class _SuspendedView:
    def __init__(self, suspended):
        self._scroll_suspended = suspended
        self._deferred_scroll = None


class _SuspendedWindow:
    def __init__(self, chat):
        self._chat = chat

    def get_chat(self, _jid):
        return self._chat

    def current_jid(self):
        return "room@example"


suspended = MainWindow.__new__(MainWindow)
suspended._unread_chats = {"room@example": {"unread": 13, "mentions": 0}}
suspended._chat_window = _SuspendedWindow(
    _SuspendedChat(_SuspendedView(True)))
suspended._chat_area_visible = lambda: True
suspended._recount_unread = lambda: None
suspended._refresh_unread_badge = lambda _jid: None
suspended._push_unread_to_chat = lambda _jid: None
suspended._schedule_unread_save = lambda: None
suspended._mark_chat_read = lambda _jid: None
# attempt=16 is the last retry: no further timer is scheduled.
MainWindow._apply_visible_unread(suspended, "room@example", 16)
check("an in-flight anchor scroll does not clear unread on open",
      suspended._unread_chats["room@example"]["unread"] == 13)

suspended._chat_window = _SuspendedWindow(
    _SuspendedChat(_SuspendedView(False), remaining=9))
MainWindow._apply_visible_unread(suspended, "room@example", 16)
check("once the anchor settles only the visible rows are removed",
      suspended._unread_chats["room@example"]["unread"] == 9)


# Opening a chat can mark visible messages seen without a scroll poll; that
# partial progress must reach the shared XEP-0490 node (walkbook/rbook 40 vs 90).
class _SeenChat:
    def __init__(self, view, remaining):
        self._view = view
        self._remaining = remaining

    def mark_visible_unread(self, move_divider=True):
        return self._remaining

    def mark_visible_mentions(self):
        return 0

    def seen_anchor(self):
        return {"ref": "m-1", "ts": "2026-10-02T10:05:00Z", "sid": "sid-1"}


seen_win = MainWindow.__new__(MainWindow)
seen_win._unread_chats = {"room@example": {
    "unread": 70, "mentions": 0, "read_ts": "2026-10-02T09:59:59Z"}}
seen_win._chat_window = _SuspendedWindow(
    _SeenChat(_SuspendedView(False), 68))
seen_win._chat_area_visible = lambda: True
seen_win._mds_pending_sid = ""
seen_win._mds_pending_jid = ""
seen_win._mds_throttle_ms = 3000
seen_win._mds_throttle_timer = SimpleNamespace(start=lambda *_a: None)
seen_win._recount_unread = lambda: None
seen_win._refresh_unread_badge = lambda _jid: None
seen_win._push_unread_to_chat = lambda _jid: None
seen_win._schedule_unread_save = lambda: None
seen_win._mark_chat_read = lambda _jid: None
MainWindow._apply_visible_unread(seen_win, "room@example", 16)
check("a newer seen point is published to the shared MDS node",
      (seen_win._mds_pending_jid, seen_win._mds_pending_sid)
      == ("room@example", "sid-1"))

seen_win._mds_pending_sid = ""
seen_win._mds_pending_jid = ""
seen_win._chat_window = _SuspendedWindow(
    _SeenChat(_SuspendedView(False), 0))
MainWindow._apply_visible_unread(seen_win, "room@example", 16)
check("a fully seen block publishes its displayed point without wiping the divider",
      seen_win._mds_pending_sid == "sid-1"
      and seen_win._mds_pending_jid == "room@example")

# Own MUC echo is stored as incoming but must not be counted as unread.
from stanza_im.core import history  # noqa: E402

room_jid = "muc@conf.example"
history.store_message(room_jid, "incoming", "mine", sender="rain",
                      timestamp="2026-10-02T10:00:00Z",
                      message_id="own-1", origin_id="own-1")
history.store_message(room_jid, "incoming", "other", sender="alice",
                      timestamp="2026-10-02T10:01:00Z",
                      message_id="other-1", origin_id="other-1")
check("history excludes our own MUC echo from unread",
      history.count_incoming_after(room_jid, "2026-10-02T09:00:00Z",
                                   exclude_sender="rain") == 1)
check("history counts other MUC senders normally",
      history.count_incoming_after(room_jid, "2026-10-02T09:00:00Z") == 2)

# Clicking an OSD for the already-current tab must reconcile the visible rows.
from PyQt6 import QtWidgets  # noqa: E402

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _OsdChat:
    def anchor_restore_pending(self):
        return False


class _OsdWindow:
    def get_chat(self, _jid):
        return _OsdChat()

    def current_jid(self):
        return "room@example"


osd = MainWindow.__new__(MainWindow)
osd._chat_window = _OsdWindow()
osd._raise_chat_area = lambda: None
refreshed = []
osd._refresh_visible_state = lambda jid: refreshed.append(jid)
MainWindow._osd_click(osd, "room@example")
_app.processEvents()
check("an OSD click on the current tab refreshes visible unread",
      refreshed == ["room@example"])

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All unread-counter tests passed.")
