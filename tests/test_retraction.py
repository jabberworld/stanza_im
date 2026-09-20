"""Offscreen tests for XEP-0424 Message Retraction.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_retraction.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_retract_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

import slixmpp

from stanza_im.core.client import (
    JabberClient, NS_RETRACT, NS_RETRACT_LEGACY, NS_FALLBACK, NS_HINTS,
    _retract_reference,
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


# 1. retraction reference parsing ---------------------------------------------
def _make_retract(ns=NS_RETRACT, retract_id="orig-1", body=""):
    m = slixmpp.Message()
    m["from"] = "bob@example.com/res"
    m["to"] = "me@example.com/r"
    m["type"] = "chat"
    if body:
        m["body"] = body
    ET.SubElement(m.xml, f"{{{ns}}}retract").set("id", retract_id)
    return m


check("retract reference parsed", _retract_reference(_make_retract()) == "orig-1")
check("legacy retract namespace parsed",
      _retract_reference(_make_retract(ns=NS_RETRACT_LEGACY)) == "orig-1")
check("no retract reference on a plain message",
      _retract_reference(slixmpp.Message()) == "")

# 2. _on_message routes a retraction without rendering the fallback body ------
c = JabberClient("me@example.com/r", "pw")
retracted, received = [], []
c.on("message_retracted", lambda *a: retracted.append(a))
c.on("message_received", lambda *a: received.append(a))
c._on_message(_make_retract(body="/me retracted a previous message"))
check("1:1 retraction emitted",
      retracted == [("bob@example.com/res", "orig-1")])
check("retraction fallback body not rendered", received == [])

# 3. _on_groupchat_message routes a retraction --------------------------------
cm = JabberClient("me@example.com/r", "pw")
muc = []
cm.on("groupchat_message_retracted", lambda *a: muc.append(a))
g = slixmpp.Message()
g["from"] = "room@conf.example/nick"
g["to"] = "me@example.com/r"
g["type"] = "groupchat"
g["body"] = "/me retracted a previous message"
ET.SubElement(g.xml, f"{{{NS_RETRACT}}}retract").set("id", "muc-1")
cm._on_groupchat_message(g)
check("muc retraction emitted",
      len(muc) == 1 and muc[0][0] == "room@conf.example"
      and muc[0][1] == "nick" and muc[0][3] == "muc-1")

# 4. outgoing retraction stanza -----------------------------------------------
r = c._build_retraction("bob@example.com", "orig-9", "chat",
                        msg_id="retract-1")
retract = next(e for e in r.xml if e.tag == f"{{{NS_RETRACT}}}retract")
check("retraction carries the target id", retract.get("id") == "orig-9")
fallback = next(e for e in r.xml if e.tag == f"{{{NS_FALLBACK}}}fallback")
check("retraction fallback points at retraction", fallback.get("for") == NS_RETRACT)
check("retraction store hint present",
      any(e.tag == f"{{{NS_HINTS}}}store" for e in r.xml))
check("retraction fallback body present",
      str(r["body"]).startswith("/me retracted"))
check("retraction keeps the given id", str(r["id"]) == "retract-1")

# 5. history persistence ------------------------------------------------------
jid = "retract@example.com"
history.store_message(jid, "incoming", "secret",
                      timestamp="2026-01-01T10:00:00", sender="bob@x",
                      message_id="h-1", origin_id="h-1")
check("retraction applied to history",
      history.retract_message(jid, "h-1") is True)
row = history.load_history(jid)[-1]
check("history tombstone stored",
      row["retracted"] is True and row["body"] == "")

jid2 = "retract2@example.com"
history.store_message(jid2, "incoming", "kept",
                      timestamp="2026-01-01T10:00:00", sender="bob@x",
                      message_id="h-2", origin_id="h-2")
history.retract_message(jid2, "h-2", marker=True, sender="bob@x")
row2 = history.load_history(jid2)[-1]
check("history marker keeps the body",
      row2["retract_marker"] is True and row2["body"] == "kept")
check("history sender guard rejects a stranger",
      history.retract_message(jid2, "h-2", marker=True, sender="eve@x")
      is False)

# 6. chat widget marker vs tombstone ------------------------------------------
cw = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw.add_message(sender="Bob", body="hello", timestamp="10:00",
               direction="incoming", reply_able_id="w-1",
               reply_author="bob@example.com/r")
check("widget marker applied",
      cw.retract_message_by_ref("w-1", marker=True,
                                from_sender="bob@example.com/r") is True)
check("widget marker keeps the body",
      cw._messages[-1]["retract_marker"] and cw._messages[-1]["body"] == "hello")
check("widget retraction ignores a stranger",
      cw.retract_message_by_ref("w-1", from_sender="eve@example.com") is False)

cw3 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw3.add_message(sender="Me", body="mine", timestamp="10:00",
                direction="outgoing", message_id="w-3", reply_able_id="w-3",
                reply_author="bob@example.com")
check("a peer cannot retract our own message",
      cw3.retract_message_by_ref("w-3", from_sender="bob@example.com") is False)

cw2 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw2.add_message(sender="Bob", body="bye", timestamp="10:00",
                direction="incoming", reply_able_id="w-2",
                reply_author="bob@example.com/r")
cw2.retract_message_by_ref("w-2")
check("widget tombstone clears the body",
      cw2._messages[-1]["retracted"] and cw2._messages[-1]["body"] == "")

# 7. rendering ----------------------------------------------------------------
theme = chat_themes.ChatThemeFactory()
tomb = theme.render_message("Bob", "secret", "10:00", "incoming",
                            retracted=True)
check("tombstone renders the retraction notice",
      "stanza-retracted-text" in tomb and "secret" not in tomb)
marker = theme.render_message("Bob", "keep", "10:00", "incoming",
                              retract_marker=True)
check("marker keeps the body and adds the cross",
      "stanza-retracted" in marker and "keep" in marker
      and "\u2715" in marker)

# 8. settings defaults + preferences control ----------------------------------
from stanza_im.core.storage import Config
cfg = Config()
check("incoming deletions default on",
      cfg.chat.allow_incoming_deletions is True)
check("confirm retraction default off", cfg.chat.confirm_retraction is False)
from stanza_im.ui.preferences import PreferencesDialog
dlg = PreferencesDialog(cfg, chat_themes.ChatThemeFactory())
check("prefs expose both retraction options",
      "allow_incoming_deletions" in dlg._controls
      and "confirm_retraction" in dlg._controls)
dlg.close()

# 9. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    return open(os.path.join(_root, *parts), encoding="utf-8").read()


_client_src = _src("stanza_im", "core", "client.py")
check("client sends/advertises retraction",
      'add_feature(NS_RETRACT)' in _client_src
      and "def send_retraction" in _client_src
      and "def _build_retraction" in _client_src)
_view_src = _src("stanza_im", "ui", "chat_view.py")
check("view wires the delete control",
      "a.action-delete" in _view_src and "__stanzaDeleteRef" in _view_src
      and "%DELETE_LABEL%" in _view_src)
_widget_src = _src("stanza_im", "ui", "chat_widget.py")
check("widget exposes the retract signal and handler",
      "message_retract_sent" in _widget_src
      and "def retract_message_by_ref" in _widget_src
      and "def _handle_delete_uri" in _widget_src)
_tmpl = _src("resources", "chatskins", "minimal-mod", "Outgoing",
             "Content.html")
check("outgoing skin carries the delete button",
      'class="action-delete"' in _tmpl
      and "stanza:delete:%DELETE_TARGET%" in _tmpl)
_inc = _src("resources", "chatskins", "minimal-mod", "Incoming",
            "Content.html")
check("incoming skin carries the (gated) delete button",
      'class="action-delete"' in _inc
      and "stanza:delete:%DELETE_TARGET%" in _inc)
check("both skins gate the delete button on data-stanza-outgoing",
      all(
          "data-stanza-outgoing" in _src("stanza_im", "ui", "chat_themes.py")
          and 'class="action-delete"' in _src(
              "resources", "chatskins", skin, direction, "Content.html")
          for skin in ("minimal-mod", "candy")
          for direction in ("Incoming", "Outgoing")))
check("page CSS hides the delete button for foreign messages",
      "data-stanza-outgoing" in _src("stanza_im", "ui", "chat_themes.py")
      and "action-delete" in _src("stanza_im", "ui", "chat_themes.py"))
check("retracted messages are marked on the wrapper",
      'data-retracted="1"' in _view_src
      and "retracted=retracted" in _view_src)
check("menu hides edit/delete on a retracted message",
      "getAttribute('data-retracted')" in _view_src)
check("page CSS hides the delete button for retracted messages",
      '[data-retracted="1"]' in _src("stanza_im", "ui", "chat_themes.py"))
_xeps = _src("XEPs.md")
check("XEPs.md lists XEP-0424", "XEP-0424" in _xeps)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All retraction tests passed.")
