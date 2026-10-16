"""Tests for the popup-anchor geometry (reaction / unicode smiley picker).

Pure math — no window is built.  Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_popup_position.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore

from stanza_im.ui.popup_position import popup_position

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


area = QtCore.QRect(0, 0, 1000, 800)
size = QtCore.QSize(360, 300)

# A button in the middle: the popup opens above it, left edges aligned.
p = popup_position(QtCore.QRect(400, 500, 20, 20), size, area)
check("opens above the button, left-aligned",
      p.x() == 400 and p.y() == 500 - 300)

# A button near the top: the popup drops below the button's bottom edge
# (never covering it).
p = popup_position(QtCore.QRect(400, 10, 20, 20), size, area)
check("falls below the button without covering it",
      p.y() == 10 + 20 and p.x() == 400)

# A button near the right edge: the popup stays attached (right edges aligned).
p = popup_position(QtCore.QRect(980, 500, 20, 20), size, area)
check("stays attached to a right-edge button",
      p.x() == 1000 - 360)

# Off-screen anchor: clamped into the available area.
p = popup_position(QtCore.QRect(-50, -50, 20, 20), size, area)
check("clamped into the area", p.x() == 0 and p.y() == 0)

# A large popup is clamped so its right/bottom edges stay on screen.
big = QtCore.QSize(2000, 2000)
p = popup_position(QtCore.QRect(500, 400, 20, 20), big, area)
check("a huge popup is clamped to the area", p.x() == 0 and p.y() == 0)


def _covers(btn, size, pos):
    return (pos.y() < btn.y() + btn.height()
            and pos.y() + size.height() > btn.y())


# The side is chosen by the room: a button in the upper half opens below it,
# a button in the lower half opens above it — always adjacent, never covering.
upper = QtCore.QRect(400, 100, 20, 20)
p = popup_position(upper, size, area)
check("an upper-half button opens below it, adjacent",
      p.y() == upper.y() + upper.height() and not _covers(upper, size, p))
lower = QtCore.QRect(400, 600, 20, 20)
p = popup_position(lower, size, area)
check("a lower-half button opens above it, adjacent",
      p.y() == lower.y() - size.height() and not _covers(lower, size, p))

# A popup that does not fit above is moved below instead of covering.
near_top = QtCore.QRect(400, 30, 20, 20)
p = popup_position(near_top, size, area)
check("no room above -> below, never covering",
      not _covers(near_top, size, p) and p.y() == near_top.y() + 20)

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All popup-position tests passed.")
