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

# 6b. clicks route to Python via navigation interception --------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_theme_src = open(os.path.join(
    _root, "stanza_im", "ui", "chat_themes.py"), encoding="utf-8").read()
check("no JS click bridge or console channel",
      "stanzaSend" not in _theme_src and "stanza-click|" not in _theme_src)
_view_src = open(os.path.join(
    _root, "stanza_im", "ui", "chat_view.py"), encoding="utf-8").read()
check("clicks routed via acceptNavigationRequest",
      "_StanzaPage" in _view_src and "acceptNavigationRequest" in _view_src
      and "_accept_navigation" in _view_src and "link_clicked.emit" in _view_src)
check("reply anchor placeholder in templates", any(
    'href="stanza:reply:%REPLY_TARGET%"' in open(
        os.path.join(_root, "resources", "chatskins", skin, direction,
                     "Content.html"), encoding="utf-8").read()
    for skin in ("candy", "minimal-mod")
    for direction in ("Incoming", "Outgoing")))
from stanza_im.ui.chat_view import _compose_reply_target
from urllib.parse import unquote as _unquote
_target = _compose_reply_target("oid-9", "alice@example.com/res", "Alice",
                                "hello bob/x")
check("reply target round trip",
      [_unquote(p) for p in _target.split("/")] ==
      ["oid-9", "alice@example.com/res", "Alice", "hello bob/x"])
check("ACTION_JS reply branch removed",
      "data-action" + "' === 'reply'" not in _view_src)
check("reply button relayed by scroll poll, never navigation",
      "a.action-reply" in _view_src
      and "window.__stanzaReplyRef" in _view_src
      and "preventDefault()" in _view_src
      and "__stanzaReplyRef || ''" in _view_src
      and "_last_reply_ref" in _view_src
      and "_clear_reply_request" in _view_src)
check("reply quote jump wired through the scroll poll",
      "a.stanza-reply-jump" in _view_src
      and "window.__stanzaJumpRef" in _view_src
      and "scrollIntoView" in _view_src
      and "_last_jump_ref" in _view_src
      and "def scroll_to_message" in _view_src)
check("jump skips the anchor restore and matches both ids",
      "keep_position" in _view_src
      and "nodes[i].getAttribute('data-reply-id') === id" in _view_src)
_hist_src = open(os.path.join(
    _root, "stanza_im", "core", "history.py"), encoding="utf-8").read()
check("jump resolution is local-only",
      "def message_exists" in _hist_src
      and "message_exists_async" in _hist_src)
check("MUC mention relayed by scroll poll, never navigation",
      "a.mention" in _view_src
      and "window.__stanzaMentionRef" in _view_src
      and "preventDefault()" in _view_src
      and "__stanzaMentionRef || ''" in _view_src
      and "_last_mention_ref" in _view_src
      and "_clear_mention_request" in _view_src)
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
      cw._reply_ref_body == "" and
      cw._input.toPlainText().startswith("> Alice wrote:"))
check("reply banner visible", not cw._reply_ctx.isHidden())

cur = cw._input.textCursor()
cur.movePosition(QtGui.QTextCursor.MoveOperation.End)
cw._input.setTextCursor(cur)
cw._input.insertPlainText("me too")
_expected_body = cw._format_quote("Alice", "are you in?") + "me too"
cw._send()
check("reply signal emitted", len(emitted) == 1 and
      emitted[0] == ("bob@example.com", _expected_body,
                     "alice@example.com/res", "abc", "", ""))
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

# 9b. clickable reply quote: DOM target resolution + jump -------------------
_entry = cw._find_message("oid-1")
check("reply target resolves to the stored message",
      cw._reply_target_id(_entry) == "oid-1")
check("reply_reference returns the target",
      cw._reply_reference({"reply_id": "oid-1"})
      == ("Alice", "are you in?", "oid-1"))

jumped = []
cw._view.scroll_to_message = lambda mid: jumped.append(mid)
cw._jump_to_message("oid-1")
check("jump scrolls when the target is loaded", jumped == ["oid-1"])

# 9b2. jump prepends must not preserve (and thus revert) the scroll anchor --
_forwarded = {}
cw._view.prepend_messages = lambda msgs, keep_position=True: _forwarded.update(
    kp=keep_position)
cw.prepend_history([{"sender": "Z", "body": "older", "timestamp": "09:00",
                     "direction": "incoming"}], False, keep_position=False)
check("jump prepend skips anchor preservation",
      _forwarded.get("kp") is False)
cw.prepend_history([{"sender": "Z", "body": "older2", "timestamp": "08:00",
                     "direction": "incoming"}], False)
check("normal prepend preserves the anchor", _forwarded.get("kp") is True)

# 9b3. local-only jump loop walks the DB and scrolls ------------------------
import asyncio as _asyncio
_target_entry = {"sender": "B", "body": "target", "timestamp": "10:00",
                 "direction": "incoming", "origin_id": "j1"}
cw3 = ChatWidget("jump2@example.com", "J", chat_themes.ChatThemeFactory())
cw3._history = [{"sender": "A", "body": "new", "timestamp": "11:00",
                 "direction": "incoming", "origin_id": "n1"}]
_scrolled = []
cw3._view.scroll_to_message = lambda mid: _scrolled.append(mid)
cw3._view.prepend_messages = lambda msgs, keep_position=True: None
cw3._view.scroll_fraction = lambda: 1.0
_saved = (history_mod.message_exists_async,
          history_mod.older_available_timestamp_async,
          history_mod.load_older_timestamp_async)


async def _exists(_jid, _sid):
    return True


async def _older(_jid, _before):
    return True


async def _page(_jid, _before, _limit):
    return [_target_entry]


history_mod.message_exists_async = _exists
history_mod.older_available_timestamp_async = _older
history_mod.load_older_timestamp_async = _page
try:
    cw3._jump_pending = "j1"
    cw3._jump_pages = 0
    _asyncio.new_event_loop().run_until_complete(cw3._load_jump_pages_async())
finally:
    (history_mod.message_exists_async,
     history_mod.older_available_timestamp_async,
     history_mod.load_older_timestamp_async) = _saved
check("local jump loads the page and scrolls to the target",
      _scrolled == ["j1"] and cw3._jump_pending == "")

# 9c. render_reply becomes a stanza:jump link when a target is known --------
_reply_html = theme.render_reply("Anna", "are you in?", "oid-1")
check("render_reply jump link",
      "stanza-reply-jump" in _reply_html
      and "stanza:jump:oid-1" in _reply_html)
check("render_reply without target stays plain",
      "stanza-reply-jump" not in theme.render_reply("Anna", "x"))

# 9d. local-only history lookup ---------------------------------------------
_tmpd2 = tempfile.mkdtemp(prefix="stanza_jump_")
_old_dir2 = history_mod.HISTORY_DIR
history_mod.HISTORY_DIR = _tmpd2
try:
    history_mod.store_message("jump@example.com", "incoming", "hi",
                              "10:00", "A", origin_id="o-1")
    check("message_exists finds a stored id",
          history_mod.message_exists("jump@example.com", "o-1"))
    check("message_exists misses an unknown id",
          not history_mod.message_exists("jump@example.com", "nope"))
finally:
    history_mod.close_all()
    history_mod.HISTORY_DIR = _old_dir2
    import shutil as _shutil
    _shutil.rmtree(_tmpd2, ignore_errors=True)

# 10. quote-only reply (message without a reference id) --------------------
plain.clear()
emitted.clear()
cw._on_reply_requested("", "alice@example.com/res", "Alice", "are you in?")
check("quote-only banner visible", not cw._reply_ctx.isHidden())
cur = cw._input.textCursor()
cur.movePosition(QtGui.QTextCursor.MoveOperation.End)
cw._input.setTextCursor(cur)
cw._input.insertPlainText("still yes")
cw._send()
check("quote-only sent as plain message",
      len(plain) == 1 and plain[0][0] == "bob@example.com"
      and plain[0][1].endswith("still yes") and len(emitted) == 0)
check("quote-only state cleared", cw._reply_id == "" and
      cw._reply_ctx.isHidden())
# cancel reply removes the inserted quote -------------------------------
cw._on_reply_requested("abc", "alice@example.com/res", "Alice", "are you in?")
_q_before = cw._input.toPlainText()
check("quote inserted on reply", bool(cw._reply_quote_text)
      and cw._input.toPlainText().startswith("> Alice wrote:"))
cw._cancel_reply()
check("cancel removes quote", cw._input.toPlainText() == ""
      and cw._reply_id == "" and cw._reply_quote_text == ""
      and cw._reply_ctx.isHidden())

# 11. reply target id fallback chain ---------------------------------------
check("reply_target_id origin", ChatWidget._reply_target_id(
    {"origin_id": "o", "archive_id": "a", "message_id": "m"}) == "o")
check("reply_target_id archive", ChatWidget._reply_target_id(
    {"origin_id": "", "archive_id": "a", "message_id": "m"}) == "a")
check("reply_target_id message", ChatWidget._reply_target_id(
    {"origin_id": "", "archive_id": "", "message_id": "m"}) == "m")
check("reply_target_id empty", ChatWidget._reply_target_id({}) == "")

# 12. stanza:reply URI drives the banner + input quote ---------------------
from urllib.parse import quote as _quote
cw2 = ChatWidget("room@conf/x", "Room", chat_themes.ChatThemeFactory(),
                 is_muc=True)
cw2._reply_ctx.setVisible(False)
cw2._open_link("stanza:reply:oid-9/" + _quote("alice@example.com/res", safe="")
               + "/Alice/" + _quote("hello bob"))
check("stanza:reply sets quote input",
      not cw2._reply_ctx.isHidden() and cw2._reply_id == "oid-9"
      and cw2._reply_ref_sender == ""
      and cw2._input.toPlainText().startswith("> Alice wrote:")
      and "hello bob" in cw2._input.toPlainText())

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
check("tab empty field adds address", cw3._input.toPlainText() == "albert: ")
cw3._tab_complete_nick()
check("tab address cycles", cw3._input.toPlainText() == "alice: ")
cw3._tab_complete_nick()
check("tab address cycles 3", cw3._input.toPlainText() == "Bob The Cat: ")
cw3._tab_complete_nick()
check("tab address cycles 4", cw3._input.toPlainText() == "zoe: ")
cw3._tab_complete_nick()
check("tab address wraps around", cw3._input.toPlainText() == "albert: ")
_type("bo")
cw3._tab_complete_nick()
check("tab prefix at line start addresses",
      cw3._input.toPlainText() == "Bob The Cat: ")
_type("echo bo")
cw3._tab_complete_nick()
check("tab prefix mid-line is bare",
      cw3._input.toPlainText() == "echo Bob The Cat")
_type("x")
check("tab no match returns False", cw3._tab_complete_nick() is False)
_type("")
cw3._tab_complete_nick(backward=True)
check("tab backward starts from end", cw3._input.toPlainText() == "zoe: ")
_type("echo hi al")
cw3._tab_complete_nick()
check("tab completes mid-line word",
      cw3._input.toPlainText() == "echo hi albert")
cw3._tab_complete_nick()
check("tab mid-line cycles bare", cw3._input.toPlainText() == "echo hi alice")

# 15. Esc collapses a MUC without leaving; Ctrl+W leaves --------------------
from stanza_im.ui.chat_window import ChatWindow
cw_win = ChatWindow(chat_themes.ChatThemeFactory(),
                    chat_themes.ChatThemeFactory())
cw_win.set_muc_leave_confirm(lambda room: True)
left_rooms = []
cw_win.muc_leave_requested.connect(lambda r: left_rooms.append(r))
cw_win.open_groupchat("room@conf/x", "Nick", "Room")
cw_win.open_chat("bob@example.com", "Bob", focus=False)
cw_win._on_escape()
check("esc collapses muc tab", not cw_win.has_chat("room@conf/x"))
check("esc does not leave muc", left_rooms == [])
check("esc keeps 1:1 tab", cw_win.has_chat("bob@example.com"))
check("esc keeps window visible", cw_win.isVisible())
cw_win.open_groupchat("room@conf/x", "Nick", "Room")
cw_win._close_current_tab()
check("ctrl-w leaves muc", left_rooms == ["room@conf/x"])
cw_win._on_escape()
check("esc closes last 1:1 tab", not cw_win.has_chat("bob@example.com"))

# 16. document_lost self-heal re-renders the conversation -------------------
check("scheme registration present",
      "_register_custom_url_schemes" in _view_src
      and "registerScheme" in _view_src and "schemeByName" not in _view_src)
check("document_lost signal exists",
      "document_lost = QtCore.pyqtSignal()" in _view_src)
restore_cw = ChatWidget("bob@example.com", "Bob",
                        chat_themes.ChatThemeFactory())
restore_cw.add_message(sender="Alice", body="hello doc",
                       timestamp="10:00", direction="incoming")
restore_cw.add_message(sender="Alice", body="second line",
                       timestamp="10:01", direction="incoming")
restore_cw._view.clear()
restore_cw._restore_after_document_lost()
check("document_lost restore keeps text",
      "hello doc" in restore_cw._view.toPlainText()
      and "second line" in restore_cw._view.toPlainText())

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)