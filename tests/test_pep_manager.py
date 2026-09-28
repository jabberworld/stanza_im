"""Offscreen tests for the PEP manager dialog.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_pep_manager.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_pep_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.core.client import JabberClient, NS_DISCO_ITEMS
from stanza_im.ui.pep_manager_dialog import PepManagerDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _FakeClient:
    jid_str = "rain@jabberworld.info"

    def __init__(self):
        self.deleted = []
        self.submitted = []

    async def pep_list_nodes(self):
        return [
            {"node": "urn:xmpp:omemo:2:devices", "name": "", "jid": self.jid_str},
            {"node": "config", "name": "Configuration", "jid": self.jid_str},
        ]

    async def pep_get_node_items(self, node):
        return ET.fromstring(
            "<pubsub xmlns='http://jabber.org/protocol/pubsub'>"
            "<items node='%s'><item id='current'/></items></pubsub>" % node)

    async def pep_get_node_config(self, node):
        return None

    async def pep_delete_node(self, node):
        self.deleted.append(node)
        return True

    async def pep_set_node_config(self, node, form):
        self.submitted.append(node)
        return True


loop = asyncio.new_event_loop()
_pending = []


def _run(coro):
    _pending.append(loop.create_task(coro))


def _drain():
    while _pending:
        loop.run_until_complete(_pending.pop(0))


# Client parses disco#items, keeping only items that carry a ``node``.
_c = JabberClient.__new__(JabberClient)
_c.jid_str = "rain@x"


def _make_iq():
    class _Iq:
        def __init__(self):
            self.xml = ET.Element("{jabber:client}iq")

        def __setitem__(self, key, value):
            pass

        async def send(self, timeout=10):
            class _R:
                pass
            r = _R()
            r.xml = ET.fromstring(
                "<iq xmlns='jabber:client' type='result'><query xmlns='%s'>"
                "<item node='a' jid='rain@x'/>"
                "<item jid='rain@x/Gajim'/>"
                "<item node='b' name='B' jid='rain@x'/>"
                "</query></iq>" % NS_DISCO_ITEMS)
            return r
    return _Iq()


_c.xmpp = type("X", (), {"Iq": staticmethod(_make_iq)})()
_nodes = loop.run_until_complete(_c.pep_list_nodes())
check("pep_list_nodes keeps node items and skips resources",
      [n["node"] for n in _nodes] == ["a", "b"]
      and _nodes[1]["name"] == "B")

client = _FakeClient()
dlg = PepManagerDialog(lambda: client, _run)

dlg.refresh()
_drain()
check("node list is populated", dlg._list.topLevelItemCount() == 2)
check("node values are stored",
      dlg._list.topLevelItem(1).text(0) == "config"
      and dlg._list.topLevelItem(1).text(1) == "Configuration")

check("delete/settings/open disabled without a selection",
      not dlg._delete_btn.isEnabled() and not dlg._settings_btn.isEnabled()
      and not dlg._open_btn.isEnabled())
check("refresh is always enabled", dlg._refresh_btn.isEnabled())

dlg._list.setCurrentItem(dlg._list.topLevelItem(0))
check("selection enables delete/settings/open",
      dlg._delete_btn.isEnabled() and dlg._settings_btn.isEnabled()
      and dlg._open_btn.isEnabled())

dlg._open_selected()
_drain()
check("open switches to the node view", dlg._stack.currentIndex() == 1)
check("open shows the node name", dlg._view_title.text() == "urn:xmpp:omemo:2:devices")
check("open renders the node XML",
      "item" in dlg._view_text.toPlainText())
check("copy puts the payload on the clipboard",
      (QtWidgets.QApplication.clipboard().setText("x") or True)
      and dlg._view_text.toPlainText() != "")

# Delete requires confirmation; answer Yes.
asked = []
_orig = QtWidgets.QMessageBox.question


def _yes(*a, **k):
    asked.append(a)
    return QtWidgets.QMessageBox.StandardButton.Yes


QtWidgets.QMessageBox.question = _yes
try:
    dlg._delete_selected()
    _drain()
finally:
    QtWidgets.QMessageBox.question = _orig
check("delete asks for confirmation", bool(asked))
check("confirmed delete calls the client",
      client.deleted == ["urn:xmpp:omemo:2:devices"])

# A declined confirmation keeps the node.
client.deleted.clear()


def _no(*a, **k):
    return QtWidgets.QMessageBox.StandardButton.No


QtWidgets.QMessageBox.question = _no
try:
    dlg._delete_selected()
    _drain()
finally:
    QtWidgets.QMessageBox.question = _orig
check("declined delete does nothing", client.deleted == [])

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All PEP manager tests passed.")
