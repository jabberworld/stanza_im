"""Tests for the collaborative whiteboard manager (Jingle + XEP-0284 SXE).

Run with:
    python3 tests/test_whiteboard_sync.py
"""
import asyncio
import os
import sys
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.xmpp import whiteboard as wb_mod
from stanza_im.xmpp.whiteboard import (NS_SXE, WhiteboardManager,
                                       WhiteboardSession, is_whiteboard_jingle)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _q(ns, tag):
    return "{%s}%s" % (ns, tag)


class _FakeStanza:
    def __init__(self, tag, sent):
        self.xml = ET.Element(tag)
        self.sent = sent
        self.fields = {}

    def __setitem__(self, key, value):
        self.fields[key] = value

    def __getitem__(self, key):
        return self.fields.get(key)

    def send(self):
        self.sent.append(self)


class _FakeXmpp:
    def __init__(self):
        self.sent = []

    def Message(self):
        return _FakeStanza("message", self.sent)

    def Iq(self):
        return _FakeStanza("iq", self.sent)


class _FakeClient:
    def __init__(self):
        self.xmpp = _FakeXmpp()
        self.events = []
        self.jid_str = "me@example.com"
        self._full_jid = "me@example.com/pc"
        self.groupchats = {}
        self.presences = {}
        self.contact_features = {}

    def emit(self, *args):
        self.events.append(args)

    def _add_resource(self, full, show="online", features=()):
        self.presences[full] = {"show": show, "type": "available"}
        self.contact_features[full] = set(features)


class _FakeIncoming:
    def __init__(self, frm, xml):
        self._frm = frm
        self.xml = xml

    def __getitem__(self, key):
        return self._frm if key == "from" else None


def _state_of(client, index=-1):
    """The most recent SXE <state> element sent by the client."""
    states = []
    for stanza in client.xmpp.sent:
        state = stanza.xml.find(".//%s" % _q(NS_SXE, "state"))
        if state is not None:
            states.append(state)
    return states[index] if states else None


def _last_sxe(client):
    for stanza in reversed(client.xmpp.sent):
        el = stanza.xml.find(_q(NS_SXE, "sxe"))
        if el is not None:
            return el
    return None


# 1. is_whiteboard_jingle ----------------------------------------------------
jingle = ET.Element(_q(wb_mod.NS_JINGLE, "jingle"))
content = ET.SubElement(jingle, _q(wb_mod.NS_JINGLE, "content"))
ET.SubElement(content, _q(wb_mod.NS_WHITEBOARD, "description"))
check("a whiteboard jingle is recognised", is_whiteboard_jingle(jingle))
empty = ET.Element(_q(wb_mod.NS_JINGLE, "jingle"))
check("a plain jingle is not a whiteboard", not is_whiteboard_jingle(empty))

# 2. start a 1:1 session -----------------------------------------------------
client = _FakeClient()
client._add_resource("bob@example.com/desktop", show="online",
                     features=(wb_mod.NS_WHITEBOARD,))
mgr = WhiteboardManager(client)
sid = mgr.start_session("bob@example.com", is_muc=False)
check("a session is created", sid in mgr.sessions)
initiate = client.xmpp.sent[0]
check("session-initiate targets the peer's full JID",
      initiate.fields.get("to") == "bob@example.com/desktop")
check("session-initiate carries the whiteboard description",
      initiate.xml.find(".//%s" % _q(wb_mod.NS_WHITEBOARD, "description"))
      is not None)
check("the document is seeded with a viewBox",
      mgr.document(sid).records[mgr.document(sid).root_rid].children)

# 3. add / update / remove shapes -------------------------------------------
rid = mgr.add_shape(sid, {"id": "s1", "d": "M 0 0 L 10 10",
                          "stroke": "#000000", "stroke-width": "2",
                          "fill": "none"})
check("add_shape returns a record id", bool(rid))
shapes = mgr.shapes(sid)
check("the shape is listed", len(shapes) == 1 and shapes[0]["rid"] == rid)
check("the shape keeps its path data", shapes[0]["d"] == "M 0 0 L 10 10")
check("adding a shape sends a <new> edit",
      _state_of(client).find(_q(NS_SXE, "new")) is not None)

mgr.update_shape(sid, rid, {"d": "M 0 0 L 20 20"})
check("updating a shape sends a <set> edit",
      _state_of(client).find(_q(NS_SXE, "set")) is not None)
check("the document reflects the update",
      mgr.shapes(sid)[0]["d"] == "M 0 0 L 20 20")

# 4. round-trip a full snapshot into a second manager -----------------------
mgr._send_state(mgr.session(sid), "bob@example.com")
snapshot = _state_of(client)
check("the snapshot carries a document-begin",
      snapshot.find(_q(NS_SXE, "document-begin")) is not None)
mgr2 = WhiteboardManager(_FakeClient())
sess2 = WhiteboardSession(sid="remote", peer="bob@example.com")
mgr2.sessions["remote"] = sess2
mgr2._apply_state(sess2, snapshot)
check("a remote manager applies the snapshot",
      len(mgr2.shapes("remote")) == 1
      and mgr2.shapes("remote")[0]["d"] == "M 0 0 L 20 20")

# 5. a full snapshot overwrites the remote document --------------------------
extra = ET.Element(_q(NS_SXE, "state"))
begin = ET.SubElement(extra, _q(NS_SXE, "document-begin"))
begin.set("prolog", "data:text/xml,")
mgr2._apply_state(sess2, extra)
check("document-begin clears the drawable records",
      mgr2.shapes("remote") == [])

# 6. remove ------------------------------------------------------------------
mgr.remove_shape(sid, rid)
check("removing a shape sends a <remove> edit",
      _state_of(client).find(_q(NS_SXE, "remove")) is not None)
check("the shape is gone", mgr.shapes(sid) == [])

# 7. MUC session announces itself and connects -------------------------------
room = "room@conference.example.com"
mgr_muc = WhiteboardManager(_FakeClient())
sid_muc = mgr_muc.start_session(room, is_muc=True)
connect = _last_sxe(mgr_muc.client)
check("a MUC session sends a <connect>",
      connect is not None
      and connect.find(_q(NS_SXE, "connect")) is not None)
check("the MUC connect is a groupchat message",
      mgr_muc.client.xmpp.sent[-1].fields.get("type") == "groupchat")
check("a MUC session is immediately ready",
      ("whiteboard_ready", sid_muc) in mgr_muc.client.events)

# 8. the host answers a participant's connect with a state-offer -------------
mgr_muc.add_shape(sid_muc, {"id": "s2", "d": "M 1 1 L 2 2"})
offer_msg = _FakeIncoming("room@conference.example.com/carol",
                          ET.Element("{jabber:client}message"))
sxe_el = ET.SubElement(offer_msg.xml, _q(NS_SXE, "sxe"))
sxe_el.set("session", sid_muc)
ET.SubElement(sxe_el, _q(NS_SXE, "connect"))
asyncio.run(mgr_muc.handle_sxe(offer_msg))
check("the host offers the state to the joiner",
      _last_sxe(mgr_muc.client).find(_q(NS_SXE, "state-offer")) is not None)

# 9. end a 1:1 session -------------------------------------------------------
mgr.end_session(sid)
check("ending a session drops it", sid not in mgr.sessions)
check("ending a 1:1 session sends session-terminate to the full JID",
      any(s.fields.get("to") == "bob@example.com/desktop"
          and s.xml.find(".//%s" % _q(wb_mod.NS_JINGLE, "jingle")) is not None
          for s in client.xmpp.sent))
check("ending emits whiteboard_ended",
      ("whiteboard_ended", sid) in client.events)

# 10. sharing with our own JID stays local (no invite loop) ------------------
own_client = _FakeClient()
mgr_own = WhiteboardManager(own_client)
sid_own = mgr_own.start_session("me@example.com", is_muc=False)
check("sharing with our own JID sends no session-initiate",
      not any(s.xml.find(".//%s" % _q(wb_mod.NS_JINGLE, "jingle")) is not None
              for s in own_client.xmpp.sent))
check("the own-JID session is marked local-only",
      mgr_own.session(sid_own).local_only)
check("the local-only session is ready",
      ("whiteboard_ready", sid_own) in own_client.events)

# 11. resource resolution for 1:1 --------------------------------------------
c = _FakeClient()
c._add_resource("carol@x/phone", show="online")
c._add_resource("carol@x/laptop", show="away",
                features=(wb_mod.NS_WHITEBOARD,))
m = WhiteboardManager(c)
m.start_session("carol@x", is_muc=False)
check("a whiteboard-capable resource is preferred",
      c.xmpp.sent[0].fields.get("to") == "carol@x/laptop")

c = _FakeClient()
c._add_resource("dave@x/phone", show="online")
m = WhiteboardManager(c)
m.start_session("dave@x", is_muc=False)
check("falls back to the best available resource",
      c.xmpp.sent[0].fields.get("to") == "dave@x/phone")

c = _FakeClient()
m = WhiteboardManager(c)
sid_none = m.start_session("erin@x", is_muc=False)
check("no resource fails fast", m.session(sid_none).failure == "unavailable")
check("no session-initiate is sent without a resource",
      not any(s.xml.find(".//%s" % _q(wb_mod.NS_JINGLE, "jingle")) is not None
              for s in c.xmpp.sent))

# 12. a Jingle error for a known session surfaces whiteboard_failed ----------
c = _FakeClient()
c._add_resource("frank@x/pc", features=(wb_mod.NS_WHITEBOARD,))
m = WhiteboardManager(c)
sid_f = m.start_session("frank@x", is_muc=False)
m.handle_error("session-initiate", sid_f, "service-unavailable")
check("a session-initiate error emits whiteboard_failed",
      ("whiteboard_failed", sid_f, "service-unavailable") in c.events)
check("the failed session is dropped", m.session(sid_f) is None)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All whiteboard sync tests passed.")
