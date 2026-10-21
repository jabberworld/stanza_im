"""Tests for the rich tooltip wrapping (long MUC topics).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_tooltip_wrap.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_tooltip_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.ui import tooltip

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


window = tooltip._window()
window.set_content("short", None)
check("a plain tooltip does not wrap",
      not window._label.wordWrap())

window.set_content("<p>" + "word " * 200 + "</p>", None,
                   wrap=True, max_width=420)
check("a wrapped tooltip wraps at the maximum width",
      window._label.wordWrap() and window._label.maximumWidth() == 420)

window.set_content("plain", None)
check("the wrapping is reset for the next tooltip",
      not window._label.wordWrap())

# A wide, unwrapped tooltip is clamped to the screen (no sideways overflow).
screen = QtWidgets.QApplication.primaryScreen()
area = screen.availableGeometry()
window.set_content("<p>" + "x" * 2000 + "</p>", None)
window.adjustSize()
wide = window.width()
tooltip._place(QtCore.QPoint(area.left(), area.top()))
check("a wide tooltip is clamped to the screen",
      wide > 0 and window.width() <= area.width()
      and window.width() < wide)

# show() carries the wrap settings to the deferred popup.
tooltip.show(QtCore.QPoint(10, 10), "text", wrap=True, max_width=300)
check("show() keeps the wrap settings",
      tooltip._PENDING[3] is True and tooltip._PENDING[4] == 300)
tooltip.hide()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All tooltip-wrap tests passed.")
