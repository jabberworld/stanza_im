"""Offscreen tests for the floating "reactions on our messages" button.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_reaction_button.py
"""
import os
import sys
import tempfile
import types

_SCRATCH = tempfile.mkdtemp(prefix="stanza_reactionbtn_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 1. label formatting ---------------------------------------------------------
cw = ChatWidget("rb@example.com", "RB", ChatThemeFactory())
view = cw._view
check("bare heart label", view._reaction_label(0) == "\u2665")
check("counted heart label", view._reaction_label(3) == "\u2665 3")
check("heart label caps at 99+", view._reaction_label(150) == "\u2665 99+")

# 2. pending map drives the count and the view --------------------------------
seen = []
cw.reaction_seen.connect(lambda jid, ref, count: seen.append((jid, ref, count)))
scrolls = []
cw._view.scroll_to_message = lambda mid, highlight=True: scrolls.append(mid)
cw._find_message = lambda ref: {"id": ref, "reply_id": ref}
cw._reply_target_id = lambda entry: entry["reply_id"]

cw.set_reaction_pending({"m1": 2, "m2": 5})
check("pending map sets the total", cw.reaction_count() == 7)
check("view shows the total", view._reaction_count == 7)
check("refs keep the map order", cw._reaction_refs == ["m1", "m2"])

# 3. a click clears one message (batch) and emits reaction_seen ---------------
cw._jump_to_next_reaction()
check("click jumps to the first pending message", scrolls == ["m1"])
check("click emits the cleared ref/count", seen == [("rb@example.com", "m1", 2)])
check("only the clicked message is cleared", cw.reaction_count() == 5
      and cw._reaction_refs == ["m2"])
cw._jump_to_next_reaction()
check("second click clears the next message", cw.reaction_count() == 0
      and cw._reaction_refs == [])
check("the button hides at zero", view._reaction_count == 0)

# 4. delta accounting (reactions others add / take back) ----------------------
from stanza_im.ui.main_window import MainWindow

mw = types.SimpleNamespace(
    _muc_self_nicks={}, _muc_users={}, _client=None,
    _reaction_pending={},
    _push_reaction_pending=lambda jid: None,
)
mw._reaction_is_mine = (
    lambda jid, by, occ: MainWindow._reaction_is_mine(mw, jid, by, occ))
_own = {"v": True}
mw._is_own_message = lambda jid, ref: _own["v"]

MainWindow._note_reaction_delta(mw, "rb@example.com", "m1", "peer@x", "", 0, 5)
check("five reactions add five", mw._reaction_pending["rb@example.com"]["m1"] == 5)
MainWindow._note_reaction_delta(mw, "rb@example.com", "m1", "peer@x", "", 5, 3)
check("taking two back subtracts two", mw._reaction_pending["rb@example.com"]["m1"] == 3)
MainWindow._note_reaction_delta(mw, "rb@example.com", "m1", "peer@x", "", 3, 0)
check("clearing the last reaction drops the entry",
      mw._reaction_pending.get("rb@example.com") in (None, {}))

_own["v"] = False
MainWindow._note_reaction_delta(mw, "rb@example.com", "m9", "peer@x", "", 0, 4)
check("reactions on foreign messages are ignored",
      not mw._reaction_pending.get("rb@example.com"))

# 5. our own reactions never count --------------------------------------------
mw._is_own_message = lambda jid, ref: True
MainWindow._note_reaction_delta(mw, "rb@example.com", "m1", "Me", "", 0, 2)
check("our own reaction is not counted",
      not mw._reaction_pending.get("rb@example.com"))

# 6. reactor set lookup --------------------------------------------------------
entries = [{"by": "peer@x", "emojis": ["a", "b"], "occupant_id": "occ1"}]
check("reactor set matched by occupant id",
      MainWindow._reactor_set(entries, "peer@x", "occ1") == ["a", "b"])
check("reactor set matched by name when no occupant id",
      MainWindow._reactor_set(entries, "peer@x", "") == ["a", "b"])
check("unknown reactor is empty",
      MainWindow._reactor_set(entries, "other@x", "") == [])

# 7. history.entry_by_ref -----------------------------------------------------
from stanza_im.core import history

history.store_message("rb@example.com", "outgoing", "hi", sender="Me",
                      origin_id="orig-1", message_id="mid-1")
entry = history.entry_by_ref("rb@example.com", "orig-1")
check("entry_by_ref finds by origin id", entry is not None
      and entry["direction"] == "outgoing")
entry = history.entry_by_ref("rb@example.com", "mid-1")
check("entry_by_ref finds by message id", entry is not None)
check("entry_by_ref returns None for an unknown ref",
      history.entry_by_ref("rb@example.com", "nope") is None)

# 8. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_view_src = open(os.path.join(_root, "stanza_im", "ui", "chat_view.py"),
                 encoding="utf-8").read()
_widget_src = open(os.path.join(_root, "stanza_im", "ui", "chat_widget.py"),
                   encoding="utf-8").read()
_window_src = open(os.path.join(_root, "stanza_im", "ui", "chat_window.py"),
                   encoding="utf-8").read()
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
check("the reaction button is relayed by the scroll poll",
      "window.__stanzaReactionPress ? 1 : 0" in _view_src
      and "self._on_reaction_clicked()" in _view_src)
check("the reaction button lives in the fab row",
      "'stanza-reaction'" in _view_src and "d.style.order = '2'" in _view_src)
check("ChatWidget pushes the pending map to the view",
      "view.reaction_jump_requested.connect" in _widget_src
      and "def set_reaction_pending" in _widget_src)
check("ChatWindow relays reaction_seen for both tab kinds",
      _window_src.count("widget.reaction_seen.connect") == 2
      and "def set_reaction_pending" in _window_src)
check("MainWindow owns the session pending map",
      "self._reaction_pending: dict" in _mw_src
      and "self._chat_window.reaction_seen.connect(self._on_reaction_seen)"
      in _mw_src)

# 9. ChatWindow relays reaction_seen with the arguments intact ----------------
# (A `lambda r, c, j=widget.jid` copied from last_seen_changed mismatched the
# widget's three-argument signal and emitted (count, jid, ref), crashing on
# the first click.)
from stanza_im.ui.chat_window import ChatWindow

_win = ChatWindow(ChatThemeFactory())
_relayed = []
_win.reaction_seen.connect(lambda j, r, c: _relayed.append((j, r, c)))
_widget = _win.open_chat("bob@example.com", "Bob")
_widget.reaction_seen.emit("bob@example.com", "m1", 3)
check("ChatWindow forwards reaction_seen as (jid, ref, count)",
      _relayed == [("bob@example.com", "m1", 3)])

cw.detach()
print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All reaction-button tests passed.")
