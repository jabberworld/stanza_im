"""Unread-anchor movement policy and divider flash.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_unread_scroll_policy.py
"""
import inspect
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_view import anchor_update_action
from stanza_im.ui.chat_widget import ChatWidget

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def action(previous, current, **kwargs):
    defaults = dict(user_scrolled=True, suspended=False, at_bottom=False,
                    armed=True)
    defaults.update(kwargs)
    return anchor_update_action(previous, current, **defaults)


check("the first poll is not an upward movement",
      action(None, 100) == ("", True))
check("a downward scroll does not move the anchor",
      action(100, 140) == ("", True))
check("the first upward movement requests one update",
      action(140, 100) == ("update", False))
check("further upward movement does not move it again",
      action(100, 60, armed=False) == ("", False))
check("a downward movement re-arms the next update",
      action(60, 80, armed=False) == ("", True))
check("reaching the bottom re-arms but never moves the anchor",
      action(140, 100, at_bottom=True) == ("", True))
check("an upward scroll at the bottom re-arms the next update",
      action(140, 100, at_bottom=True, armed=False) == ("", True))
check("a suspended scroll reports nothing",
      action(140, 100, suspended=True) == ("", True))
check("a programmatic/not-user scroll reports nothing",
      action(140, 100, user_scrolled=False) == ("", True))

flash = inspect.getsource(ChatWidget._flash_first_unread)
check("opening an unread chat flashes the divider",
      "flash_unread_separator" in flash)
check("opening an unread chat does not flash a message",
      "highlight_message" not in flash)
_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
css = ChatThemeFactory().generate_empty_page("")
check("the divider has its own flash class",
      ".stanza-unread-flash" in css and "stanza-unread-flash" in css)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All unread-scroll policy tests passed.")
