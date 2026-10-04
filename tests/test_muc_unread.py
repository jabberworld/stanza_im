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

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
_cw_src = open(os.path.join(_root, "stanza_im", "ui", "chat_widget.py"),
               encoding="utf-8").read()

ROOM = "room@conf.example"


class _Chat:
    """ChatWidget stand-in that only records what was rendered."""

    def __init__(self, jid=""):
        self.jid = jid
        self.is_muc = False
        self.rendered = []
        self.mentions = []
        self.unread_armed = 0
        self.at_bottom_flag = False
        self.read_marks = 0

    def add_message(self, **kwargs):
        # The separator has to be armed before the entry is rendered, so the
        # order of the two calls is recorded with every message.
        self.rendered.append((self.unread_armed, kwargs))

    def note_unread_arrival(self):
        self.unread_armed += 1

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

    def set_restore_anchor(self, anchor):
        pass

    def note_unread_mention(self, ref_id):
        self.mentions.append(ref_id)

    def mark_mentions_read(self):
        self.mentions = []

    def at_bottom(self):
        return self.at_bottom_flag

    def mark_read(self):
        self.read_marks += 1

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

# 1b. an open background room arms its separator before the entry is drawn ----
win = make_window()
win._roster.add_user(UserItem(jid=ROOM, name=ROOM,
                              group=tr("roster_group_conferences"),
                              status="online"))
room_chat = win._chat_window.open_groupchat(ROOM, "me", ROOM)
win._on_groupchat_message(ROOM, "alice", "first", "2026-10-02T10:00:00Z")
win._on_groupchat_message(ROOM, "me", "mine", "2026-10-02T10:01:00Z")
win._on_groupchat_message(ROOM, "alice", "second", "2026-10-02T10:02:00Z")
check("a backgrounded room arms the separator before rendering",
      [armed for armed, _ in room_chat.rendered] == [1, 1, 2])

# 2. a room on screen is not counted ------------------------------------------
win = make_window()
win._chat_window.open_chat(ROOM)
win._chat_area_visible = lambda: True
win._on_groupchat_message(ROOM, "alice", "me: ping", "2026-10-02T10:00:00Z")
check("a message in the focused room is not unread",
      win._read_state(ROOM)["unread"] == 0)
check("a focused room arms no separator",
      not win._chat_window.get_chat(ROOM).unread_armed)

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

# 4. opening a conference from the roster does not mark it read ----------------
win = make_window(chats=(ROOM,))
win._bump_unread(ROOM, mention=True)
win._bookmarks = {}
win._apply_muji_support = lambda *a, **k: None
win._apply_muc_admin = lambda *a, **k: None
win._load_history = lambda *a, **k: None
win._reset_unread = MainWindow._reset_unread.__get__(win)
win._on_contact_open(ROOM)
check("opening a conference leaves it unread",
      win._read_state(ROOM)["unread"] == 1
      and win._read_state(ROOM)["mentions"] == 1)
check("an unopened chat is never marked read by the divider",
      win._chat_window.get_chat(ROOM).read_marks == 0)

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

# 6. resuming an unread conversation from its read anchor ----------------------
win = make_window(chats=("bob@example.com",))
win._store_read_state("bob@example.com",
                      {"read_ref": "arc-9",
                       "read_ts": "2026-10-02T09:00:00Z"})
win._bump_unread("bob@example.com")
check("the stored anchor is kept for an unread chat",
      win._restore_anchor_for("bob@example.com")
      == {"ref": "arc-9", "ts": "2026-10-02T09:00:00Z",
          "sid": ""})
class _Button:
    """ToolButton stand-in recording its visibility."""

    def __init__(self):
        self.visible_flag = False
        self.text_value = ""
        self.tip = ""

    def setVisible(self, flag):
        self.visible_flag = bool(flag)

    def setText(self, text):
        self.text_value = text

    def setToolTip(self, tip):
        self.tip = tip


def method_source(src, name):
    """The body of ``MainWindow.<name>`` from the bundled source."""
    start = src.index(f"def {name}(")
    end = src.find("\n    def ", start + 1)
    return src[start:end if end > 0 else len(src)]


win = make_window(chats=("bob@example.com",))
win._reset_unread = MainWindow._reset_unread.__get__(win)
win._bump_unread("bob@example.com")
check("an unread conversation is tracked in the unread set",
      "bob@example.com" in win._unread_jids)
win._reset_unread("bob@example.com")
check("marking read leaves the unread set",
      "bob@example.com" not in win._unread_jids and win._unread_total == 0)

contact_open = method_source(_mw_src, "_on_contact_open")
check("the restore anchor is taken before the tab is opened",
      contact_open.index("restore_anchor = self._restore_anchor_for(jid)")
      < contact_open.index("open_chat(jid, display_name)")
      < contact_open.index("self._focus_chat(jid, chat"))
check("opening a chat suppresses the tab_focused handler",
      "self._opening_chat = True" in contact_open
      and "self._opening_chat = False" in contact_open)
focus_chat = method_source(_mw_src, "_focus_chat")
check("the anchor is applied to the tab that is being opened",
      "chat.set_restore_anchor(anchor)" in focus_chat
      and "self._load_history(jid, anchor)" in focus_chat
      and "self._reset_unread(" not in focus_chat)
check("a hidden tab without history loads its archive on focus",
      "elif is_new or not chat._history:" in focus_chat)
tab_focused = method_source(_mw_src, "_on_tab_focused")
check("focusing an existing tab resumes it from the anchor",
      "if self._opening_chat:" in tab_focused
      and "self._focus_chat(jid, self._chat_window.get_chat(jid))"
      in tab_focused)
pm_click = method_source(_mw_src, "_on_muc_participant_clicked")
check("a private chat is resumed the same way",
      pm_click.index("self._opening_chat = True")
      < pm_click.index("open_chat(target, nick)")
      and "self._focus_chat(target, chat)" in pm_click)
tray_cycle = method_source(_mw_src, "_on_tray_cycle_unread")
check("tray cycling does not overwrite the anchor with the newest message",
      "self._reset_unread" not in tray_cycle)


class _View:
    """ChatView stand-in recording the requested scroll target."""

    def __init__(self):
        self.scrolled = []

    def scroll_to_message(self, message_id, highlight=True):
        self.scrolled.append(message_id)


def bare_chat(jid="bob@example.com"):
    """A ChatWidget with only the buffers ``_restore_from_anchor`` touches."""
    widget = ChatWidget.__new__(ChatWidget)
    widget.jid = jid
    widget.is_muc = False
    widget._history = []
    widget._messages = []
    widget._released = False
    widget._jump_pending = ""
    widget._jump_pages = 0
    widget._restore_anchor = {}
    widget._view = _View()
    widget.jumped = []
    widget._jump_to_message = lambda ref: widget.jumped.append(ref)
    return widget


anchor = {"ref": "arc-2", "ts": "2026-10-02T10:01:00Z", "sid": "arc-2"}
widget = bare_chat()
widget._history = [
    {"timestamp": "2026-10-02T10:00:00Z", "origin_id": "m-1",
     "direction": "incoming"},
    {"timestamp": "2026-10-02T10:01:00Z", "archive_id": "arc-2",
     "origin_id": "m-2", "direction": "incoming"},
]
widget.set_restore_anchor(anchor)
widget._restore_from_anchor()
check("the view opens on the anchor message",
      widget._view.scrolled == ["m-2"] and widget.jumped == [])
check("the anchor is applied only once", widget._restore_anchor == {})

widget = bare_chat()
widget._history = [
    {"timestamp": "2026-10-02T09:30:00Z", "origin_id": "m-0",
     "direction": "incoming"},
    {"timestamp": "2026-10-02T11:00:00Z", "origin_id": "m-9",
     "direction": "incoming"},
]
widget.set_restore_anchor({"ts": "2026-10-02T10:01:00Z"})
widget._restore_from_anchor()
check("a timestamp-only anchor falls back to the newest older message",
      widget._view.scrolled == ["m-0"] and widget.jumped == [])

widget = bare_chat()
widget.set_restore_anchor({"ref": "arc-77", "ts": "2026-10-02T10:01:00Z"})
widget._restore_from_anchor()
check("an unresolvable anchor pages the local archive",
      widget._view.scrolled == [] and widget.jumped == ["arc-77"])

widget = bare_chat()
widget.set_restore_anchor({})
widget._restore_from_anchor()
check("a read conversation is not moved", widget._view.scrolled == [])

# 7. reaching the bottom of the active chat marks it read -----------------------
class _Client:
    """Records the XEP-0490 displayed states the client publishes."""

    def __init__(self):
        self.displayed = []

    def mds_mark_displayed(self, jid):
        self.displayed.append(jid)


win = make_window(chats=("bob@example.com",))
win._reset_unread = MainWindow._reset_unread.__get__(win)
win._on_chat_reached_bottom = MainWindow._on_chat_reached_bottom.__get__(win)
win._chat_at_bottom = MainWindow._chat_at_bottom.__get__(win)
win._bump_unread("bob@example.com")
chat = win._chat_window.get_chat("bob@example.com")
win._chat_window.current = "bob@example.com"
win._chat_area_active = lambda: False
win._on_chat_reached_bottom("bob@example.com")
check("a background tab reaching the bottom stays unread",
      win._read_state("bob@example.com")["unread"] == 1
      and chat.read_marks == 0)
win._chat_window.current = "carol@example.com"
win._chat_area_active = lambda: True
win._on_chat_reached_bottom("bob@example.com")
check("another tab's bottom does not clear this conversation",
      win._read_state("bob@example.com")["unread"] == 1
      and chat.read_marks == 0)
win._chat_window.current = "bob@example.com"
win._client = _Client()
win._on_chat_reached_bottom("bob@example.com")
check("the active chat at the bottom is marked read",
      win._read_state("bob@example.com")["unread"] == 0
      and "bob@example.com" not in win._unread_jids)
check("reaching the bottom takes the divider away in place",
      chat.read_marks == 1)
check("reaching the bottom publishes the displayed state",
      win._client.displayed == ["bob@example.com"])

_cw_window_src = open(os.path.join(
    _root, "stanza_im", "ui", "chat_window.py"), encoding="utf-8").read()
_cv_src = open(os.path.join(_root, "stanza_im", "ui", "chat_view.py"),
               encoding="utf-8").read()
check("the bottom report is relayed to the main window",
      "view.bottom_reached.connect(self.bottom_reached)" in _cw_src
      and "widget.bottom_reached.connect(" in _cw_window_src
      and "self.bottom_reached.emit(j)" in _cw_window_src
      and "self._chat_window.bottom_reached.connect(self._on_chat_reached_bottom)"
      in _mw_src)
check("the bottom report is edge-triggered",
      _cv_src.count("def _note_bottom(self") == 2
      and _cv_src.count("self._at_bottom_hit = True\n            self.bottom_reached.emit()") == 2
      and "_at_bottom_hit = False" in _cv_src)
check("a deferred anchor scroll never reports the bottom",
      "if self._scroll_suspended or self._deferred_scroll is not None:"
      in method_source(_cv_src, "_note_bottom"))
check("the parked scroll keeps the report suspended until it is applied",
      "self._scroll_suspended = True" in
      method_source(_cv_src, "scroll_to_message")
      and "self._scroll_suspended = False" in
      method_source(_cv_src, "_flush_deferred_scroll"))

# 8. the @ button walks the unread mentions ------------------------------------
widget = bare_chat()
widget._mention_refs = []
widget._mention_btn = _Button()
widget._history = [
    {"timestamp": "2026-10-02T10:00:00Z", "origin_id": "m-1",
     "direction": "incoming"},
    {"timestamp": "2026-10-02T10:05:00Z", "origin_id": "m-2",
     "direction": "incoming"},
]
widget.note_unread_mention("m-1")
widget.note_unread_mention("m-2")
widget.note_unread_mention("m-1")
check("the @ button shows while a mention is unread",
      widget._mention_btn.visible_flag is True
      and widget.unread_mention_count() == 2)
widget._jump_to_next_mention()
check("the mentions are walked in arrival order",
      widget._view.scrolled == ["m-1"] and widget.unread_mention_count() == 1)
widget.mark_mentions_read()
check("marking read drops the pending mentions",
      widget.unread_mention_count() == 0
      and widget._mention_btn.visible_flag is False)

widget = bare_chat()
widget._mention_refs = []
widget._mention_btn = _Button()
widget.jumped = []
widget.note_unread_mention("arc-old")
widget._jump_to_next_mention()
check("a mention outside the window pages the local archive",
      widget.jumped == ["arc-old"] and widget.unread_mention_count() == 0)

# 9. static wiring ------------------------------------------------------------
check("the room counts mentions from the highlight rule",
      "self._bump_unread(room, mention=is_mention)" in _mw_src
      and "is_mention = bool(self_nick and nick != self_nick" in _mw_src)
check("a private message counts for its chat key",
      "self._bump_unread(target)" in _mw_src)
check("an unread mention is handed to the tab",
      "chat.note_unread_mention(ref_id)" in _mw_src
      and "if is_mention:\n                self._note_unread_mention("
      in _mw_src
      and "chat.mark_mentions_read()" in _mw_src
      and "def _jump_to_next_mention(self)" in _cw_src)
check("marking read stores an anchor",
      "entry[\"read_ref\"] = str(anchor.get(\"ref\") or \"\")" in _mw_src
      and "def read_anchor(self)" in _cw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All MUC-unread tests passed.")