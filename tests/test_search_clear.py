"""Local content search fields expose Qt's clear button.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_search_clear.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_searchclear_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.conference_dialog import ConferenceBrowserDialog
from stanza_im.ui.emoji_picker_dialog import EmojiPickerDialog
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.notes_widget import NotesWidget
from stanza_im.ui.share_dialog import ShareDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
check("roster filter has a clear button",
      win._search_input.isClearButtonEnabled())
check("bookmarks filter has a clear button",
      win._bookmarks_search.isClearButtonEnabled())
check("events filter has a clear button",
      win._events_search.isClearButtonEnabled())
win.deleteLater()

notes = NotesWidget(lambda: None, lambda *_a: None)
check("notes filter has a clear button", notes._search.isClearButtonEnabled())
notes.deleteLater()

share = ShareDialog([], [], "text")
check("share filter has a clear button", share._search.isClearButtonEnabled())
share.deleteLater()

conference = ConferenceBrowserDialog(None, "example.com")
check("conference filter has a clear button",
      conference._search.isClearButtonEnabled())
conference.deleteLater()

emoji = EmojiPickerDialog()
check("emoji filter has a clear button", emoji._search.isClearButtonEnabled())
emoji.deleteLater()

# These dialogs need a live client; guard the field statically.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(path):
    return open(os.path.join(_root, "stanza_im", "ui", path),
                encoding="utf-8").read()


history = _src("history_manager.py")
check("history text search has a clear button",
      "self._search.setClearButtonEnabled(True)" in history)
check("history media filters have a clear button",
      "filter_edit.setClearButtonEnabled(True)" in history)
check("XML-console JID filter has a clear button",
      "_jid_edit.setClearButtonEnabled(True)" in _src("xml_console.py"))

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All search-clear tests passed.")
