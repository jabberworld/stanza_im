"""Offscreen tests for resuming an unread chat from its read anchor.

A conversation with unread messages must open on the message block the user
left off at instead of the very end of the archive: the window loaded from
SQLite ends at the stored anchor, and the newer messages are fetched forward
only when the user asks for them.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_read_anchor_restore.py
"""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_anchor_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core import history
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
_cw_src = open(os.path.join(_root, "stanza_im", "ui", "chat_widget.py"),
               encoding="utf-8").read()
_cv_src = open(os.path.join(_root, "stanza_im", "ui", "chat_view.py"),
               encoding="utf-8").read()

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def method_source(src, name):
    """The body of ``<class>.<name>`` from the bundled source."""
    start = src.index(f"def {name}(")
    end = src.find("\n    def ", start + 1)
    return src[start:end if end > 0 else len(src)]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _View:
    """Recording ChatView stand-in (no WebEngine, no layout)."""

    def __init__(self):
        self.messages = []
        self.statuses = []
        self.marker = ""
        self.scrolled = []
        self.cleared = 0

    def clear(self):
        self.cleared += 1
        self.messages = []
        self.statuses = []

    def add_message(self, **kwargs):
        self.messages.append(kwargs)

    def add_status(self, text, ts=""):
        self.statuses.append(text)

    def set_newer_marker(self, html):
        self.marker = html or ""

    def scroll_to_message(self, message_id, highlight=True):
        self.scrolled.append(message_id)

    def scroll_fraction(self):
        return 1.0

    def is_scrolled_up(self):
        return False

    def __getattr__(self, name):
        return lambda *a, **k: None


def row(stamp, body, mid, direction="incoming", sender="Bob"):
    return {"sender": sender, "body": body, "timestamp": stamp,
            "direction": direction, "origin_id": mid, "message_id": mid}


class _Emitter:
    """A stand-in for a pyqtBoundSignal on an uninitialised widget."""

    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in self.slots:
            slot(*args)


class _Widget(ChatWidget):
    """ChatWidget with a recordable ``bottom_reached`` (no QWidget init)."""

    bottom_reached = _Emitter()


def widget(jid="bob@example.com"):
    w = _Widget.__new__(_Widget)
    w.jid = jid
    w.display_name = "Bob"
    w.is_muc = False
    w._view = _View()
    w._history = []
    w._messages = []
    w._status_lines = []
    w._cleared = False
    w._preserve_fraction = None
    w._restore_anchor = {}
    w._released = False
    w._truncate_newer = False
    w._newer_anchor = ""
    w._newer_loading = False
    w._anchor_bottom = False
    w._last_sender = None
    w._show_avatars = False
    w._users = []
    return w


ANCHOR = {"ref": "m-3", "ts": "2026-10-02T10:02:00Z", "sid": "sid-3"}

# 1. forward paging in the local archive --------------------------------------
JID = "paging@example.com"
for i in range(1, 6):
    history.store_message(JID, "incoming", f"m{i}",
                          timestamp=f"2026-10-02T10:0{i}:00Z",
                          origin_id=f"m{i}")

newer = history.load_newer_timestamp(JID, "2026-10-02T10:03:00Z")
check("forward paging is strict and oldest-first",
      [r["body"] for r in newer] == ["m4", "m5"])
check("more to come is reported as a flag",
      history.newer_available_timestamp(JID, "2026-10-02T10:03:00Z") is True)
check("the newest row has nothing after it",
      history.newer_available_timestamp(JID, "2026-10-02T10:05:00Z") is False)
check("a first page is bounded by the requested limit",
      len(history.load_newer_timestamp(JID, "2026-10-01T00:00:00Z",
                                       limit=2)) == 2)
check("the async wrappers mirror the sync results",
      [r["body"] for r in
       run(history.load_newer_timestamp_async(JID, "2026-10-02T10:03:00Z"))]
      == ["m4", "m5"]
      and run(history.newer_available_timestamp_async(
          JID, "2026-10-02T10:03:00Z")) is True)

# 2. the anchor window renders history only ------------------------------------
w = widget()
w.set_history([row("2026-10-02T10:01:00Z", "one", "m-1"),
               row("2026-10-02T10:02:00Z", "two", "m-2")],
              50, False, anchor=ANCHOR)
w._messages = [row("2026-10-02T10:03:00Z", "three", "m-3")]
w._render_all()
check("the tab is anchored at the read point", w.truncated_at_anchor)
check("messages newer than the anchor stay hidden",
      [m["body"] for m in w._view.messages] == ["one", "two"])
check("live messages are kept in memory",
      len(w._messages) == 1 and w._messages[0]["body"] == "three")
check("a forward marker is offered", "stanza:newer:" in w._view.marker)
check("the marker counts the hidden messages", "1" in w._view.marker)

w = widget()
w.set_history([row("2026-10-02T10:01:00Z", "one", "m-1")],
              50, False, anchor=ANCHOR)
check("a hidden conversation resumes on its anchor", w.truncated_at_anchor)
check("the main window keeps the anchor out of a re-read conversation",
      "window_anchor = anchor" in method_source(_mw_src, "_load_history_async")
      and "window_anchor = None" in method_source(_mw_src, "_load_history_async"))
check("the anchor window is skipped when the archive holds nothing newer",
      "newer_available_timestamp_async" in
      method_source(_mw_src, "_load_history_async"))

# 3. the timestamp fallback still finds the anchor -----------------------------
w = widget()
w.set_history([row("2026-10-02T10:01:00Z", "one", "m-1"),
               row("2026-10-02T10:02:00Z", "two", "m-2")],
              50, False, anchor={"ts": "2026-10-02T10:01:30Z"})
w.set_restore_anchor({"ts": "2026-10-02T10:01:30Z"})
w._restore_from_anchor()
check("a timestamp-only anchor lands on the newest older message",
      w._view.scrolled == ["m-1"])

# 4. reaching the bottom of an anchored window is not "caught up" -------------
w = widget()
w.set_history([row("2026-10-02T10:02:00Z", "two", "m-2")],
              50, False, anchor=ANCHOR)
emitted = []
w.bottom_reached.connect(lambda: emitted.append(True))
w._forward_bottom_reached()
check("the bottom of an anchored window marks nothing read", not emitted)
w._set_truncated(False)
w._forward_bottom_reached()
check("after catching up the bottom marks the chat read", emitted == [True])

# 5. forwarding pages until the hidden block is complete ----------------------
PAGE = [row("2026-10-02T10:03:00Z", "three", "m-3"),
        row("2026-10-02T10:04:00Z", "four", "m-4")]
LATER = [row("2026-10-02T10:05:00Z", "five", "m-5")]


def paged(rows, more):
    """Run one forward page with a stubbed archive."""
    async def load(jid, since, limit=200):
        return list(rows)
    history.load_newer_timestamp_async = load
    history.newer_available_timestamp_async = lambda jid, since: _true(more)

    async def has_more(jid, since):
        return more
    history.newer_available_timestamp_async = has_more


def _true(value):
    return bool(value)


w = widget()
w.set_history([row("2026-10-02T10:02:00Z", "two", "m-2")],
              50, False, anchor=ANCHOR)
paged(PAGE, True)
run(w._load_newer_batch_async())
check("a page keeps the window anchored",
      w.truncated_at_anchor and w._newer_anchor == "2026-10-02T10:04:00Z")
check("the page is appended to the rendered history",
      [m["body"] for m in w._view.messages] == ["two", "three", "four"])
check("the marker stays while more rows remain", w._view.marker != "")

w = widget()
w.set_history([row("2026-10-02T10:02:00Z", "two", "m-2")],
              50, False, anchor=ANCHOR)
paged(LATER, False)
run(w._load_newer_batch_async())
check("the last page releases the anchor",
      not w.truncated_at_anchor and w._newer_anchor == "")
check("the whole conversation is rendered afterwards",
      [m["body"] for m in w._view.messages] == ["two", "five"])
check("the marker is gone once caught up", w._view.marker == "")

# 6. incoming messages only move the marker, outgoing ones catch up -----------
w = widget()
w.set_history([row("2026-10-02T10:02:00Z", "two", "m-2")],
              50, False, anchor=ANCHOR)
w._view.messages = []
w.add_message("Bob", "live", "2026-10-02T10:06:00Z", message_id="m-9")
check("an incoming message is not rendered inside the anchor window",
      w._view.messages == [] and w.truncated_at_anchor)
check("it still counts towards the marker", "1" in w._view.marker)
w.add_message("me", "mine", "2026-10-02T10:07:00Z", direction="outgoing",
              message_id="m-10")
check("our own message catches the window up", not w.truncated_at_anchor)
check("the whole window is visible after catching up",
      [m["body"] for m in w._view.messages] == ["two", "live", "mine"])

# 7. a re-read conversation is never pulled back ------------------------------
w = widget()
w.set_history([row("2026-10-02T10:01:00Z", "one", "m-1")], 50, False)
check("without an anchor the tab shows the newest messages",
      not w.truncated_at_anchor)
w._render_all()
check("live messages are rendered too",
      [m["body"] for m in w._view.messages] == ["one"])
w._truncate_newer = True
w._newer_anchor = "2026-10-02T10:01:00Z"

async def _refresh():
    entries = await history.load_history_async(JID, limit=50)
    w._preserve_fraction = w._view.scroll_fraction()
    w._set_truncated(False)
    w._history = entries
    w._render_all()

run(_refresh())
check("refreshing the history drops the anchor window",
      not w.truncated_at_anchor and w._newer_anchor == "")


# 8. the main window resumes the conversation on focus ------------------------
focus_chat = method_source(_mw_src, "_focus_chat")
check("the anchor window is loaded before the counters are cleared",
      "if anchor:" in focus_chat
      and focus_chat.index("self._load_history(jid, anchor)")
      < focus_chat.index("self._reset_unread(jid, anchor or None)"))
check("a hidden tab loads its archive when it is first shown",
      "elif is_new or not chat._history:" in focus_chat)
check("repeated loads of one conversation are collapsed",
      "if jid in self._history_loading:" in
      method_source(_mw_src, "_load_history"))
check("an anchored window is not restored by a background auto-join",
      "anchor" not in method_source(_mw_src, "_on_muc_joined"))

# 9. the anchor survives a WebEngine document reset ---------------------------
scroll_to_message = method_source(_cv_src, "scroll_to_message")
on_load = method_source(_cv_src, "_on_load_finished")
check("a scroll to the anchor waits for a loaded page",
      "if not self._ready or self._pending:" in scroll_to_message
      and 'self._deferred_scroll = ("message"' in scroll_to_message)
check("the deferred scroll is replayed once the page finished loading",
      "self._flush_deferred_scroll()" in on_load)
check("buffered messages are in the DOM before the scroll is replayed",
      on_load.index("self._append_chunk(chunk)")
      < on_load.index("self._flush_deferred_scroll()"))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All read-anchor tests passed.")
sys.exit(0)
