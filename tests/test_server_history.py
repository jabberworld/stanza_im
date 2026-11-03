"""Tests for XEP-0431 MAM full-text query construction and gating."""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_server_history_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import JabberClient, NS_DATA, NS_FULLTEXT, NS_MAM  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


client = JabberClient("me@example.com/res", "pw")
check("a client starts with an empty room-feature cache",
      client._muc_room_features == {})
client._server_features = {"urn:xmpp:fulltext:0", "urn:xmpp:mam:2"}
client._muc_room_features = {
    "room@conference.example": {"urn:xmpp:fulltext:0", "urn:xmpp:mam:2"},
}
check("account full-text support is detected",
      client.supports_mam_fulltext("bob@example.com"))
check("room full-text support is detected",
      client.supports_mam_fulltext("room@conference.example", is_muc=True))
check("unknown room support is false",
      not client.supports_mam_fulltext("other@conference.example", is_muc=True))

iq, mask = client._mam_fulltext_query(
    "me@example.com", "bob@example.com", "hello world", 100, "cursor-1")
xml = ET.tostring(iq.xml, encoding="unicode")
field = iq.xml.find(
    ".//{%s}field[@var='{%s}fulltext']" % (NS_DATA, NS_FULLTEXT))
with_field = iq.xml.find(".//{%s}field[@var='with']" % NS_DATA)
rsm = iq.xml.find(".//{http://jabber.org/protocol/rsm}set")
check("the MAM query targets the user archive", iq["to"] == "me@example.com")
check("the full-text form field carries the query",
      field is not None and field.find("{%s}value" % NS_DATA).text
      == "hello world")
check("the 1:1 query carries the peer JID",
      with_field is not None
      and with_field.find("{%s}value" % NS_DATA).text == "bob@example.com")
check("the query carries RSM max and after",
      rsm is not None
      and rsm.find("{http://jabber.org/protocol/rsm}max").text == "100"
      and rsm.find("{http://jabber.org/protocol/rsm}after").text == "cursor-1")
check("the collector mask is built", mask is not None)

room_iq, _room_mask = client._mam_fulltext_query(
    "room@conference.example", None, "hello", 100)
room_xml = ET.tostring(room_iq.xml, encoding="unicode")
check("a MUC query has no with field",
      room_iq.xml.find(".//{%s}field[@var='with']" % NS_DATA) is None)
check("a MUC query still has the full-text field",
      room_iq.xml.find(
          ".//{%s}field[@var='{%s}fulltext']" % (NS_DATA, NS_FULLTEXT))
      is not None)
check("the MAM namespace is present", NS_MAM in room_xml)

if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll server-history tests passed.")
