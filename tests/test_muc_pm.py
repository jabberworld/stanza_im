"""Conference private messages use the occupant identity in every room type.

A MUC PM is keyed by ``room/nick`` even when the room reveals real JIDs; the
real JID is metadata for the status/avatar/vCard, and a room PM relayed from
the real JID is mapped back to its occupant.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_pm.py
"""
import inspect
import os
import sys
import tempfile
from types import SimpleNamespace
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_mucpm_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.core.client import JabberClient, NS_MUC_USER
from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.include import avatars as avatars_mod
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.main_window import MainWindow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


# 1. a room PM from the real JID maps back to the occupant ------------------
class _Msg:
    def __init__(self, with_muc_user: bool):
        self.xml = ET.Element("{jabber:client}message")
        if with_muc_user:
            ET.SubElement(self.xml, "{%s}x" % NS_MUC_USER)


client = JabberClient.__new__(JabberClient)
client.groupchats = {
    "room@conf.example": SimpleNamespace(
        users={"Bob": {"real_jid": "bob@example.com/phone"}}),
    "other@conf.example": SimpleNamespace(users={}),
}
check("an occupant PM relayed from the real JID is mapped",
      client._room_pm_occupant("bob@example.com/phone", _Msg(True))
      == ("room@conf.example", "Bob"))
check("a plain 1:1 message is not treated as a room PM",
      client._room_pm_occupant("bob@example.com/phone", _Msg(False)) is None)
client.groupchats["other@conf.example"].users["Bobby"] = {
    "real_jid": "bob@example.com"}
check("an ambiguous real JID stays a normal 1:1",
      client._room_pm_occupant("bob@example.com/phone", _Msg(True)) is None)
client.groupchats["other@conf.example"].users.clear()

# 2. a PM chat shows the peer avatar ---------------------------------------
room = "room@conf.example"
target = f"{room}/Bob"
image = QtGui.QImage(24, 24, QtGui.QImage.Format.Format_RGB32)
image.fill(QtGui.QColor("#2e7d32"))
buffer = QtCore.QBuffer()
buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
image.save(buffer, "PNG")
avatar_path = avatars_mod.save_avatar(target, bytes(buffer.data()))
raw_uri = avatars_mod.avatar_data_uri(target)

cw = ChatWidget(target, "Bob", chat_themes.ChatThemeFactory())
cw.set_avatar_radius(100)
cw.set_peer_avatar(raw_uri)
check("a private chat uses the peer avatar",
      cw._user_icon("incoming").startswith("data:image/png;base64,"))
check("the peer avatar obeys the rounding setting",
      cw._user_icon("incoming") != raw_uri)
cw.detach()

# 3. the participant data drives the PM tab --------------------------------
win = MainWindow.__new__(MainWindow)
win._config = Config.defaults()
win._muc_users = {room: {"Bob": {
    "nick": "Bob", "show": "dnd", "role": "participant",
    "real_jid": "bob@example.com/phone",
    "avatar_path": avatar_path, "avatar_jid": target}}}
win._pm_targets = {target: (room, "Bob")}
win._muc_self_nicks = {}
win._vcard_muc_ctx = {}


class _FakeChat:
    def __init__(self):
        self.peer = ""
        self.refreshed = 0

    def set_peer_avatar(self, uri):
        self.peer = uri

    def refresh_avatars(self):
        self.refreshed += 1


class _FakeChatWindow:
    def __init__(self, chat):
        self.chat = chat
        self.status = []

    def get_chat(self, jid):
        return self.chat if jid == target else None

    def set_contact_status(self, jid, show):
        self.status.append((jid, show))


chat = _FakeChat()
win._chat_window = _FakeChatWindow(chat)
win._participant_info = lambda r, n: win._muc_users.get(r, {}).get(n, {})
win._apply_pm_presence(target, room, "Bob", chat)
check("the PM tab gets the participant's status",
      win._chat_window.status == [(target, "dnd")])
check("the PM tab gets the participant's avatar",
      chat.peer.startswith("data:image/png;base64,"))
check("the PM chat is marked as a room context",
      win._vcard_muc_ctx.get(target) is True)
check("the participant avatar is the one from the list",
      chat.peer == avatars_mod.avatar_file_data_uri(avatar_path))

# 4. the PM toolbar vCard follows the participant profile ------------------
shown = []
win._show_muc_participant_profile = (
    lambda r, n, j: shown.append((r, n, j)))
win._participant_real_jid = lambda info: "bob@example.com"
win._on_chat_vcard(target)
check("a PM vCard opens the participant profile with the bare JID",
      shown == [(room, "Bob", "bob@example.com")])

# 5. a card update refreshes only that PM ----------------------------------
chat2 = _FakeChat()
win._chat_window = _FakeChatWindow(chat2)
win._refresh_pm_avatars(room, "Bob")
check("an avatar update refreshes the PM avatar and messages",
      chat2.peer.startswith("data:image/png;base64,")
      and chat2.refreshed == 1)

# 6. the PM key is the occupant identity even with a real JID --------------
incoming = inspect.getsource(MainWindow._on_muc_private_message)
check("an incoming PM is keyed by room/nick",
      'target = f"{room}/{nick}"' in incoming
      and "real_jid.strip()" not in incoming)
opened = inspect.getsource(MainWindow._on_muc_participant_clicked)
check("opening a participant's PM uses the occupant key",
      'target = f"{room}/{nick}"' in opened
      and "real_jid.strip()" not in opened)
presence = inspect.getsource(MainWindow._on_groupchat_presence)
check("participant presence updates the PM tab",
      "_apply_pm_presence(target, room, nick)" in presence)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All MUC private-message tests passed.")
