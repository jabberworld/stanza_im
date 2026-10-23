"""Auto-join runs on a fresh bookmark list before the presence flood.

A stale cached list could join a conference removed on another client, so the
session first fetches the bookmarks (one attempt) and joins, then sends the
initial presence; a failed fetch is retried in the background without holding
up the session.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_autojoin_order.py
"""
import asyncio
import inspect
import os
import sys
import tempfile
from types import SimpleNamespace

_SCRATCH = tempfile.mkdtemp(prefix="stanza_autojoin_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import JabberClient

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


def _client():
    client = JabberClient.__new__(JabberClient)
    client.auto_join_conferences = True
    client.jid_str = "me@example.com"
    client.autojoin_rooms = set()
    client.groupchats = {}
    client._bookmarks_snapshot = None
    client.joined = []
    client.retries = []

    def join_muc(room, nick, password="", save_bookmark=False):
        client.joined.append((room, nick, password))

    client.join_muc = join_muc
    client._schedule_bookmark_retry = lambda: client.retries.append(1)
    return client


BOOKMARKS = [
    {"jid": "room@conf.example", "autojoin": True, "nick": "me",
     "password": "pw"},
    {"jid": "quiet@conf.example", "autojoin": False, "nick": "",
     "password": ""},
]


async def _return(value):
    return value


# 1. a fresh list joins only the auto-join rooms ---------------------------
client = _client()
client.list_bookmarks = lambda: _return(BOOKMARKS)
asyncio.run(client._autojoin_bookmarks())
check("an auto-join room is joined from the fresh list",
      client.joined == [("room@conf.example", "me", "pw")])
check("a non-autojoin bookmark is left alone",
      "quiet@conf.example" not in client.autojoin_rooms)
check("the fetched list is handed to the UI",
      client.bookmarks_snapshot() == BOOKMARKS
      and client.bookmarks_snapshot() is None)
check("no retry is scheduled for a successful fetch", client.retries == [])

# 2. a successful empty list is not an error -------------------------------
empty = _client()
empty.list_bookmarks = lambda: _return([])
asyncio.run(empty._autojoin_bookmarks())
check("an empty bookmark list schedules no retry",
      empty.retries == [] and empty.joined == [])

# 3. a failed fetch is retried in the background ---------------------------
failed = _client()
failed.list_bookmarks = lambda: _return(None)
asyncio.run(failed._autojoin_bookmarks())
check("a failed fetch schedules a background retry",
      failed.retries == [1] and failed.joined == [])

# 4. an already joined room is not joined twice ---------------------------
joined_client = _client()
joined_client.groupchats["room@conf.example"] = SimpleNamespace(joined=True)
joined_client.list_bookmarks = lambda: _return(BOOKMARKS)
asyncio.run(joined_client._autojoin_bookmarks())
check("an already joined room is skipped", joined_client.joined == [])

# 5. the session order: auto-join (fresh) before the initial presence ------
source = inspect.getsource(JabberClient._on_session_start)
check("the bookmarks are fetched/joined before the presence",
      source.index("await self._autojoin_bookmarks()")
      < source.index("self.send_presence()"))
check("the PEP subscriptions are background work",
      "loop.create_task(self._subscribe_pep_contacts())" in source)
check("the auto-join is no longer a late task",
      "create_task(self._autojoin_bookmarks())" not in source)

from stanza_im.ui.main_window import MainWindow  # noqa: E402

load_src = inspect.getsource(MainWindow._load_bookmarks)
check("the UI reuses the session's bookmark list",
      "bookmarks_snapshot()" in load_src)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All autojoin-order tests passed.")
