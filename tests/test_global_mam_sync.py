"""Offscreen tests for the account-wide MAM catch-up.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_global_mam_sync.py
"""
import asyncio
import os
import sys
import tempfile
import unittest.mock
from types import SimpleNamespace
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_global_mam_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp

from stanza_im.core import history, profiles, sync_state
from stanza_im.core.client import JabberClient
from stanza_im.ui.main_window import MainWindow

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def make_result(frm, to, body, mid, archive_id, ts, mtype="chat"):
    msg = slixmpp.Message()
    msg["from"] = frm
    msg["to"] = to
    msg["type"] = mtype
    msg["body"] = body
    msg["id"] = mid
    archived = ET.SubElement(msg.xml, "{urn:xmpp:mam:tmp}archived")
    archived.set("id", archive_id)
    archived.set("by", "me@x")
    delay = ET.SubElement(msg.xml, "{urn:xmpp:delay}delay")
    delay.set("stamp", ts)
    return msg


class _PagedMam:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    async def __call__(self, *, jid=None, with_jid=None, start=None,
                       rsm=None, **_kw):
        self.calls.append({
            "jid": jid, "with_jid": with_jid, "start": start,
            "rsm": dict(rsm or {}),
        })
        page = self.pages.pop(0)
        return {
            "type": "result",
            "mam": {"results": page["results"]},
            "mam_fin": page["fin"],
        }


profiles.set_active("me@x")
sync_state.clear()
sync_state.save_cursor(archive_id="arc-0", ts="2026-11-01T00:00:00Z",
                       migrated=True, account="me@x")


# 1. Cursor storage -----------------------------------------------------------
check("cursor round-trips",
      sync_state.load_cursor("me@x")["archive_id"] == "arc-0")
check("cursor file is 0600",
      (os.stat(sync_state.path()).st_mode & 0o777) == 0o600)
sync_state.save_cursor(archive_id="arc-a", ts="2026-11-01T10:00:00Z",
                       migrated=True, account="me@x")
check("new cursor replaces the old one",
      sync_state.load_cursor("me@x")["ts"] == "2026-11-01T10:00:00Z")
check("cursor belongs to its account",
      sync_state.load_cursor("other@x") == {})


# 2. Conversation routing -----------------------------------------------------
c = JabberClient("me@x/res", "pw")
check("incoming 1:1 routes to its bare JID",
      c._global_mam_target(make_result(
          "alice@x/phone", "me@x/res", "hi", "m1", "arc-1",
          "2026-11-01T10:00:01Z")) == ("alice@x", False))
check("outgoing 1:1 routes to the recipient",
      c._global_mam_target(make_result(
          "me@x/res", "bob@x", "yo", "m2", "arc-2",
          "2026-11-01T10:00:02Z")) == ("bob@x", False))
check("groupchat routes to the room",
      c._global_mam_target(make_result(
          "room@conf/nick", "me@x/res", "room msg", "m3", "arc-3",
          "2026-11-01T10:00:03Z", mtype="groupchat")) ==
      ("room@conf", True))
check("our own groupchat copy is not imported",
      c._global_mam_target(make_result(
          "me@x/res", "room@conf", "mine", "m4", "arc-4",
          "2026-11-01T10:00:04Z", mtype="groupchat")) == ("", False))
c._known_rooms.add("room@conf")
check("a room private message stays on the join/open path",
      c._global_mam_target(make_result(
          "room@conf/nick", "me@x/res", "pm", "m5", "arc-5",
          "2026-11-01T10:00:05Z")) == ("", False))


# 3. One page stores every affected chat and advances the cursor -------------
async def _run_sync():
    c2 = JabberClient("me@x/res", "pw")
    page = [
        make_result("alice@x/phone", "me@x/res", "alice one", "a1", "arc-1",
                    "2026-11-01T10:00:01Z"),
        make_result("me@x/res", "bob@x", "bob reply", "b1", "arc-2",
                    "2026-11-01T10:00:02Z"),
        make_result("quiet@x/phone", "me@x/res", "not stored", "q1", "arc-3",
                    "2026-11-01T10:00:03Z"),
    ]
    # The page has two stored chats; the third result is intentionally
    # filtered from the local set by using an unknown room group below.
    fake = _PagedMam([{"results": page,
                       "fin": {"complete": "true", "rsm": {"last": "arc-2"}}}])
    mam = c2.xmpp.plugin["xep_0313"]
    with unittest.mock.patch.object(mam, "retrieve", fake):
        affected = await c2.sync_global_mam()
    return c2, fake, affected


c2, fake, affected = asyncio.run(_run_sync())
alice = history.load_history("alice@x", limit=10)
bob = history.load_history("bob@x", limit=10)
check("a global page stores incoming rows", [r["body"] for r in alice] ==
      ["alice one"])
check("a global page stores outgoing rows", [r["body"] for r in bob] ==
      ["bob reply"])
check("the cursor uses the page's fin cursor",
      sync_state.load_cursor("me@x")["archive_id"] == "arc-2")
check("the global query is not filtered with_jid",
      fake.calls[0]["with_jid"] is None)
check("an affected chat set is returned",
      {"alice@x", "bob@x"}.issubset(affected))


# 4. Partial read: a remote displayed point in the middle keeps the tail -----
from stanza_im.core import unread_state

history.clear_all()


def _store(chat, body, ts, sid):
    history.store_message(chat, "incoming", body, timestamp=ts,
                          sender=chat, archive_id=sid, stanza_id=sid,
                          skip_existing=True)


_store("alice@x", "one", "2026-11-01T10:00:01Z", "a1")
_store("alice@x", "two", "2026-11-01T10:00:02Z", "a2")
_store("alice@x", "three", "2026-11-01T10:00:03Z", "a3")


class _UnreadProbe:
    def __init__(self):
        self._unread_chats = {
            "alice@x": dict(unread_state.blank(), unread=3,
                            read_ts="2026-11-01T10:00:00Z",
                            read_sid="a0"),
        }
        self._mds_remote = {"alice@x": "a2"}
        self._muc_self_nicks = {}
        self.unread_changed = SimpleNamespace(emit=lambda: None)
        self.saved = 0
        self._refreshed = []

    def _is_conference_jid(self, _key):
        return False

    async def _mds_point_sid(self, _key, _entry, _ts):
        return ""

    def _publish_mds_point(self, _key, _sid):
        pass

    def _refresh_unread_badge(self, key):
        self._refreshed.append(key)

    def _push_unread_to_chat(self, _key):
        pass

    def _recount_unread(self):
        pass

    def _schedule_unread_save(self):
        self.saved += 1


probe = _UnreadProbe()
asyncio.run(MainWindow._recompute_global_unread(
    probe, {"alice@x"}, "2026-11-01T10:00:00Z"))
entry = probe._unread_chats["alice@x"]
check("a remote point in the middle leaves the tail unread",
      entry["unread"] == 1)
check("the remote point becomes the read anchor",
      entry["read_ts"] == "2026-11-01T10:00:02Z"
      and entry["read_sid"] == "a2")


# 5. An unresolved remote id never clears an existing block ------------------
probe2 = _UnreadProbe()
probe2._mds_remote = {"alice@x": "missing-id"}
asyncio.run(MainWindow._recompute_global_unread(
    probe2, {"alice@x"}, "2026-11-01T10:00:00Z"))
check("an unresolved shared point keeps the unread block",
      probe2._unread_chats["alice@x"]["unread"] == 3)


# 6. Migration runs the legacy pass once and then uses the global cursor -----
class _FakeSyncClient:
    def __init__(self):
        self.jid_str = "me@x"
        self._global_mam_unsupported = False
        self._global_sync_start_ts = "2026-11-01T10:00:00Z"
        self.sync_calls = 0

    async def newest_global_mam_cursor(self):
        return "arc-new", "2026-11-01T10:00:00Z"

    async def sync_global_mam(self):
        self.sync_calls += 1
        return {"alice@x"}


class _StartupProbe:
    def __init__(self, client):
        self._client = client
        self.legacy_calls = 0
        self.recomputed = []

    def _has_local_state(self):
        return True

    async def _legacy_startup_reconcile(self):
        self.legacy_calls += 1

    async def _recompute_global_unread(self, keys, start_ts=""):
        self.recomputed.append((set(keys), start_ts))


sync_state.clear()
fake_client = _FakeSyncClient()
startup = _StartupProbe(fake_client)
asyncio.run(MainWindow._run_startup_sync(startup))
check("migration runs the legacy pass once", startup.legacy_calls == 1)
check("migration then runs the global pass", fake_client.sync_calls == 1)
check("migration saves a migrated cursor",
      sync_state.load_cursor("me@x")["migrated"] is True)
check("the affected chats reach the unread recompute",
      startup.recomputed == [({"alice@x"}, "2026-11-01T10:00:00Z")])
asyncio.run(MainWindow._run_startup_sync(startup))
check("a migrated profile does not repeat the legacy pass",
      startup.legacy_calls == 1 and fake_client.sync_calls == 2)


# 7. A quiet background MDS state does not start a per-chat clamp -----------
class _MdsProbe:
    def __init__(self, foreground=False):
        self._mds_remote = {}
        self.foreground = foreground
        self.anchors = []
        self.started = []

    def _resolve_mds_key(self, key):
        return key

    def _mds_foreground(self, _key):
        return self.foreground

    def _set_mds_anchor(self, key, sid):
        self.anchors.append((key, sid))

    async def _run_mds_clamp(self, _key, _sid, *, force=False):
        return None

    def _start_task(self, coro):
        self.started.append(coro)
        coro.close()


bg = _MdsProbe(False)
MainWindow._on_mds_displayed(bg, "quiet@x", "sid-1")
check("a quiet MDS state is kept without a clamp",
      bg._mds_remote == {"quiet@x": "sid-1"}
      and bg.anchors == [] and not bg.started)
fg = _MdsProbe(True)
MainWindow._on_mds_displayed(fg, "active@x", "sid-2")
check("a foreground MDS state still starts a clamp",
      fg.anchors == [] and len(fg.started) == 1)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All global-MAM tests passed.")
