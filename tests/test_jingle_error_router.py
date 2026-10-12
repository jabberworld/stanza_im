"""The Jingle router must ignore error replies.

An error reply to a Jingle IQ echoes the original <jingle> (action included);
routing it as an incoming action produced a bogus whiteboard invite.

Run with:
    python3 tests/test_jingle_error_router.py
"""
import asyncio
import os
import sys
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import JabberClient  # noqa: E402
from stanza_im.xmpp import jingle as jingle_mod  # noqa: E402
from stanza_im.xmpp import whiteboard as wb_mod  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Reply:
    pass


class _Iq:
    def __init__(self, iq_type):
        self._type = iq_type
        self.xml = ET.Element("{jabber:client}iq")
        jingle = ET.SubElement(self.xml, "{%s}jingle" % jingle_mod.NS_JINGLE)
        jingle.set("action", "session-initiate")
        jingle.set("sid", "s1")
        ET.SubElement(jingle, "{%s}description" % wb_mod.NS_WHITEBOARD)

    def __getitem__(self, key):
        return self._type if key == "type" else None

    def get_error(self):
        return {"condition": "service-unavailable"}

    def reply(self):
        return _Reply()


class _Xmpp:
    def __init__(self):
        self.sent = []

    def send(self, stanza):
        self.sent.append(stanza)


class _Manager:
    def __init__(self):
        self.sessions = {}
        self.calls = []

    @staticmethod
    async def _noop():
        return None

    def dispatch(self, *args):
        self.calls.append(args)
        return self._noop()

    def _dispatch(self, *args):
        self.calls.append(args)
        return self._noop()


def _client():
    client = JabberClient.__new__(JabberClient)
    client.whiteboard = _Manager()
    client.rtp_calls = _Manager()
    client.file_transfer = _Manager()
    client.xmpp = _Xmpp()
    client._start_task = lambda coro: coro.close()
    return client


# 1. an error reply is neither routed nor answered ---------------------------
client = _client()
asyncio.run(client._dispatch_jingle_iq(_Iq("error")))
check("an error Jingle IQ is not routed to any manager",
      not client.whiteboard.calls and not client.rtp_calls.calls
      and not client.file_transfer.calls)
check("an error Jingle IQ is not answered with a result",
      client.xmpp.sent == [])

# 2. a real action is still routed and acked ---------------------------------
client = _client()
asyncio.run(client._dispatch_jingle_iq(_Iq("set")))
check("a set Jingle IQ reaches the whiteboard manager",
      len(client.whiteboard.calls) == 1)
check("a set Jingle IQ is acked", len(client.xmpp.sent) == 1)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All jingle-error-router tests passed.")
