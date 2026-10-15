"""Offscreen tests for the QTextBrowser chat fallback (``webengine_mode=off``).

The fallback ChatView must keep API parity with the WebEngine one
(``add_message`` kwargs, ``update_reactions``, ``shutdown``) and must wrap long
messages.  The fallback is only reachable when the web engine is disabled, so
the test forces that before importing ``chat_view``.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_fallback_view.py
"""
import os
import sys
import tempfile

os.environ["XDG_DATA_HOME"] = os.path.join(tempfile.mkdtemp(), "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tempfile.mkdtemp(), "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.include import constants

i18n_load("en")

# Force the fallback before chat_view is imported (it picks the class on load).
constants.set_webengine_enabled(False)

from stanza_im.ui import chat_view  # noqa: E402
from stanza_im.ui.chat_view import ChatView  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def no_raise(name, fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        check(name, False)
        print("   raised:", repr(exc))
        return
    check(name, True)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
check("the fallback view is selected", chat_view.HAS_WEBENGINE is False)

view = ChatView()
view.resize(360, 300)
view.show()
app.processEvents()

# 1. add_message must accept the full WebEngine kwarg set ---------------------
no_raise("add_message accepts the full kwargs", lambda: view.add_message(
    "Alice", "hi there", "12:00", "incoming", is_next=False,
    sender_color="#000", user_icon_path="", message_id="m1", unstyled=False,
    raw_timestamp="2026-10-15T12:00:00Z", reply_able_id="", reply_author="",
    reply_quote=None, outgoing=False, edited=False, hats=None, retracted=False,
    retract_marker=False, retract_reason="", retract_by="", moderatable=False,
    reactions=[{"emoji": "\U0001F44D", "count": 2, "mine": False, "title": ""}],
    unread_marker=False, media=None, encrypted=False,
    markup={"spans": []}))
check("the reactions suffix is rendered",
      "\U0001F44D 2" in view.toPlainText())

# 2. long messages wrap ------------------------------------------------------
view.clear()
view.add_message("Bob", "word " * 200, "12:01", "incoming")
app.processEvents()
check("a long message wraps (vertical scroll)",
      view.verticalScrollBar().maximum() > 0)
check("no horizontal scrollbar",
      not view.horizontalScrollBar().isVisible())

# 3. the rest of the view API used by chat_widget must exist -----------------
no_raise("update_reactions does not raise",
         lambda: view.update_reactions("m1", "<span/>"))
no_raise("shutdown does not raise", view.shutdown)
no_raise("add_status does not raise", lambda: view.add_status("subject", "12:02"))
no_raise("prepend_messages does not raise", lambda: view.prepend_messages([
    {"sender": "Carol", "body": "older", "timestamp": "2026-10-15T11:00:00Z",
     "direction": "incoming"}]))
check("prepend keeps the older message", "older" in view.toPlainText())

# 4. the document is bounded and the undo stack is off ----------------------
check("undo/redo is disabled", view.isUndoRedoEnabled() is False)
view.clear()
for i in range(600):
    view.add_message("Bob", f"message {i}", "12:00", "incoming")
app.processEvents()
check("the document is bounded to the cap",
      view.document().blockCount() <= ChatView._MAX_BLOCKS + 1)
check("the newest message is kept", "message 599" in view.toPlainText())
check("the oldest message is trimmed", "message 0" not in view.toPlainText())

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All fallback-view tests passed.")
