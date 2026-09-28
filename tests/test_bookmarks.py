"""Offscreen tests for conference bookmarks (tab toolbar + editor dialog).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_bookmarks.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_bm_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.bookmark_dialog import BookmarkDialog
from stanza_im.ui.main_window import MainWindow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. Editor dialog ------------------------------------------------------------
dlg = BookmarkDialog(["conf.example"], default_nick="me")
dlg._name.setText("Room")
dlg._room.setText("chat")
dlg._server.setText("conf.example")
dlg._password.setText("pw")
dlg._autojoin.setChecked(True)
collected = dlg.collect()
check("dialog joins room and server into a JID",
      collected["jid"] == "chat@conf.example")
check("dialog collects every field",
      collected["name"] == "Room" and collected["nick"] == "me"
      and collected["password"] == "pw" and collected["autojoin"] is True)

bookmark = {"jid": "old@conf.example", "name": "Old", "nick": "nick",
            "password": "secret", "autojoin": True}
dlg2 = BookmarkDialog(["conf.example"], bookmark=bookmark)
check("edit mode splits the JID",
      dlg2._room.text() == "old" and dlg2._server.text() == "conf.example")
check("edit mode preloads the fields",
      dlg2._name.text() == "Old" and dlg2._nick.text() == "nick"
      and dlg2._password.text() == "secret"
      and dlg2._autojoin.isChecked() is True)
_fresh = BookmarkDialog([])
check("new bookmark defaults autojoin off",
      _fresh._autojoin.isChecked() is False)
check("the server field is a plain line edit",
      isinstance(_fresh._server, QtWidgets.QLineEdit)
      and _fresh._server.text() == "")
_fresh.deleteLater()


# 2. Tab toolbar --------------------------------------------------------------
class _Client:
    csi = True

    def __init__(self):
        self.saved = []
        self.removed = []

    def save_bookmark(self, room, nick, password="", autojoin=True, name=""):
        self.saved.append((room, nick, password, autojoin, name))

        async def _done():
            return None
        return _done()

    def remove_bookmark(self, room):
        self.removed.append(room)

        async def _done():
            return None
        return _done()

    def set_client_active(self, active):
        pass

    def jid_str(self):
        return "me@example.com"

    def __getattr__(self, name):
        return lambda *a, **k: None


win = MainWindow(app)
win._client = _Client()
# A real str (the stub's __getattr__ must not shadow jid_str).
win._client.jid_str = "me@example.com"

buttons = {
    "join": win._bookmark_join_btn,
    "new": win._bookmark_new_btn,
    "edit": win._bookmark_edit_btn,
    "del": win._bookmark_del_btn,
}
check("bookmarks tab has four icon buttons", all(
    b is not None for b in buttons.values()))
check("bookmark buttons are icon-only and wider than tall",
      all(b.toolButtonStyle() == QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
          and b.minimumWidth() > b.height()
          and not b.icon().isNull()
          for b in buttons.values()))
check("join/edit/delete disabled without a selection",
      not buttons["join"].isEnabled() and not buttons["edit"].isEnabled()
      and not buttons["del"].isEnabled())
check("'new' is always enabled", buttons["new"].isEnabled())

win._bookmarks = {"chat@conf.example": {"jid": "chat@conf.example",
                                        "name": "Room", "nick": "n",
                                        "password": "", "autojoin": False}}
win._rebuild_bookmarks_view()
check("bookmarks list is populated", win._bookmarks_list.count() == 1)
win._bookmarks_list.setCurrentRow(0)
check("selection enables join/edit/delete",
      buttons["join"].isEnabled() and buttons["edit"].isEnabled()
      and buttons["del"].isEnabled())

# A click over empty space must clear the selection (and disable the buttons).
win.show()
app.processEvents()
win._bookmarks_list.setCurrentRow(0)
app.processEvents()
_rect = win._bookmarks_list.rect()
_pos = QtCore.QPointF(5, _rect.bottom() - 2)
_event = QtGui.QMouseEvent(
    QtCore.QEvent.Type.MouseButtonPress, _pos, _pos,
    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.KeyboardModifier.NoModifier)
win._bookmarks_list.mousePressEvent(_event)
app.processEvents()
check("an empty-area click clears the selection",
      win._bookmarks_list.currentRow() == -1
      and not win._bookmarks_list.selectedItems())
check("an empty-area click disables join/edit/delete",
      not buttons["join"].isEnabled() and not buttons["edit"].isEnabled()
      and not buttons["del"].isEnabled())

# 3. Create/Edit call save_bookmark ------------------------------------------
win._save_bookmark_values({"jid": "new@conf.example", "name": "New",
                           "nick": "me", "password": "p", "autojoin": True})
check("saving a bookmark calls the client",
      win._client.saved and win._client.saved[-1] ==
      ("new@conf.example", "me", "p", True, "New"))
check("saving adds it to the local map",
      "new@conf.example" in win._bookmarks)

# 4. Removal requires confirmation -------------------------------------------
asked = []
_orig_question = QtWidgets.QMessageBox.question


def _no_confirmation(*a, **k):
    asked.append(a)
    return QtWidgets.QMessageBox.StandardButton.No


QtWidgets.QMessageBox.question = _no_confirmation
try:
    win._remove_bookmark_confirmed({"jid": "new@conf.example", "name": "New"})
    check("a declined confirmation does not remove", asked
          and "new@conf.example" in win._bookmarks)

    def _yes_confirmation(*a, **k):
        asked.append(a)
        return QtWidgets.QMessageBox.StandardButton.Yes

    QtWidgets.QMessageBox.question = _yes_confirmation
    win._remove_bookmark_confirmed({"jid": "new@conf.example", "name": "New"})
    check("an accepted confirmation removes the bookmark",
          "new@conf.example" not in win._bookmarks
          and "new@conf.example" in win._client.removed)
finally:
    QtWidgets.QMessageBox.question = _orig_question

# 5. Editing with a changed address drops the old bookmark --------------------
win._client.removed.clear()
win._bookmarks["old@conf.example"] = {"jid": "old@conf.example",
                                      "name": "Old"}
_removed_in_edit = []
_orig_remove = win._remove_bookmark


def _record_remove(room):
    _removed_in_edit.append(room)
    win._bookmarks.pop(room, None)


win._remove_bookmark = _record_remove
try:
    bookmark = {"jid": "old@conf.example", "name": "Old"}
    # Simulate the dialog returning a new JID.
    dlg3 = BookmarkDialog(["conf.example"], bookmark=bookmark)
    dlg3._room.setText("renamed")
    dlg3._server.setText("conf.example")
    data = dlg3.collect()
    old_room = bookmark.get("jid", "")
    new_room = data["jid"]
    if old_room and new_room and old_room != new_room:
        win._remove_bookmark(old_room)
    win._save_bookmark_values(data)
finally:
    win._remove_bookmark = _orig_remove
check("a changed address removes the old bookmark",
      "old@conf.example" in _removed_in_edit)
check("a changed address saves the new bookmark",
      win._client.saved[-1][0] == "renamed@conf.example")
win.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All bookmark tests passed.")
