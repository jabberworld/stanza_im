"""vCard value selection, URL/mailto links and participant address copy.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_vcard_links.py
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.ui import vcard_dialog as vd
from stanza_im.ui.main_window import MainWindow

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


card = {
    "jid": "bob@example.com",
    "fn": "Bob",
    "url": "example.com/page",
    "email": "bob@example.com",
}
dlg = vd.VCardInfoDialog("bob@example.com", card)
url_label = dlg._field_labels["url"]
email_label = dlg._field_labels["email"]
check("the URL field is a clickable link",
      'href="https://example.com/page"' in url_label.text())
check("the email field is a mailto link",
      'href="mailto:bob@example.com"' in email_label.text())
check("vCard values are selectable",
      bool(url_label.textInteractionFlags()
           & QtCore.Qt.TextInteractionFlag.TextSelectableByMouse))
check("the URL label does not navigate internally",
      not url_label.openExternalLinks())
dlg.deleteLater()

# A participant card must not copy the room's ?join action.
QtWidgets.QApplication.clipboard().clear()
participant = vd.VCardInfoDialog(
    "room@conf.example/Nick", {"jid": "room@conf.example/Nick"}, conference=False)
participant._copy_jid()
copied = QtWidgets.QApplication.clipboard().text()
check("participant address has no ?join", "?join" not in copied
      and "room@conf.example/Nick" in copied)
participant.deleteLater()

room = vd.VCardInfoDialog(
    "room@conf.example", {"jid": "room@conf.example"}, conference=True)
room._copy_jid()
check("a real room card keeps ?join",
      QtWidgets.QApplication.clipboard().text().endswith("?join"))
room.deleteLater()


class _Probe:
    def __init__(self, *args, **kwargs):
        self.conference = bool(kwargs.get("conference", False))
        self.finished = SimpleNamespace(connect=lambda *a: None)
        self.refresh_requested = SimpleNamespace(connect=lambda *a: None)
        self.features_requested = SimpleNamespace(connect=lambda *a: None)
        self.edit_requested = SimpleNamespace(connect=lambda *a: None)

    def setModal(self, _modal):
        pass

    def show(self):
        pass


win = MainWindow.__new__(MainWindow)
win._client = None
win._conference_roster = {"room@conf.example"}
win._muc_self_nicks = set()
win._vcard_muc_ctx = {"room@conf.example/Nick": True}
win._vcard_dialogs = {}
win._vcard_status = lambda _jid, _card: {}
win._find_open_vcard = lambda _jid: None
win._can_edit_room_vcard = lambda _room: False
win._chat_dialog_parent = lambda: None
old = vd.VCardInfoDialog
vd.VCardInfoDialog = _Probe
try:
    MainWindow._open_vcard_info(
        win, "room@conf.example/Nick", {"jid": "room@conf.example/Nick"})
finally:
    vd.VCardInfoDialog = old
check("a participant vCard is not marked as a room",
      win._vcard_dialogs["room@conf.example/Nick"].conference is False)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All vCard-link tests passed.")
