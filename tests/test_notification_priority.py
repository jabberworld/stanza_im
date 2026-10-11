"""Tests for per-contact notification priority (local store, XEP-0131, OSD).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_notification_priority.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_prio_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core import notification_priorities as np
from stanza_im.core.client import _shim_urgency
from stanza_im.i18n import load as i18n_load, tr
from stanza_im.ui.main_window import MainWindow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. local store -------------------------------------------------------------
np.set_profile("me@example.com")
np.save({})
np.set("bob@example.com", "high")
np.set("eve@example.com", "low")
check("set stores a priority", np.get("bob@example.com") == "high")
check("set stores low", np.get("eve@example.com") == "low")
check("an unknown contact is normal (empty)",
      np.get("nobody@example.com") == "")
np.set("bob@example.com", "normal")   # clears
check("setting normal clears the entry", np.get("bob@example.com") == "")
np.set_many({"bob@example.com": "high", "carol@example.com": "low"})
check("set_many writes several entries",
      np.all() == {"bob@example.com": "high", "eve@example.com": "low",
                   "carol@example.com": "low"})

# 2. server payload ----------------------------------------------------------
payload = np.build_payload([{"jid": "a@b", "priority": "high"},
                            {"jid": "c@d", "priority": "bogus"},
                            {"jid": "", "priority": "low"}])
parsed = np.parse_payload(payload)
check("payload keeps only valid jid/priority pairs",
      parsed == [{"jid": "a@b", "priority": "high"}])

# 3. XEP-0131 SHIM urgency ---------------------------------------------------
def _msg(headers=""):
    return ET.fromstring(
        "<message xmlns='jabber:client'><body>x</body>%s</message>" % headers)


_shim = ("<headers xmlns='http://jabber.org/protocol/shim'>"
         "<header name='Urgency'>%s</header></headers>")
check("urgency high is parsed", _shim_urgency(_msg(_shim % "high")) == "high")
check("urgency medium is parsed",
      _shim_urgency(_msg(_shim % "medium")) == "medium")
check("urgency low is parsed", _shim_urgency(_msg(_shim % "low")) == "low")
check("the header name is case-insensitive",
      _shim_urgency(_msg(
          "<headers xmlns='http://jabber.org/protocol/shim'>"
          "<header name='urgency'>HIGH</header></headers>")) == "high")
check("no headers means no urgency", _shim_urgency(_msg()) == "")
check("an unrelated header is ignored",
      _shim_urgency(_msg(
          "<headers xmlns='http://jabber.org/protocol/shim'>"
          "<header name='TTL'>60</header></headers>")) == "")

# 4. effective priority (user setting over XEP-0131) -------------------------
win = MainWindow(app)
win._notification_priorities = {"bob@example.com": "high",
                                "eve@example.com": "low"}
eff = win._effective_priority
check("a high-priority contact stays high", eff("bob@example.com") == "high")
check("a user high overrides an urgency low",
      eff("bob@example.com", "low") == "high")
check("a user low overrides an urgency high",
      eff("eve@example.com", "high") == "low")
check("urgency high applies without a setting", eff("x@y", "high") == "high")
check("urgency low applies without a setting", eff("x@y", "low") == "low")
check("urgency medium maps to normal", eff("x@y", "medium") == "normal")
check("no setting and no urgency is normal", eff("x@y") == "normal")
check("the priority is looked up by bare JID",
      eff("bob@example.com/resource") == "high")

# 5. the important counter and the sticky OSD --------------------------------
win._client = object()
win._config.notifications.osd_enabled = True
win._unread_chats = {}
win._bump_unread("bob@example.com", important=True)
check("an important message bumps the important counter",
      win._unread_chats["bob@example.com"]["important"] == 1)
rec = win._osd._find_sticky("priority")
check("a sticky OSD appears for important messages", rec is not None)
check("the sticky title is the important header",
      rec["window"]._title_label.text() == tr("osd_priority_title"))
check("the sticky body carries the count",
      "1" in rec["window"]._body_label.text())
win._reset_unread("bob@example.com")
check("the sticky is dismissed when nothing important remains",
      win._osd._find_sticky("priority") is None)
win.deleteLater()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All notification-priority tests passed.")
