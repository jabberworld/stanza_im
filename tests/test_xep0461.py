"""Offscreen smoke test for XEP-0461 Message Replies.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_xep0461.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xml.etree import ElementTree as ET

from PyQt6 import QtCore, QtGui, QtWidgets
import slixmpp

from stanza_im.core import client as client_mod
from stanza_im.core import history as history_mod
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes

i18n_load("en")


FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def make_message(body="hello", mid="abc", oid="", sid_by="", sid_id=""):
    m = slixmpp.Message()
    m["id"] = mid
    m["body"] = body
    if oid:
        el = ET.SubElement(m.xml, "{urn:xmpp:sid:0}origin-id")
        el.set("id", oid)
    if sid_by and sid_id:
        el = ET.SubElement(m.xml, "{urn:xmpp:sid:0}stanza-id")
        el.set("by", sid_by)
        el.set("id", sid_id)
    return m


# 1. XML helpers ----------------------------------------------------------
msg = make_message(oid="oid-1", sid_by="room@conf.example", sid_id="sid-9")
reply = ET.SubElement(msg.xml, "{urn:xmpp:reply:0}reply")
reply.set("to", "anna@example.com/tablet")
reply.set("id", "abc")

check("_reply_reference to", client_mod._reply_reference(msg) ==
      ("anna@example.com/tablet", "abc"))
check("_origin_id", client_mod._origin_id(msg) == "oid-1")
check("_stanza_id exact by", client_mod._stanza_id(msg, "room@conf.example") == "sid-9")
check("_stanza_id full by", client_mod._stanza_id(msg, "room@conf.example/bot") == "sid-9")

# 2. _attach_reply (reply first child + XEP-0421 fallback) ----------------
m2 = make_message(body="Me: the plan changed", mid="m2")
client_mod.JabberClient._attach_reply(
    m2, "bob@example.com/Swift", "abc", prefix_len=14)
children = list(m2.xml)
check("reply is first child",
      children[0].tag == "{urn:xmpp:reply:0}reply" and
      children[0].get("to") == "bob@example.com/Swift" and
      children[0].get("id") == "abc")
fb = [el for el in m2.xml if el.tag == "{urn:xmpp:fallback:0}fallback"]
check("fallback present", len(fb) == 1 and fb[0].get("for") == "urn:xmpp:reply:0")

# 3. compose_reply_body quote format --------------------------------------
quote = client_mod.compose_reply_body("Alice wrote:\nare you in?")
check("quote lines", quote.startswith("> Alice wrote:\n> are you in?\n") and
      quote.endswith("\n"))

# 4. send_message builds a reply body when ref is known --------------------
# (patch send to capture, without connecting)
sent = []
c = client_mod.JabberClient("me@example.com", "pw")
c.xmpp.send = lambda stanza: sent.append(stanza)
message_id = c.send_message(
    "bob@example.com", "me too", reply_to="bob@example.com/Swift",
    reply_id="abc", reply_ref_sender="Anna", reply_ref_body="are you in?")
check("send_message returns id", bool(message_id))
check("send_message reply first child",
      sent and sent[0].xml[0].tag == "{urn:xmpp:reply:0}reply")
check("send_message body quoted",
      sent and str(sent[0]["body"]).startswith("> Anna wrote:"))
plain_id = c.send_message("bob@example.com", "just hi")
check("plain message unquoted",
      sent[-1] and str(sent[-1]["body"]) == "just hi")

# 4b. quote-only send (no resolvable reference) -----------------------------
sent.clear()
qonly_id = c.send_message("bob@example.com", "me too",
                          reply_ref_sender="Anna", reply_ref_body="are you in?")
check("quote-only returns id", bool(qonly_id))
check("quote-only body quoted",
      sent and str(sent[-1]["body"]).startswith("> Anna wrote:"))
check("quote-only has no reply element",
      sent and not any(el.tag == "{urn:xmpp:reply:0}reply"
                       for el in sent[-1].xml))

# 5. history round-trip ----------------------------------------------------
tmpd = tempfile.mkdtemp(prefix="xep0461_hist_")
try:
    old_dir = history_mod.HISTORY_DIR
    history_mod.HISTORY_DIR = tmpd
    ok = history_mod.store_message(
        "bob@example.com", "outgoing", "> Anna wrote:\n> are you in?\nme too",
        timestamp="2026-01-01T10:00:00", sender="Me",
        origin_id="m2", reply_to="bob@example.com/Swift", reply_id="abc")
    check("store reply in history", ok)
    rows = history_mod.load_history("bob@example.com", limit=10)
    check("load reply fields", rows and rows[0]["origin_id"] == "m2" and
          rows[0]["reply_to"] == "bob@example.com/Swift" and
          rows[0]["reply_id"] == "abc")
    history_mod.HISTORY_DIR = old_dir
finally:
    import shutil
    shutil.rmtree(tmpd, ignore_errors=True)

# 6. theme render_reply ----------------------------------------------------
theme = chat_themes.ChatThemeFactory()
html = theme.render_reply("Anna", "are you in?")
check("render_reply markup", html and "stanza-reply" in html and
      "Anna" in html)
bare = theme.render_reply("Anna", "")
check("render_reply no-snippet", bare and "stanza-reply" in bare)

# 6b. reply button JS routes via the page-level link handler ---------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_theme_src = open(os.path.join(
    _root, "stanza_im", "ui", "chat_themes.py"), encoding="utf-8").read()
check("reply JS routes via on_link_clicked",
      "stanza:reply:" in _theme_src and "on_link_clicked" in _theme_src)
check("reply JS stanza-id fallback",
      "data-stanza-id" in _theme_src)
_view_src = open(os.path.join(
    _root, "stanza_im", "ui", "chat_view.py"), encoding="utf-8").read()
check("ACTION_JS reply branch removed",
      "data-action" + "' === 'reply'" not in _view_src)
check("qwebchannel bundled",
      os.path.isfile(os.path.join(_root, "resources", "qwebchannel.js")))
from stanza_im.ui import chat_themes as _ct
check("webchannel script non-empty", bool(_ct._webchannel_script()))

# 7. ChatWidget reply flow (offscreen, QTextBrowser fallback) --------------
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
from stanza_im.ui.chat_widget import ChatWidget

cw = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
emitted = []
cw.message_reply_sent.connect(lambda *a: emitted.append(a))

cw._on_reply_requested("abc", "alice@example.com/res", "Alice",
                       "are you in?")
check("reply state set", cw._reply_id == "abc" and
      cw._reply_to == "alice@example.com/res" and
      cw._reply_ref_body == "are you in?")
check("reply banner visible", not cw._reply_ctx.isHidden())

cw._input.setPlainText("me too")
cw._send()
check("reply signal emitted", len(emitted) == 1 and
      emitted[0] == ("bob@example.com", "me too", "alice@example.com/res",
                     "abc", "Alice", "are you in?"))
check("reply state cleared", cw._reply_id == "" and
      cw._reply_ctx.isHidden())

# 8. plain send still goes through message_sent ---------------------------
plain = []
cw.message_sent.connect(lambda *a: plain.append(a))
cw._input.setPlainText("hi")
cw._send()
check("plain message_sent", len(plain) == 1 and plain[0] ==
      ("bob@example.com", "hi"))

# 9. reply quote resolution from stored message ---------------------------
cw.add_message(sender="Alice", body="are you in?",
               timestamp="10:00", direction="incoming",
               reply_able_id="oid-1", reply_author="alice@example.com/res")
resolved = cw._reply_quote_for({"reply_id": "oid-1"})
check("reply_quote_for", resolved == ("Alice", "are you in?"))

# 10. quote-only reply (message without a reference id) --------------------
emitted.clear()
cw._on_reply_requested("", "alice@example.com/res", "Alice", "are you in?")
check("quote-only banner visible", not cw._reply_ctx.isHidden())
cw._input.setPlainText("still yes")
cw._send()
check("quote-only reply emitted with empty id",
      len(emitted) == 1 and emitted[0] ==
      ("bob@example.com", "still yes", "alice@example.com/res",
       "", "Alice", "are you in?"))
check("quote-only state cleared", cw._reply_id == "" and
      cw._reply_ctx.isHidden())

# 11. reply target id fallback chain ---------------------------------------
check("reply_target_id origin", ChatWidget._reply_target_id(
    {"origin_id": "o", "archive_id": "a", "message_id": "m"}) == "o")
check("reply_target_id archive", ChatWidget._reply_target_id(
    {"origin_id": "", "archive_id": "a", "message_id": "m"}) == "a")
check("reply_target_id message", ChatWidget._reply_target_id(
    {"origin_id": "", "archive_id": "", "message_id": "m"}) == "m")
check("reply_target_id empty", ChatWidget._reply_target_id({}) == "")

# 12. stanza:reply URI drives the banner via _open_link --------------------
from urllib.parse import quote as _quote
cw2 = ChatWidget("room@conf/x", "Room", chat_themes.ChatThemeFactory(),
                 is_muc=True)
cw2._reply_ctx.setVisible(False)
cw2._open_link("stanza:reply:oid-9/" + _quote("alice@example.com/res", safe="")
               + "/Alice/" + _quote("hello bob"))
check("stanza:reply sets banner",
      not cw2._reply_ctx.isHidden() and cw2._reply_id == "oid-9"
      and cw2._reply_ref_sender == "Alice"
      and cw2._reply_ref_body == "hello bob")

# 13. stanza:mention inserts "nick: " with focus (MUC only) -----------------
cw2.show()
cw2.activateWindow()
QtWidgets.QApplication.processEvents()
cw2._input.setPlainText("")
cw2._open_link("stanza:mention:" + _quote("Bob The Cat"))
check("stanza:mention inserts",
      cw2._input.toPlainText() == "Bob The Cat: ")
check("stanza:mention focuses input", cw2._input.hasFocus())
plain_chat = ChatWidget("x@example.com", "X", chat_themes.ChatThemeFactory())
plain_chat._open_link("stanza:mention:" + _quote("Bob"))
check("stanza:mention ignored in 1:1",
      plain_chat._input.toPlainText() == "")

# 14. Tab completion of MUC nicks ------------------------------------------
cw3 = ChatWidget("room@conf/y", "Room", chat_themes.ChatThemeFactory(),
                 is_muc=True)
cw3.update_muc_users([
    {"nick": "alice"}, {"nick": "albert"}, {"nick": "zoe"},
    {"nick": "Bob The Cat"},
])


def _type(text):
    cw3._input.setPlainText(text)
    cur = cw3._input.textCursor()
    cur.movePosition(QtGui.QTextCursor.MoveOperation.End)
    cw3._input.setTextCursor(cur)


cw3._input.setFocus()
_type("")
cw3._tab_complete_nick()
check("tab all nicks first", cw3._input.toPlainText() == "albert")
cw3._tab_complete_nick()
check("tab all nicks cycle", cw3._input.toPlainText() == "alice")
_type("bo")
cw3._tab_complete_nick()
check("tab prefix match", cw3._input.toPlainText() == "Bob The Cat")
_type("x")
check("tab no match returns False", cw3._tab_complete_nick() is False)
_type("")
cw3._tab_complete_nick(backward=True)
check("tab backward starts from end", cw3._input.toPlainText() == "zoe")
_type("echo hi al")
cw3._tab_complete_nick()
check("tab completes mid-line word",
      cw3._input.toPlainText() == "echo hi albert")

# 15. Esc collapses current tab, others remain -----------------------------
from stanza_im.ui.chat_window import ChatWindow
cw_win = ChatWindow(chat_themes.ChatThemeFactory(),
                    chat_themes.ChatThemeFactory())
cw_win.set_muc_leave_confirm(lambda room: True)
cw_win.open_groupchat("room@conf/x", "Nick", "Room")
cw_win.open_chat("bob@example.com", "Bob", focus=False)
cw_win._on_escape()
check("esc closes muc tab", not cw_win.has_chat("room@conf/x"))
check("esc keeps 1:1 tab", cw_win.has_chat("bob@example.com"))
check("esc keeps window visible", cw_win.isVisible())
cw_win._on_escape()
check("esc closes last tab", not cw_win.has_chat("bob@example.com"))

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)