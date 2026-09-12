"""Chat-tab status icons and Esc hiding for MainWindow.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_tab_status_esc.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_tab_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.ui.chat_window import ChatWindow
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.icons import init_icons
from stanza_im.ui.main_window import MainWindow

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
theme = ChatThemeFactory()
icons = init_icons()


def _tab_icon(cw, jid):
    idx = cw._tab_widget.indexOf(cw._tabs[jid])
    return cw._tab_widget.tabIcon(idx) if idx >= 0 else None


def _icon_non_empty(icon):
    return icon is not None and not icon.isNull()


# ── 1:1 chat tab status icons ──────────────────────────────────────

cw = ChatWindow(theme, icons=icons)
cw.open_chat("alice@example.com", "Alice")
cw.open_chat("bob@example.com", "Bob")

# ── 1. each show key → non-empty icon
for show in ("online", "chat", "away", "xa", "dnd", "offline"):
    cw.set_contact_status("alice@example.com", show)
    icon = _tab_icon(cw, "alice@example.com")
    check(f"1:1 tab icon non-empty [{show}]", _icon_non_empty(icon))

# ── 2. None → icon cleared
cw.set_contact_status("alice@example.com", None)
icon = _tab_icon(cw, "alice@example.com")
check("1:1 tab icon cleared for None", not _icon_non_empty(icon))

# ── 3. status set before open_chat is applied on open
cw2 = ChatWindow(theme, icons=icons)
cw2.set_contact_status("charlie@example.com", "away")
cw2.open_chat("charlie@example.com", "Charlie")
icon = _tab_icon(cw2, "charlie@example.com")
check("pre-seeded status applied on open", _icon_non_empty(icon))

# ── 4. set_contact_status on unknown JID → no crash, stored until opened
cw3 = ChatWindow(theme, icons=icons)
cw3.set_contact_status("dave@example.com", "dnd")
cw3.open_chat("dave@example.com", "Dave")
icon = _tab_icon(cw3, "dave@example.com")
check("unknown JID status stored and applied on open", _icon_non_empty(icon))

# ── 5. MUC tab gets a status icon
cw4 = ChatWindow(theme, muc_theme_factory=theme, icons=icons)
cw4.open_groupchat("room@example.com", "admin", "Room")
cw4.set_contact_status("room@example.com", "online")
icon = _tab_icon(cw4, "room@example.com")
check("MUC tab icon set", _icon_non_empty(icon))

# ── 6. MUC status set before open works
cw5 = ChatWindow(theme, muc_theme_factory=theme, icons=icons)
cw5.set_contact_status("room2@example.com", "chat")
cw5.open_groupchat("room2@example.com", "admin", "Room2")
icon = _tab_icon(cw5, "room2@example.com")
check("MUC pre-seeded status applied on open", _icon_non_empty(icon))

# ── 7. no icons param → no crash, icon empty (fallback)
cw_no_icons = ChatWindow(theme)
cw_no_icons.open_chat("eve@example.com", "Eve")
cw_no_icons.set_contact_status("eve@example.com", "online")
icon = _tab_icon(cw_no_icons, "eve@example.com")
check("no icons param: icon empty (fallback)", not _icon_non_empty(icon))

# ── MainWindow Esc hides to tray ───────────────────────────────────

win = MainWindow(app)
win._idle_timer.stop()
win._tray.hide()   # no real systray in tests
win.show()

esc = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                      QtCore.Qt.Key.Key_Escape,
                      QtCore.Qt.KeyboardModifier.NoModifier)
QtWidgets.QApplication.sendEvent(win, esc)

check("Esc: window hidden", not win.isVisible())
check("Esc: _visible is False", win._visible is False)
check("Esc accepted", esc.isAccepted())

# non-Esc key: super() path, window stays visible
win.show()
non_esc = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                          QtCore.Qt.Key.Key_A,
                          QtCore.Qt.KeyboardModifier.NoModifier)
QtWidgets.QApplication.sendEvent(win, non_esc)
check("non-Esc: window still visible", win.isVisible())

win.close()
cw.close()
cw2.close()
cw3.close()
cw4.close()
cw5.close()
cw_no_icons.close()

print("\nAll tests passed ✓" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)