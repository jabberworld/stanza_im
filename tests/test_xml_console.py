"""Offscreen smoke tests for the XML console.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_xml_console.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_xmlc_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp
from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.core.client import JabberClient, _StanzaXMPP
from stanza_im.ui import xml_console
from stanza_im.ui.xml_console import (COLORS, XmlConsoleDialog, bare_jid,
                                      classify)

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── classification ───────────────────────────────────────────────
check("bare JID drops resource and lowercases",
      bare_jid("Alice@Example.COM/Phone") == "alice@example.com")
check("bare JID of empty stays empty", bare_jid("") == "")

check("incoming message classified",
      classify("<message xmlns='jabber:client' from='a@b' to='c@d'/>")
      == ("message", "a@b", "c@d"))
check("presence classified",
      classify("<presence xmlns='jabber:client' from='a@b'/>")[0] == "presence")
check("iq classified",
      classify("<iq xmlns='jabber:client' type='get' id='1'/>")[0] == "iq")
check("SM classified",
      classify("<r xmlns='urn:xmpp:sm:3'/>")[0] == "sm")
check("CSI falls into other",
      classify("<active xmlns='urn:xmpp:csi:0'/>")[0] == "other")
check("stream footer falls into other",
      classify("</stream:stream>") == ("other", "", ""))
check("keep-alive whitespace dropped", classify("   \n ") is None)
check("empty payload dropped", classify("") is None)

# ── colour palette (per spec) ────────────────────────────────────
check("incoming message is red", COLORS[("message", True)] == "#ff5c5c")
check("incoming presence is orange", COLORS[("presence", True)] == "#ffa64d")
check("incoming iq is turquoise", COLORS[("iq", True)] == "#00ced1")
check("incoming sm is blue", COLORS[("sm", True)] == "#4d8bff")
check("outgoing message is yellow", COLORS[("message", False)] == "#ffd93b")
check("outgoing presence is green", COLORS[("presence", False)] == "#4cd964")
check("outgoing iq is light blue", COLORS[("iq", False)] == "#4fc3f7")
check("outgoing sm is purple", COLORS[("sm", False)] == "#c07cff")
check("all ten kind/direction colours defined",
      len(COLORS) == 10 and len(set(COLORS.values())) >= 9)


# ── send_raw_xml on the real client ──────────────────────────────
class _FakeStream:
    def __init__(self):
        self.out = []

    def send_raw(self, data):
        self.out.append(data)


client = JabberClient.__new__(JabberClient)
client.xmpp = _FakeStream()
sent = client.send_raw_xml("<message to='a@b'><body>hi</body></message>")
check("send_raw_xml reports one stanza", sent == 1)
check("send_raw_xml serializes the stanza",
      "<message" in client.xmpp.out[0] and "<body>hi</body>" in client.xmpp.out[0])
client.xmpp.out.clear()
client.send_raw_xml("<iq type='get'><query xmlns='jabber:iq:roster'/></iq>")
check("send_raw_xml assigns an id to iq", 'id="xmlc-' in client.xmpp.out[0])
client.xmpp.out.clear()
check("send_raw_xml accepts multiple elements",
      client.send_raw_xml("<presence/><message/>") == 2
      and len(client.xmpp.out) == 2)
client.xmpp.out.clear()
check("send_raw_xml strips an xml declaration",
      client.send_raw_xml("<?xml version='1.0'?><presence/>") == 1
      and client.xmpp.out[0].startswith("<presence"))
try:
    client.send_raw_xml("<not-closed>")
    invalid_raised = False
except ET.ParseError:
    invalid_raised = True
check("send_raw_xml rejects malformed XML", invalid_raised)


# ── _StanzaXMPP hook ─────────────────────────────────────────────
captured = []
probe = object.__new__(_StanzaXMPP)
probe._xml_console_hook = lambda incoming, text: captured.append((incoming, text))
_orig_send_raw = slixmpp.ClientXMPP.send_raw
_orig_recv = slixmpp.ClientXMPP.recv_stanza
slixmpp.ClientXMPP.send_raw = lambda self, data: None
slixmpp.ClientXMPP.recv_stanza = lambda self, stanza: None
try:
    _StanzaXMPP.send_raw(probe, b"<presence/>")

    class _FakeStanza:
        def __str__(self):
            return "<message xmlns='jabber:client' from='a@b'/>"

    _StanzaXMPP.recv_stanza(probe, _FakeStanza())
finally:
    slixmpp.ClientXMPP.send_raw = _orig_send_raw
    slixmpp.ClientXMPP.recv_stanza = _orig_recv
check("hook fires for outgoing bytes", captured[0] == (False, "<presence/>"))
check("hook fires for incoming stanza with XML",
      captured[1] == (True, "<message xmlns='jabber:client' from='a@b'/>"))


# ── dialog behaviour ─────────────────────────────────────────────
class FakeClient:
    def __init__(self):
        self.hook = None
        self.sent = []

    def set_xml_console_hook(self, hook):
        self.hook = hook

    def send_raw_xml(self, text):
        self.sent.append(text)
        return 1


fake = FakeClient()
dlg = XmlConsoleDialog(lambda: fake, None)
check("capture is off by default", dlg._enable.isChecked() is False)
check("hook not attached while disabled", fake.hook is None)

dlg._enable.setChecked(True)
check("enabling attaches the hook", fake.hook is not None)
fake.hook(True, "<message xmlns='jabber:client' from='alice@example.com/phone'>"
                "<body>hello</body></message>")
fake.hook(False, "<iq xmlns='jabber:client' type='result' id='1'/>")
out = dlg._output.toPlainText()
check("incoming message is shown", "hello" in out)
check("outgoing iq is shown", "type='result'" in out)
check("buffer holds both stanzas", len(dlg._buffer) == 2)

# kind filter hides and restores
dlg._kind_boxes["iq"].setChecked(False)
check("unchecking IQ hides it", "type='result'" not in dlg._output.toPlainText())
check("message survives the IQ filter", "hello" in dlg._output.toPlainText())
dlg._kind_boxes["iq"].setChecked(True)
check("rechecking IQ restores it", "type='result'" in dlg._output.toPlainText())

# bare-JID filter
dlg._jid_edit.setText("alice@example.com")
check("bare JID keeps a resourceful match", "hello" in dlg._output.toPlainText()
      and "type='result'" not in dlg._output.toPlainText())
dlg._jid_edit.setText("bob@example.com")
check("non-matching JID hides everything",
      dlg._output.toPlainText().strip() == "")
dlg._jid_edit.clear()

# clear
dlg._on_clear()
check("clear empties the buffer", dlg._buffer == [])
check("clear empties the output", dlg._output.toPlainText() == "")

# export writes the displayed text
dlg._on_raw(True, "<message xmlns='jabber:client' from='a@b'><body>x</body></message>")
export_path = os.path.join(_SCRATCH, "export.txt")
_orig_save = QtWidgets.QFileDialog.getSaveFileName
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (export_path, ""))
try:
    dlg._on_export()
finally:
    QtWidgets.QFileDialog.getSaveFileName = _orig_save
check("export writes the visible text",
      os.path.exists(export_path)
      and "<body>x</body>" in open(export_path, encoding="utf-8").read())

# disabling detaches
dlg._enable.setChecked(False)
check("disabling detaches the hook", fake.hook is None)

# input dialog text round-trip
entry = xml_console.XmlInputDialog(None)
entry._edit.setPlainText("<presence/>")
check("input dialog returns the typed text", entry.text() == "<presence/>")

# ── i18n keys present ────────────────────────────────────────────
check("menu label translated", tr("menu_xml_console") != "menu_xml_console")
check("other filter label translated", tr("xml_console_other") == "Other")

# ── main window wiring (static) ──────────────────────────────────
mw = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "stanza_im", "ui", "main_window.py"), encoding="utf-8").read()
check("Actions menu adds the console item",
      'tr("menu_xml_console")' in mw and 'xml-konzole.svg' in mw)
check("login re-attaches an open console",
      "self._xml_console.attach_client()" in mw)
check("handler opens the console",
      "def _on_xml_console" in mw and "XmlConsoleDialog" in mw)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
