"""Offscreen smoke tests for XEP-0280 Message Carbons and the language picker.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_carbons.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_carb_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

import slixmpp
from slixmpp import Message

from stanza_im.core.client import JabberClient
from stanza_im.ui import subject_dialog

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. language picker ----------------------------------------------------------
check("language list expanded", len(subject_dialog._PRESET_LANGUAGES) >= 20)
combo = subject_dialog.SubjectDialog("room@x", [])._language_combo()
check("language combo non-editable", not combo.isEditable())
check("language combo carries codes",
      combo.count() == len(subject_dialog._PRESET_LANGUAGES)
      and combo.itemData(combo.count() - 1) ==
      subject_dialog._PRESET_LANGUAGES[-1][0])


# 2. XEP-0280 client plumbing -------------------------------------------------
c = JabberClient("me@example.com/res1", "pw", message_carbons=True)
check("carbons toggle stored", c.message_carbons is True)
got_received = []
got_sent = []
c.on("message_received", lambda *a: got_received.append(a))
c.on("message_carbon_sent", lambda *a: got_sent.append(a))


def make_received(body="hello", mid="in-1", mtype="chat"):
    outer = Message()
    outer["from"] = "me@example.com/other"
    outer["to"] = "me@example.com/res1"
    outer["type"] = "chat"
    inner = Message()
    inner["from"] = "alice@example.com/res"
    inner["to"] = "me@example.com/res1"
    inner["type"] = mtype
    inner["body"] = body
    inner["id"] = mid
    rec = ET.SubElement(outer.xml, "{urn:xmpp:carbons:2}received")
    fw = ET.SubElement(rec, "{urn:xmpp:forward:0}forwarded")
    fw.append(inner.xml)
    return outer


def make_sent(body="out", mid="out-1", to="bob@example.com"):
    outer = Message()
    outer["from"] = "me@example.com/other"
    outer["to"] = "me@example.com/res1"
    outer["type"] = "chat"
    inner = Message()
    inner["from"] = "me@example.com/other"
    inner["to"] = to
    inner["type"] = "chat"
    inner["body"] = body
    inner["id"] = mid
    sent = ET.SubElement(outer.xml, "{urn:xmpp:carbons:2}sent")
    fw = ET.SubElement(sent, "{urn:xmpp:forward:0}forwarded")
    fw.append(inner.xml)
    return outer


c._on_carbon_received(make_received())
check("carbon received emitted",
      len(got_received) == 1 and got_received[0][0] == "alice@example.com/res"
      and got_received[0][1] == "hello" and got_received[0][-1] is True)

c._on_carbon_received(make_received(mtype="groupchat"))
check("carbon received ignores groupchat", len(got_received) == 1)

c._on_carbon_sent(make_sent())
check("carbon sent emitted",
      len(got_sent) == 1 and got_sent[0][0] == "bob@example.com"
      and got_sent[0][1] == "out" and got_sent[0][3] == "out-1")

# carbons disabled → no enable call on session start is driven by the flag;
# verify the flag is honoured when constructing the client.
c2 = JabberClient("me@example.com/res1", "pw", message_carbons=False)
check("carbons toggle off", c2.message_carbons is False)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)