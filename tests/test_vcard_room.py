"""Offscreen tests for the conference vCard viewer/editor wiring.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_vcard_room.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_roomvcard_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.vcard_dialog import VCardEditDialog, VCardInfoDialog

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()

# 1. the toolbar button opens the ROOM vCard, not our own ---------------------
win._muc_users = {"room@conf.example": {
    "me": {"real_jid": "me@example.com/desk", "affiliation": "owner"}}}
win._muc_self_nicks = {"room@conf.example": "me"}
shown = []
win._show_profile = lambda jid: shown.append(jid)
win._show_muc_room_info("room@conf.example")
check("room info opens the room JID", shown == ["room@conf.example"])

# 2. affiliation decides editing rights ---------------------------------------
def rights(aff):
    win._muc_users = {"room@conf.example": {
        "me": {"real_jid": "me@example.com/desk", "affiliation": aff}}}
    return win._can_edit_room_vcard("room@conf.example")


check("owner may edit", rights("owner"))
check("admin may edit", rights("admin"))
check("member may not edit", not rights("member"))
check("none may not edit", not rights("none"))

# 3. VCardInfoDialog Edit button ---------------------------------------------
room_card = {"jid": "room@conf.example", "fn": "Room"}
dlg = VCardInfoDialog("room@conf.example", room_card, show_edit=True,
                      can_edit=True)
check("edit button visible for a room", not dlg._edit_btn.isHidden())
check("edit button enabled with rights", dlg._edit_btn.isEnabled())
emitted = []
dlg.edit_requested.connect(lambda j: emitted.append(j))
dlg._edit_btn.click()
check("edit button emits the jid", emitted == ["room@conf.example"])
dlg.deleteLater()

dlg2 = VCardInfoDialog("room@conf.example", room_card, show_edit=True,
                       can_edit=False)
check("edit button disabled without rights", not dlg2._edit_btn.isEnabled())
dlg2.deleteLater()

dlg3 = VCardInfoDialog("bob@example.com", {"jid": "bob@example.com"},
                       show_edit=False, can_edit=False)
check("edit button hidden for a contact", dlg3._edit_btn.isHidden())
dlg3.deleteLater()

# 4. editor reuse -------------------------------------------------------------
edit = VCardEditDialog({"jid": "room@conf.example", "fn": "Room"},
                       title_key="vcard_edit_room_title")
check("editor uses the room title", "Conference" in edit.windowTitle())
check("editor keeps the room jid", edit.collect()["jid"]
      == "room@conf.example")
edit.deleteLater()

# 5. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_client_src = open(os.path.join(_root, "stanza_im", "core", "client.py"),
                   encoding="utf-8").read()
check("client publishes a room vCard",
      "async def set_room_vcard" in _client_src
      and "publish_vcard(stanza, jid=room)" in _client_src)
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
check("room info no longer uses our real JID",
      'member.get("real_jid") or room' not in _mw_src
      and "def _save_room_vcard" in _mw_src)
check("room vCard dialogs parent to the chat window",
      "parent = self._chat_dialog_parent() if is_room else self" in _mw_src
      and "VCardEditDialog(data, parent or self" in _mw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All room-vCard tests passed.")
