"""Offscreen tests for the MUC display-name source setting.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_name.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_mucname_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load, tr
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.preferences import PreferencesDialog

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 1. default ------------------------------------------------------------------
check("default name source is from_name",
      Config().chat.muc_name_source == "from_name")

# 2. name resolution ----------------------------------------------------------
win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
win._muc_self_nicks = {"room@conf.example": "me"}
win._muc_names = {"room@conf.example": "Room Name"}
win._muc_vcard_names = {
    "room@conf.example": {"fn": "Full Name", "nickname": "Nick"}}
win._bookmarks = {}
seen_titles = []
win._chat_window.set_chat_title = lambda room, title: seen_titles.append(title)
win._sync_conference_roster = lambda room: None

win._config.chat.muc_name_source = "from_name"
check("from_name uses the disco name",
      win._muc_display_name("room@conf.example") == "Room Name")
win._apply_muc_name("room@conf.example")
check("apply updates the tab title", seen_titles == ["Room Name"])

win._config.chat.muc_name_source = "from_vcard"
check("from_vcard prefers the vCard FN",
      win._muc_display_name("room@conf.example") == "Full Name")
win._muc_vcard_names["room@conf.example"] = {"fn": "", "nickname": "Nick"}
check("from_vcard falls back to the nickname",
      win._muc_display_name("room@conf.example") == "Nick")

# The bookmark name is the explicit user label and wins in both modes.
win._bookmarks = {"room@conf.example": {"name": "My Room"}}
check("bookmark name wins in from_vcard",
      win._muc_display_name("room@conf.example") == "My Room")
win._config.chat.muc_name_source = "from_name"
check("bookmark name wins in from_name",
      win._muc_display_name("room@conf.example") == "My Room")
win._bookmarks = {}

win._muc_vcard_names["room@conf.example"] = {"fn": "", "nickname": ""}
win._config.chat.muc_name_source = "from_vcard"
check("empty vCard falls back to the room name",
      win._muc_display_name("room@conf.example") == "Room Name")

win._muc_names = {}
win._muc_vcard_names["room@conf.example"] = {"fn": "", "nickname": ""}
check("no name falls back to the JID localpart",
      win._muc_display_name("room@conf.example") == "room")

win._config.chat.muc_name_source = "from_name"
win._muc_vcard_names["room@conf.example"] = {
    "fn": "Full Name", "nickname": "Nick"}
check("from_name ignores the vCard",
      win._muc_display_name("room@conf.example") == "room")

check("explicit preferred name beats the localpart",
      win._muc_display_name("room@conf.example", preferred="Pref") == "Pref")

# 3. refresh iterates the joined rooms ---------------------------------------
refreshed = []
win._apply_muc_name = lambda room: refreshed.append(room)
win._muc_self_nicks = {"a@x": "me", "b@x": "me"}
win._refresh_muc_names()
check("refresh covers every joined room", sorted(refreshed) == ["a@x", "b@x"])

# 4. preferences control ------------------------------------------------------
cfg = Config()
dlg = PreferencesDialog(cfg, ChatThemeFactory())
combo = dlg._controls["muc_name_source"]
check("prefs exposes the name source",
      sorted(combo.itemData(i) for i in range(combo.count()))
      == ["from_name", "from_vcard"])
check("prefs default is from_name",
      combo.itemData(combo.currentIndex()) == "from_name")
info = [b for b in dlg.findChildren(QtWidgets.QToolButton)
        if b.toolTip() == tr("prefs_muc_name_source_info")]
check("name source has an info tooltip", bool(info))
dlg.close()

# 5. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
check("display name consults the setting",
      'getattr(self._config.chat, "muc_name_source", "from_name")' in _mw_src)
check("bookmark name has top priority",
      'self._bookmarks.get(room) or {}).get("name"' in _mw_src)
check("vCard reception stores fn and nickname",
      '"fn": card.get("fn")' in _mw_src
      and '"nickname": card.get("nickname")' in _mw_src
      and "self._apply_muc_name(room_jid)" in _mw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All MUC-name tests passed.")
