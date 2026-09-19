"""Offscreen tests for replying to the last message with the Up key.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_reply_up.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_replyup_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def press_up(widget, ctrl: bool = False) -> bool:
    mods = (QtCore.Qt.KeyboardModifier.ControlModifier if ctrl
            else QtCore.Qt.KeyboardModifier.NoModifier)
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                            QtCore.Qt.Key.Key_Up, mods)
    return bool(widget.eventFilter(widget._input, event))


def new_widget(jid="bob@example.com", is_muc=False, nick="me"):
    widget = ChatWidget(jid, "Chat", chat_themes.ChatThemeFactory(),
                        is_muc=is_muc)
    if is_muc:
        widget.set_self_nick(nick)
    return widget


# 1. Up on an empty input replies to the last incoming message ----------------
cw = new_widget()
cw.add_message(sender="Bob", body="hello there", timestamp="10:00",
               direction="incoming", reply_able_id="orig-bob",
               reply_author="bob@example.com/res")
check("up is consumed", press_up(cw) is True)
check("reply target set", cw._reply_id == "orig-bob")
check("reply addressed to the author", cw._reply_to == "bob@example.com/res")
check("reply banner visible", not cw._reply_ctx.isHidden())
check("quote inserted", "> Bob wrote:" in cw._input.toPlainText()
      and "hello there" in cw._input.toPlainText())

# 2. a second Up (quote already in the input) is left to the editor -----------
check("up ignored while composing a reply", press_up(cw) is False)

# 3. Up with a non-empty input does not start a reply -------------------------
cw2 = new_widget()
cw2.add_message(sender="Bob", body="hi", timestamp="10:00",
                direction="incoming", reply_able_id="orig-2",
                reply_author="bob@example.com/res")
cw2._input.setPlainText("draft")
check("up not consumed with text", press_up(cw2) is False)
check("no reply started", cw2._reply_id == "")
check("draft untouched", cw2._input.toPlainText() == "draft")

# 4. our own newest message is skipped ----------------------------------------
cw3 = new_widget()
cw3.add_message(sender="Bob", body="question?", timestamp="10:00",
                direction="incoming", reply_able_id="orig-3",
                reply_author="bob@example.com/res")
cw3.add_message(sender="Me", body="my answer", timestamp="10:01",
                direction="outgoing", message_id="mine-3")
check("own message skipped by _reply_to_last", cw3._reply_to_last() is True)
check("replied to the incoming message", cw3._reply_id == "orig-3")

# 5. MUC: our own nick is skipped too -----------------------------------------
cw4 = new_widget("room@conf.example/me", is_muc=True, nick="me")
cw4.add_message(sender="bob", body="muc question", timestamp="10:00",
                direction="incoming", reply_able_id="muc-4",
                reply_author="room@conf.example/bob")
cw4.add_message(sender="me", body="muc answer", timestamp="10:01",
                direction="incoming", message_id="muc-mine")
check("muc own nick skipped", cw4._reply_to_last() is True)
check("muc replied to the other occupant", cw4._reply_id == "muc-4")

# 6. messages without a replyable id are skipped ------------------------------
cw5 = new_widget()
cw5.add_message(sender="Bob", body="no ids", timestamp="10:00",
                direction="incoming")
check("no replyable target", cw5._reply_to_last() is False)
check("up not consumed", press_up(cw5) is False)

# 7. Ctrl+Up still edits the last own message --------------------------------
cw6 = new_widget()
cw6.add_message(sender="Me", body="editable", timestamp="10:00",
                direction="outgoing", message_id="edit-6",
                reply_able_id="origin-6")
check("ctrl+up consumed", press_up(cw6, ctrl=True) is True)
check("edit started", cw6._editing_id == "edit-6"
      and cw6._input.toPlainText() == "editable")

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
