"""MUC message avatars use the participant's cached file.

The sidebar paints ``user["avatar_path"]`` directly while a message used to
resolve the avatar by its JID; a stale (old-name) path or a participant known
only after the history was rendered left the messages with a placeholder.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_avatar_refresh.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_mucav_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.include import avatars as avatars_mod
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


image = QtGui.QImage(16, 16, QtGui.QImage.Format.Format_RGB32)
image.fill(QtGui.QColor("#1565c0"))
buffer = QtCore.QBuffer()
buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
image.save(buffer, "PNG")
png = bytes(buffer.data())

room = "avroom@conf.example"
nick = "Боб"
target = f"{room}/{nick}"
path = avatars_mod.save_avatar(target, png)


class _View:
    def __init__(self):
        self.calls = []

    def update_sender_avatar(self, sender, uri):
        self.calls.append((sender, uri))


cw = ChatWidget(room, "Room", chat_themes.ChatThemeFactory(), is_muc=True)
cw._view = _View()
cw._messages = [{"sender": nick, "direction": "incoming", "sender_jid": "",
                 "body": "hi", "timestamp": "2026-10-24T09:00:00.000000Z"}]

cw.update_muc_users([{"nick": nick, "show": "online", "role": "participant",
                      "avatar_jid": target, "avatar_path": path}])
check("a newly known avatar repaints the sender's messages",
      len(cw._view.calls) >= 1 and cw._view.calls[0][0] == nick
      and cw._view.calls[0][1].startswith("data:image/png"))

cw._view.calls.clear()
cw.update_muc_users([{"nick": nick, "show": "online", "role": "participant",
                      "avatar_jid": target, "avatar_path": path}])
check("an unchanged avatar path does not repaint again",
      cw._view.calls == [])

by_jid = cw._user_icon("incoming", target, nick)
by_nick = cw._user_icon("incoming", "", nick)
check("the message avatar is the participant's file either way",
      by_jid == by_nick and by_jid.startswith("data:image/png"))
check("the message avatar is not the placeholder",
      by_jid == cw._user_icon("incoming", "", nick) and bool(by_jid))

cw.detach()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All MUC avatar-refresh tests passed.")
