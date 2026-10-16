"""Offscreen tests for the Psi-style unread indicator (tabs + window title).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_unread_title.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_unread_title_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtGui, QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_window import ChatWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


RED = QtGui.QColor(0xcc, 0x00, 0x00)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# Default: the option is on.
check("show_unread_in_tabs defaults to on",
      getattr(Config().appearance, "show_unread_in_tabs", True) is True)

cw = ChatWindow(chat_themes.ChatThemeFactory())
bob = cw.open_chat("bob@example.com", "Bob")
room = cw.open_groupchat("room@conf.example", "me", "Room")

bob_idx = cw._tab_widget.indexOf(bob)
room_idx = cw._tab_widget.indexOf(room)
bar = cw._tab_widget.tabBar()


def text(idx):
    return cw._tab_widget.tabText(idx)


def color(idx):
    return bar.tabTextColor(idx)


# 1:1 unread → "[N] name" and red.
cw.set_unread("bob@example.com", 3, 0)
check("1:1 tab shows the unread prefix", text(bob_idx) == "[3] Bob")
check("1:1 tab with unread is red", color(bob_idx) == RED)

# MUC unread without a mention → prefix but no red.
cw.set_unread("room@conf.example", 10, 0)
check("MUC tab shows the unread prefix", text(room_idx) == "[10] Room")
check("MUC tab without a mention is not red", not color(room_idx).isValid())

# MUC unread with a mention → red.
cw.set_unread("room@conf.example", 10, 1)
check("MUC tab with a mention is red", color(room_idx) == RED)

# Window title sums every open tab, whichever is active.
cw._tab_widget.setCurrentIndex(bob_idx)
check("window title sums the open tabs", cw.windowTitle() == "[13] Bob")
cw._tab_widget.setCurrentIndex(room_idx)
check("window title follows the active tab", cw.windowTitle() == "[13] Room")

# Clearing the unread removes the prefix and the color.
cw.set_unread("bob@example.com", 0, 0)
check("no unread removes the prefix", text(bob_idx) == "Bob")
check("no unread clears the color", not color(bob_idx).isValid())
check("the window total drops the read tab", cw.windowTitle() == "[10] Room")

# The option turns the whole indicator off (and back on).
cw.set_show_unread_in_tabs(False)
check("option off removes the tab prefix", text(room_idx) == "Room")
check("option off removes the window total", cw.windowTitle() == "Room")
cw.set_show_unread_in_tabs(True)
check("option on restores the tab prefix", text(room_idx) == "[10] Room")
check("option on restores the window total", cw.windowTitle() == "[10] Room")

# Closing a tab drops its counter from the total.
cw.set_unread("bob@example.com", 4, 0)
check("both tabs count", cw.windowTitle() == "[14] Room")
cw.close_chat("bob@example.com")
check("closing a tab drops its unread", cw.windowTitle() == "[10] Room")

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All unread-title tests passed.")
