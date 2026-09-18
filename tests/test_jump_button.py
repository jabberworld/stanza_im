"""Offscreen tests for the chat 'jump to bottom' button (count + two steps).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_jump_button.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_jumpbtn_")
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

cw = ChatWidget("jb@example.com", "JB", ChatThemeFactory())
view = cw._view

# 1. scrolled-up detection ----------------------------------------------------
view._overflow = True
view._fraction = 0.5
check("scrolled up detected", view.is_scrolled_up())
view._fraction = 1.0
check("at bottom is not scrolled up", not view.is_scrolled_up())
view._overflow = False
view._fraction = 0.5
check("no overflow is not scrolled up", not view.is_scrolled_up())

# 2. counting + first-unread memory + label -----------------------------------
view._overflow = True
view._fraction = 0.5
view.note_new_message("m1")
view.note_new_message("m2")
check("new messages counted", view._new_count == 2)
check("first unread remembered", view._first_unread_id == "m1")
check("label shows the number", view._jump_button.text() == "\u25bc 2")
check("label caps at 99+", view._jump_label(120) == "\u25bc 99+")

# 3. two-step click -----------------------------------------------------------
events = []
_real_scroll_to_message = view.scroll_to_message
_real_scroll_to_bottom = view.scroll_to_bottom
view._jump_has_target = lambda: True
view.scroll_to_message = lambda mid, highlight=True: events.append(
    ("msg", mid, highlight))
view.scroll_to_bottom = lambda: events.append(("bottom",))
view._on_jump_clicked()
check("first click goes to the first unread",
      events == [("msg", "m1", False)] and view._jumped_once)
check("count kept until the bottom", view._new_count == 2)
view._on_jump_clicked()
check("second click goes to the bottom and resets",
      events[-1] == ("bottom",) and view._new_count == 0
      and view._first_unread_id == "" and not view._jumped_once)

# 4. reaching the bottom resets ----------------------------------------------
view.scroll_to_message = _real_scroll_to_message
view.scroll_to_bottom = _real_scroll_to_bottom
view.note_new_message("m3")
view.scroll_to_bottom()
check("scroll_to_bottom clears the counter", view._new_count == 0
      and view._first_unread_id == "")

# 5. ChatWidget counts only incoming (not own) messages -----------------------
calls = []
scrolls = []
view.is_scrolled_up = lambda: True
view.note_new_message = lambda tid="": calls.append(tid)
_real_scroll = view.scroll_to_bottom
view.scroll_to_bottom = lambda: scrolls.append(True)
cw.add_message(sender="A", body="hi", timestamp="10:00",
               direction="incoming", reply_able_id="x1")
check("incoming message counted", calls == ["x1"])
check("incoming message does not force-scroll", scrolls == [])
cw.add_message(sender="Me", body="yo", timestamp="10:01", direction="outgoing")
check("outgoing message not counted", calls == ["x1"])
check("own message scrolls to bottom", scrolls == [True])
view.scroll_to_bottom = _real_scroll

# 6. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_view_src = open(os.path.join(_root, "stanza_im", "ui", "chat_view.py"),
                 encoding="utf-8").read()
check("mixin implements the counter/two-step API",
      all(k in _view_src for k in ("note_new_message", "_on_jump_clicked",
                                   "_jump_label", "_first_unread_id")))
_jump_js = _view_src.split('_JUMP_JS = """', 1)[1].split('"""', 1)[0]
check("HTML jump button delegates to Python",
      "window.bridge.on_jump_clicked()" in _jump_js
      and "scrollTo" not in _jump_js)
check("jump button press is also relayed by the scroll poll",
      "window.__stanzaJumpPress = 1;" in _jump_js
      and "window.__stanzaJumpPress ? 1 : 0" in _view_src
      and "self._on_jump_clicked()" in _view_src)
_widget_src = open(os.path.join(_root, "stanza_im", "ui", "chat_widget.py"),
                   encoding="utf-8").read()
check("add_message feeds the counter",
      "self._view.note_new_message(self._reply_target_id(entry))" in _widget_src)
check("add_message no longer force-scrolls every message",
      "self._anchor_bottom = True\n        self._view.scroll_to_bottom()"
      not in _widget_src)

cw.detach()
print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All jump-button tests passed.")
