"""Offscreen tests for XEP-0439 Quick Response parsing and rendering.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_quick_response.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tempfile.mkdtemp(), "config")
os.environ["XDG_DATA_HOME"] = os.path.join(tempfile.mkdtemp(), "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(tempfile.mkdtemp(), "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets
import slixmpp

from stanza_im.core.client import JabberClient, _quick_response
from stanza_im.core import history
from stanza_im.include import constants
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. Parser ------------------------------------------------------------------
msg = slixmpp.Message()
msg["body"] = "Pick one"
ns = "urn:xmpp:tmp:quick-response"
xml_lang = "{http://www.w3.org/XML/1998/namespace}lang"
for value, label, lang in (("yes", "Yes!", "en"), ("no", "", "en"),
                           ("yes", "duplicate", "en")):
    el = msg.xml.makeelement("{%s}response" % ns, {
        "value": value, "label": label, xml_lang: lang})
    msg.xml.append(el)
for action_id, label in (("merge", "Merge"), ("merge", "Again")):
    msg.xml.append(msg.xml.makeelement("{%s}action" % ns, {
        "id": action_id, "label": label, xml_lang: "en"}))
quick = _quick_response(msg)
check("response and action payloads parse",
      quick is not None and len(quick["responses"]) == 2
      and len(quick["actions"]) == 1)
check("response labels fall back to the value",
      quick["responses"][1]["label"] == "no")
check("response language is preserved",
      quick["responses"][0]["lang"] == "en")
check("a message without quick response has no payload",
      _quick_response(slixmpp.Message()) is None)

# 2. History round-trip ------------------------------------------------------
constants.set_active_profile("quick@example.com")
jid = "bot@example.com"
check("quick response is stored",
      history.store_message(jid, "incoming", "Pick one",
                            quick_response=quick))
loaded = history.load_history(jid, 10)
check("quick response survives a history reload",
      len(loaded) == 1 and loaded[0]["quick_response"] == quick)
history.close(jid)

# 3. Rendering ---------------------------------------------------------------
theme = ChatThemeFactory()
html = theme.render_message(
    "Bot", "Pick one", "12:00", "incoming",
    quick_response=quick, quick_response_active=True,
    quick_response_ref="m1")
check("response buttons render under the body",
      html.index("Pick one") < html.index("stanza-quick-response"))
check("response href carries the message and language",
      "stanza:quick:response/m1/yes/en" in html)
check("action buttons render",
      "stanza:quick:action/m1/merge" in html)
inactive = theme.render_message(
    "Bot", "Pick one", "12:00", "incoming",
    quick_response=quick, quick_response_active=False,
    quick_response_ref="m1")
check("an older response is hidden", "stanza-quick-response" not in inactive)
check("actions stay on an older message", "stanza-quick-action" in inactive)

# 4. Active prompt rules -----------------------------------------------------
def entry(direction, sender, sender_jid, body, ref, responses=None,
          timestamp="2026-01-01T00:00:00"):
    return {
        "direction": direction,
        "sender": sender,
        "sender_jid": sender_jid,
        "body": body,
        "message_id": ref,
        "timestamp": timestamp,
        "quick_response": ({"responses": responses, "actions": []}
                           if responses else None),
    }


widget = ChatWidget.__new__(ChatWidget)
widget._history = []
widget._messages = []
widget._quick_response_used_refs = set()
widget.is_muc = True
bot = entry("incoming", "Bot", "bot@example.com", "Poll", "q1",
            [{"value": "yes", "label": "Yes", "lang": "en"}],
            "2026-01-01T00:00:01")
alice = entry("incoming", "Alice", "alice@example.com", "yes", "a1",
              timestamp="2026-01-01T00:00:02")
widget._history = [bot, alice]
check("another MUC participant does not hide the poll",
      widget._compute_quick_response_refs() == {"q1"})
bot_done = entry("incoming", "Bot", "bot@example.com", "Done", "q2",
                 timestamp="2026-01-01T00:00:03")
widget._history.append(bot_done)
check("the bot's newer plain text hides its poll",
      widget._compute_quick_response_refs() == set())
widget._history = [bot]
widget._quick_response_used_refs.add("q1")
check("a consumed response is not offered again",
      widget._compute_quick_response_refs() == set())

widget_1to1 = ChatWidget.__new__(ChatWidget)
widget_1to1._history = [
    entry("incoming", "Bot", "bot@example.com", "Poll", "q1",
          [{"value": "yes", "label": "Yes", "lang": "en"}],
          "2026-01-01T00:00:01"),
]
widget_1to1._messages = []
widget_1to1._quick_response_used_refs = set()
widget_1to1.is_muc = False
widget_1to1._history.append(
    entry("incoming", "Bot", "bot@example.com", "New question", "q2",
          timestamp="2026-01-01T00:00:02"))
check("1:1 newer text without responses hides the prompt",
      widget_1to1._compute_quick_response_refs() == set())

# 5. Outgoing body language -------------------------------------------------
client = JabberClient("me@example.com/res", "pw")
out, _mid = client._compose_message("bot@example.com", "yes", lang="ru")
body = next(child for child in out.xml
            if str(child.tag).rsplit("}", 1)[-1] == "body")
check("response body copies xml:lang",
      body.get("{http://www.w3.org/XML/1998/namespace}lang") == "ru")

print()
print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
