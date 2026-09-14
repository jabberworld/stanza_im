"""Tests for the XEP-0202 Entity Time workaround.

slixmpp 1.17's ``xep_0202.set_tzo`` feeds a time-only string to
``xep_0082.parse`` and raises when answering a ``<time/>`` request, so the
client installs its own responder.  These tests check the reply shape and the
outgoing query parser.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_time.py
"""
import asyncio
import os
import re
import sys
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp

from stanza_im.core.client import JabberClient, NS_TIME

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


client = JabberClient("me@example.com/res", "pw")

# ── 1. incoming <time/> request is answered correctly ---------------------
iq = slixmpp.Iq()
iq["type"] = "get"
iq["to"] = "me@example.com/res"
iq["from"] = "bob@example.com/phone"
ET.SubElement(iq.xml, "{%s}time" % NS_TIME)
sent = []
client.xmpp.send = lambda stanza: sent.append(stanza)
client._on_time_request(iq)

check("time request answered", len(sent) == 1)
reply = sent[0]
check("time reply is a result", reply["type"] == "result")
utc = reply.xml.find("{%s}time/{%s}utc" % (NS_TIME, NS_TIME))
tzo = reply.xml.find("{%s}time/{%s}tzo" % (NS_TIME, NS_TIME))
check("time reply has utc", utc is not None and bool(utc.text)
      and utc.text.endswith("Z")
      and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", utc.text))
check("time reply has tzo", tzo is not None
      and re.match(r"^[+-]\d{2}:\d{2}$", tzo.text or ""))


# ── 2. outgoing query parses the peer's answer ---------------------------
def _fake_iq_factory(result_xml):
    class _FakeIq:
        def __init__(self):
            self.xml = ET.Element("{jabber:client}iq")

        def __setitem__(self, key, value):
            pass

        async def send(self, timeout=None):
            return type("R", (), {"xml": result_xml})()

    return _FakeIq


result = ET.Element("{jabber:client}iq")
time_el = ET.SubElement(result, "{%s}time" % NS_TIME)
ET.SubElement(time_el, "{%s}utc" % NS_TIME).text = "2026-09-14T10:00:00Z"
ET.SubElement(time_el, "{%s}tzo" % NS_TIME).text = "+03:00"
client.xmpp.Iq = _fake_iq_factory(result)
parsed = asyncio.run(client._get_entity_time("bob@example.com"))
check("entity time parsed", parsed == {"utc": "2026-09-14T10:00:00Z",
                                       "tzo": "+03:00"})

print("\nAll tests passed" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
