"""Tests for XEP-0012 last activity on the vCard Status tab.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_last_activity.py
"""
import asyncio
import os
import re
import sys
import tempfile
import types
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_lastact_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import en, load as i18n_load, ru
from stanza_im.core.client import JabberClient
from stanza_im.ui.main_window import _format_last_seen
from stanza_im.ui.vcard_dialog import VCardInfoDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


_RESP = ("<iq xmlns='jabber:client' type='result' id='a9d53a' "
         "to='rain@jabberworld.info/walkbook' from='34512@jabberworld.info'>"
         "<query xmlns='jabber:iq:last' seconds='114153'>"
         "Stream reset by peer</query></iq>")


class _Result:
    def __init__(self, xml):
        self.xml = xml


class _Iq:
    def __init__(self, response, fail=False):
        self._response = response
        self._fail = fail
        self.xml = ET.Element("iq")

    def __setitem__(self, key, value):
        self.xml.set(key, str(value))

    async def send(self, timeout=None):
        if self._fail:
            raise RuntimeError("no reply")
        return _Result(self._response)


class _Xmpp:
    def __init__(self, response, fail=False):
        self._response = response
        self._fail = fail

    def Iq(self):
        return _Iq(self._response, self._fail)


# 1. the client parses seconds and the free-text status ----------------------
fake = types.SimpleNamespace(xmpp=_Xmpp(ET.fromstring(_RESP)))
info = asyncio.run(JabberClient.get_last_activity(fake, "34512@jabberworld.info"))
check("last activity seconds are parsed", info.get("seconds") == 114153)
check("last activity status text is parsed",
      info.get("status") == "Stream reset by peer")

# 2. a failed query yields no info -------------------------------------------
fake_fail = types.SimpleNamespace(xmpp=_Xmpp(None, fail=True))
check("a failed last-activity query returns nothing",
      asyncio.run(JabberClient.get_last_activity(fake_fail, "x@example.com"))
      == {})

# 3. the absolute formatter --------------------------------------------------
seen = _format_last_seen(114153)
check("last seen is an absolute date-time",
      re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", seen) is not None)

# 4. the vCard Status tab carries the fields and shows them ------------------
check("the last-seen i18n label exists",
      "vcard_field_last_seen" in en.STRINGS
      and "vcard_field_last_seen" in ru.STRINGS)
check("the last-status i18n label exists",
      "vcard_field_last_status" in en.STRINGS
      and "vcard_field_last_status" in ru.STRINGS)

dlg = VCardInfoDialog("34512@jabberworld.info",
                      {"jid": "34512@jabberworld.info", "fn": "Rain"},
                      status={"presence": "offline",
                              "last_seen": seen,
                              "last_status": "Stream reset by peer"})
check("the dialog has a last-seen field", "last_seen" in dlg._field_labels)
check("the dialog has a last-status field", "last_status" in dlg._field_labels)
check("the dialog shows the last-seen value",
      dlg._field_labels["last_seen"].text() == seen)
check("the dialog shows the last-status value",
      dlg._field_labels["last_status"].text() == "Stream reset by peer")
dlg.update_status({"last_status": "Gone"})
check("update_status refreshes the field in place",
      dlg._field_labels["last_status"].text() == "Gone")
dlg.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All last-activity tests passed.")
