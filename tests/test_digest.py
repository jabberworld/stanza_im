"""Offscreen tests for the Notifications Digest plugin.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_digest.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_digest_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load, tr
from stanza_im.plugins import digest
from stanza_im.ui.osd import OsdManager

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _FakeApp(QtCore.QObject):
    unread_changed = QtCore.pyqtSignal()

    def __init__(self, osd):
        super().__init__()
        self._osd = osd
        # A non-None client means "logged in" (the digest is gated on it).
        self._client = object()
        self._unread_chats = {}
        self._conference_roster = set()
        self._muc_self_nicks = {}
        self.opened = []

    def _on_tray_cycle_unread(self):
        self.opened.append(True)


def _cfg():
    cfg = Config()
    cfg.notifications.osd_enabled = True
    cfg.notifications.osd_duration = 5
    return cfg


# 0. before login (no client) the digest never appears -----------------------
mgr0 = OsdManager(_cfg())
fake0 = _FakeApp(mgr0)
fake0._client = None
fake0._unread_chats = {"alice@example.com": {"unread": 5, "mentions": 0}}
digest.activate(fake0)
check("no digest before login", len(mgr0._windows) == 0)
fake0.unread_changed.emit()
check("a pre-login unread change still shows nothing", len(mgr0._windows) == 0)
fake0._client = object()
fake0.unread_changed.emit()
check("the digest appears once logged in", len(mgr0._windows) == 1)
digest.deactivate(fake0)

# 1. activation shows a sticky digest ----------------------------------------
mgr = OsdManager(_cfg())
fake = _FakeApp(mgr)
digest.activate(fake)
check("no digest while nothing is unread", len(mgr._windows) == 0)

fake._unread_chats = {
    "alice@example.com": {"unread": 30, "mentions": 0},
    "bob@example.com": {"unread": 20, "mentions": 0},
    "room@conf.example": {"unread": 5, "mentions": 3},
    "other@conf.example": {"unread": 2, "mentions": 0},
}
fake._conference_roster = {"room@conf.example", "other@conf.example"}
fake.unread_changed.emit()
check("a sticky digest appears", len(mgr._windows) == 1)
_rec = mgr._windows[0]
check("the digest is sticky", _rec.get("sticky") is True)
_win = _rec["window"]
check("the digest title is the summary header",
      _win._title_label.text() == tr("digest_title"))
_body = _win._body_label.text()
check("the digest counts contact messages",
      "50 new messages from 2 contacts" in _body)
check("the digest counts conference mentions",
      "3 mentions in 1 conferences" in _body)
check("a non-mention conference message is not counted",
      "55" not in _body and "from 3 contacts" not in _body)

# 2. it updates in place when the counters change ----------------------------
fake._unread_chats["alice@example.com"]["unread"] = 31
fake.unread_changed.emit()
check("the digest updates in place", len(mgr._windows) == 1
      and "51" in _win._body_label.text())

# 3. clicking opens the topmost unread chat, keeps the digest ----------------
_win._click()
check("clicking the digest opens the topmost unread chat",
      fake.opened == [True])
check("clicking the digest keeps it on screen", len(mgr._windows) == 1)

# 4. manual close hides it until the counters grow ---------------------------
_win._close()
check("closing the digest hides it", len(mgr._windows) == 0)
fake.unread_changed.emit()   # same counts: stays hidden
check("a same-count refresh does not re-show the digest", len(mgr._windows) == 0)
fake._unread_chats["alice@example.com"]["unread"] = 32
fake.unread_changed.emit()
check("a grown count re-shows the digest", len(mgr._windows) == 1)

# 5. clearing the counters dismisses it --------------------------------------
fake._unread_chats = {}
fake.unread_changed.emit()
check("no unread dismisses the digest", len(mgr._windows) == 0)

# 6. deactivation removes the digest and the subscription --------------------
fake._unread_chats = {"alice@example.com": {"unread": 1, "mentions": 0}}
fake.unread_changed.emit()
check("the digest is back before deactivation", len(mgr._windows) == 1)
digest.deactivate(fake)
check("deactivation dismisses the digest", len(mgr._windows) == 0)
check("deactivation clears the plugin state",
      getattr(fake, digest._STATE, None) is None)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All digest tests passed.")
