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


# 4b. Removing our own reaction (click on a data-mine chip) --------------------
w3 = _make_widget()
e3 = {"sender": "Bob", "direction": "incoming",
      "origin_id": "ORIG3", "message_id": "",
      "reactions": [{"by": "Me", "emojis": ["😀", "👍"], "at": "10:00"}]}
w3._messages.append(e3)
check("our chip is marked mine before removal",
      next(c for c in w3.compute_reactions(e3) if c["emoji"] == "😀")["mine"])
check("set_reactions finds a message by origin_id",
      w3.set_reactions("ORIG3", []) is True)
check("our reaction entry is removed", e3["reactions"] == [])
check("no chips remain after removal", w3.compute_reactions(e3) == [])

# The reverse: removing one of two emoji keeps the other.
w3b = _make_widget()
e3b = {"sender": "Bob", "direction": "incoming",
       "origin_id": "ORIG4", "message_id": "ORIG4",
       "reactions": [{"by": "Me", "emojis": ["😀", "👍"], "at": "10:00"}]}
w3b._messages.append(e3b)
_kept = [e for e in e3b["reactions"][0]["emojis"] if e != "😀"]
w3b.set_reactions("ORIG4",
                  [{"by": "Me", "emojis": _kept, "at": "10:00"}])
chips_left = w3b.compute_reactions(e3b)
check("removing one emoji keeps the other",
      len(chips_left) == 1 and chips_left[0]["emoji"] == "👍"
      and chips_left[0]["mine"] is True)


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
check("more-chip is clickable (marker present)",
      'data-reactions-more="1"' in capped)


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
check("ChatView defines the reaction-ref clearers",
      hasattr(ChatView, "_clear_reactions_request")
      and hasattr(ChatView, "_clear_unreact_request")
      and hasattr(ChatView, "_clear_react_request"))

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

check("ChatWidget.reaction_requested carries 4 args",
      _signal_arity(_CW.reaction_requested) == 4)
check("ChatWidget/ChatWindow reaction_requested arity matches",
      _signal_arity(_CW.reaction_requested)
      == _signal_arity(ChatWindow.reaction_requested))
check("ChatWidget/ChatWindow unreaction_requested arity matches",
      _signal_arity(_CW.unreaction_requested)
      == _signal_arity(ChatWindow.unreaction_requested))
check("ChatWidget/ChatWindow reactions_list_requested arity matches",
      _signal_arity(_CW.reactions_list_requested) == 2
      and _signal_arity(_CW.reactions_list_requested)
      == _signal_arity(ChatWindow.reactions_list_requested))


def _slot_accepts(slot, arity):
    """True when *slot* (an unbound function) can take *arity* arguments.

    ``self`` is excluded; a slot with optional trailing arguments accepts any
    count between its required and total positional parameters.
    """
    params = [p for p in inspect.signature(slot).parameters.values()
              if p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)][1:]
    required = [p for p in params if p.default is inspect.Parameter.empty]
    return len(required) <= arity <= len(params)


from stanza_im.ui.main_window import MainWindow

check("MainWindow slot accepts ChatWindow.reaction_requested arity",
      _slot_accepts(MainWindow._on_reaction_requested,
                    _signal_arity(ChatWindow.reaction_requested)))
check("MainWindow slot accepts ChatWindow.unreaction_requested arity",
      _slot_accepts(MainWindow._on_unreaction_requested,
                    _signal_arity(ChatWindow.unreaction_requested)))
check("MainWindow slot accepts ChatWindow.reactions_list_requested arity",
      _slot_accepts(MainWindow._on_reactions_list_requested,
                    _signal_arity(ChatWindow.reactions_list_requested)))


# 9. "+k / list" relay --------------------------------------------------------
w4 = _make_widget()
seen = []
w4.reactions_list_requested.connect(lambda *a: seen.append(a))
w4._open_link("stanza:reactions:" + "MsgID")
check("stanza:reactions relays reactions_list_requested",
      seen == [("alice@example.com", "MsgID")])
seen2 = []
w4.reactions_list_requested.connect(lambda *a: seen2.append(a))
w4._open_link("stanza:reactions:")
check("an empty reactions ref is ignored", not seen2)

# 10. unreact payload encoding (regression) ------------------------------------
# New format: sid and emoji percent-encoded separately.
w5 = _make_widget()
un = []
w5.unreaction_requested.connect(lambda *a: un.append(a))
w5._open_link("stanza:unreact:a4532a/" + "%F0%9F%8F%B3%EF%B8%8F")
check("unreact with separately-encoded parts parses",
      un == [("alice@example.com", "a4532a", "🏳️")])

# Legacy format: the whole 'sid/emoji' pair encoded (separator was %2F).
un2 = []
w5.unreaction_requested.connect(lambda *a: un2.append(a))
w5._open_link("stanza:unreact:a4532a%2F%F0%9F%8F%B3%EF%B8%8F")
check("unreact with a pre-encoded pair still parses",
      un2 == [("alice@example.com", "a4532a", "🏳️")])


print()
if FAILURES:
    print(f"{len(FAILURES)} test(s) FAILED: {FAILURES}")
    sys.exit(1)
print("All tests passed.")
