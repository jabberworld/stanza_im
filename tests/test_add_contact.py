"""Offscreen tests for the add-contact gateway selector + directed presence.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_add_contact.py
"""
import asyncio
import os
import sys
import tempfile

os.environ["XDG_DATA_HOME"] = os.path.join(tempfile.mkdtemp(), "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tempfile.mkdtemp(), "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core.client import JabberClient
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.add_contact_dialog import AddContactDialog

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _FakeClient:
    jid_str = "me@example.com/res"

    async def discover_services(self, server):
        return [
            {"jid": "xmpp.example.com", "name": "J2J", "category": "gateway",
             "type": "XMPP"},
            {"jid": "conf.example.com", "name": "Conf", "category": "conference",
             "type": "text"},
        ]

    async def gateway_info(self, service):
        return {"gateway": True, "desc": "Jabber-to-Jabber", "prompt": "Enter JID"}


loop = asyncio.get_event_loop()

# 1. the service selector lists the account's gateways ------------------------
dlg = AddContactDialog([], _FakeClient())
loop.run_until_complete(asyncio.sleep(0.1))
data = [dlg._service.itemData(i) for i in range(dlg._service.count())]
check("the service selector lists the gateway", "xmpp.example.com" in data)
check("a conference is not offered as a service",
      "conf.example.com" not in data)
dlg.close()

# 2. a preselected gateway is chosen and its info loaded ----------------------
dlg2 = AddContactDialog([], _FakeClient(),
                        gateways=[("J2J", "xmpp.example.com")],
                        preselect="xmpp.example.com")
loop.run_until_complete(asyncio.sleep(0.1))
check("preselect picks the gateway",
      dlg2._service.currentData() == "xmpp.example.com")
check("the gateway box is enabled", dlg2._gateway_box.isEnabled())
check("the gateway description is loaded",
      "Jabber-to-Jabber" in dlg2._gateway_desc.text())
dlg2.close()

# 3. directed presence (connect / disconnect a transport) ---------------------
sent = []


class _Presence:
    def __init__(self):
        self.d = {}

    def __setitem__(self, key, value):
        self.d[key] = value

    def send(self):
        sent.append(dict(self.d))


class _Xmpp:
    def Presence(self):
        return _Presence()


class _PC:
    priority_mode = "manual"
    priority = 50
    xmpp = _Xmpp()
    _effective_priority = JabberClient._effective_priority


JabberClient.send_directed_presence(_PC(), "gw@example", "unavailable",
                                    "Disconnected")
JabberClient.send_directed_presence(_PC(), "gw@example")
check("directed unavailable presence",
      sent[0]["to"] == "gw@example" and sent[0]["type"] == "unavailable"
      and sent[0]["status"] == "Disconnected")
check("directed available presence",
      sent[1]["to"] == "gw@example" and sent[1]["type"] == "available"
      and sent[1]["priority"] == 50)

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All add-contact tests passed.")
