"""Offscreen smoke tests for XEP-0490 Message Displayed Synchronization.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_mds.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_mds_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

import slixmpp

from stanza_im.core.client import (
    JabberClient, NS_MDS, NS_PUBSUB, NS_PUBSUB_EVENT, NS_MDS_ASSIST,
)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


c = JabberClient("me@example.com/res", "pw", message_displayed_sync=True)
c._mds_pubsub_options = True
c._mds_server_assist = True

mds_events = []
c.on("mds_displayed", lambda *a: mds_events.append(a))

# 1. PEP publish IQ shape ------------------------------------------------------
iq = c._mds_build_pep("bob@example.com", "sid-123")
xml = iq.xml
item = next(it for it in xml.iter(f"{{{NS_PUBSUB}}}item"))
check("pep item id is chat jid", item.get("id") == "bob@example.com")
publish = next(xml.iter(f"{{{NS_PUBSUB}}}publish"))
check("pep node", publish.get("node") == NS_MDS)
disp = next(xml.iter(f"{{{NS_MDS}}}displayed"))
sid_el = next(disp.iter("{urn:xmpp:sid:0}stanza-id"))
check("pep stanza-id by/id",
      sid_el.get("by") == c.jid_str and sid_el.get("id") == "sid-123")
opts = list(xml.iter(f"{{{NS_PUBSUB}}}publish-options"))
check("pep publish-options", len(opts) == 1)

# without publish-options support -------------------------------------------
c._mds_pubsub_options = False
iq2 = c._mds_build_pep("bob@example.com", "sid-2")
check("no options when unsupported",
      len(list(iq2.xml.iter(f"{{{NS_PUBSUB}}}publish-options"))) == 0)
c._mds_pubsub_options = True

# 2. server-assist message shape ------------------------------------------------
msg = c._mds_build_message("bob@example.com", "sid-3", "msgid-9")
mxml = msg.xml
marker = next(mxml.iter("{urn:xmpp:chat-markers:0}displayed"))
check("assist chat-marker id", marker.get("id") == "msgid-9")
s2 = next(mxml.iter(f"{{{NS_MDS}}}displayed"))
st2 = next(s2.iter("{urn:xmpp:sid:0}stanza-id"))
check("assist mds sid", st2.get("id") == "sid-3")

# 3. remote apply dedup + emit -------------------------------------------------
c._mds_apply_remote("bob@example.com", "sid-10")
check("apply emits", len(mds_events) == 1 and mds_events[0] == ("bob@example.com",))
c._mds_apply_remote("bob@example.com", "sid-10")
check("apply dedups", len(mds_events) == 1)
c._mds_apply_remote("", "")
check("apply ignores empties", len(mds_events) == 1)

# 4. scan PEP result items -------------------------------------------------------
root = ET.Element("root")
items = ET.SubElement(root, f"{{{NS_PUBSUB}}}items")
items.set("node", NS_MDS)
item = ET.SubElement(items, f"{{{NS_PUBSUB}}}item")
item.set("id", "alice@example.com")
disp = ET.SubElement(item, f"{{{NS_MDS}}}displayed")
st = ET.SubElement(disp, "{urn:xmpp:sid:0}stanza-id")
st.set("by", c.jid_str)
st.set("id", "sid-alice")
found = list(c._mds_scan_result(root))
check("scan result", found == [("alice@example.com", "sid-alice", c.jid_str)])

# 5. notification event handling -----------------------------------------------
headline = slixmpp.Message()
headline["type"] = "headline"
headline["from"] = "me@example.com"
headline["to"] = "me@example.com/res"
event = ET.SubElement(headline.xml, f"{{{NS_PUBSUB_EVENT}}}event")
ev_items = ET.SubElement(event, f"{{{NS_PUBSUB_EVENT}}}items")
ev_items.set("node", NS_MDS)
ev_item = ET.SubElement(ev_items, f"{{{NS_PUBSUB_EVENT}}}item")
ev_item.set("id", "carol@example.com")
edisp = ET.SubElement(ev_item, f"{{{NS_MDS}}}displayed")
est = ET.SubElement(edisp, "{urn:xmpp:sid:0}stanza-id")
est.set("by", c.jid_str)
est.set("id", "sid-carol")

_before = list(mds_events)
c._on_message(headline)
check("notification applies", len(mds_events) == len(_before) + 1
      and mds_events[-1] == ("carol@example.com",))

# notification from a third party is ignored ------------------------------------
h2 = slixmpp.Message()
h2["type"] = "headline"
h2["from"] = "evil@elsewhere.im"
h2["to"] = "me@example.com/res"
ev2 = ET.SubElement(h2.xml, f"{{{NS_PUBSUB_EVENT}}}event")
it2 = ET.SubElement(ET.SubElement(
    ev2, f"{{{NS_PUBSUB_EVENT}}}items"),
    f"{{{NS_PUBSUB_EVENT}}}item")
it2.set("id", "dave@example.com")
d2 = ET.SubElement(it2, f"{{{NS_MDS}}}displayed")
st2b = ET.SubElement(d2, "{urn:xmpp:sid:0}stanza-id")
st2b.set("by", "evil@elsewhere.im")
st2b.set("id", "sid-dave")
_before2 = list(mds_events)
c._on_message(h2)
check("foreign notification ignored", list(mds_events) == _before2)

# 6. mark-displayed uses tracked sid -------------------------------------------
c._mds_track("eve@example.com", slixmpp.Message(), "sid-track")
check("track sid", c._mds_last_sid.get("eve@example.com") == "sid-track")
c.mds_mark_displayed("eve@example.com")
check("mark updates local", c._mds_local.get("eve@example.com") == "sid-track")

# 7. toggle off ----------------------------------------------------------------
c_off = JabberClient("me@example.com/r", "pw", message_displayed_sync=False)
c_off.mds_mark_displayed("any@example.com")
check("disabled does nothing", not c_off._mds_local)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)