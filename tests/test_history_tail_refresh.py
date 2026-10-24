"""Merging newly stored history into the open chat window.

A conference server replays its archive on join (archived groupchat messages)
and the MAM backfill stores rows while the tab is open; those used to stay
invisible until the tab was reopened.  The tail refresh reloads the window only
for the visible, not-scrolled-up conversation.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_history_tail_refresh.py
"""
import asyncio
import inspect
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_tailref_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core import history
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui import chat_widget as chat_widget_mod

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])


class _StubView(QtWidgets.QWidget):
    """Minimal view stand-in (no WebEngine page in the tests)."""

    def __init__(self):
        super().__init__()
        self.highlight_nick = ""
        self.scrolled_up = False
        self.cleared = 0
        self.time_scrolls = []
        self.bottom_scrolls = 0

    def shutdown(self):
        pass

    def set_chat_zoom(self, factor):
        pass

    def scroll_fraction(self):
        return 1.0

    def clear(self):
        self.cleared += 1

    def add_status(self, text, timestamp=""):
        pass

    def add_message(self, *args, **kwargs):
        pass

    def scroll_to_bottom(self):
        self.bottom_scrolls += 1

    def scroll_to_time(self, timestamp):
        self.time_scrolls.append(timestamp)

    def set_scroll_fraction(self, fraction):
        pass

    def seed_unseen(self, *args, **kwargs):
        pass

    def scroll_to_message(self, *args, **kwargs):
        pass

    def is_scrolled_up(self):
        return self.scrolled_up

    def update_sender_avatar(self, *args, **kwargs):
        pass

    def set_media_thumbnail(self, *args, **kwargs):
        pass


jid = "tail@conf.example"
history.store_message(jid, "incoming", "old one", sender="A",
                      timestamp="2026-10-21T10:00:00.000000Z")
history.store_message(jid, "incoming", "old two", sender="B",
                      timestamp="2026-10-21T11:00:00.000000Z")
old = history.load_history(jid, 10)

cw = chat_widget_mod.ChatWidget(
    jid, "Room", chat_themes.ChatThemeFactory(), is_muc=True)
cw._create_view = lambda theme: _StubView()
cw._view = _StubView()
cw._window_size = 10
cw.set_history(old, 10, True)
check("the window starts at the old tail",
      cw.newest_ts() == "2026-10-21T11:00:00.000000Z")

# A newer archived message is stored behind the open window.
history.store_message(jid, "incoming", "new today", sender="C",
                      timestamp="2026-10-22T12:00:00.000000Z")

# A background tab must not build/reload a page.
check("a hidden tab is not refreshed",
      asyncio.run(cw.refresh_tail_if_newer()) is False)

cw.show()
app.processEvents()
cw._view.scrolled_up = True
check("a transient non-bottom view does not block the refresh",
      asyncio.run(cw.refresh_tail_if_newer(force=False)) is True)
check("the new message is now the newest",
      cw.newest_ts() == "2026-10-22T12:00:00.000000Z"
      and cw._history[-1]["body"] == "new today")

# A genuine user scroll-up (reported by the view) keeps the window alone.
cw._on_view_bottom()
check("reaching the bottom clears the user-scroll flag",
      cw._user_scrolled_up is False)
cw._view.scrolled_up = True
cw._on_last_seen("someone@conf/today", "2026-10-22T12:00:00.000000Z", "")
check("a user scroll sets the flag", cw._user_scrolled_up is True)
check("a tab scrolled up by the user is not refreshed",
      asyncio.run(cw.refresh_tail_if_newer()) is False)

cw._on_view_bottom()
cw._view.scrolled_up = False
check("a second refresh is a no-op when nothing is newer",
      asyncio.run(cw.refresh_tail_if_newer()) is False)

# A suspended tab defers the refresh to resume().
cw._suspended = True
cw.schedule_tail_refresh()
check("a suspended tab defers the tail refresh",
      cw._tail_refresh_on_resume is True
      and asyncio.run(cw.refresh_tail_if_newer()) is False)
cw._suspended = False
cw._tail_refresh_on_resume = False

# A join replay may be older than the shown tail: a forced refresh reloads the
# window, a normal one still treats "nothing newer" as a no-op.
jid2 = "replay@conf.example"
for i in range(5):
    history.store_message(jid2, "incoming", f"m{i}", sender="A",
                          timestamp=f"2026-10-2{i + 1}T10:00:00.000000Z")
rows = history.load_history(jid2, 10)
w = chat_widget_mod.ChatWidget(
    jid2, "Room", chat_themes.ChatThemeFactory(), is_muc=True)
w._view = _StubView()
w.set_history(rows[3:], 10, True)
w._window_size = 10
w.show()
app.processEvents()
history.store_message(jid2, "incoming", "replay old", sender="B",
                      timestamp="2026-10-22T09:00:00.000000Z")
check("an older-only stored row does not trigger a normal refresh",
      asyncio.run(w.refresh_tail_if_newer()) is False)
check("a forced refresh reloads the window",
      asyncio.run(w.refresh_tail_if_newer(force=True)) is True)
check("the older replay row is merged",
      any(entry["body"] == "replay old" for entry in w._history))
w.detach()

# The read anchor may point at a legacy row without ids: scroll by timestamp,
# and never leave the reloaded page at its top.
w2 = chat_widget_mod.ChatWidget(
    "anchor@conf.example", "Room", chat_themes.ChatThemeFactory(), is_muc=True)
w2._view = _StubView()
w2._history = [{"sender": "A", "body": "old", "direction": "incoming",
                "timestamp": "2026-10-22T10:00:00.000000Z",
                "message_id": "", "origin_id": "", "archive_id": ""}]
w2._messages = []
w2._restore_anchor = {"ref": "", "ts": "2026-10-22T10:00:00.000000Z"}
w2._restore_from_anchor()
check("an id-less anchor scrolls by its timestamp",
      w2._view.time_scrolls == ["2026-10-22T10:00:00.000000Z"])
w2._restore_anchor = {"ref": "", "ts": "2020-01-01T00:00:00.000000Z"}
w2._restore_from_anchor()
check("an unreachable anchor falls back to the bottom",
      w2._view.bottom_scrolls == 1)
w2.detach()

# Local paging is independent of the server archive state.
calls = []
w3 = chat_widget_mod.ChatWidget(
    "paging@conf.example", "Room", chat_themes.ChatThemeFactory(), is_muc=True)
w3._view = _StubView()
_real_older = w3._load_older_batch
w3._load_older_batch = lambda: calls.append("local")
w3._on_near_top()
check("a near-top before the first window does not page",
      calls == [])
w3._window_size = 10
w3.set_history([], 10, False)
w3._on_near_top()
check("after the first window a near-top pages locally",
      calls == ["local"])

calls.clear()
w3._server_exhausted = True
w3._on_near_top()
check("an exhausted server archive does not block local paging",
      calls == ["local"])

calls.clear()
w3._load_older_batch = _real_older
server = []
w3.load_more_from_server = lambda: server.append("server")
w3._db_exhausted = True
w3._server_archive_available = False
w3._on_near_top()
check("a room without an archive does not ask the server",
      server == [] and calls == [])

w3._server_archive_available = True
w3._on_near_top()
check("an available archive is asked when the local window ends",
      server == ["server"] and calls == [])
w3.detach()

# The archived replay and the MAM fetch both schedule the refresh.
from stanza_im.ui.main_window import MainWindow  # noqa: E402

check("an archived history replay schedules a tail refresh",
      "schedule_tail_refresh(" in inspect.getsource(
          MainWindow._on_groupchat_message))
check("a MAM backfill schedules a tail refresh",
      "schedule_tail_refresh(" in inspect.getsource(
          MainWindow._fetch_server_history))

cw.detach()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All history tail-refresh tests passed.")
