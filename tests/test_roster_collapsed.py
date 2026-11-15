"""Offscreen tests for persisted roster group expansion."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.ui.roster_widget import RosterWidget

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


widget = RosterWidget()
widget.set_collapsed_groups(["RSS"])
rss = widget.add_group("RSS")
other = widget.add_group("Friends")
check("a persisted collapsed group starts collapsed", not rss.expanded)
check("an unknown group starts expanded", other.expanded)
check("collapsed names are returned",
      widget.collapsed_groups() == ["RSS"])

events = []
widget.group_toggled.connect(lambda name, expanded: events.append(
    (name, expanded)))
widget.clear()
widget.set_collapsed_groups(["RSS"])
rss = widget.add_group("RSS")
widget.resize(240, 200)
event = QtGui.QMouseEvent(
    QtCore.QEvent.Type.MouseButtonPress,
    QtCore.QPointF(10, 5), QtCore.QPointF(10, 5),
    QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.KeyboardModifier.NoModifier)
widget.mousePressEvent(event)
check("a left click expands the group", rss.expanded)
check("the toggle signal reports the new state",
      events == [("RSS", True)])

widget.set_collapsed_groups(["RSS"])
widget.clear()
rss_again = widget.add_group("RSS")
check("the collapsed state survives a roster rebuild",
      not rss_again.expanded)

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All roster-collapse tests passed")
