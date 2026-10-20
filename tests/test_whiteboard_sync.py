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

    def send(self, callback=None, timeout=None):
        # IQs keep their result callback (the test fires it to simulate the
        # acknowledgement); messages just record the stanza.
        self.callback = callback
        self.sent.append(self)
        return None


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
                          "fill": "none", "stroke-linecap": "round",
                          "stroke-linejoin": "round",
                          "fill-rule": "evenodd"})
check("add_shape returns a record id", bool(rid))
shapes = mgr.shapes(sid)
check("the shape is listed", len(shapes) == 1 and shapes[0]["rid"] == rid)
check("the shape keeps its path data", shapes[0]["d"] == "M 0 0 L 10 10")
check("add_shape carries cap/join/fill-rule",
      (shapes[0]["stroke-linecap"], shapes[0]["stroke-linejoin"],
       shapes[0]["fill-rule"]) == ("round", "round", "evenodd"))
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

# 5. a snapshot is merged, not a replace ------------------------------------
extra = ET.Element(_q(NS_SXE, "state"))
begin = ET.SubElement(extra, _q(NS_SXE, "document-begin"))
begin.set("prolog", "data:text/xml,")
mgr2._apply_state(sess2, extra)
check("an empty snapshot keeps the local shapes",
      len(mgr2.shapes("remote")) == 1)

# A snapshot from a foreign host (its own root RID) is merged: the host's root
# RID is adopted (XEP-0284 §10.3) and the local shapes are re-parented under it.
snap = ET.Element(_q(NS_SXE, "state"))
ET.SubElement(snap, _q(NS_SXE, "document-begin"))
root_new = ET.SubElement(snap, _q(NS_SXE, "new"))
root_new.set("rid", "other-root")
root_new.set("type", "element")
root_new.set("name", "svg")
root_new.set("primary-weight", "0")
shape_new = ET.SubElement(snap, _q(NS_SXE, "new"))
shape_new.set("rid", "shape2")
shape_new.set("type", "element")
shape_new.set("parent", "other-root")
shape_new.set("name", "path")
shape_new.set("primary-weight", "1")
d_attr = ET.SubElement(snap, _q(NS_SXE, "new"))
d_attr.set("rid", "shape2-d")
d_attr.set("type", "attr")
d_attr.set("parent", "shape2")
d_attr.set("name", "d")
d_attr.set("chdata", "M 5 5 L 9 9")
ET.SubElement(snap, _q(NS_SXE, "document-end"))
mgr2._apply_state(sess2, snap)
remote = mgr2.shapes("remote")
check("a foreign snapshot's root RID is adopted",
      mgr2.document("remote").root_rid == "other-root")
check("a snapshot merges a new shape without losing the local one",
      len(remote) == 2 and any(s["d"] == "M 5 5 L 9 9" for s in remote)
      and any(s["d"] == "M 0 0 L 20 20" for s in remote))

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

# 13. upload_http_media returns a full XEP-0385 media dict ------------------
import tempfile as _tf  # noqa: E402
from stanza_im.core.client import JabberClient  # noqa: E402

jc = JabberClient.__new__(JabberClient)


async def _svc():
    return "upload.example"


async def _slot(service, name, size, ctype):
    return ("http://put", "https://upload.example/%s" % name, {})


async def _put(url, path, headers, progress):
    return None


jc._http_upload_service = _svc
jc._http_upload_slot = _slot
jc._http_upload_put = _put
_tmp = _tf.NamedTemporaryFile(suffix=".png", delete=False)
_tmp.write(b"png")
_tmp.close()
_media = asyncio.run(jc.upload_http_media(_tmp.name, 1280, 720))
check("upload_http_media returns a full media dict",
      _media["url"] == "https://upload.example/" + os.path.basename(_tmp.name)
      and _media["name"] == os.path.basename(_tmp.name)
      and _media["size"] == 3 and _media["media_type"] == "image/png"
      and _media["width"] == 1280 and _media["height"] == 720
      and "sha-256" in _media["hashes"])
os.remove(_tmp.name)

# 14. MUC: one deterministic session per room, edits render across peers -----
a = WhiteboardManager(_FakeClient())
b = WhiteboardManager(_FakeClient())
sid_a = a.start_session("room@conference.example", is_muc=True)
sid_b = b.start_session("room@conference.example", is_muc=True)
check("both peers of a room get the same session id", sid_a == sid_b)
check("the shared document uses the fixed root rid",
      a.document(sid_a).root_rid == "0")

a.add_shape(sid_a, {"id": "s1", "d": "M 0 0 L 10 10"})
_edit = _state_of(a.client)
_in = _FakeIncoming("room@conference.example/a",
                    ET.Element("{jabber:client}message"))
_sxe = ET.SubElement(_in.xml, _q(NS_SXE, "sxe"))
_sxe.set("session", sid_a)
_sxe.append(_edit)
asyncio.run(b.handle_sxe(_in))
check("a peer's incremental edit lands in the shared document",
      len(b.shapes(sid_b)) == 1
      and b.shapes(sid_b)[0]["d"] == "M 0 0 L 10 10")

# 15. board activity (start/end) announcements ------------------------------
c = _FakeClient()
m = WhiteboardManager(c)
sid = m.start_session("room@conference.example", is_muc=True)
check("starting a MUC board announces activity",
      ("whiteboard_activity", "room@conference.example", True) in c.events)

# A passive occupant learns from a peer's <connect>.
c2 = _FakeClient()
m2 = WhiteboardManager(c2)
_in = _FakeIncoming("room@conference.example/alice",
                    ET.Element("{jabber:client}message"))
_sxe = ET.SubElement(_in.xml, _q(NS_SXE, "sxe"))
_sxe.set("session", "peer-sid")
ET.SubElement(_sxe, _q(NS_SXE, "connect"))
asyncio.run(m2.handle_sxe(_in))
check("a passive occupant sees the board activity",
      ("whiteboard_activity", "room@conference.example", True) in c2.events)

_in2 = _FakeIncoming("room@conference.example/alice",
                     ET.Element("{jabber:client}message"))
_sxe2 = ET.SubElement(_in2.xml, _q(NS_SXE, "sxe"))
_sxe2.set("session", "peer-sid")
ET.SubElement(_sxe2, _q(NS_SXE, "close"))
asyncio.run(m2.handle_sxe(_in2))
check("a <close/> ends the board activity",
      ("whiteboard_activity", "room@conference.example", False) in c2.events)
check("a <close/> emits whiteboard_ended",
      ("whiteboard_ended", "peer-sid") in c2.events)

# end_session broadcasts <close/> in a MUC.
c3 = _FakeClient()
m3 = WhiteboardManager(c3)
sid3 = m3.start_session("room@conference.example", is_muc=True)
m3.end_session(sid3)
check("ending a MUC board broadcasts <close/>",
      _last_sxe(c3) is not None
      and _last_sxe(c3).find(_q(NS_SXE, "close")) is not None)
check("ending a MUC board announces inactivity",
      ("whiteboard_activity", "room@conference.example", False) in c3.events)

# A presence advertisement (late room joiner).
c4 = _FakeClient()
m4 = WhiteboardManager(c4)
_pres = _FakeIncoming("room@conference.example/bob",
                      ET.Element("{jabber:client}presence"))
ET.SubElement(_pres.xml, _q(NS_SXE, "sxe"))
asyncio.run(m4.handle_sxe_presence(_pres))
check("a presence board advertisement announces activity",
      ("whiteboard_activity", "room@conference.example", True) in c4.events)

# 16. undo / redo ------------------------------------------------------------
c = _FakeClient()
c._add_resource("bob@example.com/pc", features=(wb_mod.NS_WHITEBOARD,))
m = WhiteboardManager(c)
sid = m.start_session("bob@example.com", is_muc=False)
rid = m.add_shape(sid, {"id": "s1", "d": "M 0 0 L 10 10"})
check("the shape is present", len(m.shapes(sid)) == 1)
check("undo is available", m.can_undo(sid))
_sent_before = len(c.xmpp.sent)
m.undo(sid)
check("undo removes the added shape", m.shapes(sid) == [])
check("undo broadcasts the inverse edit", len(c.xmpp.sent) > _sent_before)
check("redo is available", m.can_redo(sid))
m.redo(sid)
check("redo re-adds the shape", len(m.shapes(sid)) == 1)

# undo a transform (an attribute <set>)
rid2 = m.shapes(sid)[0]["rid"]
m.update_shape(sid, rid2, {"transform": "matrix(1 0 0 1 50 50)"})
check("the transform is applied", m.shapes(sid)[0]["transform"] != "")
m.undo(sid)
check("undo restores the previous transform",
      m.shapes(sid)[0]["transform"] == "")

# a new operation clears the redo stack
m.undo(sid)
check("redo is available after an undo", m.can_redo(sid))
m.add_shape(sid, {"id": "s2", "d": "M 1 1 L 2 2"})
check("a new operation clears the redo stack", not m.can_redo(sid))

# undo a remove restores the shape
rid3 = m.add_shape(sid, {"id": "s3", "d": "M 3 3 L 4 4"})
_before = len(m.shapes(sid))
m.remove_shape(sid, rid3)
check("remove drops the shape", len(m.shapes(sid)) == _before - 1)
m.undo(sid)
check("undo restores the removed shape", len(m.shapes(sid)) == _before)

# undo a remote edit
c5 = _FakeClient()
m5 = WhiteboardManager(c5)
sid5 = m5.start_session("room@conference.example", is_muc=True)
_in = _FakeIncoming("room@conference.example/alice",
                    ET.Element("{jabber:client}message"))
_sxe = ET.SubElement(_in.xml, _q(NS_SXE, "sxe"))
_sxe.set("session", sid5)
_state = ET.SubElement(_sxe, _q(NS_SXE, "state"))
_n = ET.SubElement(_state, _q(NS_SXE, "new"))
_n.set("rid", "remote-1")
_n.set("type", "element")
_n.set("parent", "0")
_n.set("name", "path")
_n.set("primary-weight", "1")
_d = ET.SubElement(_state, _q(NS_SXE, "new"))
_d.set("rid", "remote-1-d")
_d.set("type", "attr")
_d.set("parent", "remote-1")
_d.set("name", "d")
_d.set("chdata", "M 0 0 L 5 5")
asyncio.run(m5.handle_sxe(_in))
check("a remote edit is applied", len(m5.shapes(sid5)) == 1)
m5.undo(sid5)
check("undo reverts a remote edit", m5.shapes(sid5) == [])

# 17. the snapshot prolog carries the XML declaration and the SVG DOCTYPE ----
c = _FakeClient()
c._add_resource("bob@example.com/pc", features=(wb_mod.NS_WHITEBOARD,))
m = WhiteboardManager(c)
sid = m.start_session("bob@example.com", is_muc=False)
m._send_state(m.session(sid), "bob@example.com")
_begin = _state_of(c).find(_q(NS_SXE, "document-begin"))
check("the document-begin prolog carries the XML prolog and DOCTYPE",
      _begin is not None and "%3C%21DOCTYPE" in (_begin.get("prolog") or ""))

# 18. the canvas viewBox comes from the document (the host's is authoritative)
m2 = WhiteboardManager(_FakeClient())
sid2 = m2.start_session("room@conference.example", is_muc=True)
check("the default viewBox is our canvas size", m2.view_box(sid2) == (1280, 720))
_doc2 = m2.document(sid2)
_vb_set = ET.Element(_q(NS_SXE, "state"))
_set = ET.SubElement(_vb_set, _q(NS_SXE, "set"))
_set.set("target", _doc2.find_attr(_doc2.root_rid, "viewBox"))
_set.set("chdata", "0 0 600 400")
_in = _FakeIncoming("room@conference.example/alice",
                    ET.Element("{jabber:client}message"))
_sxe = ET.SubElement(_in.xml, _q(NS_SXE, "sxe"))
_sxe.set("session", sid2)
_sxe.append(_vb_set)
asyncio.run(m2.handle_sxe(_in))
check("a peer's viewBox change updates the canvas size",
      m2.view_box(sid2) == (600, 400))

# 19. refusing an incoming session sends session-terminate (unsupported) -----
class _IqStub:
    def __init__(self, frm):
        self._d = {"from": frm, "type": "set"}

    def __getitem__(self, key):
        return self._d.get(key)


c = _FakeClient()
m = WhiteboardManager(c)
_j = ET.Element(_q(wb_mod.NS_JINGLE, "jingle"))
_j.set("action", "session-initiate")
_j.set("sid", "inv-1")
_content = ET.SubElement(_j, _q(wb_mod.NS_JINGLE, "content"))
ET.SubElement(_content, _q(wb_mod.NS_WHITEBOARD, "description"))
asyncio.run(m.dispatch("session-initiate", _j, _IqStub("bob@example.com/pc")))
check("an incoming session-initiate is tracked", "inv-1" in m.sessions)
m.refuse_session("inv-1")
check("refusing drops the session", "inv-1" not in m.sessions)
_term = c.xmpp.sent[-1]
_jingle_out = _term.xml.find(".//%s" % _q(wb_mod.NS_JINGLE, "jingle"))
_reason = _term.xml.find(".//%s" % _q(wb_mod.NS_JINGLE, "reason"))
check("the refusal is a session-terminate with unsupported-applications",
      _jingle_out is not None and _jingle_out.get("action") == "session-terminate"
      and _reason is not None
      and _reason.find(_q(wb_mod.NS_JINGLE, "unsupported-applications"))
      is not None)

# 20. an embedded (data:) image round-trips through the document -------------
c = _FakeClient()
c._add_resource("bob@example.com/pc", features=(wb_mod.NS_WHITEBOARD,))
m = WhiteboardManager(c)
sid = m.start_session("bob@example.com", is_muc=False)
_uri = "data:image/png;base64,iVBORw0KGgo="
_img_rid = m.add_shape(sid, {"tag": "image", "id": "img1", "x": "10",
                             "y": "20", "width": "64", "height": "64",
                             "href": _uri})
check("add_shape creates an <image> element",
      m.document(sid).records[_img_rid].name == "image")
_imgs = [s for s in m.shapes(sid) if s.get("tag") == "image"]
check("the image is listed with its source and size",
      len(_imgs) == 1 and _imgs[0]["href"] == _uri
      and _imgs[0]["width"] == "64" and _imgs[0]["height"] == "64")
_href_rid = m.document(sid).find_attr(_img_rid, "xlink:href")
check("the image source lives in an xlink:href attribute",
      _href_rid is not None
      and m.document(sid).records[_href_rid].ns == wb_mod.NS_XLINK)
check("the image source is broadcast in a <new> edit",
      _state_of(c).find(_q(NS_SXE, "new")) is not None)

# 21. stacking order (primary-weight) ----------------------------------------
c = _FakeClient()
c._add_resource("bob@example.com/pc", features=(wb_mod.NS_WHITEBOARD,))
m = WhiteboardManager(c)
sid = m.start_session("bob@example.com", is_muc=False)
r1 = m.add_shape(sid, {"id": "a", "d": "M 0 0 L 1 1"})
r2 = m.add_shape(sid, {"id": "b", "d": "M 0 0 L 2 2"})
check("shapes are ordered by insertion",
      [s["rid"] for s in m.shapes(sid)] == [r1, r2])
m.reorder(sid, r1, "front")
check("bring-to-front moves the shape last",
      [s["rid"] for s in m.shapes(sid)] == [r2, r1])
m.reorder(sid, r1, "back")
check("send-to-back moves the shape first",
      [s["rid"] for s in m.shapes(sid)] == [r1, r2])
m.reorder(sid, r1, "forward")
check("bring-forward swaps with the next sibling",
      [s["rid"] for s in m.shapes(sid)] == [r2, r1])
check("reorder broadcasts a <set>",
      _state_of(c).find(_q(NS_SXE, "set")) is not None)
check("reorder is undoable", m.can_undo(sid))
m.undo(sid)
check("undo restores the previous order",
      [s["rid"] for s in m.shapes(sid)] == [r1, r2])

# 22. canvas resize (viewBox) ------------------------------------------------
m.set_view_box(sid, 800, 600)
check("set_view_box updates the document viewBox", m.view_box(sid) == (800, 600))
check("set_view_box broadcasts a <set>",
      _state_of(c).find(_q(NS_SXE, "set")) is not None)
m.undo(sid)
check("undo restores the previous viewBox", m.view_box(sid) == (1280, 720))

# 23. undo restores an overwritten attribute value ---------------------------
r3 = m.add_shape(sid, {"id": "c", "d": "M 0 0 L 9 9"})
m.update_shape(sid, r3, {"d": "M 1 1 L 8 8"})
check("update_shape changes the path data",
      [s for s in m.shapes(sid) if s["rid"] == r3][0]["d"] == "M 1 1 L 8 8")
m.undo(sid)
check("undo restores the overwritten path data",
      [s for s in m.shapes(sid) if s["rid"] == r3][0]["d"] == "M 0 0 L 9 9")

# 24. grouping / ungrouping --------------------------------------------------
c = _FakeClient()
c._add_resource("bob@example.com/pc", features=(wb_mod.NS_WHITEBOARD,))
m = WhiteboardManager(c)
sid = m.start_session("bob@example.com", is_muc=False)
ra = m.add_shape(sid, {"id": "a", "d": "M 0 0 L 1 1"})
rb = m.add_shape(sid, {"id": "b", "d": "M 0 0 L 2 2"})
g = m.group_shapes(sid, [ra, rb])
check("group_shapes creates a <g>",
      bool(g) and m.document(sid).records[g].name == "g")
check("the grouped shapes carry the group rid",
      len([s for s in m.shapes(sid) if s.get("group") == g]) == 2)
check("the group is broadcast in a <new> edit",
      _state_of(c).find(_q(NS_SXE, "new")) is not None)
check("grouping is undoable", m.can_undo(sid))
m.undo(sid)
check("undo dissolves the group",
      all(not s.get("group") for s in m.shapes(sid)))

# ungroup composes a non-identity group transform into the children
g2 = m.group_shapes(sid, [ra, rb])
check("the group can be recreated", bool(g2) and g2 != g)
m.set_group_transform(sid, g2, "matrix(1 0 0 1 5 7)")
_g = [s for s in m.shapes(sid) if s.get("group") == g2]
check("the group transform is reported",
      _g and _g[0]["group-transform"] == "matrix(1 0 0 1 5 7)")
m.ungroup(sid, g2)
check("ungroup removes the <g>", g2 not in m.document(sid).records)
_children = {s["rid"]: s for s in m.shapes(sid)}
check("ungroup composes the group transform into a child",
      _children[ra]["transform"] == "matrix(1 0 0 1 5 7)"
      or _children[rb]["transform"] == "matrix(1 0 0 1 5 7)")
check("ungroup is undoable", m.can_undo(sid))
m.undo(sid)
check("undo restores the group", g2 in m.document(sid).records)

# 25. XEP-0353 JMI (whiteboard proposal) -------------------------------------
from stanza_im.xmpp import jmi  # noqa: E402


class _MsgStub:
    def __init__(self, frm):
        self.xml = ET.Element("{jabber:client}message")
        self._frm = frm

    def __getitem__(self, key):
        return self._frm if key == "from" else None


_prop = ET.Element(_q(jmi.NS_JINGLE_MSG, "propose"))
_prop.set("id", "p1")
ET.SubElement(_prop, _q(wb_mod.NS_WHITEBOARD, "description"))
_pmsg = _MsgStub("bob@example.com/pc")
_pmsg.xml.append(_prop)
check("jmi.action_of reads the action", jmi.action_of(_pmsg) == "propose")
check("jmi.description_ns reads the application type",
      jmi.description_ns(_pmsg) == wb_mod.NS_WHITEBOARD)

c = _FakeClient()
m = WhiteboardManager(c)
m.handle_jingle_message(_pmsg)
check("an incoming propose is recorded", "p1" in m._proposals)
check("an incoming propose emits whiteboard_proposed",
      ("whiteboard_proposed", "p1", "bob@example.com", "bob@example.com/pc")
      in c.events)
check("owns_jmi knows the proposal", m.owns_jmi("p1"))
m.answer_proposal("p1", True)
_ans = c.xmpp.sent[-1]
check("answering with proceed sends <proceed>",
      _ans.xml.find(_q(jmi.NS_JINGLE_MSG, "proceed")) is not None)
check("the proceed targets the proposer's full JID",
      _ans.fields.get("to") == "bob@example.com/pc")
check("the accepted proposal is remembered", "p1" in m._proceeded)


async def _reject_case():
    cc = _FakeClient()
    mm = WhiteboardManager(cc)
    future = asyncio.get_event_loop().create_future()
    mm._proceed_futures["s9"] = future
    reject = ET.Element(_q(jmi.NS_JINGLE_MSG, "reject"))
    reject.set("id", "s9")
    msg = _MsgStub("bob@example.com/pc")
    msg.xml.append(reject)
    mm.handle_jingle_message(msg)
    return future.done() and future.result() is False


check("a reject resolves the pending proceed future with False",
      asyncio.run(_reject_case()))


class _JmiClient(_FakeClient):
    def supports_feature(self, bare, feature):
        return feature == jmi.NS_JINGLE_MSG

    def _start_task(self, coro):
        self.started = getattr(self, "started", [])
        self.started.append(coro)
        coro.close()
        return None


jc = _JmiClient()
jc._add_resource("bob@example.com/pc", features=(wb_mod.NS_WHITEBOARD,))
jm = WhiteboardManager(jc)
jm.start_session("bob@example.com", is_muc=False)
check("a JMI-capable peer is proposed to",
      bool(getattr(jc, "started", None)))
check("no session-initiate is sent before a proceed",
      not any(s.xml.find(".//%s" % _q(wb_mod.NS_JINGLE, "jingle")) is not None
              for s in jc.xmpp.sent))


class _BuildClient:
    class _Xmpp:
        def Message(self):
            return _FakeStanza("message", [])

    def __init__(self):
        self.xmpp = _BuildClient._Xmpp()


_built = jmi.build(_BuildClient(), "propose", "bob@x", "s1",
                   [(wb_mod.NS_WHITEBOARD, {})])
check("jmi.build writes the action and the description",
      _built.xml.find(_q(jmi.NS_JINGLE_MSG, "propose")) is not None
      and _built.xml.find(".//%s" % _q(wb_mod.NS_WHITEBOARD, "description"))
      is not None)
check("jmi.build adds the XEP-0334 store hint",
      _built.xml.find("{urn:xmpp:hints}store") is not None)

# 26. a move announces the (newly created) transform attribute --------------
c = _FakeClient()
c._add_resource("bob@example.com/pc", features=(wb_mod.NS_WHITEBOARD,))
m = WhiteboardManager(c)
sid = m.start_session("bob@example.com", is_muc=False)
r = m.add_shape(sid, {"id": "s1", "d": "M 0 0 L 1 1"})
m._send_state(m.session(sid), "bob@example.com")
snapshot = _state_of(c)
peer = WhiteboardManager(_FakeClient())
psess = WhiteboardSession(sid="remote", peer="bob@example.com")
peer.sessions["remote"] = psess
peer._apply_state(psess, snapshot)
check("the peer has the shape", len(peer.shapes("remote")) == 1)
m.update_shape(sid, r, {"transform": "matrix(1 0 0 1 5 7)"})
state = _state_of(c)
check("a move announces the transform attribute with a <new>",
      any(el.get("name") == "transform"
          for el in state.findall(_q(NS_SXE, "new"))))
peer._apply_state(psess, state)
check("the peer applies the move",
      peer.shapes("remote")[0]["transform"] == "matrix(1 0 0 1 5 7)")

# 27. joining a peer-hosted session: accept echo, connect after the ack -------
class _ResultStub:
    def __init__(self, kind="result"):
        self._kind = kind

    def get(self, key, default=None):
        return self._kind if key == "type" else default


def _host_offer(sid, host="bob@example.com/pc"):
    jingle = ET.Element(_q(wb_mod.NS_JINGLE, "jingle"))
    jingle.set("sid", sid)
    jingle.set("initiator", host)
    content = ET.SubElement(jingle, _q(wb_mod.NS_JINGLE, "content"))
    ET.SubElement(content, _q(wb_mod.NS_WHITEBOARD, "description"))
    transport = ET.SubElement(content,
                              _q(wb_mod.NS_SXE_TRANSPORT, "transport"))
    host_el = ET.SubElement(transport, _q(wb_mod.NS_SXE_TRANSPORT, "host"))
    host_el.text = host
    return jingle


def _connects(client):
    out = []
    for stanza in client.xmpp.sent:
        el = stanza.xml.find(_q(NS_SXE, "sxe"))
        if el is not None and el.find(_q(NS_SXE, "connect")) is not None:
            out.append(el)
    return out


def _accept_stanza(client):
    for stanza in reversed(client.xmpp.sent):
        jingle = stanza.xml.find(_q(wb_mod.NS_JINGLE, "jingle"))
        if jingle is not None and jingle.get("action") == "session-accept":
            return stanza
    return None


async def _join(sid="host-1", host="bob@example.com/pc"):
    client = _FakeClient()
    manager = WhiteboardManager(client)
    manager._connect_retry_delays = ()
    await manager.dispatch("session-initiate", _host_offer(sid, host),
                           _IqStub(host))
    manager.join_session(host.split("/", 1)[0], sid)
    return client, manager


async def _accept_echo_case():
    client, manager = await _join()
    accept = _accept_stanza(client)
    jingle = accept.xml.find(_q(wb_mod.NS_JINGLE, "jingle"))
    host_el = jingle.find(".//%s" % _q(wb_mod.NS_SXE_TRANSPORT, "host"))
    no_connect = not _connects(client)
    accept.callback(_ResultStub("result"))
    sent_connect = bool(_connects(client))
    manager.end_session("host-1")
    return host_el.text, jingle.get("responder"), no_connect, sent_connect


_host_text, _responder, _no_connect, _sent_connect = asyncio.run(
    _accept_echo_case())
check("the accept echoes the offered host (not ourselves)",
      _host_text == "bob@example.com/pc")
check("the accept names the responder", _responder == "me@example.com/pc")
check("no connect is sent before the accept is acknowledged", _no_connect)
check("a connect follows the accept acknowledgement", _sent_connect)


async def _retry_case():
    client, manager = await _join("host-2")
    manager._connect_retry_delays = (0.01, 0.01)
    _accept_stanza(client).callback(_ResultStub("result"))
    first = len(_connects(client))
    await asyncio.sleep(0.05)
    retried = len(_connects(client))
    offer = ET.Element(_q(NS_SXE, "sxe"))
    offer.set("session", "host-2")
    ET.SubElement(offer, _q(NS_SXE, "state-offer"))
    msg = _MsgStub("bob@example.com/pc")
    msg.xml.append(offer)
    await manager.handle_sxe(msg)
    after_offer = len(_connects(client))
    await asyncio.sleep(0.05)
    still = len(_connects(client))
    manager.end_session("host-2")
    return first, retried, after_offer, still


_first, _retried, _after_offer, _still = asyncio.run(_retry_case())
check("the first connect is sent on the acknowledgement", _first == 1)
check("the connect is retried while no state arrives", _retried == 3)
check("a state offer stops the connect retries", _still == _after_offer)


async def _buffer_case():
    client, manager = await _join("host-3")
    _accept_stanza(client).callback(_ResultStub("result"))
    manager.add_shape("host-3", {"id": "mine", "d": "M 0 0 L 5 5"})
    before = [s for s in client.xmpp.sent
              if s.xml.find(".//%s" % _q(NS_SXE, "new")) is not None]
    state = ET.Element(_q(NS_SXE, "sxe"))
    state.set("session", "host-3")
    st = ET.SubElement(state, _q(NS_SXE, "state"))
    begin = ET.SubElement(st, _q(NS_SXE, "document-begin"))
    begin.set("prolog", wb_mod.DOC_PROLOG)
    new = ET.SubElement(st, _q(NS_SXE, "new"))
    for key, value in (("rid", "their-rid"), ("type", "element"),
                       ("parent", "0"), ("primary-weight", "3"),
                       ("name", "path")):
        new.set(key, value)
    end = ET.SubElement(st, _q(NS_SXE, "document-end"))
    end.set("last-sender", "")
    end.set("last-id", "")
    msg = _MsgStub("bob@example.com/pc")
    msg.xml.append(state)
    await manager.handle_sxe(msg)
    flushed = [s for s in client.xmpp.sent
               if s.xml.find(".//%s" % _q(NS_SXE, "new")) is not None]
    session = manager.session("host-3")
    shapes = {s.get("id") for s in manager.shapes("host-3")}
    manager.end_session("host-3")
    return len(before), len(flushed), session.synced, shapes


_before, _flushed, _synced, _shapes = asyncio.run(_buffer_case())
check("an edit made before the state is not sent yet", _before == 0)
check("the host snapshot marks the session synchronized", _synced)
check("the buffered edit is flushed after the snapshot", _flushed > 0)
check("both drawings are merged in the document", "mine" in _shapes)

# 28. Jingle senders: a board switched off is read-only for both -------------
async def _senders_case():
    client = _FakeClient()
    manager = WhiteboardManager(client)
    manager._connect_retry_delays = ()
    offer = _host_offer("host-4")
    content = offer.find(_q(wb_mod.NS_JINGLE, "content"))
    content.set("senders", "none")
    await manager.dispatch("session-initiate", offer,
                           _IqStub("bob@example.com/pc"))
    manager.join_session("bob@example.com", "host-4")
    accept = _accept_stanza(client)
    echoed = accept.xml.find(".//%s" % _q(wb_mod.NS_JINGLE, "content"))
    # The host sends its (empty) snapshot: become synchronized, then toggle.
    snap = ET.Element(_q(NS_SXE, "sxe"))
    snap.set("session", "host-4")
    st = ET.SubElement(snap, _q(NS_SXE, "state"))
    begin = ET.SubElement(st, _q(NS_SXE, "document-begin"))
    begin.set("prolog", wb_mod.DOC_PROLOG)
    end = ET.SubElement(st, _q(NS_SXE, "document-end"))
    end.set("last-sender", "")
    end.set("last-id", "")
    snap_msg = _MsgStub("bob@example.com/pc")
    snap_msg.xml.append(snap)
    await manager.handle_sxe(snap_msg)
    blocked = not manager.may_edit("host-4")
    rid_blocked = manager.add_shape("host-4", {"id": "nope", "d": "M 0 0 L 1 1"})
    sent_blocked = any(
        s.xml.find(".//%s" % _q(NS_SXE, "new")) is not None
        for s in client.xmpp.sent)

    modify = ET.Element(_q(wb_mod.NS_JINGLE, "jingle"))
    modify.set("sid", "host-4")
    mod_content = ET.SubElement(modify, _q(wb_mod.NS_JINGLE, "content"))
    mod_content.set("name", "whiteboard")
    mod_content.set("creator", "initiator")
    mod_content.set("senders", "both")
    await manager.dispatch("content-modify", modify,
                           _IqStub("bob@example.com/pc"))
    editable = manager.may_edit("host-4")
    events = [e for e in client.events if e[0] == "whiteboard_senders"]
    rid_after = manager.add_shape("host-4", {"id": "yes", "d": "M 0 0 L 2 2"})
    sent_after = any(
        s.xml.find(".//%s" % _q(NS_SXE, "new")) is not None
        for s in client.xmpp.sent)
    manager.end_session("host-4")
    return (echoed.get("senders"), blocked, rid_blocked, sent_blocked,
            editable, events, rid_after, sent_after)


(_echoed, _blocked, _rid_blocked, _sent_blocked, _editable, _events,
 _rid_after, _sent_after) = asyncio.run(_senders_case())
check("the accept echoes the offered senders", _echoed == "none")
check("senders=none makes the board read-only for us", _blocked)
check("edits are refused while we may not edit",
      _rid_blocked == "" and not _sent_blocked)
check("content-modify both restores editing", _editable)
check("the senders change is announced",
      bool(_events) and _events[-1][1:] == ("host-4", True))
check("editing works again after content-modify",
      bool(_rid_after) and _sent_after)

# 29. a local drawing becomes the shared document ---------------------------
async def _seed_host_case():
    client = _FakeClient()
    client._add_resource("bob@example.com/pc", features=(wb_mod.NS_WHITEBOARD,))
    manager = WhiteboardManager(client)
    attrs = [{"tag": "path", "id": "s1", "d": "M 0 0 L 10 10",
              "stroke": "#1a1a1a", "stroke-width": "2", "fill": "none",
              "stroke-linecap": "round", "stroke-linejoin": "round",
              "fill-rule": "evenodd", "transform": ""}]
    sid = manager.start_session("bob@example.com", is_muc=False,
                                shapes=attrs, view_box=(800, 600))
    shapes = manager.shapes(sid)
    box = manager.view_box(sid)
    broadcast = any(
        s.xml.find(".//%s" % _q(NS_SXE, "new")) is not None
        for s in client.xmpp.sent)
    manager._send_state(manager.session(sid), "bob@example.com/pc")
    snapshot = _state_of(client)
    in_snapshot = any(el.get("type") == "attr" and el.get("name") == "id"
                      and el.get("chdata") == "s1"
                      for el in snapshot.findall(_q(NS_SXE, "new")))
    return shapes, box, broadcast, in_snapshot


(_seed_shapes, _seed_box, _seed_broadcast, _in_snapshot) = asyncio.run(
    _seed_host_case())
check("a local drawing is put into the shared document",
      len(_seed_shapes) == 1 and _seed_shapes[0]["id"] == "s1")
check("the shared session adopts the board size", _seed_box == (800, 600))
check("nothing is broadcast before a peer joins", not _seed_broadcast)
check("the snapshot carries the local drawing", _in_snapshot)


# 30. a locally drawn board merges into a host's session --------------------
async def _seed_join_case():
    client = _FakeClient()
    manager = WhiteboardManager(client)
    manager._connect_retry_delays = ()
    await manager.dispatch("session-initiate", _host_offer("host-5"),
                           _IqStub("bob@example.com/pc"))
    manager.join_session("bob@example.com", "host-5")
    _accept_stanza(client).callback(_ResultStub("result"))
    manager.seed_local_shapes("host-5", [{
        "tag": "path", "id": "local1", "d": "M 0 0 L 20 20",
        "stroke": "#1a1a1a", "stroke-width": "2", "fill": "none"}])
    session = manager.session("host-5")
    buffered = len(session.pending)
    sent_before = any(
        s.xml.find(".//%s" % _q(NS_SXE, "new")) is not None
        for s in client.xmpp.sent)
    state = ET.Element(_q(NS_SXE, "sxe"))
    state.set("session", "host-5")
    st = ET.SubElement(state, _q(NS_SXE, "state"))
    begin = ET.SubElement(st, _q(NS_SXE, "document-begin"))
    begin.set("prolog", wb_mod.DOC_PROLOG)
    root = ET.SubElement(st, _q(NS_SXE, "new"))
    for key, value in (("rid", "host-root"), ("type", "element"),
                       ("name", "svg"), ("primary-weight", "0")):
        root.set(key, value)
    view = ET.SubElement(st, _q(NS_SXE, "new"))
    for key, value in (("rid", "host-view"), ("type", "attr"),
                       ("parent", "host-root"), ("name", "viewBox"),
                       ("chdata", "0 0 600 400"), ("primary-weight", "3")):
        view.set(key, value)
    end = ET.SubElement(st, _q(NS_SXE, "document-end"))
    end.set("last-sender", "")
    end.set("last-id", "")
    msg = _MsgStub("bob@example.com/pc")
    msg.xml.append(state)
    await manager.handle_sxe(msg)
    flushed = any(
        s.xml.find(".//%s" % _q(NS_SXE, "new")) is not None
        for s in client.xmpp.sent)
    box = manager.view_box("host-5")
    ids = {s.get("id") for s in manager.shapes("host-5")}
    manager.end_session("host-5")
    return buffered, sent_before, flushed, box, ids


(_buf, _sent_before, _flushed, _join_box, _join_ids) = asyncio.run(
    _seed_join_case())
check("a local drawing is buffered until the snapshot", _buf > 0)
check("the local drawing is not sent before the state", not _sent_before)
check("the buffered drawing reaches the host after the snapshot", _flushed)
check("the host's viewBox wins after the merge", _join_box == (600, 400))
check("the merged document keeps the local shape", "local1" in _join_ids)


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All whiteboard sync tests passed.")
