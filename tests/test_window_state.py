"""Minimized chat windows count as unavailable for unread purposes.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_window_state.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from types import SimpleNamespace

from stanza_im.ui.main_window import MainWindow


FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _win(minimized: bool, visible: bool = True):
    return SimpleNamespace(
        _unified=False,
        _chat_window=SimpleNamespace(isMinimized=lambda: minimized),
        _chat_area_visible=lambda: visible,
    )


check("a visible, restored chat is available",
      MainWindow._chat_area_available(_win(False)) is True)
check("a minimized chat is not treated as read on screen",
      MainWindow._chat_area_available(_win(True)) is False)
check("a hidden chat is unavailable",
      MainWindow._chat_area_available(_win(False, visible=False)) is False)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All window-state tests passed.")
