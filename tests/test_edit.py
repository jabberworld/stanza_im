"""Offscreen smoke tests for XEP-0308 Last Message Correction (custom).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_edit.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_edit_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

import slixmpp

from stanza_im.core.client import (
    JabberClient, _replace_reference, NS_CORRECT,
)
from stanza_im.core import history
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. replace attachment + reference extraction -------------------------------
C = JabberClient("me@example.com/r", "pw")
msg = C.xmpp.Message()
msg["id"] = "new-1"
msg["body"] = "new text"
C._attach_replace(msg, "orig-1")
repl = next(el for el in msg.xml
            if el.tag == "{%s}replace" % NS_CORRECT)
check("replace first child", list(msg.xml).index(repl) == 0)
check("replace id", repl.get("id") == "orig-1")
check("new id differs", msg.xml.attrib.get("id") != "orig-1")
check("replace reference parsed", _replace_reference(msg) == "orig-1")

# 2. incoming corrections (1:1) replace vs new message ------------------------
def make_corrected(body="edited", ref="orig-9", mtype="chat"):
    m = slixmpp.Message()
    m["from"] = "alice@example.com/res"
    m["to"] = "me@example.com/r"
    m["type"] = mtype
    m["body"] = body
    m["id"] = "cor-1"
    ET.SubElement(m.xml, "{%s}replace" % NS_CORRECT).set("id", ref)
    return m

c_on = JabberClient("me@example.com/r", "pw", allow_incoming_edits=True)
corr = []
newmsg = []
c_on.on("message_corrected", lambda *a, **k: corr.append(a))
c_on.on("message_received", lambda *a, **k: newmsg.append(a))
c_on._on_message(make_corrected())
check("1:1 correction replaces",
      len(corr) == 1 and corr[0][0] == "alice@example.com/res"
      and corr[0][1] == "orig-9" and corr[0][2] == "edited"
      and len(newmsg) == 0)

c_off = JabberClient("me@example.com/r", "pw", allow_incoming_edits=False)
corr2 = []
newmsg2 = []
c_off.on("message_corrected", lambda *a, **k: corr2.append(a))
c_off.on("message_received", lambda *a, **k: newmsg2.append(a))
c_off._on_message(make_corrected())
check("1:1 correction becomes new message when disabled",
      len(corr2) == 0 and len(newmsg2) == 1
      and newmsg2[0][1] == "edited")

# 3. incoming MUC corrections ------------------------------------------------
def make_muc_corrected(body="edited-muc", ref="muc-1"):
    m = slixmpp.Message()
    m["from"] = "room@conf/nick"
    m["to"] = "me@example.com/r"
    m["type"] = "groupchat"
    m["body"] = body
    m["id"] = "cor-muc"
    ET.SubElement(m.xml, "{%s}replace" % NS_CORRECT).set("id", ref)
    return m

muc_corr = []
muc_new = []
cm = JabberClient("me@example.com/r", "pw", allow_incoming_edits=True)
cm.on("groupchat_message_corrected", lambda *a, **k: muc_corr.append(a))
cm.on("groupchat_message", lambda *a, **k: muc_new.append(a))
cm._on_groupchat_message(make_muc_corrected())
check("muc correction replaces",
      len(muc_corr) == 1 and muc_corr[0][0] == "room@conf"
      and muc_corr[0][1] == "muc-1" and not muc_new)

# 4. chat widget edit flow (fallback view) ------------------------------------
cw = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
emitted = []
cw.message_edit_sent.connect(lambda *a: emitted.append(a))
cw.add_message(sender="Me", body="first draft", timestamp="10:00",
               direction="outgoing", message_id="mid-1",
               reply_able_id="origin-1")
check("edit_last_sent starts", cw._edit_last_sent() is True)
check("input prefilled", cw._input.toPlainText() == "first draft")
check("edit banner visible", not cw._edit_ctx.isHidden())
cw._input.setPlainText("second draft")
cw._send()
check("edit sent signal", emitted and emitted[0] ==
      ("bob@example.com", "second draft", "mid-1"))
check("edit state cleared",
      cw._editing_id == "" and cw._edit_ctx.isHidden())

# cancel restores previous text
cw._input.setPlainText("abc")
cw._begin_edit(cw._messages[-1])
cw._input.setPlainText("typo")
cw._cancel_edit()
check("edit cancel restores", cw._input.toPlainText() == "abc"
      and cw._editing_id == "")

# Ctrl+Up picks the newest live message even when older history exists
cw4 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw4._history.append({"sender": "Me", "body": "old-history",
                     "timestamp": "09:00", "direction": "outgoing",
                     "message_id": "hist-old", "edited": False})
cw4.add_message(sender="Me", body="newer1", timestamp="10:00",
                direction="outgoing", message_id="new-1")
cw4.add_message(sender="Me", body="newer2", timestamp="10:01",
                direction="outgoing", message_id="new-2")
cw4._edit_last_sent()
check("ctrl-up picks newest live", cw4._input.toPlainText() == "newer2")

# non-last message editable via reference ------------------------------------
cw2 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw2.add_message(sender="Me", body="older", timestamp="10:00",
                direction="outgoing", message_id="older-1")
cw2.add_message(sender="Me", body="newer", timestamp="10:01",
                direction="outgoing", message_id="newer-1")
ok = cw2.edit_message_by_ref("older-1", "older-edited")
check("replace older message", ok is True
      and cw2._messages[0]["body"] == "older-edited"
      and cw2._messages[0]["edited"] is True)

# 5. history store/replace with message_id + edited --------------------------
jid = "history-edit@example.com"
history.store_message(jid, "outgoing", "original",
                      timestamp="2026-01-01T10:00:00", sender="Me",
                      message_id="hist-1")
history.replace_message(jid, "hist-1", "corrected")
rows = history.load_history(jid)
check("history replaced",
      rows and rows[-1]["body"] == "corrected"
      and rows[-1]["edited"] is True
      and rows[-1]["message_id"] == "hist-1")

# 5b. outgoing origin-id (XEP-0359) ------------------------------------------
_out, _mid = C._compose_message("bob@example.com", "hello")
_oid = _out.xml.find("{urn:xmpp:sid:0}origin-id")
check("outgoing messages carry an origin-id",
      _oid is not None and _oid.get("id") == _mid)

# 5c. corrections delivered as carbons ---------------------------------------
def make_carbon(which="sent", body="edited-carbon", ref="orig-c",
                frm="me@example.com/other", to="bob@example.com"):
    outer = slixmpp.Message()
    outer["to"] = "me@example.com/r"
    outer["type"] = "chat"
    carb = ET.SubElement(outer.xml, "{urn:xmpp:carbons:2}%s" % which)
    fwd = ET.SubElement(carb, "{urn:xmpp:forward:0}forwarded")
    inner = ET.SubElement(fwd, "{jabber:client}message")
    inner.set("from", frm)
    inner.set("to", to)
    inner.set("type", "chat")
    inner.set("id", "cor-carbon")
    ET.SubElement(inner, "{%s}replace" % NS_CORRECT).set("id", ref)
    ET.SubElement(inner, "{jabber:client}body").text = body
    return outer


c_carb = JabberClient("me@example.com/r", "pw", allow_incoming_edits=True)
carb_corr = []
carb_sent = []
c_carb.on("message_corrected", lambda *a, **k: carb_corr.append((a, k)))
c_carb.on("message_carbon_sent", lambda *a, **k: carb_sent.append((a, k)))
c_carb._on_carbon_sent(make_carbon("sent", "edited-own", "orig-own"))
check("a sent carbon correction is applied locally",
      len(carb_corr) == 1
      and carb_corr[0][0][0] == "bob@example.com"
      and carb_corr[0][0][1] == "orig-own"
      and carb_corr[0][0][2] == "edited-own"
      and not carb_sent)
carb_corr.clear()
c_carb._on_carbon_received(make_carbon(
    "received", "edited-foreign", "orig-f", "alice@example.com/res"))
check("a received carbon correction is applied",
      len(carb_corr) == 1
      and carb_corr[0][0][0] == "alice@example.com/res"
      and carb_corr[0][0][1] == "orig-f"
      and carb_corr[0][0][2] == "edited-foreign")

# 5d. MAM corrections are edits, not new messages ----------------------------
def make_mam_replace(ref="orig-mam", body="edited-mam"):
    result = ET.Element("{urn:xmpp:mam:2}result")
    result.set("id", "arc-mam")
    fwd = ET.SubElement(result, "{urn:xmpp:forward:0}forwarded")
    inner = ET.SubElement(fwd, "{jabber:client}message")
    inner.set("from", "bob@example.com/r")
    inner.set("to", "me@example.com/r")
    inner.set("type", "chat")
    inner.set("id", "cor-mam")
    ET.SubElement(inner, "{%s}replace" % NS_CORRECT).set("id", ref)
    ET.SubElement(inner, "{jabber:client}body").text = body
    delay = ET.SubElement(fwd, "{urn:xmpp:delay}delay")
    delay.set("stamp", "2026-10-31T20:18:40Z")
    return result


mam_rows, _parsed, _skipped, _reasons = C._mam_rows(
    "bob@example.com", [make_mam_replace()])
check("a MAM correction row carries replace_id",
      mam_rows and mam_rows[0]["replace_id"] == "orig-mam")

import asyncio  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


mam_jid = "mam-edit@example.com"
history.store_message(mam_jid, "incoming", "original",
                      timestamp="2026-10-31T20:00:00Z", sender="bob",
                      message_id="orig-mam", origin_id="orig-mam")
_run(C._apply_mam_edits(mam_jid, [{
    "direction": "incoming", "body": "edited", "sender": "bob",
    "timestamp": "2026-10-31T20:18:40Z", "replace_id": "orig-mam",
}]))
_mam_rows = history.load_history(mam_jid)
check("a MAM correction replaces the original",
      len(_mam_rows) == 1 and _mam_rows[0]["body"] == "edited"
      and _mam_rows[0]["edited"] is True)

orphan_jid = "mam-edit-orphan@example.com"
_run(C._apply_mam_edits(orphan_jid, [{
    "direction": "incoming", "body": "orphan edit", "sender": "bob",
    "timestamp": "2026-10-31T20:19:00Z", "replace_id": "missing",
    "message_id": "cor-orphan", "origin_id": "cor-orphan",
}]))
_orphan_rows = history.load_history(orphan_jid)
check("an orphan MAM correction is kept as a message",
      _orphan_rows and _orphan_rows[-1]["body"] == "orphan edit"
      and _orphan_rows[-1]["edited"] is True)

# 5e. replace_message matches the other stable ids ---------------------------
sid_jid = "stanza-edit@example.com"
history.store_message(sid_jid, "incoming", "original",
                      timestamp="2026-10-31T20:00:00Z", sender="bob",
                      message_id="m-sid", origin_id="o-sid",
                      stanza_id="sid-9", archive_id="arc-9")
check("replace_message matches a stanza-id",
      history.replace_message(sid_jid, "sid-9", "edited")
      and history.load_history(sid_jid)[-1]["body"] == "edited")
check("replace_message matches an archive-id",
      history.replace_message(sid_jid, "arc-9", "edited-2")
      and history.load_history(sid_jid)[-1]["body"] == "edited-2")

cw_sid = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw_sid.add_message(sender="Me", body="original", timestamp="10:00",
                   direction="outgoing", message_id="m-sid",
                   stanza_id="sid-widget")
check("the widget edits by stanza-id",
      cw_sid.edit_message_by_ref("sid-widget", "edited")
      and cw_sid._messages[-1]["body"] == "edited")

# 6. Edit menu JS routing present --------------------------------------------
_view_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "ui", "chat_view.py"), encoding="utf-8").read()
_rootdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
check("edit menu sets poll request",
      "window.__stanzaEditRef =" in _view_src
      and "setTimeout(closeMenu, 0)" in _view_src
      and "data-stanza-outgoing" in _view_src)
check("no navigation for edit",
      "href=\"stanza:edit:" not in _view_src
      and "edit.href = 'stanza:edit:'" not in _view_src
      and "window.location.href = 'stanza:edit:'" not in _view_src
      and "relay.click()" not in _view_src
      and "querySelector('.action-edit')" not in _view_src)
check("poll delivers edit ref",
      "window.__stanzaEditRef || ''" in _view_src
      and "link_clicked.emit(\"stanza:edit:\" + requested)" in _view_src)
check("no inline edit anchor or css", all(
    ".action-edit" not in _view_src
    and ".action-edit" not in open(
        os.path.join(_rootdir, "resources", "chatskins", skin, "main.css"),
        encoding="utf-8").read()
    for skin in ("minimal-mod", "candy")))
check("post-click content probe present",
      "_schedule_content_probe" in _view_src
      and "_verify_after_click" in _view_src
      and "document_lost.emit" in _view_src)

# 7. edited marker rendered at the end of the phrase by the theme -------------
from stanza_im.ui.chat_themes import ChatThemeFactory
theme = ChatThemeFactory()
html_plain = theme.render_message("Bob", "hello world", "10:00", "incoming")
html_edited = theme.render_message("Bob", "hello world", "10:00",
                                   "incoming", edited=True)
check("edited marker in theme",
      "class=\"stanza-edited\"" in html_edited and "font-size:16px" in html_edited)
pos_plain = html_plain.index("hello world")
pos_edit = html_edited.index("class=\"stanza-edited\"")
check("marker after phrase", pos_edit > pos_plain)
check("marker absent when not edited", "stanza-edited" not in html_plain)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)