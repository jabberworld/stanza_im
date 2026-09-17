"""Offscreen smoke tests for the Share action and address-less xmpp: URIs.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_share.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_share_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.core import client as client_mod
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_view import share_payload
from stanza_im.ui.share_dialog import ShareDialog
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.roster_style import UserItem

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. share_payload ----------------------------------------------------------
check("share media url wins",
      share_payload("https://page", "https://img.png", "image", "text")
      == "https://img.png")
check("share link when no media",
      share_payload("https://page", "", "", "text") == "https://page")
check("share selected text",
      share_payload("", "", "", "  hello  ") == "hello")
check("share ignores internal links",
      share_payload("stanza:view:image/x", "", "", "") == "")
check("share ignores data media",
      share_payload("", "data:image/png;base64,AAAA", "image", "") == "")
check("share empty", share_payload("", "", "", "") == "")

# 2. forwarded body ---------------------------------------------------------
body = "Forwarded:\n" + client_mod.compose_reply_body("https://x.test")
check("forwarded body quotes the link",
      body == "Forwarded:\n> https://x.test\n\n")

# 3. ShareDialog selection --------------------------------------------------
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
dlg = ShareDialog([("bob@example.com", "Bob"), ("ann@example.com", "Ann")],
                  [("room@conf.example", "Room")], "https://x.test")
check("share dialog has no selection initially", dlg.selected_targets() == [])
dlg._contacts_root.child(0).setCheckState(0, QtCore.Qt.CheckState.Checked)
dlg._conf_root.child(0).setCheckState(0, QtCore.Qt.CheckState.Checked)
check("share dialog returns checked targets",
      sorted(dlg.selected_targets()) == sorted([
          ("bob@example.com", False), ("room@conf.example", True)]))
check("send button enabled with a selection", dlg._send.isEnabled())
dlg._search.setText("ann")
check("search filters non-matches", dlg._contacts_root.child(0).isHidden())
dlg.close()


# 4. MainWindow share routing ----------------------------------------------
class _FakeClient:
    def __init__(self):
        self.sent = []
        self.muc = []
        self.jid_str = "me@example.com/desk"

    def send_message(self, jid, body, *a, **k):
        self.sent.append((jid, body))
        return "mid-1"

    def send_muc_message(self, room, body, *a, **k):
        self.muc.append((room, body))


win = MainWindow(app)
win._idle_timer.stop()
win._client = _FakeClient()
win._tray.show_message = lambda *a, **k: None
win._display_local_outgoing = lambda jid, body, mid: None
win._roster._users = [
    UserItem(jid="bob@example.com", name="Bob", group="Friends"),
    UserItem(jid="room@conf.example", name="Room", group="Conferences"),
]
win._muc_self_nicks = {"room@conf.example": "me"}
win._muc_names = {"room@conf.example": "Room"}
win._conference_roster = {"room@conf.example"}

check("share contacts exclude conferences",
      win._share_contacts() == [("bob@example.com", "Bob")])
check("share conferences use display names",
      win._share_conferences() == [("room@conf.example", "Room")])

win._send_share("https://x.test",
                [("bob@example.com", False), ("room@conf.example", True)])
check("share sends to a contact",
      win._client.sent == [("bob@example.com",
                            "Forwarded:\n> https://x.test\n\n")])
check("share sends to a conference",
      win._client.muc == [("room@conf.example",
                           "Forwarded:\n> https://x.test\n\n")])

# 5. address-less xmpp: URI routes to share ---------------------------------
shared = []
win._on_share_requested = lambda content: shared.append(content)
win._on_xmpp_uri("xmpp:?message;body=https%3A%2F%2Fgultsch.de%2Fposts%2F")
check("address-less xmpp: opens share with the body",
      shared == ["https://gultsch.de/posts/"])

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
