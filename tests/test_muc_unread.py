"""Unread counting in conferences and MUC private messages."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core import unread_state
from stanza_im.i18n import tr
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.roster_style import RosterStyle, UserItem
from stanza_im.ui.roster_widget import RosterWidget

FAILURES = []


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    if not ok:
        FAILURES.append(label)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

ROOM = "room@conf.example"


class _Chat:
    """ChatWidget stand-in that only records what was rendered."""

    def __init__(self, jid=""):
        self.jid = jid
        self.is_muc = False
        self.rendered = []

    def add_message(self, **kwargs):
        self.rendered.append(kwargs)

    def add_status(self, *args, **kwargs):
        pass

    def set_self_nick(self, *args, **kwargs):
        pass

    def update_muc_users(self, *args, **kwargs):
        pass

    def set_subject(self, *args, **kwargs):
        pass

    def set_bookmarked(self, *args, **kwargs):
        pass

    def read_anchor(self):
        return {}

    @property
    def _history(self):
        return []



class _ChatWindow:
    def __init__(self, chats=()):
        self._chats = {jid: _Chat(jid) for jid in chats}
        self.current = ""

    def get_chat(self, jid):
        return self._chats.get(jid)

    def open_chat(self, jid, display_name="", focus=True):
        chat = self._chats.setdefault(jid, _Chat(jid))
        self.current = jid
        return chat

    def open_groupchat(self, room, nick, display_name=""):
        chat = self._chats.setdefault(room, _Chat(room))
        chat.is_muc = True
        self.current = room
        return chat

    def set_chat_title(self, *args, **kwargs):
        pass

    def set_muc_title(self, *args, **kwargs):
        pass

    def has_chat(self, jid):
        return jid in self._chats

    def current_jid(self):
        return self.current

    def set_contact_status(self, *args, **kwargs):
        pass


def make_window(chats=()):
    win = MainWindow.__new__(MainWindow)
    win._unread_chats = {}
    win._unread_jids = set()
    win._unread_total = 0
    win._pm_roster = set()
    win._pm_targets = {}
    win._muc_users = {ROOM: {"alice": {"nick": "alice", "show": "online",
                                        "status": "", "real_jid": ""}}}
    win._muc_self_nicks = {ROOM: "me"}
    win._tab_activity = {}
    win._roster = RosterWidget()
    win._roster.set_trailing_groups({tr("roster_group_conferences"),
                                     tr("roster_group_personal_messages")})
    win._chat_window = _ChatWindow(chats)
    win._client = None
    win._schedule_roster_repaint = lambda: None
    win._start_task = lambda coro: coro.close()
    win._maybe_osd_groupchat = lambda *a, **k: None
    win._maybe_osd_message = lambda *a, **k: None
    win._notify_incoming_message = lambda *a, **k: None
    win._remember_contact = lambda *a, **k: None
    win._muc_display_name = lambda room: room
    win._play_sound = lambda *a, **k: None
    win._apply_call_support = lambda *a, **k: None
    win._chat_area_visible = lambda: False
    win._sync_tray_blink = lambda: None
    # The debounced disk write needs a real QTimer on a real window.
    win._schedule_unread_save = lambda: None
    win._recount_unread()
    return win


# 1. a groupchat message counts as unread for the room -----------------------
win = make_window()
win._roster.add_user(UserItem(jid=ROOM, name=ROOM,
                              group=tr("roster_group_conferences"),
                              status="online"))
win._on_groupchat_message(ROOM, "alice", "hello there", "2026-10-02T10:00:00Z")
state = win._read_state(ROOM)
check("a room message counts as unread",
      state["unread"] == 1 and state["mentions"] == 0)
check("the room badge is refreshed",
      next(u for u in win._roster._users
           if u.jid == ROOM).unread_count == 1)

win._on_groupchat_message(ROOM, "alice", "me: are you there?",
                          "2026-10-02T10:01:00Z")
state = win._read_state(ROOM)
check("a message naming our nickname counts as a mention",
      state["unread"] == 2 and state["mentions"] == 1)
check("the composite badge shows both numbers",
      RosterStyle.badge_text(UserItem(jid=ROOM, name=ROOM, group="g",
                                      unread_count=state["unread"],
                                      unread_mentions=state["mentions"])
                             ) == "2 / 1")

win._on_groupchat_message(ROOM, "me", "thanks", "2026-10-02T10:02:00Z")
check("our own room message is not counted",
      win._read_state(ROOM)["unread"] == 2)

win._on_groupchat_message(ROOM, "alice", "old", "2026-10-02T09:00:00Z",
                          archived=True, archive_id="arc-1")
check("an archived replay is not counted",
      win._read_state(ROOM)["unread"] == 2)

# 2. a room on screen is not counted ------------------------------------------
win = make_window()
win._chat_window.open_chat(ROOM)
win._chat_area_visible = lambda: True
win._on_groupchat_message(ROOM, "alice", "me: ping", "2026-10-02T10:00:00Z")
check("a message in the focused room is not unread",
      win._read_state(ROOM)["unread"] == 0)

# 3. a private message counts for its sender ---------------------------------
win = make_window()
win._on_muc_private_message(ROOM, "alice", "psst", "2026-10-02T10:00:00Z")
target = f"{ROOM}/alice"
check("a private message counts for its sender",
      win._read_state(target)["unread"] == 1)
check("the sender gets a roster row",
      any(u.jid == target and u.unread_count == 1
          for u in win._roster._users))
win._on_muc_private_message(ROOM, "alice", "again", "2026-10-02T10:01:00Z")
check("a second private message counts too",
      win._read_state(target)["unread"] == 2)

target = f"{ROOM}/alice"
win = make_window(chats=(target,))
win._chat_area_visible = lambda: True
win._chat_window.open_chat(target)
win._on_muc_private_message(ROOM, "alice", "psst", "2026-10-02T10:01:00Z")
check("a private message in the focused chat is not unread",
      win._read_state(target)["unread"] == 0)

# 4. opening a conference from the roster clears its counters ------------------
win = make_window(chats=(ROOM,))
win._bump_unread(ROOM, mention=True)
win._bookmarks = {}
win._apply_muji_support = lambda *a, **k: None
win._apply_muc_admin = lambda *a, **k: None
win._load_history = lambda *a, **k: None
win._reset_unread = MainWindow._reset_unread.__get__(win)
win._on_contact_open(ROOM)
check("opening a conference marks it read",
      win._read_state(ROOM)["unread"] == 0
      and win._read_state(ROOM)["mentions"] == 0)

# 5. the read anchor comes from the newest displayed message -------------------
chat = ChatWidget("bob@example.com", "Bob", ChatThemeFactory())
chat._history = [
    {"sender": "Bob", "body": "one", "timestamp": "2026-10-02T10:00:00Z",
     "direction": "incoming", "origin_id": "m-1", "message_id": "m-1"},
    {"sender": "Bob", "body": "two", "timestamp": "2026-10-02T10:01:00Z",
     "direction": "incoming", "archive_id": "arc-2", "origin_id": "m-2"},
]
anchor = chat.read_anchor()
check("the anchor prefers the server stanza-id",
      anchor["ref"] == "arc-2" and anchor["sid"] == "arc-2"
      and anchor["ts"] == "2026-10-02T10:01:00Z")
check("an empty conversation has no anchor",
      ChatWidget("x@y", "X", ChatThemeFactory()).read_anchor() == {})

# 6. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
_cw_src = open(os.path.join(_root, "stanza_im", "ui", "chat_widget.py"),
               encoding="utf-8").read()
check("the room counts mentions from the highlight rule",
      "self._bump_unread(room, mention=is_mention)" in _mw_src
      and "is_mention = bool(self_nick and nick != self_nick" in _mw_src)
check("a private message counts for its chat key",
      "self._bump_unread(target)" in _mw_src)
check("marking read stores an anchor",
      "entry[\"read_ref\"] = str(anchor.get(\"ref\") or \"\")" in _mw_src
      and "def read_anchor(self)" in _cw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All MUC-unread tests passed.")