"""Offscreen tests for the redesigned roster contact tooltip.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_roster_tooltip.py
"""
import os
import re
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_tooltip_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


_STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


class _Contact:
    def __init__(self):
        self.resources = {
            "laptop": {"show": "online", "status": "Working now",
                       "priority": 5, "client": "Gajim",
                       "client_version": "1.5.0", "client_tzo": "+03:00",
                       "caps_node": ""},
        }
        self.status = ""
        self.avatar_path = None


class _FakeClient:
    def __init__(self):
        self.pep_data = {"bob@example.com": {"mood": {"key": "happy"}}}

    def get_contact(self, jid):
        return _Contact()

    def subscription(self, jid):
        return "both"


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
win._client = _FakeClient()
win._roster_name = lambda jid: "Bob"
win._conference_roster = set()
win._muc_self_nicks = {}

html, _avatar = win._roster_tooltip("bob@example.com")

check("header has the name", "<b>Bob</b>" in html)
check("header has the JID", "bob@example.com" in html)
check("subscription shown", tr("tooltip_subscription") in html)
check("status icon before the resource", "jabber-online.png" in html)
check("resource name in bold", "<b>laptop</b>" in html)
check("clock icon shown", "clock.svg" in html)
check("local time formatted", bool(_STAMP.search(html)))
check("client name and version", "Gajim 1.5.0" in html)
check("client label", tr("tooltip_client") in html)
check("status label", tr("tooltip_status") in html)
check("status message shown", "Working now" in html)
check("PEP mood line present", tr("pep_mood") in html)

check("PEP statuses above the resource block",
      html.index(tr("pep_mood")) < html.index("<b>laptop</b>"))
check("resource tree is a table", "<table" in html)
check("time sits on its own row after the resource",
      html.index("<b>laptop</b>") < html.index("clock.svg"))
check("client line after the resource line",
      html.index("<b>laptop</b>") < html.index("Gajim 1.5.0"))
check("status after the client line",
      html.index("Gajim 1.5.0") < html.index("Working now"))

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All roster-tooltip tests passed.")
