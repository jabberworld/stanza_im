"""Offscreen test for the MUC participant list interactions.

- a double click on a participant opens the private chat (participant_clicked),
  while a single click only selects the row;
- a click on empty space of the list clears the selection.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_participant_list.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_partlist_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.ui import chat_themes
from stanza_im.ui import chat_widget as chat_widget_mod

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
theme = chat_themes.ChatThemeFactory()

cw = chat_widget_mod.ChatWidget(
    "room@conf.example/Rain", "Room", theme, is_muc=True)
cw.update_muc_users([
    {"nick": "Alice", "role": "participant", "show": "online",
     "real_jid": "alice@example.com"},
    {"nick": "Bob", "role": "visitor", "show": "away"},
    {"nick": "Rain", "role": "moderator", "affiliation": "owner",
     "show": "online"},
])
cw.show()
app.processEvents()

lw = cw._users_list


def item_by_nick(nick):
    for i in range(lw.count()):
        if lw.item(i).data(QtCore.Qt.ItemDataRole.UserRole) == nick:
            return lw.item(i)
    return None


item_alice = item_by_nick("Alice")
rect = lw.visualItemRect(item_alice)
center = rect.center()
check("participant row visible", rect.width() > 0 and rect.height() > 0)


def _event(typ, pos):
    return QtGui.QMouseEvent(
        typ, QtCore.QPointF(pos),
        QtCore.QPointF(lw.viewport().mapToGlobal(pos)),
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.MouseButton.NoButton,
        QtCore.Qt.KeyboardModifier.NoModifier)


def click_row(pos):
    QtWidgets.QApplication.sendEvent(lw.viewport(), _event(
        QtCore.QEvent.Type.MouseButtonPress, pos))
    QtWidgets.QApplication.sendEvent(lw.viewport(), _event(
        QtCore.QEvent.Type.MouseButtonRelease, pos))


# ── 1. single click: select only, no private chat ---------------------
opened = []
cw.participant_clicked.connect(lambda room, nick: opened.append((room, nick)))
click_row(center)
check("single click selects the row", item_alice.isSelected())
check("single click does not open private chat", opened == [])

# ── 2. double click: opens the private chat ---------------------------
opened.clear()
QtWidgets.QApplication.sendEvent(lw.viewport(), _event(
    QtCore.QEvent.Type.MouseButtonPress, center))
QtWidgets.QApplication.sendEvent(lw.viewport(), _event(
    QtCore.QEvent.Type.MouseButtonRelease, center))
QtWidgets.QApplication.sendEvent(lw.viewport(), _event(
    QtCore.QEvent.Type.MouseButtonDblClick, center))
QtWidgets.QApplication.sendEvent(lw.viewport(), _event(
    QtCore.QEvent.Type.MouseButtonRelease, center))
check("double click opens private chat",
      opened == [("room@conf.example/Rain", "Alice")])

# ── 3. empty-area click clears the selection --------------------------
lw.setCurrentItem(item_alice)
check("row selected before empty click", item_alice.isSelected())
empty = QtCore.QPoint(max(1, rect.x()), lw.viewport().height() - 2)
check("empty point hits no item", lw.itemAt(empty) is None)
click_row(empty)
check("empty click clears selection",
      not item_alice.isSelected() and lw.currentItem() is None)

cw.close()

# ── 4. wiring: double-click source, no itemClicked --------------------
src = open(os.path.join(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))),
    "stanza_im/ui/chat_widget.py")).read()
check("wiring uses itemDoubleClicked",
      "itemDoubleClicked.connect(" in src
      and "self._on_muc_user_double_clicked)" in src)
check("no itemClicked wiring remains", "itemClicked.connect" not in src)
check("participant list subclass present",
      "class _ParticipantList(QtWidgets.QListWidget)" in src
      and "self.itemAt(event.position().toPoint()) is None" in src)

print("\nAll tests passed" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)