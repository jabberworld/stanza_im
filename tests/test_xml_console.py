"""Offscreen smoke tests for the XML console.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_xml_console.py
"""
import logging
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

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.core.client import JabberClient
from stanza_im.ui import xml_console
from stanza_im.ui.xml_console import (COLORS, XmlConsoleDialog, classify,
                                      format_xml, jid_matches)

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── JID substring filter ─────────────────────────────────────────
check("empty filter matches everything", jid_matches("a@b", "c@d", "") is True)
check("whitespace filter matches everything",
      jid_matches("a@b", "c@d", "   ") is True)
check("domain substring matches a MUC JID",
      jid_matches("room@conference.linuxoid.in/nick", "", "conference.linuxoid.in")
      is True)
check("domain substring matches the recipient side",
      jid_matches("", "room@conference.linuxoid.in/nick", "conference.linuxoid.in")
      is True)
check("substring filter is case-insensitive",
      jid_matches("Room@Conference.Linuxoid.IN/nick", "", "conference.linuxoid") is True)
check("non-matching filter is rejected",
      jid_matches("room@conference.linuxoid.in/nick", "", "jabber.ru") is False)
check("resource is part of the searched string",
      jid_matches("user@host/phone", "", "phone") is True)
check("bare JID still matches its resourceful form",
      jid_matches("user@host/phone", "", "user@host") is True)


# ── classification ───────────────────────────────────────────────
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

# regression: slixmpp omits the default jabber:client namespace on top-level
# stanzas, so a bare <message> must still classify as a message.
check("namespace-less message classified",
      classify("<message to='a@b' type='chat'><body>x</body></message>")
      == ("message", "", "a@b"))
check("namespace-less presence classified",
      classify("<presence from='a@b'/>")[0] == "presence")
check("namespace-less iq classified",
      classify("<iq type='get' id='1'/>")[0] == "iq")
check("prefixed message classified",
      classify("<ns0:message xmlns:ns0='jabber:client' from='a@b'/>")
      == ("message", "a@b", ""))
check("foreign namespace is not a message",
      classify("<message xmlns='urn:example:custom'/>")[0] == "other")

# ── pretty printing ──────────────────────────────────────────────
formatted = format_xml("<message to='a@b'><event xmlns='urn:x'><items node='n'>"
                       "<item id='1'><tune/></item></items></event></message>")
check("nested elements are indented", "\n  <event" in formatted
      and "\n    <items" in formatted and "\n      <item" in formatted)
check("text-only element stays on one line",
      format_xml("<message><body>hi</body></message>")
      == "<message>\n  <body>hi</body>\n</message>")
check("no xml declaration is emitted", "<?xml" not in formatted)
check("unparseable payload is returned as-is",
      format_xml("</stream:stream>") == "</stream:stream>")
check("empty payload stays empty", format_xml("   ") == "")

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


# ── log handler parsing (the capture mechanism) ──────────────────
records = []
handler = xml_console._XmlConsoleLogHandler(lambda i, t: records.append((i, t)))


def _record(message, args):
    return logging.LogRecord("slixmpp.xmlstream", logging.DEBUG, __file__, 1,
                             message, args, None)


handler.emit(_record("SEND: %s", ("<presence/>",)))
handler.emit(_record("RECV: %s", (b"<message/>",)))
handler.emit(_record("Event triggered: message", ()))
check("handler parses SEND", records[0] == (False, "<presence/>"))
check("handler decodes bytes and parses RECV", records[1] == (True, "<message/>"))
check("handler ignores other debug records", len(records) == 2)


# ── dialog behaviour ─────────────────────────────────────────────
class FakeClient:
    def __init__(self):
        self.sent = []

    def send_raw_xml(self, text):
        self.sent.append(text)
        return 1


logger = logging.getLogger("slixmpp.xmlstream")
level_before = logger.level
fake = FakeClient()
dlg = XmlConsoleDialog(lambda: fake, None)
check("capture is off by default", dlg._enable.isChecked() is False)
check("logger is not attached while disabled",
      dlg._log_handler not in logger.handlers)

dlg._enable.setChecked(True)
check("enabling attaches the logger", dlg._log_handler in logger.handlers)
check("enabling raises the logger to DEBUG", logger.level == logging.DEBUG)

# The live path: slixmpp logs the raw dump at DEBUG (same as -x / the file log).
logger.debug("RECV: %s",
             "<message from='alice@example.com/phone'><body>hello</body></message>")
logger.debug("SEND: %s", "<iq type='result' id='1'/>")
logger.debug("SEND: %s", b"<presence from='bob@example.com'/>")
logger.debug("Event triggered: message")
out = dlg._output.toPlainText()
check("incoming message is shown", "hello" in out)
check("outgoing iq is shown", 'type="result"' in out)
check("bytes record is decoded", "<presence" in out)
check("unrelated debug records are ignored", len(dlg._buffer) == 3)

# controlled entries for the filter checks
dlg._on_clear()
dlg._on_raw(True, "<message xmlns='jabber:client' "
                  "from='alice@example.com/phone'><body>hello</body></message>")
dlg._on_raw(False, "<iq xmlns='jabber:client' type='result' id='1'/>")
check("buffer holds both stanzas", len(dlg._buffer) == 2)

# kind filter hides and restores
dlg._kind_boxes["iq"].setChecked(False)
check("unchecking IQ hides it", 'type="result"' not in dlg._output.toPlainText())
check("message survives the IQ filter", "hello" in dlg._output.toPlainText())
dlg._kind_boxes["iq"].setChecked(True)
check("rechecking IQ restores it", 'type="result"' in dlg._output.toPlainText())

# substring JID filter
dlg._jid_edit.setText("alice@example.com")
check("bare JID keeps a resourceful match", "hello" in dlg._output.toPlainText()
      and 'type="result"' not in dlg._output.toPlainText())
dlg._jid_edit.setText("EXAMPLE.com")
check("filter is a case-insensitive substring",
      "hello" in dlg._output.toPlainText())
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

# disabling detaches the logger and restores its level
dlg._enable.setChecked(False)
check("disabling detaches the logger", dlg._log_handler not in logger.handlers)
check("disabling restores the logger level", logger.level == level_before)

# input dialog text round-trip
entry = xml_console.XmlInputDialog(None)
entry._edit.setPlainText("<presence/>")
check("input dialog returns the typed text", entry.text() == "<presence/>")

# ── i18n keys present ────────────────────────────────────────────
check("menu label translated", tr("menu_xml_console") != "menu_xml_console")
check("other filter label translated", tr("xml_console_other") == "Other")

# ── main window wiring (static) ──────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
mw = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
          encoding="utf-8").read()
xc = open(os.path.join(_root, "stanza_im", "ui", "xml_console.py"),
          encoding="utf-8").read()
check("Actions menu adds the console item",
      'tr("menu_xml_console")' in mw and 'xml-konzole.svg' in mw)
check("handler opens the console",
      "def _on_xml_console" in mw and "XmlConsoleDialog" in mw)
check("capture uses the slixmpp raw logger", "slixmpp.xmlstream" in xc)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
