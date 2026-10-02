"""Offscreen tests for unread-counter persistence across restarts.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_unread_state.py
"""
import asyncio
import os
import stat
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_unread_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core import unread_state
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. unread_state round-trip --------------------------------------------------
unread_state.save({"a@x": 3, "b@x": 0, "": 5, "c@x": "bad"})
check("round-trip keeps positive counts only",
      unread_state.load() == {"a@x": 3})
check("state file is 0600",
      stat.S_IMODE(os.stat(unread_state.path()).st_mode) == 0o600)

unread_state.save({"a@x": 3}, {"a@x": "sid-1", "b@x": "ignored"})
counts, displayed = unread_state.load_state()
check("displayed sid round-trips",
      counts == {"a@x": 3} and displayed == {"a@x": "sid-1"})

with open(unread_state.path(), "w", encoding="utf-8") as fh:
    fh.write('{"x@y": 5}')
counts, displayed = unread_state.load_state()
check("legacy int format still loads",
      counts == {"x@y": 5} and displayed == {})

# 1b. v2 payload: unread + mentions + read anchor -----------------------------
import json

unread_state.save_chats({
    "bob@example.com": {"unread": 4, "read_sid": "sid-1",
                        "read_ts": "2026-10-02T10:00:00", "read_ref": "m-1"},
    "room@conf.example": {"unread": 234, "mentions": 2},
    "old@x": {"unread": 0, "read_sid": "sid-old"},
    "empty@x": {},
    "": {"unread": 9},
    "junk@x": {"unread": "bad", "mentions": None, "read_sid": 5},
}, account="me@example.com")
chats = unread_state.load_chats("me@example.com")
check("v2 keeps unread and mention counters",
      chats["room@conf.example"]["unread"] == 234
      and chats["room@conf.example"]["mentions"] == 2)
check("v2 keeps the read anchor",
      chats["bob@example.com"]["read_ts"] == "2026-10-02T10:00:00"
      and chats["bob@example.com"]["read_ref"] == "m-1"
      and chats["bob@example.com"]["read_sid"] == "sid-1")
check("v2 keeps a read conversation's displayed sid",
      "old@x" in chats and chats["old@x"]["unread"] == 0)
check("empty, nameless and junk records are dropped",
      "empty@x" not in chats and "" not in chats and "junk@x" not in chats)
with open(unread_state.path(), encoding="utf-8") as fh:
    raw = json.load(fh)
check("file uses the v2 chats section",
      isinstance(raw.get("chats"), dict) and raw.get("account") == "me@example.com")
check("legacy views are derived from v2",
      unread_state.load() == {"bob@example.com": 4, "room@conf.example": 234}
      and unread_state.load_state()[1] == {"bob@example.com": "sid-1",
                                           "old@x": "sid-old"})
check("records expose every field",
      set(unread_state.blank()) == {"unread", "mentions", "read_sid",
                                    "read_ts", "read_ref"})

with open(unread_state.path(), "w", encoding="utf-8") as fh:
    fh.write('{"x@y": {"count": 7, "displayed": "sid-v1"}}')
converted = unread_state.load_chats()
check("v1 payload converts to a v2 record",
      converted["x@y"] == {"unread": 7, "mentions": 0, "read_sid": "sid-v1",
                           "read_ts": "", "read_ref": ""})

# Account-bound state: another account's counters must be ignored.
unread_state.save({"me@here": 4}, account="me@here")
check("account is persisted", unread_state.load_account() == "me@here")
check("matching account loads",
      unread_state.load_state("me@here")[0] == {"me@here": 4})
check("foreign account is ignored",
      unread_state.load_state("other@there") == ({}, {}))
check("the account key does not leak into the counts",
      "account" not in unread_state.load())

# Seed a "previous session" state before the window starts.
unread_state.save({"bob@example.com": 2, "room@conf.example": 1},
                  {"bob@example.com": "sid-old"})

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 2. MainWindow restores counters --------------------------------------------
win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
check("restored total", win._unread_total == 3)
check("restored jids",
      win._unread_jids == {"bob@example.com", "room@conf.example"})
check("restored displayed sid",
      win._unread_displayed == {"bob@example.com": "sid-old"})
check("tray does not blink before login", not win._tray._blink_active)

win._on_session_started()
check("tray blinks after login", win._tray._blink_active)
win._on_disconnected()
check("tray stops blinking on disconnect", not win._tray._blink_active)
win._on_session_started()

win._add_roster_item({"jid": "bob@example.com", "name": "Bob",
                      "groups": ["Friends"]})
bob = next(u for u in win._roster._users if u.jid == "bob@example.com")
check("badge restored on the roster row", bob.unread_count == 2)

# 3. bump / reset keep the store and roster in sync --------------------------
win._bump_unread("bob@example.com")
check("bump updates the counter and total",
      win._unread_counts["bob@example.com"] == 3 and win._unread_total == 4)
check("bump updates the roster badge", next(
    u for u in win._roster._users
    if u.jid == "bob@example.com").unread_count == 3)

win._reset_unread("bob@example.com")
check("reset clears the counter",
      "bob@example.com" not in win._unread_counts and win._unread_total == 1)

win._flush_unread()
check("flush persists the current state",
      unread_state.load() == {"room@conf.example": 1})

# 4. startup MDS catch-up must not wipe restored unread ----------------------
from stanza_im.core.client import JabberClient

win._unread_chats["carol@example.com"] = unread_state.blank()
win._unread_chats["carol@example.com"]["unread"] = 4
win._unread_chats["carol@example.com"]["read_sid"] = "carol-sid-old"
win._recount_unread()
c = JabberClient("me@example.com/res", "pw", message_displayed_sync=True)
c.set_displayed_state(win._unread_displayed)
c.on("mds_displayed", win._on_mds_displayed)
c._mds_apply_remote("carol@example.com", "carol-sid-old")
check("stale catch-up keeps restored unread",
      win._unread_counts.get("carol@example.com") == 4)


# the clamp reads the archive off-loop, so run the scheduled task here
_pending = []
_start_task = win._start_task
win._start_task = _pending.append
c._mds_apply_remote("carol@example.com", "carol-sid-new")
win._start_task = _start_task
asyncio.get_event_loop().run_until_complete(
    asyncio.gather(*_pending, return_exceptions=True))
check("newer remote state clears unread",
      "carol@example.com" not in win._unread_counts)
check("seed keeps blank sids out",
      c._mds_local.get("carol@example.com") == "carol-sid-new")

# 5. a remote displayed state is clamped against our own unread block -------
from stanza_im.core import history

for _sid, _ts in (("arc-1", "2026-10-02T10:00:00Z"),
                  ("arc-2", "2026-10-02T11:00:00Z")):
    history.store_message("dave@example.com", "incoming", f"m {_sid}", _ts,
                          sender="dave", archive_id=_sid, origin_id=_sid,
                          message_id=_sid)
check("the archive resolves a displayed id to its timestamp",
      history.timestamp_for_ref("dave@example.com", "arc-1")
      == "2026-10-02T10:00:00Z"
      and history.newest_timestamp("dave@example.com")
      == "2026-10-02T11:00:00Z")


def _remote(key, sid):
    """Feed a remote XEP-0490 state through the real handler and settle it."""
    pending = []
    start_task = win._start_task
    win._start_task = pending.append
    try:
        win._on_mds_displayed(key, sid)
    finally:
        win._start_task = start_task
    asyncio.get_event_loop().run_until_complete(
        asyncio.gather(*pending, return_exceptions=True))


win._unread_chats["dave@example.com"] = unread_state.blank()
win._unread_chats["dave@example.com"]["unread"] = 2
win._recount_unread()
_remote("dave@example.com", "arc-2")
check("a device that read everything clears our unread",
      win._unread_counts.get("dave@example.com", 0) == 0
      and win._unread_chats["dave@example.com"]["read_sid"] == "arc-2"
      and win._unread_chats["dave@example.com"]["read_ts"]
      == "2026-10-02T11:00:00Z")

win._unread_chats["dave@example.com"]["unread"] = 2
win._recount_unread()
_remote("dave@example.com", "arc-1")
check("a device behind us keeps the unread block",
      win._unread_counts.get("dave@example.com") == 2
      and win._unread_chats["dave@example.com"]["read_sid"] == "arc-2")

win._pm_targets["room@conf.example/dave"] = ("room@conf.example", "dave")
check("a private message resolves to its own conversation",
      win._resolve_mds_key("room@conf.example/dave")
      == "room@conf.example/dave")
check("a bare room address stays the conference",
      win._resolve_mds_key("room@conf.example") == "room@conf.example")
check("a one-to-one chat resolves to its bare jid",
      win._resolve_mds_key("bob@example.com/stanza") == "bob@example.com")

# 6. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
check("roster rows carry the stored counters",
      "unread_count=self._unread_counts.get(jid, 0)" in _mw_src)
check("quit flushes unread state", "self._flush_unread()" in _mw_src)
check("startup seeds the displayed state",
      "set_displayed_state(self._unread_displayed)" in _mw_src)
check("flush persists the displayed sids and the account",
      "unread_state.save_chats(self._unread_chats" in _mw_src
      and "account=self._config.jid" in _mw_src)
check("mention counters reach the roster rows",
      "unread_mentions=self._unread_mentions.get(jid, 0)" in _mw_src
      and "unread_mentions=self._unread_mentions.get(room, 0)" in _mw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All unread-state tests passed.")
