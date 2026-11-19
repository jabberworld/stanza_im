"""Context menu for chat tabs: Hide and Leave conference.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_tab_context_menu.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_tab_menu_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_window import ChatWindow
from stanza_im.ui.icons import init_icons

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
icons = init_icons()
theme = ChatThemeFactory()
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def action(cw, widget, text):
    menu = cw._build_tab_context_menu(widget)
    for item in menu.actions():
        if item.text() == text:
            return item
    return None


cw = ChatWindow(theme, muc_theme_factory=theme, icons=icons)
direct = cw.open_chat("alice@example.com", "Alice")
pm = cw.open_chat("room@example.com/nick", "PM")
room = cw.open_groupchat("room@example.com", "me", "Room")

check("a 1:1 tab offers only Hide",
      [a.text() for a in cw._build_tab_context_menu(direct).actions()]
      == ["Hide"])
check("a private message tab is treated as a chat",
      [a.text() for a in cw._build_tab_context_menu(pm).actions()]
      == ["Hide"])
check("a conference offers Hide and Leave conference",
      [a.text() for a in cw._build_tab_context_menu(room).actions()]
      == ["Hide", "Leave conference"])

closed = []
cw.tab_closed.connect(closed.append)
action(cw, direct, "Hide").trigger()
check("Hide closes a 1:1 tab", not cw.has_chat("alice@example.com"))
check("Hide reports the closed 1:1 tab",
      closed == ["alice@example.com"])

left = []
cw.muc_leave_requested.connect(left.append)
action(cw, room, "Hide").trigger()
check("Hide closes a conference tab without leaving",
      not cw.has_chat("room@example.com") and left == [])

cw2 = ChatWindow(theme, muc_theme_factory=theme, icons=icons)
cw2._muc_leave_confirm = lambda _room: True
room2 = cw2.open_groupchat("room2@example.com", "me", "Room 2")
left2 = []
cw2.muc_leave_requested.connect(left2.append)
action(cw2, room2, "Leave conference").trigger()
check("Leave conference requests a leave",
      left2 == ["room2@example.com"])
check("Leave conference closes the tab",
      not cw2.has_chat("room2@example.com"))

cw3 = ChatWindow(theme, muc_theme_factory=theme, icons=icons)
cw3.open_chat("bob@example.com", "Bob")
# Empty tab-bar space must not open a menu or crash.
cw3._on_tab_context_menu(QtCore.QPoint(5000, 5000))
check("empty tab-bar space is ignored", cw3.has_chat("bob@example.com"))

cw.close()
cw2.close()
cw3.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All tab-context tests passed.")
