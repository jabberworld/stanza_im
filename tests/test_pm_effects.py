"""PM participant status, tooltip avatar and offline send guard.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_pm_effects.py
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.main_window import MainWindow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Chat:
    def __init__(self):
        self.status = None
        self.pm_mode = False
        self.available = None
        self.peer_avatar = ""

    def set_contact_status(self, _jid, show):
        self.status = show

    def set_pm_mode(self, _real=""):
        self.pm_mode = True

    def set_pm_peer_available(self, available):
        self.available = available

    def set_peer_avatar(self, uri):
        self.peer_avatar = uri


class _Window:
    def __init__(self, chat):
        self.chat = chat

    def get_chat(self, _jid):
        return self.chat

    def set_contact_status(self, jid, show):
        self.chat.set_contact_status(jid, show)


def _pm_window(chat, users):
    win = MainWindow.__new__(MainWindow)
    win._muc_users = users
    win._pm_targets = {"room@conf.example/Nick": ("room@conf.example", "Nick")}
    win._vcard_muc_ctx = {}
    win._chat_window = _Window(chat)
    return win


chat = _Chat()
win = _pm_window(chat, {})
MainWindow._apply_pm_presence(
    win, "room@conf.example/Nick", "room@conf.example", "Nick", chat)
check("an absent PM occupant is offline, not online", chat.status == "offline")
check("an absent PM occupant disables sending", chat.available is False)

chat2 = _Chat()
win2 = _pm_window(chat2, {
    "room@conf.example": {"Nick": {"nick": "Nick", "show": "away"}}
})
MainWindow._apply_pm_presence(
    win2, "room@conf.example/Nick", "room@conf.example", "Nick", chat2)
check("an online participant keeps its show", chat2.status == "away")
check("an online participant enables sending", chat2.available is True)

# The roster tooltip uses the participant's avatar, not the room's.
class _Client:
    def get_contact(self, jid):
        return SimpleNamespace(avatar_path="/room-avatar.png")


win3 = MainWindow.__new__(MainWindow)
win3._client = _Client()
win3._pm_targets = {"room@conf.example/Nick": ("room@conf.example", "Nick")}
win3._muc_users = {"room@conf.example": {
    "Nick": {"nick": "Nick", "show": "offline",
             "avatar_path": "/participant-avatar.png"}}}
win3._participant_info = lambda room, nick: win3._muc_users[room][nick]
html, avatar = MainWindow._roster_tooltip(win3, "room@conf.example/Nick")
check("the PM tooltip names the participant", "<b>Nick</b>" in html)
check("the PM tooltip uses the participant avatar",
      avatar == "/participant-avatar.png")

# The actual widget shows the offline banner and disables Send.
widget = ChatWidget("room@conf.example/Nick", "Nick",
                    chat_themes.ChatThemeFactory())
widget.set_pm_mode("")
widget.set_pm_peer_available(False)
check("PM offline shows a banner", bool(widget._pm_offline_label.text()))
check("PM offline disables the Send button", not widget._send_btn.isEnabled())
widget.set_pm_peer_available(True)
check("PM rejoin clears the banner", not widget._pm_offline_label.text())
check("PM rejoin enables Send", widget._send_btn.isEnabled())
widget.detach()
widget.deleteLater()

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All PM-effect tests passed.")
