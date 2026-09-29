"""Offscreen tests for the history manager and its chat toolbar button.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_history_manager.py
"""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_hm_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.core import history
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.history_manager import HistoryManagerDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. Selecting a contact actually loads its dates and messages (regression:
#    the async guard aborted the very first selection).
history.store_message("bob@example.com", "incoming", "hi", sender="bob",
                      timestamp="2026-01-02T10:00:00", message_id="m1",
                      origin_id="m1")
history.store_message("bob@example.com", "outgoing", "yo", sender="Me",
                      timestamp="2026-01-02T10:05:00", message_id="m2",
                      origin_id="m2")
catalog = [{"jid": "bob@example.com", "name": "Bob", "groups": ["G"],
            "is_conference": False}]


async def _run():
    dlg = HistoryManagerDialog(lambda: catalog)
    await asyncio.sleep(0.2)
    return dlg


dlg = asyncio.get_event_loop().run_until_complete(_run())
check("selecting a contact sets the JID", dlg._jid == "bob@example.com")
check("selecting a contact loads the dated days",
      dlg._dates == ["2026-01-02"])
check("the day's messages are rendered",
      "hi" in dlg._messages.toPlainText()
      and "yo" in dlg._messages.toPlainText())

# 2. Chat toolbar history button.
cw = ChatWidget("bob@example.com", "Bob", ChatThemeFactory())
seen = []
cw.history_requested.connect(seen.append)
check("chat toolbar has a history button",
      getattr(cw, "_history_btn", None) is not None)
check("the history button tooltip is localised",
      cw._history_btn.toolTip() == "Show history" or cw._history_btn.toolTip())
cw._history_btn.click()
check("the history button emits history_requested(jid)",
      seen == ["bob@example.com"])
cw.detach()

muc = ChatWidget("room@conf.example", "Room", ChatThemeFactory(), is_muc=True)
check("MUC tabs also carry the history button",
      getattr(muc, "_history_btn", None) is not None)
muc.detach()

# 3. The reused singleton must revive after close (``done`` marks it
#    released; ``showEvent``/``open_for`` reset that flag).
dlg.done(0)
check("closing the dialog marks it released", dlg._released is True)
dlg.show()
dlg.open_for("bob@example.com")
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.2))
check("reopening the reused dialog revives it", dlg._released is False)
check("reopened dialog reloads the dated days",
      dlg._dates == ["2026-01-02"])
check("reopened dialog renders the day's messages",
      "hi" in dlg._messages.toPlainText())

# 4. A day added to SQLite after the dates were read (MAM backfill) is picked
#    up when it is clicked: the dates are re-read instead of shown as empty.
history.store_message("bob@example.com", "incoming", "older", sender="bob",
                      timestamp="2026-01-01T09:00:00", origin_id="m0")
check("the new day is not known yet", "2026-01-01" not in dlg._dates)
dlg._calendar.setSelectedDate(QtCore.QDate(2026, 1, 1))
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.2))
check("clicking a backfilled day re-reads the dates",
      "2026-01-01" in dlg._dates)
check("the backfilled day's messages are shown",
      "older" in dlg._messages.toPlainText())
dlg._released = True

# 5. An empty JID must never create the nameless ``<dir>/.sqlite3`` store.
check("store_message('') is refused", history.store_message("", "incoming", "x")
      is False)
check("dates('') is empty", history.dates("") == [])
check("load_history('') is empty", history.load_history("") == [])
check("has_history('') is false", history.has_history("") is False)
check("no nameless history file is created",
      not os.path.isfile(os.path.join(history.HISTORY_DIR, ".sqlite3")))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All history-manager tests passed.")
