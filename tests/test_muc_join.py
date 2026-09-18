"""Offscreen tests for MUC join reliability (status gating + auto-join).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_join.py
"""
import os
import sys
import tempfile
import time

_SCRATCH = tempfile.mkdtemp(prefix="stanza_mucjoin_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.roster_style import UserItem

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _FakeChat:
    def __init__(self):
        self.statuses = []

    def add_status(self, text, timestamp):
        self.statuses.append(text)

    def update_muc_users(self, users, self_nick=""):
        pass


class _FakeGI:
    nick = "me"
    password = "pw"
    joined = False


class _FakeAutoClient:
    def __init__(self):
        self.autojoin_rooms = {"room@conf.example"}
        self.groupchats = {"room@conf.example": _FakeGI()}
        self.jid_str = "me@example.com/res"
        self.joined = []

    def join_muc(self, room, nick, password="", save_bookmark=True):
        self.joined.append((room, nick, password))


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
win._client = None
win._apply_muc_admin = lambda room: None
win._config.chat.muc_show_presence = True
win._config.chat.muc_show_status = True
win._muc_self_nicks = {"room@conf.example": "me"}
win._muc_joined = set()
win._muc_join_grace = {}
chat = _FakeChat()
win._chat_window.get_chat = lambda room: chat

# 1. presence status lines are gated by the join trigger ----------------------
win._on_groupchat_presence("room@conf.example", "bob", "online", "")
check("no status before muc_joined", chat.statuses == [])

win._muc_joined.add("room@conf.example")
win._muc_join_grace["room@conf.example"] = time.monotonic()
win._on_groupchat_presence("room@conf.example", "carol", "online", "")
check("no status during the grace window", chat.statuses == [])

win._muc_join_grace["room@conf.example"] = time.monotonic() - 5.0
win._on_groupchat_presence("room@conf.example", "dave", "online", "")
check("status shown after the grace window", len(chat.statuses) == 1)

# 2. auto-join retry policy ---------------------------------------------------
win._client = _FakeAutoClient()
win._muc_autojoin_tries = {}
scheduled = []
_orig_single_shot = QtCore.QTimer.singleShot
QtCore.QTimer.singleShot = lambda ms, fn: scheduled.append((ms, fn))
try:
    check("transient failure schedules a retry",
          win._schedule_autojoin_retry("room@conf.example", "timeout")
          and win._muc_autojoin_tries["room@conf.example"] == 1)
    check("first backoff is 5 s", scheduled and scheduled[0][0] == 5000)

    chat.statuses.clear()
    win._on_muc_join_error("room@conf.example", "timeout", "")
    check("transient error does not show a failure yet", chat.statuses == [])

    tries_before = win._muc_autojoin_tries["room@conf.example"]
    win._on_muc_join_error("room@conf.example", "forbidden", "")
    check("permanent error shows a failure", len(chat.statuses) == 1)
    check("permanent error does not retry",
          win._muc_autojoin_tries["room@conf.example"] == tries_before)

    win._schedule_autojoin_retry("room@conf.example", "timeout")  # 2
    win._schedule_autojoin_retry("room@conf.example", "timeout")  # 3
    check("retry count is bounded at three",
          not win._schedule_autojoin_retry("room@conf.example", "timeout"))

    client = win._client
    client.joined.clear()
    win._muc_self_nicks = {}
    scheduled[-1][1]()   # run the last scheduled retry
    check("retry re-joins with the stored nick/password",
          client.joined == [("room@conf.example", "me", "pw")])
finally:
    QtCore.QTimer.singleShot = _orig_single_shot

# 3. bookmarked rooms are classified as conferences even before joining ------
win._client = None
win._bookmarks = {"room@conf.example": {"jid": "room@conf.example"}}
win._conference_roster = set()
win._muc_self_nicks = {}
win._muc_display_name = lambda room: "Room"
win._remember_contact = lambda *a, **k: None
win._schedule_roster_repaint = lambda: None
win._roster.clear()
win._roster.add_user(UserItem(jid="room@conf.example", name="Room",
                              group="Friends"))
win._classify_bookmarked_conferences()
users = [u for u in win._roster._users if u.jid == "room@conf.example"]
check("bookmarked room moved to the conferences group",
      users and users[0].group == "Conferences")
check("bookmarked room registered as a conference",
      "room@conf.example" in win._conference_roster)

# 4. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_client_src = open(os.path.join(_root, "stanza_im", "core", "client.py"),
                   encoding="utf-8").read()
check("auto-join skips only joined rooms",
      "gi is not None and gi.joined" in _client_src)
check("auto-join retries the bookmarks fetch",
      "Bookmarks fetch failed" in _client_src)
check("join_muc cancels a stale join task",
      "old_task.cancel()" in _client_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All MUC-join tests passed.")
