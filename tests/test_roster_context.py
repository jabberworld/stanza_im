"""Offscreen tests for roster group/contact context-menu handling.

A right click on a group header must only open the group menu — it must not
also collapse/expand the group.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_roster_context.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_rosterctx_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402

from stanza_im.ui.roster_style import UserItem  # noqa: E402
from stanza_im.ui.roster_widget import RosterWidget  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _press(button):
    return QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonPress,
        QtCore.QPointF(10, 10), QtCore.QPointF(10, 10),
        button, button, QtCore.Qt.KeyboardModifier.NoModifier)


w = RosterWidget()
w.resize(200, 200)
group = w.add_group("Friends")
w.add_user(UserItem(jid="bob@example.com", name="Bob", group="Friends"))

# A right click on the group header must not toggle the group.
group.expanded = True
w.mousePressEvent(_press(QtCore.Qt.MouseButton.RightButton))
check("a right click does not toggle the group", group.expanded is True)
w.mousePressEvent(_press(QtCore.Qt.MouseButton.LeftButton))
check("a left click toggles the group", group.expanded is False)

# The context-menu event still routes to the right signal.
events = []
w.group_context_menu.connect(lambda name, pos: events.append(("group", name)))
w.contact_context_menu.connect(lambda jid, pos: events.append(("user", jid)))


def _ctx(y):
    return QtGui.QContextMenuEvent(
        QtGui.QContextMenuEvent.Reason.Mouse,
        QtCore.QPoint(10, y), QtCore.QPoint(10, y))


w.contextMenuEvent(_ctx(10))
check("a right click on the header emits the group menu",
      events == [("group", "Friends")])

events.clear()
group.expanded = True
w.contextMenuEvent(_ctx(30))
check("a right click on a row emits the contact menu",
      events == [("user", "bob@example.com")])

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All roster-context tests passed.")
