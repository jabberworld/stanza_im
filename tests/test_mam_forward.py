"""Offscreen tests for forward MAM gap sync and XEP-0490 cursor safety.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_mam_forward.py
"""
import asyncio
import os
import sys
import tempfile
import unittest.mock
from types import SimpleNamespace
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_mam_forward_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp

from stanza_im.core import history, unread_state
from stanza_im.core.client import JabberClient
from stanza_im.ui.main_window import MainWindow

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def make_result(frm, body, mid, archive_id, ts):
    msg = slixmpp.Message()
    msg["from"] = frm
    msg["to"] = "me@x/res"
    msg["type"] = "chat"
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


# 1. Pagination follows the RSM cursor until complete -------------------------
def _run_pagination():
    c = JabberClient("me@x/res", "pw")
    mam = c.xmpp.plugin["xep_0313"]
    page1 = [
        make_result("me@x", "Сообщение 111", "o-111", "arc-111",
                    "2026-11-01T10:54:35Z"),
        make_result("rain@jabberworld.info", "hello", "i-1", "arc-1",
                    "2026-11-01T10:54:36Z"),
    ]
    page2 = [
        make_result("me@x", "Сообщение 333", "o-333", "arc-333",
                    "2026-11-01T10:54:39Z"),
    ]
    fake = _PagedMam([
        {"results": page1,
         "fin": {"complete": "false", "rsm": {"last": "arc-1"}}},
        {"results": page2,
         "fin": {"complete": "true", "rsm": {"last": "arc-333"}}},
    ])
    with unittest.mock.patch.object(mam, "retrieve", fake):
        incoming = asyncio.run(c.fetch_history_mam_after(
            "rain@jabberworld.info",
            start_ts="2026-11-01T10:54:30.000000Z", limit=2))
    rows = history.load_history("rain@jabberworld.info", limit=20)
    return incoming, fake.calls, [row["body"] for row in rows]


incoming, calls, bodies = _run_pagination()
check("forward pagination reads the second page", len(calls) == 2)
check("the second page continues after the first page cursor",
      calls[1]["rsm"].get("after") == "arc-1")
check("forward pagination stores every page",
      "Сообщение 111" in bodies and "Сообщение 333" in bodies)
check("only unique incoming rows are counted", incoming == 1)
check("the page fin complete flag stops the walk",
      calls[1]["rsm"].get("after") == "arc-1")


# 1b. The real <fin/> element yields the completion flag and RSM cursor -------
_fin_iq = slixmpp.Iq()
_fin = ET.SubElement(_fin_iq.xml, "{urn:xmpp:mam:2}fin")
_fin.set("complete", "false")
_fin_set = ET.SubElement(_fin, "{http://jabber.org/protocol/rsm}set")
_fin_last = ET.SubElement(_fin_set, "{http://jabber.org/protocol/rsm}last")
_fin_last.text = "arc-fin"
check("the raw MAM fin state is parsed",
      JabberClient._mam_fin_state(_fin_iq) == (False, "arc-fin"))


# 2. An unresolved shared id never becomes an RSM ``after`` cursor ----------
async def _fake_forward(jid, start_ts=None, after_id="", limit=100,
                        is_muc=None, max_pages=20):
    _fake_forward.calls.append((jid, start_ts, after_id, limit, is_muc))
    return 0


_fake_forward.calls = []


def _recon(shared_sid, read_ts, *, unread=0):
    r = MainWindow.__new__(MainWindow)
    r._client = SimpleNamespace(
        _mds_local={"rain@jabberworld.info": shared_sid},
        fetch_history_mam_after=_fake_forward)
    r._unread_chats = {"rain@jabberworld.info": {
        **unread_state.blank(), "unread": unread, "read_ts": read_ts}}
    r._mam_unsupported = set()
    r._muc_joined = set()
    r._known_conferences = set()
    r._muc_self_nicks = {}
    r._conference_roster = set()
    r._bookmarks = {}
    r._config = None
    r._chat_window = None
    r._mds_reconciling = set()
    r._mds_reconciled = set()
    r._history_gap_checked = {}
    r._recount_unread = lambda: None
    r._refresh_unread_badge = lambda _jid: None
    r._push_unread_to_chat = lambda _jid: None
    r._schedule_unread_save = lambda: None
    return r


_fake_forward.calls = []
_r = _recon("missing-origin-id", "2026-11-01T10:54:00Z")
asyncio.run(_r._reconcile_mds_unread("rain@jabberworld.info", force=True))
check("an unresolved shared id starts from the local read point",
      _fake_forward.calls
      and _fake_forward.calls[0][1] == "2026-11-01T10:54:00Z")
check("an unresolved shared id is not sent as after",
      _fake_forward.calls and _fake_forward.calls[0][2] == "")


# 3. A chat with no read state still gets its tail gap filled ----------------
_fake_forward.calls = []
history.store_message(
    "tail@example", "incoming", "old local", "2026-11-01T09:00:00Z",
    sender="tail@example", archive_id="tail-old", origin_id="tail-old",
    message_id="tail-old")
_r2 = _recon("", "")
_r2._client = SimpleNamespace(
    _mds_local={}, fetch_history_mam_after=_fake_forward)
_r2._unread_chats = {}
asyncio.run(_r2._reconcile_mds_unread("tail@example", force=True))
check("a chat without read state syncs from its newest local row",
      _fake_forward.calls
      and _fake_forward.calls[0][1] == "2026-11-01T09:00:00Z")
check("a history-only gap sync does not invent unread",
      not _r2._unread_chats.get("tail@example", {}).get("unread"))


# 4. A local message/origin id is never promoted to the MDS point -----------
history.store_message(
    "origin@example", "outgoing", "local only", "2026-11-01T10:00:00Z",
    sender="Me", archive_id="", stanza_id="", origin_id="origin-1",
    message_id="origin-1")
_m = MainWindow.__new__(MainWindow)
_m._unread_chats = {"origin@example": {**unread_state.blank(),
                                      "read_sid": "read-1"}}
point = asyncio.run(MainWindow._mds_point_sid(
    _m, "origin@example", _m._unread_chats["origin@example"],
    "2026-11-01T10:00:00Z"))
check("_mds_point_sid never returns a local origin id", point != "origin-1")


# 4b. End-to-end: an old invalid shared id still stores the outgoing tail -----
def _run_broken_shared_id():
    # Earlier asyncio.run() calls closed the default loop; slixmpp's stanza
    # stream constructor needs one to create its ``disconnected`` future.
    asyncio.set_event_loop(asyncio.new_event_loop())
    c = JabberClient("me@x/res", "pw")
    c._mds_local["gapstore@example.com"] = "54d78060-origin"
    mam = c.xmpp.plugin["xep_0313"]
    page = [
        make_result("me@x", "Сообщение 111", "o-111", "arc-111",
                    "2026-11-01T10:54:35Z"),
        make_result("me@x", "Сообщение 222", "o-222", "arc-222",
                    "2026-11-01T10:54:37Z"),
        make_result("me@x", "Сообщение 333", "o-333", "arc-333",
                    "2026-11-01T10:54:39Z"),
    ]
    fake = _PagedMam([{
        "results": page,
        "fin": {"complete": "true", "rsm": {"last": "arc-333"}},
    }])
    r = MainWindow.__new__(MainWindow)
    r._client = c
    r._unread_chats = {"gapstore@example.com": {
        **unread_state.blank(), "unread": 0,
        "read_ts": "2026-10-31T22:14:59.079671Z"}}
    r._mam_unsupported = set()
    r._muc_joined = set()
    r._known_conferences = set()
    r._muc_self_nicks = {}
    r._conference_roster = set()
    r._bookmarks = {}
    r._config = None
    r._chat_window = None
    r._mds_reconciling = set()
    r._mds_reconciled = set()
    r._history_gap_checked = {}
    r._recount_unread = lambda: None
    r._refresh_unread_badge = lambda _jid: None
    r._push_unread_to_chat = lambda _jid: None
    r._schedule_unread_save = lambda: None
    with unittest.mock.patch.object(mam, "retrieve", fake):
        asyncio.run(r._reconcile_mds_unread("gapstore@example.com",
                                            force=True))
    rows = history.load_history("gapstore@example.com", limit=20)
    return [row["body"] for row in rows], fake.calls


_broken_bodies, _broken_calls = _run_broken_shared_id()
check("an invalid shared id still stores the outgoing tail",
      _broken_bodies == ["Сообщение 111", "Сообщение 222", "Сообщение 333"])
check("the broken shared id is not used as an after cursor",
      _broken_calls and _broken_calls[0]["rsm"].get("after") is None
      and _broken_calls[0]["start"] is not None)


# 5. The view reports only the server stanza-id as the MDS sid --------------
_src_path = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "stanza_im", "ui", "chat_view.py")
with open(_src_path, encoding="utf-8") as fh:
    _src = fh.read()
check("the JS seen point has no local message-id fallback",
      "best.getAttribute('data-stanza-sid') || ''" in _src
      and "data-stanza-sid')\n      || best.getAttribute('data-stanza-id')"
      not in _src)


if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll tests passed.")
