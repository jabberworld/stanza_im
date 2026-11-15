"""Offscreen test: a long MUC subject opens at its first character."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


widget = ChatWidget("room@conf.example", "Room", ChatThemeFactory(),
                    is_muc=True)
subject = "Начало темы " + "очень длинная тема " * 20
widget.set_subject([("", subject)])
check("the whole subject is stored", widget._subject_edit.text() == subject)
check("the subject starts at the first character",
      widget._subject_edit.cursorPosition() == 0)
check("the subject is left-aligned",
      bool(widget._subject_edit.alignment()
           & 0x0001))  # Qt.AlignmentFlag.AlignLeft
widget.detach()

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All MUC-subject alignment tests passed")
