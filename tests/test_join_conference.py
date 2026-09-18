"""Offscreen smoke tests for MUC join JID construction.

The join dialogs returned room and server separately; the callers used to
drop the server, so a join of ``room`` on server ``linuxoid.in`` produced
the bare JID ``room`` (no @domain), and disco#info was sent to ``to=linuxoid``
(remote-server-not-found).  Verify ``_join_muc(..., server=...)`` builds the
full ``room@server`` JID and that a room that already carries ``@`` is left
untouched.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_join_conference.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_join_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets
from stanza_im.ui.main_window import MainWindow

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _FakeChat:
    def __init__(self):
        self.self_nick = None
        self.bookmarked = None

    def set_self_nick(self, nick):
        self.self_nick = nick

    def update_muc_users(self, users, self_nick=""):
        pass

    def add_status(self, *_a):
        pass

    def set_bookmarked(self, flag):
        self.bookmarked = flag


class _FakeChatWindow:
    def __init__(self):
        self.open_jids = []
        self.chat = _FakeChat()

    def has_chat(self, jid):
        return False

    def get_chat(self, jid):
        return self.chat

    def open_groupchat(self, jid, nick, display_name):
        self.open_jids.append(jid)

    def set_muji_support(self, room, enabled):
        pass

    def set_muji_active(self, room, active, video=False):
        pass

    def set_muc_admin(self, room, can_manage):
        pass


class _FakeClient:
    def __init__(self):
        self.joined = []
        self.info = []
        self.cards = []

    def get_contact(self, jid):
        return None

    def join_muc(self, room, nick, **kwargs):
        self.joined.append([room, nick, kwargs])

    def get_muc_info(self, room):
        self.info.append(room)

    def get_vcard(self, jid, force=False):
        self.cards.append(jid)

    def save_bookmark(self, room, nick, password, autojoin=False, name=""):
        self.bookmarked = [room, nick, password, autojoin, name]


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
win = MainWindow(app)
win._idle_timer.stop()
win._chat_window = _FakeChatWindow()
win._client = _FakeClient()
win._start_task = lambda coro: None
win._load_history = lambda jid: None
win._request_vcard = lambda jid, force=False: None
win._sync_conference_roster = lambda room: None

# 1. room without @ + server -> room@server (the reported bug)
win._join_muc("myroom", "nick", server="linuxoid.in")
check("join builds room@server",
      win._client.joined == [["myroom@linuxoid.in", "nick", {"password": "",
                                                             "save_bookmark": False}]])
check("chat opened with full jid", win._chat_window.open_jids == ["myroom@linuxoid.in"])
check("disco#info uses full jid", win._client.info == ["myroom@linuxoid.in"])
check("self nick stored under full jid", win._muc_self_nicks.get("myroom@linuxoid.in") == "nick")

# 2. room already a full jid -> untouched even when server is given
win._join_muc("other@example.org", "nick", server="linuxoid.in")
check("full jid not double-joined",
      win._client.joined[-1][0] == "other@example.org")
check("server ignored for full jid",
      win._chat_window.open_jids[-1] == "other@example.org")

# 3. no server -> room passed through (bookmarks come as full jids)
win._join_muc("plainroom", "nick")
check("no server leaves bare room",
      win._client.joined[-1][0] == "plainroom")

# 4. the join dialog collect() shape used by both callers
win._join_muc("fromdialog", "nick", password="pw", save_bookmark=True,
              bookmark_name="label", autojoin=True, server="conf.example.com")
check("dialog-param join builds full jid",
      win._client.joined[-1] == ["fromdialog@conf.example.com", "nick",
                                 {"password": "pw", "save_bookmark": False}])
check("dialog bookmark saved with name+autojoin",
      win._client.bookmarked == ["fromdialog@conf.example.com", "nick",
                                 "pw", True, "label"])

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)