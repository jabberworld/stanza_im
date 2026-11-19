"""Offscreen tests for session-only XEP-0333 read receipts.

The delivery check (XEP-0184) and the read eye (XEP-0333) are separate
indicators.  The eye is never persisted to SQLite; MUC viewers are collected
for the current session and their names are capped in the tooltip.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_read_receipts.py
"""
import os
import sys
import tempfile

os.environ["XDG_DATA_HOME"] = os.path.join(tempfile.mkdtemp(), "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tempfile.mkdtemp(), "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class View:
    def __init__(self):
        self.read = []

    def mark_message_read(self, ref, title=""):
        self.read.append((ref, title))

    def __getattr__(self, name):
        return lambda *a, **k: None


def widget(is_muc=False):
    w = ChatWidget.__new__(ChatWidget)
    w.jid = "room@conf.example" if is_muc else "bob@example.com"
    w.is_muc = is_muc
    w._self_nick = "me" if is_muc else ""
    w._view = View()
    w._messages = []
    w._history = []
    return w


# 1. Outgoing displayed marker becomes a read eye ----------------------------
w = widget()
w._messages.append({"sender": "Me", "body": "hi", "direction": "outgoing",
                    "message_id": "m1", "origin_id": "m1"})
w.mark_message_read("m1", "Bob")
check("the viewer is stored on the outgoing row",
      w._messages[0].get("read_by") == ["Bob"])
check("the view is updated with the read title",
      w._view.read and w._view.read[-1][0] == "m1")
check("a 1:1 tooltip says Seen", w._view.read[-1][1] == "Seen")
w.mark_message_read("m1", "Bob")
check("a repeated viewer is not duplicated",
      w._messages[0].get("read_by") == ["Bob"])

# 2. Incoming messages never get a read eye ---------------------------------
w = widget()
w._messages.append({"sender": "Bob", "body": "hi", "direction": "incoming",
                    "message_id": "m2", "origin_id": "m2"})
w.mark_message_read("m2", "Bob")
check("incoming rows are ignored", "read_by" not in w._messages[0])
check("the view is not touched for an incoming row", w._view.read == [])

# 3. MUC viewers are listed and capped --------------------------------------
w = widget(is_muc=True)
w._messages.append({"sender": "me", "body": "to room", "direction": "outgoing",
                    "message_id": "m3", "origin_id": "m3"})
for i in range(12):
    w.mark_message_read("m3", f"user{i}")
check("all MUC viewers are kept for the session",
      len(w._messages[0]["read_by"]) == 12)
title = w._view.read[-1][1]
check("the MUC tooltip names the first ten viewers",
      "user0" in title and "user9" in title)
check("the MUC tooltip counts the rest",
      "and 2 more" in title)
check("the MUC tooltip does not list the eleventh name", "user10" not in title)

# 4. Theme rendering: eye only on outgoing messages --------------------------
theme = ChatThemeFactory()
out = theme.render_message("Me", "hello", "10:00", "outgoing",
                           read_title="Seen")
inc = theme.render_message("Bob", "hello", "10:00", "incoming",
                           read_title="Seen")
check("outgoing HTML carries the eye", "read-receipt" in out
      and "\U0001F441" in out)
check("outgoing HTML carries the tooltip", 'title="Seen"' in out)
check("incoming HTML never carries the eye", "read-receipt" not in inc)
plain = ChatThemeFactory().render_message("Me", "hello", "10:00", "outgoing")
check("an unread outgoing message carries no eye", "read-receipt" not in plain)

# 5. Re-rendering keeps the session read state ------------------------------
src = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "stanza_im", "ui", "chat_widget.py"),
    encoding="utf-8").read()
check("the read title is part of the re-render kwargs",
      '"read_title": self._read_receipt_title(entry)' in src)

# 6. MainWindow routes 1:1 and MUC displayed markers separately --------------
class ChatWindow:
    def __init__(self):
        self.chats = {}
        self.calls = []

    def get_chat(self, jid):
        return self.chats.get(jid)

    def current_jid(self):
        return ""


class Chat:
    def __init__(self):
        self.reads = []

    def mark_message_read(self, ref, viewer=""):
        self.reads.append((ref, viewer))


def main_window():
    mw = MainWindow.__new__(MainWindow)
    mw._config = SimpleNamespace(chat=SimpleNamespace(show_receipts=True))
    mw._chat_window = ChatWindow()
    mw._pm_targets = {}
    mw._muc_self_nicks = {"room@conf.example": "me"}
    mw._known_conferences = set()
    mw._conference_roster = set()
    mw._muc_joined = set()
    mw._bookmarks = set()
    mw._is_conference_jid = lambda jid: jid == "room@conf.example"
    mw._roster_name = lambda jid: "Bob" if jid == "bob@example.com" else ""
    return mw


mw = main_window()
one = Chat()
mw._chat_window.chats["bob@example.com"] = one
MainWindow._on_chat_marker_displayed(mw, "bob@example.com/phone", "m1")
check("a 1:1 displayed marker reaches the bare-JID chat",
      one.reads == [("m1", "Bob")])

room = Chat()
mw._chat_window.chats["room@conf.example"] = room
MainWindow._on_chat_marker_displayed(mw, "room@conf.example/Alice", "m2")
check("a MUC displayed marker reaches the room chat",
      room.reads == [("m2", "Alice")])

if FAILURES:
    print("\nFAILURES:", FAILURES)
    sys.exit(1)
print("\nAll read-receipt tests passed.")
