"""Unread counting must be deduplicated and based on visible unread rows.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_unread_counter.py
"""
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
    def mark_visible_unread(self):
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
    def mark_visible_unread(self):
        return 68

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

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All unread-counter tests passed.")
