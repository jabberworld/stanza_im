"""Offscreen regression test: closing a chat tab must free its widget.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_tab_leak.py
"""
import gc
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_tab_leak_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_window import ChatWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _drain(app):
    """Run the event loop enough for deleteLater() to take effect."""
    app.processEvents()
    app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    app.processEvents()
    gc.collect()


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

cw = ChatWindow(ChatThemeFactory())
_drain(app)
base = len(app.allWidgets())

for i in range(10):
    jid = "user%d@example.com" % i
    cw.open_chat(jid, "User %d" % i)
    check("tab opened %d" % i, cw.has_chat(jid))
    cw.close_chat(jid)

# MUC tabs take the header branch (a 1:1 tab does not), so cover both.
for i in range(5):
    room = "room%d@conference.example.com" % i
    cw.open_groupchat(room, "me", "Room %d" % i)
    check("muc opened %d" % i, cw.has_chat(room))
    cw.close_chat(room)

_drain(app)
after = len(app.allWidgets())

check("all tabs closed", cw._tab_widget.count() == 0)
check("closed tabs do not leak widgets (base=%d after=%d)"
      % (base, after), after <= base + 1)

# The leak fix must stay in place (static guard; WebEngine is unavailable in
# this sandbox so the runtime check above exercises the fallback view).
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cw_src = open(os.path.join(_root, "stanza_im", "ui", "chat_window.py"),
               encoding="utf-8").read()
check("close_chat deletes the page widget",
      "widget.setParent(None)" in _cw_src and "widget.deleteLater()" in _cw_src)
_view_src = open(os.path.join(_root, "stanza_im", "ui", "chat_view.py"),
                 encoding="utf-8").read()
check("ChatView has a shutdown hook", "def shutdown" in _view_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All tab-leak tests passed.")
