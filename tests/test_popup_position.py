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

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All popup-position tests passed.")
