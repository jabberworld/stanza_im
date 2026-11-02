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
from types import SimpleNamespace

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
      set(unread_state.blank()) == {"unread", "mentions", "important",
                                    "read_sid", "read_ts", "read_ref",
                                    "seen_sid", "seen_ts", "seen_ref",
                                    "seen_at"})

with open(unread_state.path(), "w", encoding="utf-8") as fh:
    fh.write('{"x@y": {"count": 7, "displayed": "sid-v1"}}')
converted = unread_state.load_chats()
check("v1 payload converts to a v2 record",
      converted["x@y"] == {"unread": 7, "mentions": 0, "important": 0,
                           "read_sid": "sid-v1", "read_ts": "", "read_ref": "",
                           "seen_sid": "", "seen_ts": "", "seen_ref": "",
                           "seen_at": 0.0})

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
from stanza_im.core import history

history.store_message(
    "carol@example.com", "incoming", "new", "2026-10-02T12:00:00Z",
    sender="carol", archive_id="carol-sid-new", origin_id="carol-sid-new",
    message_id="carol-sid-new")
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
win._unread_chats["dave@example.com"]["read_ts"] = ""
win._unread_chats["dave@example.com"]["seen_ts"] = ""
win._unread_chats["dave@example.com"]["read_sid"] = ""
win._unread_chats["dave@example.com"]["seen_sid"] = ""
win._recount_unread()
_remote("dave@example.com", "arc-1")
check("a device behind us clears only the read prefix",
      win._unread_counts.get("dave@example.com") == 1
      and win._unread_chats["dave@example.com"]["read_sid"] == "arc-1"
      and win._unread_chats["dave@example.com"]["read_ts"]
      == "2026-10-02T10:00:00Z")

win._unread_chats["erin@example.com"] = unread_state.blank()
win._unread_chats["erin@example.com"]["unread"] = 3
win._recount_unread()
_remote("erin@example.com", "unknown-remote-id")
check("an unresolved remote id never clears unread",
      win._unread_counts.get("erin@example.com") == 3)

# 5b. MDS+MAM variant A: rebuild unread after a displayed point -------------
history.store_message("room@example", "incoming", "old", "2026-10-02T11:00:00Z",
                      sender="bob", archive_id="arc-2", origin_id="arc-2",
                      message_id="arc-2")
history.store_message("room@example", "incoming", "new", "2026-10-02T12:00:00Z",
                      sender="bob", archive_id="arc-3", origin_id="arc-3",
                      message_id="arc-3")
recon = MainWindow.__new__(MainWindow)
recon._client = SimpleNamespace(_mds_local={"room@example": "arc-2"})
recon._unread_chats = {}
recon._mam_unsupported = {"room@example"}  # local replay is enough here
recon._muc_joined = {"room@example"}
recon._known_conferences = set()
recon._muc_self_nicks = {}
recon._chat_window = None
recon._mds_reconciling = set()
recon._mds_reconciled = set()
recon._recount_unread = lambda: None
recon._refresh_unread_badge = lambda _jid: None
recon._push_unread_to_chat = lambda _jid: None
recon._schedule_unread_save = lambda: None
asyncio.get_event_loop().run_until_complete(
    recon._reconcile_mds_unread("room@example"))
check("variant A rebuilds unread from the displayed point",
      recon._unread_chats["room@example"]["unread"] == 1
      and recon._unread_chats["room@example"]["read_sid"] == "arc-2"
      and recon._unread_chats["room@example"]["read_ts"]
      == "2026-10-02T11:00:00Z")

# A local read point equal to the MDS point must not suppress the rebuild;
# another device may have accumulated messages after the same point.
_stale_ts = "2026-10-02T11:00:00Z"
for _sid, _ts in (("stale-1", _stale_ts),
                  ("stale-2", "2026-10-02T12:00:00Z"),
                  ("stale-3", "2026-10-02T13:00:00Z"),
                  ("stale-4", "2026-10-02T14:00:00Z")):
    history.store_message("stale@example", "incoming", f"m {_sid}", _ts,
                          sender="bob", archive_id=_sid, origin_id=_sid,
                          message_id=_sid)
recon2 = MainWindow.__new__(MainWindow)
recon2._client = SimpleNamespace(
    _mds_local={"stale@example": "stale-1"})
recon2._unread_chats = {
    "stale@example": {**unread_state.blank(), "unread": 2,
                      "read_sid": "stale-1", "read_ts": _stale_ts,
                      "seen_ts": _stale_ts}}
recon2._mam_unsupported = {"stale@example"}
recon2._muc_joined = {"stale@example"}
recon2._known_conferences = set()
recon2._muc_self_nicks = {}
recon2._chat_window = None
recon2._mds_reconciling = set()
recon2._mds_reconciled = set()
recon2._recount_unread = lambda: None
recon2._refresh_unread_badge = lambda _jid: None
recon2._push_unread_to_chat = lambda _jid: None
recon2._schedule_unread_save = lambda: None
asyncio.get_event_loop().run_until_complete(
    recon2._reconcile_mds_unread("stale@example"))
check("an equal read point still rebuilds a stale unread block",
      recon2._unread_chats["stale@example"]["unread"] == 3
      and recon2._unread_chats["stale@example"]["read_sid"] == "stale-1")

# A local seen point newer than the shared displayed point wins: a throttled
# publish may have been lost, so the shared node is stale (walkbook 40 vs
# rbook 90).  The local point is republished instead of being rolled back.
_force_ts = "2026-10-02T11:00:00Z"
for _sid, _ts in (("force-1", _force_ts),
                  ("force-2", "2026-10-02T12:00:00Z"),
                  ("force-3", "2026-10-02T13:00:00Z"),
                  ("force-4", "2026-10-02T14:00:00Z")):
    history.store_message("forced@example", "incoming", f"m {_sid}", _ts,
                          sender="bob", archive_id=_sid, origin_id=_sid,
                          message_id=_sid)


def _forced_recon(published):
    r = MainWindow.__new__(MainWindow)
    r._client = SimpleNamespace(
        _mds_local={"forced@example": "force-1"},
        mds_mark_displayed=lambda jid, sid: published.append((jid, sid)))
    r._unread_chats = {
        "forced@example": {**unread_state.blank(), "unread": 1,
                           "read_sid": "force-1", "read_ts": _force_ts,
                           "seen_sid": "force-3",
                           "seen_ts": "2026-10-02T13:00:00Z"}}
    r._mam_unsupported = {"forced@example"}
    r._muc_joined = {"forced@example"}
    r._known_conferences = set()
    r._muc_self_nicks = {}
    r._chat_window = None
    r._mds_reconciling = set()
    r._mds_reconciled = set()
    r._recount_unread = lambda: None
    r._refresh_unread_badge = lambda _jid: None
    r._push_unread_to_chat = lambda _jid: None
    r._schedule_unread_save = lambda: None
    return r


_skip_published = []
_force_skip = _forced_recon(_skip_published)
asyncio.get_event_loop().run_until_complete(
    _force_skip._reconcile_mds_unread("forced@example"))
check("a newer local seen point still skips the non-forced rebuild",
      _force_skip._unread_chats["forced@example"]["unread"] == 1)
check("a skipped rebuild republishes the newer local point",
      _skip_published == [("forced@example", "force-3")])

_go_published = []
_force_go = _forced_recon(_go_published)
asyncio.get_event_loop().run_until_complete(
    _force_go._reconcile_mds_unread("forced@example", force=True))
check("a forced startup rebuild prefers the newer local seen point",
      _force_go._unread_chats["forced@example"]["unread"] == 1
      and _force_go._unread_chats["forced@example"]["read_sid"] == "force-3")
check("the forced rebuild repairs the stale shared point",
      _go_published == [("forced@example", "force-3")])

# A forced startup pass reconstructs the gap for a chat with no local unread
# block: the device was offline while another client displayed new messages
# (rbook showed only the 5 live messages, walkbook/monocles showed 30).
for _sid, _ts in (("gap-1", "2026-10-02T11:00:00Z"),
                  ("gap-2", "2026-10-02T12:00:00Z"),
                  ("gap-3", "2026-10-02T13:00:00Z")):
    history.store_message("gap@example", "incoming", f"m {_sid}", _ts,
                          sender="bob", archive_id=_sid, origin_id=_sid,
                          message_id=_sid)


def _gap_recon(key, shared_sid, read_ts, unread=0):
    r = MainWindow.__new__(MainWindow)
    r._client = SimpleNamespace(_mds_local={key: shared_sid})
    r._unread_chats = {key: {
        **unread_state.blank(), "unread": unread, "read_sid": "old",
        "read_ts": read_ts}}
    r._mam_unsupported = {key}
    r._muc_joined = set()
    r._known_conferences = set()
    r._muc_self_nicks = {}
    r._chat_window = None
    r._mds_reconciling = set()
    r._mds_reconciled = set()
    r._recount_unread = lambda: None
    r._refresh_unread_badge = lambda _jid: None
    r._push_unread_to_chat = lambda _jid: None
    r._schedule_unread_save = lambda: None
    return r


_gap = _gap_recon("gap@example", "gap-1", "2026-10-02T10:00:00Z")
asyncio.get_event_loop().run_until_complete(
    _gap._reconcile_mds_unread("gap@example", force=True))
check("a forced startup rebuild covers an offline gap with no local block",
      _gap._unread_chats["gap@example"]["unread"] == 2
      and _gap._unread_chats["gap@example"]["read_sid"] == "gap-1")

_gap_skip = _gap_recon("gap@example", "gap-1", "2026-10-02T14:00:00Z")
asyncio.get_event_loop().run_until_complete(
    _gap_skip._reconcile_mds_unread("gap@example", force=True))
check("a forced rebuild skips when the shared point is not newer",
      _gap_skip._unread_chats["gap@example"]["unread"] == 0)

# An EQUAL point still needs a rebuild: another device displayed up to the
# same message while new messages after it arrived only on the server (rbook
# counted just the 5 live messages while walkbook had 24).
_gap_equal = _gap_recon("gap@example", "gap-1", "2026-10-02T11:00:00Z")
asyncio.get_event_loop().run_until_complete(
    _gap_equal._reconcile_mds_unread("gap@example", force=True))
check("an equal shared point still rebuilds the gap",
      _gap_equal._unread_chats["gap@example"]["unread"] == 2)

# The shared id is not in the local archive (the device never stored it): the
# gap is fetched, but unread is counted from the local read point, never from
# the raw MAM page size (an old/pruned id must not resurrect read messages).
for _sid, _ts in (("prune-2", "2026-10-02T12:00:00Z"),
                  ("prune-3", "2026-10-02T13:00:00Z")):
    history.store_message("prune@example", "incoming", f"m {_sid}", _ts,
                          sender="bob", archive_id=_sid, origin_id=_sid,
                          message_id=_sid)
_prune = _gap_recon("prune@example", "missing-id",
                    "2026-10-02T12:00:00Z")
asyncio.get_event_loop().run_until_complete(
    _prune._reconcile_mds_unread("prune@example", force=True))
check("an unresolved shared id counts from the local read point",
      _prune._unread_chats["prune@example"]["unread"] == 1)

# An old unjoined room (bimroom) is recognised as a conference from its
# domain, is not rebuilt as a 1:1, and its restored unread is cleared.
_conf_win = MainWindow.__new__(MainWindow)
_conf_win._conference_roster = set()
_conf_win._muc_self_nicks = {}
_conf_win._known_conferences = set()
_conf_win._bookmarks = {}
_conf_win._unread_chats = {}
_conf_win._config = None
check("a conference-service domain is recognised as a room",
      MainWindow._is_conference_jid(
          _conf_win, "bimroom@conference.jabberworld.info"))
check("a 1:1 contact is not a room",
      not MainWindow._is_conference_jid(_conf_win, "rain@jabberworld.info"))
_conf_win._bookmarks = {"saved@conf.example": {}}
check("a bookmarked room is recognised even with a plain domain",
      MainWindow._is_conference_jid(_conf_win, "saved@conf.example"))
check("a MUC private message is not a room",
      not MainWindow._is_conference_jid(
          _conf_win, "bimroom@conference.jabberworld.info/rain"))

_conf_recon = MainWindow.__new__(MainWindow)
_conf_recon._client = SimpleNamespace(
    _mds_local={"bimroom@conference.jabberworld.info": "old-sid"})
_conf_recon._unread_chats = {}
_conf_recon._muc_joined = set()
_conf_recon._known_conferences = set()
_conf_recon._muc_self_nicks = {}
_conf_recon._bookmarks = {}
_conf_recon._conference_roster = set()
_conf_recon._config = None
_conf_recon._chat_window = None
_conf_recon._mds_reconciling = set()
_conf_recon._mds_reconciled = set()
asyncio.get_event_loop().run_until_complete(
    _conf_recon._reconcile_mds_unread(
        "bimroom@conference.jabberworld.info", force=True))
check("an unjoined room is not rebuilt as a 1:1",
      _conf_recon._unread_chats == {})

_clean = MainWindow.__new__(MainWindow)
_clean._unread_chats = {"bimroom@conference.jabberworld.info": {
    "unread": 2, "mentions": 0, "important": 0}}
_clean._bookmarks_loaded = True
_clean._bookmarks = {}
_clean._known_conferences = set()
_clean._muc_self_nicks = {}
_clean._muc_joined = set()
_clean._conference_roster = set()
_clean._config = None
_clean._recount_unread = lambda: None
_clean._refresh_unread_badge = lambda _jid: None
_clean._schedule_unread_save = lambda: None
changed = MainWindow._clear_inactive_conference_unread(_clean)
check("an unjoined room's restored unread is cleared",
      changed == ["bimroom@conference.jabberworld.info"]
      and _clean._unread_chats[
          "bimroom@conference.jabberworld.info"]["unread"] == 0)

win._pm_targets["room@conf.example/dave"] = ("room@conf.example", "dave")
check("a private message resolves to its own conversation",
      win._resolve_mds_key("room@conf.example/dave")
      == "room@conf.example/dave")
check("a bare room address stays the conference",
      win._resolve_mds_key("room@conf.example") == "room@conf.example")
check("a one-to-one chat resolves to its bare jid",
      win._resolve_mds_key("bob@example.com/stanza") == "bob@example.com")

# 5c. the read point wins over an older partial-progress point ----------------
_pravda = MainWindow.__new__(MainWindow)
_pravda._unread_chats = {"pravda@example": {
    **unread_state.blank(), "unread": 64,
    "read_ref": "read-ref", "read_ts": "2026-11-01T14:12:48Z",
    "read_sid": "read-sid",
    "seen_ref": "seen-ref", "seen_ts": "2026-11-01T03:33:34Z",
    "seen_sid": "seen-sid"}}
_pravda_anchor = MainWindow._restore_anchor_for(_pravda, "pravda@example")
check("an older seen point never resumes before the read point",
      _pravda_anchor.get("ts") == "2026-11-01T14:12:48Z"
      and _pravda_anchor.get("sid") == "read-sid")
_pravda._unread_chats["pravda@example"]["seen_ts"] = \
    "2026-11-01T15:00:00Z"
_pravda_anchor2 = MainWindow._restore_anchor_for(_pravda, "pravda@example")
check("a newer partial-progress point still wins",
      _pravda_anchor2.get("ts") == "2026-11-01T15:00:00Z")

# 5d. an origin-only MDS id is not a server displayed point -------------------
_kkm = "kkm@example"
history.store_message(
    _kkm, "outgoing", "encrypted", "2026-10-19T13:38:00Z", sender="Me",
    archive_id="", stanza_id="", origin_id="origin-kkm",
    message_id="origin-kkm")
history.store_message(
    _kkm, "incoming", "after", "2026-10-20T10:00:00Z", sender=_kkm,
    archive_id="arc-after", stanza_id="arc-after", origin_id="arc-after",
    message_id="arc-after")
check("timestamp_for_server_ref ignores a local origin id",
      history.timestamp_for_server_ref(_kkm, "origin-kkm") == "")
check("timestamp_for_server_ref accepts a server id",
      history.timestamp_for_server_ref(_kkm, "arc-after")
      .startswith("2026-10-20T10:00:00"))
_kkm_recon = MainWindow.__new__(MainWindow)
_kkm_recon._client = SimpleNamespace(
    _mds_local={_kkm: "origin-kkm"})
_kkm_recon._unread_chats = {_kkm: {
    **unread_state.blank(), "read_ref": "origin-kkm",
    "read_sid": "origin-kkm", "read_ts": "2026-10-19T13:38:00Z",
    "seen_ref": "origin-kkm", "seen_sid": "origin-kkm",
    "seen_ts": "2026-10-19T13:38:00Z"}}
_kkm_recon._mam_unsupported = {_kkm}
_kkm_recon._muc_joined = set()
_kkm_recon._known_conferences = set()
_kkm_recon._muc_self_nicks = {}
_kkm_recon._conference_roster = set()
_kkm_recon._bookmarks = {}
_kkm_recon._config = None
_kkm_recon._chat_window = None
_kkm_recon._mds_reconciling = set()
_kkm_recon._mds_reconciled = set()
_kkm_recon._history_gap_checked = {}
_kkm_recon._recount_unread = lambda: None
_kkm_recon._refresh_unread_badge = lambda _jid: None
_kkm_recon._push_unread_to_chat = lambda _jid: None
_kkm_recon._schedule_unread_save = lambda: None
asyncio.get_event_loop().run_until_complete(
    _kkm_recon._reconcile_mds_unread(_kkm, force=True))
check("an origin-only shared id never creates unread",
      not (_kkm_recon._unread_chats.get(_kkm) or {}).get("unread"))

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
check("an unresolved shared id is not a newer local point",
      "local_ts and remote_ts and local_ts > remote_ts" in _mw_src)
check("the forced rebuild covers a chat with no local unread block",
      "shared_ahead = (not shared_ts or not local_ts" in _mw_src)
check("an unresolved shared id counts from the local point",
      "anchor_ts = ts or local_ts" in _mw_src)
check("an equal displayed point still triggers the forced rebuild",
      "or shared_ts >= local_ts" in _mw_src)
check("unjoined rooms are never rebuilt as 1:1",
      "self._is_conference_jid(key) and key not in self._muc_joined"
      in _mw_src)
check("invisible non-conference keys do not notify",
      "if roster_jids and jid not in roster_jids" in _mw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All unread-state tests passed.")
