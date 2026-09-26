"""Offscreen tests for XEP-0444 Message Reactions.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_reactions.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_react_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

import slixmpp

from stanza_im.core.client import (
    JabberClient, NS_REACTIONS, NS_OCCUPANT_ID, _reactions,
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


# 1. stanza parsing -----------------------------------------------------------
def _make_reactions(target="orig-1", emojis=("😀",), mtype="chat",
                    from_="bob@example.com/res"):
    m = slixmpp.Message()
    m["from"] = from_
    m["to"] = "me@example.com/r"
    m["type"] = mtype
    node = ET.SubElement(m.xml, f"{{{NS_REACTIONS}}}reactions")
    node.set("id", target)
    for emoji in emojis:
        ET.SubElement(node, f"{{{NS_REACTIONS}}}reaction").text = emoji
    return m


check("reactions reference parsed",
      _reactions(_make_reactions()) == ("orig-1", ["😀"]))
check("multiple reactions parsed",
      _reactions(_make_reactions(emojis=("😀", "👍"))) == ("orig-1", ["😀", "👍"]))
check("empty reaction set parsed",
      _reactions(_make_reactions(emojis=())) == ("orig-1", []))
check("plain message has no reactions",
      _reactions(slixmpp.Message()) is None)


# 2. outgoing stanza (built, not sent) ----------------------------------------
# Mirror the retraction tests: inspect the built stanza directly instead of
# sending it (no live stream is available offscreen).
client = JabberClient.__new__(JabberClient)
client.xmpp = slixmpp.ClientXMPP("me@example.com/r", "pw")
client.groupchats = {}

out = client._build_reactions("bob@example.com", "orig-9", ["😀", "❤️"])
check("reaction stanza built", out is not None)
node = out.xml.find(f"{{{NS_REACTIONS}}}reactions")
check("reactions node present with target id",
      node is not None and node.get("id") == "orig-9")
check("reaction children serialized",
      [c.text for c in node.findall(f"{{{NS_REACTIONS}}}reaction")]
      == ["😀", "❤️"])
check("1:1 default type is chat", out["type"] == "chat")
check("stanza carries an id", bool(str(out["id"])))

client.groupchats = {"room@conf": object()}
room_out = client._build_reactions("room@conf", "sid-1", ["🎉"])
check("room default type is groupchat", room_out["type"] == "groupchat")

check("_build_reactions rejects empty target",
      client._build_reactions("", "x", ["😀"]) is None)
check("_build_reactions rejects empty id",
      client._build_reactions("bob@example.com", "", ["😀"]) is None)
check("send_reactions returns '' on an invalid target",
      client.send_reactions("", "x", ["😀"]) == "")


# 3. history persistence ------------------------------------------------------
jid = "alice@example.com"
history.store_message(jid, "incoming", "hi", sender="bob@example.com",
                      origin_id="MSG1", message_id="MSG1")
check("set_reactions stores bob",
      history.set_reactions(jid, "MSG1", "bob@example.com", ["😀", "👍"],
                            at="2026-01-01 10:00"))
check("set_reactions stores carol",
      history.set_reactions(jid, "MSG1", "carol@example.com", ["😀"],
                            at="2026-01-01 10:01"))
stored = history.reactions(jid, "MSG1")
check("two reactor entries stored", len(stored) == 2)
check("emoji list preserved",
      sorted(stored[0]["emojis"]) == sorted(["😀", "👍"])
      or sorted(stored[1]["emojis"]) == sorted(["😀", "👍"]))

history.set_reactions(jid, "MSG1", "bob@example.com", ["🎉"])
stored = history.reactions(jid, "MSG1")
bob = next(e for e in stored if e["by"] == "bob@example.com")
check("reaction set replaces the sender's previous set",
      bob["emojis"] == ["🎉"])

check("clearing our reactions works",
      history.set_reactions(jid, "MSG1", "Me", [], occupant_id="occ-me"))
check("occupant-id keyed entry removed",
      all(e.get("occupant_id") != "occ-me"
          for e in history.reactions(jid, "MSG1")))


# 4. ChatWidget chip aggregation ----------------------------------------------
def _make_widget(is_muc=False, self_nick="", users=None):
    w = ChatWidget("alice@example.com", "Alice",
                   chat_themes.ChatThemeFactory(), is_muc=is_muc)
    w._self_nick = self_nick
    w._users = list(users or [])
    return w


w = _make_widget()
entry = {"reactions": [
    {"by": "bob@example.com", "emojis": ["😀", "👍"], "at": "10:00"},
    {"by": "carol@example.com", "emojis": ["😀"], "at": "10:01"},
    {"by": "Me", "emojis": ["❤️"], "at": "10:02"},
], "sender": "bob@example.com", "direction": "incoming"}
chips = w.compute_reactions(entry)
by_emoji = {c["emoji"]: c for c in chips}
check("counts aggregated", by_emoji["😀"]["count"] == 2)
check("own reaction flagged as mine", by_emoji["❤️"]["mine"] is True)
check("foreign reaction not mine", by_emoji["😀"]["mine"] is False)
check("chips sorted by count desc",
      [c["emoji"] for c in chips][0] == "😀")
check("tooltip lists reactors and times",
      "10:00" in by_emoji["😀"]["title"])

w2 = _make_widget(is_muc=True, self_nick="me",
                  users=[{"nick": "me", "occupant_id": "occ-1"}])
mentry = {"reactions": [
    {"by": "me", "occupant_id": "occ-1", "emojis": ["😀"], "at": "11:00"},
    {"by": "other", "occupant_id": "occ-2", "emojis": ["😀"], "at": "11:01"},
], "sender": "other", "direction": "incoming"}
mchips = w2.compute_reactions(mentry)
check("MUC count includes both reactors",
      next(c for c in mchips if c["emoji"] == "😀")["count"] == 2)
check("MUC own reaction detected by occupant-id",
      next(c for c in mchips if c["emoji"] == "😀")["mine"] is True)


# 5. Chip rendering -----------------------------------------------------------
html = chat_themes._render_reactions_chips(
    [{"emoji": "😀", "count": 3, "mine": True, "title": "t"},
     {"emoji": "👍", "count": 1, "mine": False, "title": "t"}])
check("chip markup includes the emoji", "😀" in html)
check("own chip has data-mine", 'data-mine="1"' in html)
check("chip shows the count", ">3<" in html)
_quoted = chat_themes._render_reactions_chips(
    [{"emoji": "😀", "count": 1, "mine": False,
      "title": 'who "q" — 10:00'}])
check("tooltip quotes are HTML-escaped", "&quot;q&quot;" in _quoted)
check("tooltip title attribute survives", "title=\"who" in _quoted)

many = [{"emoji": chr(0x1F600 + i), "count": 1, "mine": False, "title": "t"}
        for i in range(10)]
capped = chat_themes._render_reactions_chips(many)
check("chip list is capped",
      capped.count('class="stanza-reaction"') >= 6)
check("overflow shows a more-chip", "reaction-more" in capped)


# 6. Emoji catalogue ----------------------------------------------------------
from stanza_im.include import emoji_data

check("catalogue has all categories",
      set(emoji_data.categories()) == {
          "smileys", "gestures", "hearts", "nature", "food",
          "objects", "symbols", "flags"})
check("catalogue is non-trivial", len(emoji_data.all_emoji()) > 200)
check("category lookup works", len(emoji_data.by_category("smileys")) > 10)
check("search finds hearts", emoji_data.search("heart"))
check("search is keyword based", "❤️" in emoji_data.search("love")
      or "😍" in emoji_data.search("love"))


# 7. Signature coverage -------------------------------------------------------
import inspect

from stanza_im.ui.chat_view import ChatView
from stanza_im.ui.chat_themes import ChatThemeFactory

check("render_message accepts reactions",
      "reactions" in inspect.signature(
          ChatThemeFactory.render_message).parameters)
check("ChatView.add_message accepts reactions",
      "reactions" in inspect.signature(ChatView.add_message).parameters)
check("render_message_html accepts reactions",
      "reactions" in inspect.signature(
          ChatView.render_message_html).parameters)

from stanza_im.ui.chat_widget import ChatWidget as _CW
check("ChatWidget exposes set_reactions",
      hasattr(_CW, "set_reactions") and hasattr(_CW, "compute_reactions"))
check("ChatWidget declares reaction signals",
      hasattr(_CW, "reaction_requested")
      and hasattr(_CW, "unreaction_requested"))
check("ChatView declares the picker anchor signal",
      hasattr(ChatView, "reaction_anchor"))

from stanza_im.ui import emoji_picker_dialog as picker
check("picker exposes an emoji font helper",
      callable(getattr(picker, "emoji_font_family", None))
      and callable(getattr(picker, "emoji_font", None)))
check("picker keeps 'Recent' out of the category tabs",
      "recent" not in picker._CATEGORY_KEYS)
_sig = inspect.signature(picker.EmojiPickerDialog.__init__)
check("picker accepts recent + can_remove", "recent" in _sig.parameters
      and "can_remove" in _sig.parameters)


# 8. Signal arity compatibility ----------------------------------------------
# A pyqtSignal signature mismatch only surfaces at runtime, when a sender is
# connected to a receiver with different arity -> crash on open_chat.  Compare
# the signatures explicitly so a future edit cannot reintroduce it.
def _signal_arity(signal):
    """Number of arguments a bound pyqtSignal carries.

    PyQt6 exposes ``signature.signatures`` as a tuple of comma-separated type
    strings (e.g. ``('QString,QString,int,int)',)``), so the argument count is
    the number of commas plus one.
    """
    sigs = getattr(signal, "signatures", None)
    if sigs:
        text = sigs[0].strip().rstrip(")")
        return 0 if not text else len(text.split(","))
    text = str(signal)
    if "(" in text and ")" in text:
        inner = text[text.index("(") + 1:text.rindex(")")].strip()
        return 0 if not inner else len(inner.split(","))
    return None


from stanza_im.ui.chat_window import ChatWindow

_check = _CW.reaction_requested
check("ChatWidget.reaction_requested carries 4 args",
      _signal_arity(_CW.reaction_requested) == 4)
check("ChatWidget/ChatWindow reaction_requested arity matches",
      _signal_arity(_CW.reaction_requested)
      == _signal_arity(ChatWindow.reaction_requested))
check("ChatWidget/ChatWindow unreaction_requested arity matches",
      _signal_arity(_CW.unreaction_requested)
      == _signal_arity(ChatWindow.unreaction_requested))

# The MainWindow slot must accept exactly what ChatWindow emits.
from stanza_im.ui.main_window import MainWindow

_slot = inspect.signature(MainWindow._on_reaction_requested)
_required = [p for p in _slot.parameters.values()
             if p.default is inspect.Parameter.empty
             and p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)]
check("MainWindow._on_reaction_requested accepts the emitted arity",
      len(_required) <= _signal_arity(ChatWindow.reaction_requested)
      <= len([p for p in _slot.parameters.values()
              if p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)]))


print()
if FAILURES:
    print(f"{len(FAILURES)} test(s) FAILED: {FAILURES}")
    sys.exit(1)
print("All tests passed.")
