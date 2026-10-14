"""Offscreen tests for the vCard Status tab (per-resource blocks + formatting).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_vcard_status.py
"""
import os
import re
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_vcardstatus_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.vcard_dialog import VCardInfoDialog

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


_STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


class _Contact:
    def __init__(self, resources):
        self.resources = resources
        self.status = ""
        self.avatar_path = None


class _FakeClient:
    def __init__(self):
        self.pep_data = {}
        self.contacts = {}

    def get_contact(self, jid):
        return self.contacts.get(jid) or _Contact({})

    def subscription(self, jid):
        return "both"

    def fetch_pep(self, jid):
        pass

    def probe_entity(self, jid):
        pass


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
client = _FakeClient()
win._client = client
win._muc_users = {}
win._vcard_muc_ctx = {}

CARD = {"jid": "bob@example.com", "fn": "Bob", "fetched_at": 1700000000}

# 1. a 1:1 contact shows its own resources --------------------------------
client.contacts["bob@example.com"] = _Contact({
    "laptop": {"show": "online", "status": "Working", "priority": 5,
               "client": "Gajim", "client_version": "1.5.0",
               "client_tzo": "+03:00", "caps_node": ""},
})
status = win._vcard_status("bob@example.com", CARD)
check("one client block", len(status["clients"]) == 1)
block = status["clients"][0]
check("block resource", block["resource"] == "laptop")
check("block client+version", block["client"] == "Gajim"
      and block["version"] == "1.5.0")
check("block local time formatted", bool(_STAMP.match(block["client_time"])))
check("vcard_updated formatted", bool(_STAMP.match(status["vcard_updated"])))
check("no flat resource field", "resource" not in status)

# 2. a roster contact that shares a MUC occupant's JID is not hijacked -----
win._muc_users = {"room@conf.example": {
    "rain": {"real_jid": "rain@jabberworld.info", "show": "online",
             "status": "hi", "client": "Psi", "client_version": "1.5",
             "client_tzo": "+02:00"},
}}
client.contacts["rain@jabberworld.info"] = _Contact({
    "phone": {"show": "away", "status": "later", "priority": 3,
              "client": "Conversations", "client_version": "2.0",
              "client_tzo": "+01:00", "caps_node": ""},
})
status = win._vcard_status("rain@jabberworld.info",
                           {"jid": "rain@jabberworld.info", "fn": "Rain"})
check("roster contact keeps its own resource",
      status["clients"][0]["resource"] == "phone")
check("roster contact does not get the MUC nick",
      all(c["resource"] != "rain" for c in status["clients"]))

# 3. an explicit MUC context shows the occupant block ----------------------
win._vcard_muc_ctx["rain@jabberworld.info"] = True
status = win._vcard_status("rain@jabberworld.info",
                           {"jid": "rain@jabberworld.info", "fn": "Rain"})
check("MUC context uses the occupant nick",
      status["clients"][0]["resource"] == "rain")
check("MUC block carries the client",
      status["clients"][0]["client"] == "Psi")

# 4. the dialog renders the client blocks in the Status tab ----------------
win._vcard_muc_ctx.clear()
status = win._vcard_status("bob@example.com", CARD)
dlg = VCardInfoDialog("bob@example.com", CARD, status=status)
html = dlg._clients_label.text()
check("dialog renders the resource", "<b>laptop</b>" in html)
check("dialog renders the client version", "Gajim 1.5.0" in html)
check("dialog renders the status message", "Working" in html)
check("dialog uses the status icon", "jabber-online.png" in html)
check("dialog uses the clock icon", "clock.svg" in html)
check("status label present", tr("tooltip_status") in html)

# 5. the tabs take the extra space (they hug the header) -------------------
box = dlg._content.layout()
check("tabs have stretch 1", box.stretch(box.indexOf(dlg._tabs)) == 1)

# 6. the info dialog is opened non-modally (show, not open) ----------------
import stanza_im.ui.vcard_dialog as vd

shown = {}
_orig_cls = vd.VCardInfoDialog


class _Probe(_orig_cls):
    def open(self, *a):
        shown["open"] = True

    def show(self, *a):
        shown["show"] = True


vd.VCardInfoDialog = _Probe
win._request_last_activity = lambda *a: None
try:
    win._vcard_dialogs.clear()
    win._open_vcard_info("bob@example.com", CARD)
finally:
    vd.VCardInfoDialog = _orig_cls
check("vCard opened with show(), not open()",
      shown.get("show") and not shown.get("open"))

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All vCard-status tests passed.")
