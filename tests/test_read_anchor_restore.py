"""Offscreen tests for resuming an unread chat on its read anchor.

A conversation with unread messages must open with **all** of the new messages
already on screen — there is no forward pager any more.  The persisted read
anchor then only does two things: it places the "unread messages" separator
above the first unseen message and it is the position the window opens at.  The
separator stays in the window until the chat is reopened.

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

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.core import history  # noqa: E402
from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.ui import chat_themes  # noqa: E402
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.chat_widget import ChatWidget  # noqa: E402

i18n_load("en")

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
_cw_src = open(os.path.join(_root, "stanza_im", "ui", "chat_widget.py"),
               encoding="utf-8").read()
_cv_src = open(os.path.join(_root, "stanza_im", "ui", "chat_view.py"),
               encoding="utf-8").read()
_ct_src = open(os.path.join(_root, "stanza_im", "ui", "chat_themes.py"),
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
    w._unread_boundary = {}
    w._unread_marker_shown = False
    w._unread_armed = False
    w._unread_passed = False
    w._unread_resolving = False
    w._anchor_bottom = False
    w._last_sender = None
    w._show_avatars = False
    w._users = []
    w._jump_pending = ""
    w._jump_pages = 0
    w._db_exhausted = False
    w._server_exhausted = False
    w._hist_loading = False
    w._server_fetching = False
    w._window_size = 50
    w._start_task = lambda coro: None
    return w


ANCHOR = {"ref": "m-3", "ts": "2026-10-02T10:03:00Z", "sid": "sid-3"}

# 1. the window holds every message, the anchor only separates the block -------
w = widget()
w.set_history([row("2026-10-02T10:01:00Z", "one", "m-1"),
               row("2026-10-02T10:02:00Z", "two", "m-2"),
               row("2026-10-02T10:03:00Z", "three", "m-3"),
               row("2026-10-02T10:04:00Z", "four", "m-4")],
              50, False, anchor=ANCHOR)
check("the whole window is rendered up front",
      [m["body"] for m in w._view.messages]
      == ["one", "two", "three", "four"])
check("the separator lands above the first message past the anchor",
      [m["body"] for m in w._view.messages if m["unread_marker"]] == ["four"])
check("the boundary is kept for the reopening",
      w.unread_boundary.get("ref") == "m-3")

# 2. no anchor → no separator ---------------------------------------------------
w = widget()
w.set_history([row("2026-10-02T10:01:00Z", "one", "m-1")], 50, False)
check("a re-read conversation carries no separator",
      not any(m["unread_marker"] for m in w._view.messages))
check("the window opens at the newest message", w._anchor_bottom)

# 3. a read point older than the window waits for the archive -------------------
w = widget()
w.set_history([row("2026-10-02T10:04:00Z", "four", "m-4"),
               row("2026-10-02T10:05:00Z", "five", "m-5")],
              50, False, anchor=ANCHOR)
check("an unread block larger than the window defers the separator",
      w._unread_resolving
      and not any(m["unread_marker"] for m in w._view.messages))
w._history = [row("2026-10-02T10:02:00Z", "read", "m-2"),
              row("2026-10-02T10:03:00Z", "last read", "m-3"),
              row("2026-10-02T10:04:00Z", "four", "m-4"),
              row("2026-10-02T10:05:00Z", "five", "m-5")]
w._view.messages = []
w._finish_unread_resolve(w._history[1])
check("the separator is placed once the window is complete",
      [m["body"] for m in w._view.messages if m["unread_marker"]] == ["four"])
check("the resume scrolls to the read point",
      w._view.scrolled == ["m-3"] and not w._unread_resolving)

# 3b. an unresolvable read point falls back to the first message ---------------
w = widget()
w.set_history([row("2026-10-02T10:04:00Z", "four", "m-4")],
              50, False, anchor=ANCHOR)
w._view.messages = []
w._finish_unread_resolve(None)
check("a read point the archive cannot reach marks the first message",
      [m["body"] for m in w._view.messages if m["unread_marker"]] == ["four"])

# 3b2. a timestamp-only read point never waits ---------------------------------
w = widget()
w.set_restore_anchor({"ref": "", "ts": ANCHOR["ts"], "sid": ""})
w.set_history([row("2026-10-02T10:04:00Z", "four", "m-4")],
              50, False, anchor={"ref": "", "ts": ANCHOR["ts"]})
check("a timestamp-only read point also waits for its page",
      w._unread_resolving)
w._view.messages = []
w._restore_from_anchor()
check("a timestamp-only read point places the separator anyway",
      not w._unread_resolving
      and [m["body"] for m in w._view.messages if m["unread_marker"]] == ["four"])

# 3c. the separator is emitted once per render ---------------------------------
w = widget()
w.set_history([row("2026-10-02T10:02:00Z", "two", "m-2"),
               row("2026-10-02T10:03:00Z", "three", "m-3"),
               row("2026-10-02T10:04:00Z", "four", "m-4")],
              50, False, anchor=ANCHOR)
check("a reachable read point separates immediately",
      [m["body"] for m in w._view.messages if m["unread_marker"]] == ["four"])
w._view.messages = []
w._render_all()
check("a re-render re-emits the separator exactly once",
      len([m for m in w._view.messages if m["unread_marker"]]) == 1)

# 4. a timestamp-only anchor falls back to time ---------------------------------
w = widget()
w.set_history([row("2026-10-02T10:01:00Z", "one", "m-1"),
               row("2026-10-02T10:02:00Z", "two", "m-2")],
              50, False, anchor={"ts": "2026-10-02T10:01:30Z"})
check("without a reference the timestamp decides the separator",
      [m["body"] for m in w._view.messages if m["unread_marker"]] == ["two"])
w.set_restore_anchor({"ts": "2026-10-02T10:01:30Z"})
w._restore_from_anchor()
check("a timestamp-only anchor lands on the newest older message",
      w._view.scrolled == ["m-1"])

# 5. unread arriving in a background tab gets its own separator ------------------
w = widget()
w.set_history([row("2026-10-02T10:01:00Z", "one", "m-1")], 50, False)
check("a read tab starts without a boundary", not w.unread_boundary)
w.add_message("Bob", "live", "2026-10-02T10:02:00Z", message_id="m-9")
check("a read tab renders without a separator",
      not any(m["unread_marker"] for m in w._view.messages))
w.note_unread_arrival()
check("a read tab takes the newest message on screen as its boundary",
      w.unread_boundary.get("ts") == "2026-10-02T10:02:00Z")
w.add_message("Bob", "live", "2026-10-02T10:06:00Z", message_id="m-9")
check("an armed tab separates the message that just arrived",
      [m["body"] for m in w._view.messages if m["unread_marker"]] == ["live"])
w.add_message("Bob", "again", "2026-10-02T10:07:00Z", message_id="m-10")
check("later messages are not separated again",
      len([m for m in w._view.messages if m["unread_marker"]]) == 1)
w._view.messages = []
w._render_all()
check("the separator survives a re-render of a background tab",
      [m["body"] for m in w._view.messages if m["unread_marker"]] == ["again"])
w.set_unread_boundary(ANCHOR)
check("the boundary can be dropped again", w.unread_boundary == ANCHOR)

# 6. our own message keeps the separator where it is ----------------------------
w = widget()
w.set_history([row("2026-10-02T10:03:00Z", "three", "m-3")],
              50, False, anchor=ANCHOR)
w.add_message("me", "mine", "2026-10-02T10:06:00Z", direction="outgoing",
              message_id="m-10")
check("our reply stays inside the unread block",
      [m["body"] for m in w._view.messages if m["unread_marker"]] == ["mine"])

# 7. reading the block does not remove the separator ----------------------------
w = widget()
w.set_history([row("2026-10-02T10:04:00Z", "four", "m-4")],
              50, False, anchor=ANCHOR)
w.set_unread_boundary({})
check("clearing the boundary drops it", not w.unread_boundary)

# 8. reaching the bottom marks the conversation read ---------------------------
w = widget()
w.set_history([row("2026-10-02T10:04:00Z", "four", "m-4")],
              50, False, anchor=ANCHOR)
emitted = []
w.bottom_reached.connect(lambda: emitted.append(True))
w.bottom_reached.emit()
check("the bottom of the full window marks the chat read", emitted == [True])
check("the view reports the bottom straight through",
      "view.bottom_reached.connect(self.bottom_reached)" in _cw_src)
check("there is no forward pager left in the widget",
      "load_newer" not in _cw_src and "stanza:newer" not in _cw_src
      and "_forward_bottom_reached" not in _cw_src)
check("there is no forward pager left in the view",
      "stanza-newer" not in _cv_src and "__stanzaNewerRef" not in _cv_src)
check("the archive forward pager is gone",
      not hasattr(history, "load_newer_timestamp")
      and not hasattr(history, "newer_available_timestamp"))

# 9. the theme renders the separator -------------------------------------------
factory = ChatThemeFactory()
html = factory.render_message(sender="Bob", body="hi", timestamp="12:00",
                              direction="incoming", unread_marker=True)
check("the separator is prepended to the message",
      html.startswith('<div class="stanza-unread">'))
check("the separator is not emitted without the flag",
      "stanza-unread" not in factory.render_message(
          sender="Bob", body="hi", timestamp="12:00", direction="incoming"))
check("an action line carries no separator",
      "stanza-unread" not in factory.render_action("Bob", "waves", "12:00"))
check("the separator size is relative, so it follows the chat font",
      "font-size: 0.85em" in chat_themes._UNREAD_CSS)
check("both chat pages carry the separator rule",
      _ct_src.count("{_UNREAD_CSS}") == 2)

# 10. the main window loads the tail and arms background tabs ------------------
load_async = method_source(_mw_src, "_load_history_async")
check("the window is the ordinary tail of the conversation",
      "history.load_history_async(jid, limit=window)" in load_async
      and "until=" not in load_async
      and "newer_available" not in load_async)
check("the anchor only reaches the separator", "anchor=anchor" in load_async)
arm = method_source(_mw_src, "_arm_unread_separator")
check("an unread message arms the separator of an open tab",
      "note_unread_arrival()" in arm
      and "note_unread_arrival()" not in method_source(_mw_src,
                                                       "_bump_unread"))
for handler in ("_on_message_received", "_on_muc_private_message",
                "_on_groupchat_message"):
    body = method_source(_mw_src, handler)
    check(f"{handler} arms the separator before the entry is rendered",
          body.index("_arm_unread_separator") < body.index("add_message"))

# 11. the opening order still protects the read state --------------------------
focus_chat = method_source(_mw_src, "_focus_chat")
check("the window is loaded before the counters are cleared",
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

# 12. the anchor survives a WebEngine document reset ---------------------------
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