"""Offscreen tests for the call UI (incoming dialog, roster naming).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_call_ui.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_callui_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.ui.call_window import CallWindow, IncomingCallDialog  # noqa: E402
from stanza_im.ui.main_window import MainWindow  # noqa: E402

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. the incoming dialog: accept on the right, reject on the left ------------
dlg = IncomingCallDialog("Bob", "audio")
row = None
for _i in range(dlg.layout().count()):
    _item = dlg.layout().itemAt(_i)
    if _item.layout() is not None and _item.layout().indexOf(dlg._reject) >= 0:
        row = _item.layout()
        break
check("the incoming dialog has a button row", row is not None)
check("the reject button is at the left edge",
      row.itemAt(0).widget() is dlg._reject)
check("a stretch separates the buttons",
      row.itemAt(1).spacerItem() is not None)
check("the accept button is at the right edge",
      row.itemAt(2).widget() is dlg._accept)
dlg.close()

# 2. a call peer resolves to its roster name (bare JID when unknown) ---------
class _User:
    def __init__(self, jid, name):
        self.jid = jid
        self.name = name


class _Roster:
    _users = [_User("bob@example.com", "Bob")]


mw = MainWindow.__new__(MainWindow)
mw._roster = _Roster()
check("a call peer resolves to its roster name",
      mw._call_display_name("bob@example.com/desk") == "Bob")
check("an unnamed roster contact falls back to its JID",
      mw._call_display_name("bob@example.com") == "Bob")
check("an unknown call peer falls back to the bare JID",
      mw._call_display_name("x@y/res") == "x@y")

# 3. the active call window has a mute-the-peer (speaker) button -------------
cw = CallWindow("s1", "Bob", video=False)
check("the call window has a mute-peer button", hasattr(cw, "_hear_btn"))
heard = []
cw.receive_toggled.connect(lambda sid, enabled: heard.append((sid, enabled)))
cw._hear_btn.setChecked(True)
check("muting the peer emits receive_toggled(False)",
      heard == [("s1", False)])
cw._hear_btn.setChecked(False)
check("unmuting the peer emits receive_toggled(True)",
      heard[-1] == ("s1", True))
cw.close()


# 4. the call dialogs show an avatar (or the placeholder) --------------------
def _has_avatar_label(widget):
    return any(not lbl.pixmap().isNull()
               for lbl in widget.findChildren(QtWidgets.QLabel))


ad = IncomingCallDialog("Bob", "audio")
check("the incoming dialog shows an avatar", _has_avatar_label(ad))
ad.close()
acw = CallWindow("s2", "Bob", video=False)
check("the audio call window shows an avatar", _has_avatar_label(acw))
acw.close()
vcw = CallWindow("s3", "Bob", video=True)
check("a video call window has no avatar", not _has_avatar_label(vcw))
vcw.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All call-UI tests passed.")
