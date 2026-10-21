"""Tests for focusing an already-open chat (window raise/restore).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_chat_focus.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_focus_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_window import ChatWindow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


window = ChatWindow(ChatThemeFactory())
window.open_chat("bob@example.com", "Bob")
window.open_chat("carol@example.com", "Carol")

# An existing tab is focused and the minimized window is restored, so the
# user notices that the conversation is already open.
window.showMinimized()
window._focus_tab("bob@example.com")
check("focusing an existing tab restores a minimized window",
      not window.isMinimized() and window.isVisible())
check("focusing an existing tab switches to it",
      window.current_jid() == "bob@example.com")

window.showMinimized()
window.open_chat("carol@example.com", "Carol")
check("opening an already-open chat restores the window too",
      not window.isMinimized()
      and window.current_jid() == "carol@example.com")

_source = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "stanza_im", "ui", "chat_window.py"),
    encoding="utf-8").read()
_focus = _source.split("def _focus_tab", 1)[1].split("\n    def ", 1)[0]
check("focusing a tab goes through the shared raise helper",
      "_raise_window(" in _focus
      and "self.show()" not in _focus and "self.raise_()" not in _focus)
_raise = _source.split("def _raise_window", 1)[1].split("\n    def ", 1)[0]
check("the raise helper restores and activates the window",
      "showNormal()" in _raise and "raise_()" in _raise
      and "activateWindow()" in _raise)

window.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All chat-focus tests passed.")
