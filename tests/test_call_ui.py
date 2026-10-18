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
from stanza_im.ui.main_window import MainWindow  # noqa: E402

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. a call peer resolves to its roster name (bare JID when unknown) ---------
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

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All call-UI tests passed.")
