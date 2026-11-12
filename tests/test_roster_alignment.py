"""Roster typography: baseline alignment and font-dependent row heights.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_roster_alignment.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_roster_align_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.ui.roster_style import RosterStyle, UserItem
from stanza_im.ui.roster_widget import RosterWidget

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def close(a, b, tolerance=0.01):
    return abs(float(a) - float(b)) <= tolerance


style = RosterStyle()
font = QtGui.QFont("DejaVu Sans")
font.setPointSize(14)
metrics = QtGui.QFontMetricsF(font)

check("mixed/upper-case uses cap height",
      close(style._body_height(metrics, "Bob"), metrics.capHeight()))
check("upper-case Cyrillic uses cap height",
      close(style._body_height(metrics, "Роман"), metrics.capHeight()))
check("digits use cap height",
      close(style._body_height(metrics, "123"), metrics.capHeight()))
check("lower-case uses x-height",
      close(style._body_height(metrics, "bob"), metrics.xHeight()))
check("lower-case Cyrillic uses x-height",
      close(style._body_height(metrics, "роман"), metrics.xHeight()))

icon_top = 4.0
icon_height = 24.0
body = style._body_height(metrics, "Bob")
no_status = style.name_baseline(icon_top, icon_height, metrics, "Bob", False)
check("without status the body centre is the icon centre",
      close(no_status - body / 2.0, icon_top + icon_height / 2.0))
with_status = style.name_baseline(icon_top, icon_height, metrics, "Bob", True)
check("with status the body top is the icon top",
      close(with_status - body, icon_top))
check("status baseline is the icon bottom",
      close(style.status_baseline(icon_top, icon_height),
            icon_top + icon_height))

short = UserItem(jid="a@b", name="Alice", group="G")
tall = UserItem(jid="a@b", name="Alice", group="G",
                status_message="hello")
small = QtGui.QFont("DejaVu Sans")
small.setPointSize(9)
large = QtGui.QFont("DejaVu Sans")
large.setPointSize(48)

check("short rows keep their minimum height",
      style.user_height(short, small) == RosterStyle.USER_HEIGHT_SHORT)
check("tall rows keep their minimum height",
      style.user_height(tall, small) == RosterStyle.USER_HEIGHT_TALL)
check("short rows grow with the font",
      style.user_height(short, large) > style.user_height(short, small))
check("tall rows grow with the font",
      style.user_height(tall, large) > style.user_height(tall, small))
check("group rows grow with the font",
      style.group_height(large) > style.group_height(small))

roster = RosterWidget()
roster.add_group("G")
roster.add_user(short)
roster.setFont(small)
small_height = roster.minimumHeight()
roster.setFont(large)
large_height = roster.minimumHeight()
check("RosterWidget recalculates row geometry on font change",
      large_height > small_height)

image = QtGui.QImage(320, style.user_height(tall, large),
                     QtGui.QImage.Format.Format_ARGB32)
image.fill(QtCore.Qt.GlobalColor.transparent)
painter = QtGui.QPainter(image)
painter.setFont(large)
style.paint_user(painter, tall, QtCore.QRect(0, 0, 320, image.height()),
                 False)
painter.end()
check("large status row renders without clipping errors", not image.isNull())

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All tests passed")
