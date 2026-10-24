"""Outgoing call targeting: ignore a busy reject from a non-JMI resource.

Old servers fork the XEP-0353 <propose/> to every resource.  A desktop client
without Jingle Message Initiation (e.g. Psi+) may answer <reject><busy/></reject>
and abort the call while the phone resources are still ringing.  Such a reject
must be ignored as long as another resource advertises JMI.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_call_targeting.py
"""
import inspect
import os
import sys
import tempfile
from types import SimpleNamespace
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_targeting_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp

from stanza_im.xmpp import jingle_rtp
from stanza_im.xmpp.jingle_rtp import (
    JingleRtpManager, NS_JINGLE, NS_JINGLE_MSG)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


JMI = "urn:xmpp:jingle-message:0"
RTP = "urn:xmpp:jingle:apps:rtp:1"
BARE = "rain@example.com"
PSI = f"{BARE}/psi"
PHONE1 = f"{BARE}/phone1"
PHONE2 = f"{BARE}/phone2"


class _Client:
    def __init__(self):
        self.contact_features = {
            PSI: {"urn:xmpp:jingle:1", "urn:xmpp:jingle:apps:file-transfer:5"},
            PHONE1: {JMI, RTP, "urn:xmpp:jingle:apps:rtp:video"},
            PHONE2: {JMI, RTP},
        }
        self.presences = {
            PSI: {"type": "available", "show": "online"},
            PHONE1: {"type": "available", "show": "online"},
            PHONE2: {"type": "available", "show": "away"},
        }
        self.emitted = []

    def emit(self, *args):
        self.emitted.append(args)


def manager():
    mgr = JingleRtpManager.__new__(JingleRtpManager)
    mgr.client = _Client()
    mgr.sessions = {}
    mgr._pending_proposals = {}
    mgr._proceeded = set()
    mgr.closed = []

    def _close(session, state, reason=""):
        mgr.closed.append((session.sid, state, reason))
        mgr.sessions.pop(session.sid, None)

    mgr._close_session = _close
    return mgr


def reject(frm, sid, busy=True):
    msg = slixmpp.Message()
    msg["from"] = frm
    msg["to"] = "me@example.com/r"
    msg["type"] = "chat"
    element = ET.SubElement(msg.xml, "{%s}reject" % NS_JINGLE_MSG)
    element.set("id", sid)
    if busy:
        reason = ET.SubElement(element, "{%s}reason" % NS_JINGLE)
        ET.SubElement(reason, "{%s}busy" % NS_JINGLE)
    return msg


# 1. a JMI-capable resource is chosen for the fallback session-initiate -----
mgr = manager()
mgr.sessions["s1"] = SimpleNamespace(sid="s1", peer_full=BARE)
best = mgr._best_jmi_resource(BARE)
check("the best JMI resource is a phone, not the non-JMI desktop",
      best in (PHONE1, PHONE2))
check("the resource with the better presence wins", best == PHONE1)
check("a bare JID without JMI resources yields nothing",
      mgr._best_jmi_resource("other@example.com") == "")

# 2. a busy reject from the non-JMI desktop is ignored ----------------------
mgr._pending_proposals["s1"] = {"from": PSI, "media": "audio"}
handled = mgr.handle_message(reject(PSI, "s1"))
check("the spurious busy is handled but ignored",
      handled is True and mgr.closed == [] and "s1" in mgr.sessions)
check("the pending proposal is kept", "s1" in mgr._pending_proposals)

# 3. a reject from a real JMI phone still ends the call ---------------------
mgr.handle_message(reject(PHONE1, "s1"))
check("a phone reject ends the session",
      mgr.closed == [("s1", "ended", "reject")]
      and "s1" not in mgr.sessions)

# 4. without any JMI resource the reject is honoured ------------------------
mgr2 = manager()
mgr2.client.contact_features = {f"{BARE}/psi": {"urn:xmpp:jingle:1"}}
mgr2.client.presences = {PSI: {"type": "available", "show": "online"}}
mgr2.sessions["s2"] = SimpleNamespace(sid="s2", peer_full=BARE)
mgr2.handle_message(reject(PSI, "s2"))
check("a lone non-JMI resource can still reject",
      mgr2.closed == [("s2", "ended", "reject")])

# 5. start_call leaves the propose on the bare JID --------------------------
src = inspect.getsource(JingleRtpManager.start_call)
check("the fallback session-initiate targets a JMI resource",
      "_best_jmi_resource(peer_bare)" in src)
check("the propose still goes to the bare JID",
      'target = (session.peer_bare if action == "propose"' in
      inspect.getsource(JingleRtpManager._send_jingle_message))

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All call-targeting tests passed.")
