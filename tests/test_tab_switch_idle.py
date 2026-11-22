"""Tab switches must not re-push unchanged counters or window titles.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_tab_switch_idle.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_tab_switch_idle_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.include import constants

i18n_load("en")
constants.set_webengine_enabled(False)

from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_window import ChatWindow

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

window = ChatWindow(ChatThemeFactory())
bob = window.open_chat("bob@example.com", "Bob")
room = window.open_groupchat("room@conf.example", "me", "Room")

# 1. ChatWindow.set_unread() ------------------------------------------------
check("first counter change is applied",
      window.set_unread("bob@example.com", 3, 0) is True
      and window._tab_unread["bob@example.com"] == (3, 0))

applied = []
original_apply = window._apply_tab_unread
original_title = window._update_title
window._apply_tab_unread = lambda jid: (
    applied.append(("tab", jid)), original_apply(jid))[1]
window._update_title = lambda: applied.append(("title", ""))
check("the same counter is ignored",
      window.set_unread("bob@example.com", 3, 0) is False and applied == [])
check("a changed counter is applied",
      window.set_unread("bob@example.com", 4, 0) is True
      and applied == [("tab", "bob@example.com"), ("title", "")])
window._apply_tab_unread = original_apply
window._update_title = original_title

# 2. ChatWindow._update_title() --------------------------------------------
window._last_title = None
titles = []
original_set_title = window.setWindowTitle
window.setWindowTitle = lambda text: (
    titles.append(text), original_set_title(text))[1]
window._update_title()
window._update_title()
check("an unchanged title is set only once", len(titles) == 1)
window.setWindowTitle = original_set_title

# 3. ChatWidget unread / mention counters ----------------------------------
bob.set_unread_count(5)
view = bob._view
view_calls = []
original_unseen = view.set_unseen_count
original_mention = view.set_mention_count
original_reaction = view.set_reaction_count
view.set_unseen_count = lambda count, target=None: (
    view_calls.append(("unread", count)), original_unseen(count, target))[1]
view.set_mention_count = lambda count: (
    view_calls.append(("mention", count)), original_mention(count))[1]
view.set_reaction_count = lambda count: (
    view_calls.append(("reaction", count)), original_reaction(count))[1]

check("the same unread count is ignored",
      bob.set_unread_count(5) is False and view_calls == [])
check("a changed unread count reaches the view",
      bob.set_unread_count(6) is True
      and view_calls == [("unread", 6)])
view_calls.clear()
check("the same mention count is ignored",
      bob.set_mention_count(0) is False and view_calls == [])
check("a changed mention count reaches the view",
      bob.set_mention_count(2) is True
      and view_calls == [("mention", 2)])

# 4. ChatWidget reaction map ------------------------------------------------
bob.set_reaction_pending({"m1": 2, "m2": 5})
view_calls.clear()
check("the same reaction map is ignored",
      bob.set_reaction_pending({"m1": 2, "m2": 5}) is False
      and view_calls == [])
check("a changed reaction map reaches the view",
      bob.set_reaction_pending({"m1": 3, "m2": 5}) is True
      and view_calls == [("reaction", 8)])

# 5. A rebuilt view still receives the current counters ---------------------
bob.set_unread_count(7)
bob.set_mention_count(4)
bob.set_reaction_pending({"m9": 1})
bob.suspend()
bob.resume()
check("a resumed view gets the unread count",
      bob._view._new_count == 7)
check("a resumed view gets the mention count",
      bob._view._mention_count == 4)
check("a resumed view gets the reaction count",
      bob._view._reaction_count == 1)

bob.detach()
window.close_all()
window.close()

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All tab-switch idle tests passed.")
