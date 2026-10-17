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
catalog: list[dict] = [{"jid": "bob@example.com", "name": "Bob",
                        "groups": ["G"], "is_conference": False},
                       {"jid": "empty@example.com", "name": "Empty",
                        "groups": ["G"], "is_conference": False}]


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

# 1b. Global (all-contacts) search: only matching contacts stay in the tree.
history.store_message("carol@example.com", "incoming", "hello world",
                      sender="carol", timestamp="2026-02-03T09:00:00",
                      message_id="c1", origin_id="c1")
# A later, non-matching day so the "newest" differs from the matched one.
history.store_message("carol@example.com", "outgoing", "later note",
                      sender="Me", timestamp="2026-03-01T08:00:00",
                      message_id="c2", origin_id="c2")
catalog2: list[dict] = [
    {"jid": "bob@example.com", "name": "Bob", "groups": ["G"],
     "is_conference": False},
    {"jid": "carol@example.com", "name": "Carol", "groups": ["G"],
     "is_conference": False},
]


async def _global():
    d = HistoryManagerDialog(lambda: catalog2)
    await asyncio.sleep(0.2)
    d._btn_all_contacts.setChecked(True)
    d._search.setText("hello")
    d._on_search_run()
    await asyncio.sleep(0.4)
    return d


gd = asyncio.get_event_loop().run_until_complete(_global())
check("global search keeps only matching contacts",
      gd._catalog_filter == {"carol@example.com"})
check("global search filters the left tree",
      gd._tree.topLevelItemCount() == 1
      and gd._tree.topLevelItem(0).childCount() == 1
      and gd._tree.topLevelItem(0).child(0).text(0) == "Carol")
check("global search lists the matching day",
      gd._results.count() == 1
      and "Carol" in gd._results.item(0).text()
      and "2026-02-03" in gd._results.item(0).text())
check("the tree is expanded in the global search",
      gd._tree.topLevelItem(0).isExpanded())

# 1c. Opening a result lands on the matched day (not the newest) and
#     highlights the match; the results field is resizable.
asyncio.get_event_loop().run_until_complete(
    gd._open_global_result("carol@example.com", "2026-02-03"))
check("a global result opens the matched day, not the newest",
      gd._date == "2026-02-03")
check("a global result highlights the match", len(gd._matches) >= 1)

gd._set_results_height(220)
check("the results field is resizable",
      gd._results_height == 220 and gd._results.minimumHeight() == 220)
gd._set_results_height(9999)
check("the results height is clamped", gd._results_height == 400)
check("the results resize handle follows visibility",
      gd._results_handle.isVisible() == gd._results.isVisible())

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

# 6. Switching from a contact with history to one without clears the view.
dlg._released = False
dlg._jid = ""
dlg._select_jid("bob@example.com")
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.2))
check("switched to Bob and loaded his messages",
      "hi" in dlg._messages.toPlainText())
dlg._select_jid("empty@example.com")
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.2))
check("switching to a contact without history empties the dates",
      dlg._dates == [])
check("switching to a contact without history clears the messages",
      dlg._messages.toPlainText().strip() == "")
check("switching to a contact without history drops the entries",
      dlg._entries == [])
dlg._released = True

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All history-manager tests passed.")
