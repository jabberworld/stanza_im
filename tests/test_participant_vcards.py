"""Conference participant vCards: cache-first and a rate-limited queue.

A 200-participant join used to schedule one vCard IQ per occupant.  The client
now applies a cached card immediately and fetches the misses through one slow
background worker; a previously cached avatar file is used by nick without any
request.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_participant_vcards.py
"""
import asyncio
import inspect
import os
import sys
import tempfile
from types import SimpleNamespace
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_participant_vcards_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core.client import JabberClient, _vcard_photo_hash

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


def _client(room, nicks):
    client = JabberClient("me@example.com/res", "pw")
    client.PARTICIPANT_VCARD_INTERVAL = 0
    client.groupchats[room] = SimpleNamespace(
        users={nick: {} for nick in nicks})
    return client


def _events(client):
    events = []
    client.on("vcard_received", lambda jid, card: events.append((jid, card)))
    return events


async def _wait(client):
    task = client._participant_vcard_task
    if task is not None:
        await asyncio.wait_for(task, 2)


# 1. a cached card is applied without a request -----------------------------
async def cache_hit():
    room = "cache@conf.example"
    client = _client(room, ["alice"])
    events = _events(client)
    fetched = []

    async def fake(jid):
        fetched.append(jid)

    client._participant_vcard_fetch = fake
    client._vcard_cache.put(f"{room}/alice", {"fn": "Alice"})
    client.queue_participant_vcard(room, "alice")
    check("a cached card is applied immediately",
          events and events[0][0] == f"{room}/alice")
    check("a cached card does not start a request",
          not fetched and client._participant_vcard_task is None)
    client.queue_participant_vcard(room, "alice")
    check("the same cached card is not emitted twice", len(events) == 1)


# 2. a cache miss is fetched once, through room/nick ------------------------
async def cache_miss():
    room = "miss@conf.example"
    client = _client(room, ["bob"])
    events = _events(client)
    fetched = []

    async def fake(jid):
        fetched.append(jid)
        client._vcard_cache.put(jid, {"fn": "Bob"})

    client._participant_vcard_fetch = fake
    client.queue_participant_vcard(room, "bob")
    client.queue_participant_vcard(room, "bob")
    await _wait(client)
    check("a miss is fetched once through the occupant JID",
          fetched == [f"{room}/bob"])
    client.queue_participant_vcard(room, "bob")
    check("a resolved participant is not requested again",
          len(fetched) == 1 and client._participant_vcard_task is None)


# 3. an occupant who left before the fetch is skipped -----------------------
async def departed():
    room = "gone@conf.example"
    client = _client(room, ["gone"])
    fetched = []

    async def fake(jid):
        fetched.append(jid)

    client._participant_vcard_fetch = fake
    client.queue_participant_vcard(room, "gone")
    client.groupchats[room].users.clear()
    await _wait(client)
    check("a participant who left before the fetch is skipped", fetched == [])


# 4. misses are processed one at a time, in order ---------------------------
async def ordered():
    room = "order@conf.example"
    client = _client(room, ["u1", "u2", "u3"])
    fetched = []

    async def fake(jid):
        fetched.append(jid)

    client._participant_vcard_fetch = fake
    for nick in ("u1", "u2", "u3"):
        client.queue_participant_vcard(room, nick)
    await _wait(client)
    check("queued cards are fetched in order",
          fetched == [f"{room}/u1", f"{room}/u2", f"{room}/u3"])


# 4b. a changed vCard photo hash re-validates a cached card ----------------
async def revalidate():
    room = "reval@conf.example"
    client = _client(room, ["vera"])
    events = _events(client)
    fetched = []

    async def fake(jid):
        fetched.append(jid)

    client._participant_vcard_fetch = fake
    client._vcard_cache.put(f"{room}/vera",
                            {"fn": "Vera", "photo_hash": "old"})
    client.queue_participant_vcard(room, "vera", "new")
    check("a cached stale card is still applied at once",
          events and events[0][0] == f"{room}/vera")
    await _wait(client)
    check("a changed photo hash re-validates once",
          fetched == [f"{room}/vera"])
    client.queue_participant_vcard(room, "vera", "new")
    await _wait(client)
    check("the re-validation does not repeat in the session",
          fetched == [f"{room}/vera"])

    match_room = "match@conf.example"
    match = _client(match_room, ["vera"])
    match_fetched = []

    async def match_fake(jid):
        match_fetched.append(jid)

    match._participant_vcard_fetch = match_fake
    match._vcard_cache.put(f"{match_room}/vera",
                           {"fn": "Vera", "photo_hash": "same"})
    match.queue_participant_vcard(match_room, "vera", "same")
    await _wait(match)
    check("a matching photo hash needs no request", match_fetched == [])


# 4c. the presence photo hash parser ---------------------------------------
xml = ET.fromstring(
    "<presence xmlns='jabber:client'><x xmlns='vcard-temp:x:update'>"
    "<photo>hash123</photo></x></presence>")
check("the XEP-0153 photo hash is parsed",
      _vcard_photo_hash(SimpleNamespace(xml=xml)) == "hash123")
check("a presence without a photo hash yields nothing",
      _vcard_photo_hash(SimpleNamespace(
          xml=ET.fromstring("<presence xmlns='jabber:client'/>"))) == "")


asyncio.run(cache_hit())
asyncio.run(cache_miss())
asyncio.run(departed())
asyncio.run(ordered())
asyncio.run(revalidate())

check("participant cards have a day-long TTL",
      JabberClient.PARTICIPANT_VCARD_MAX_AGE == 24 * 60 * 60)
check("participant fetches run at two per second",
      JabberClient.PARTICIPANT_VCARD_INTERVAL == 0.5)

# 5. the UI uses the queue and a cached avatar file by nick -----------------
from stanza_im.ui.main_window import MainWindow  # noqa: E402

src = inspect.getsource(MainWindow._on_groupchat_presence)
check("a presence queues the card instead of requesting it directly",
      "queue_participant_vcard(" in src
      and "photo_hash" in src
      and "get_vcard(" not in src)
check("the presence uses the cached-avatar fallback",
      "_muc_cached_avatar(" in src)

join_src = inspect.getsource(MainWindow._on_muc_joined)
seed_src = inspect.getsource(MainWindow._seed_muc_chat)
check("a room join queues the participant cards",
      "queue_participant_vcard(room, nick)" in join_src
      and "get_vcard(" not in join_src
      and "get_vcard(" not in seed_src)

from stanza_im.include.avatars import (  # noqa: E402
    avatar_path, default_avatar, save_avatar)

win = MainWindow.__new__(MainWindow)
room = "avatar@conf.example"
check("no cached avatar yields no path",
      win._muc_cached_avatar(room, "carol", {}) == ("", ""))
raw = open(default_avatar(), "rb").read()
saved = save_avatar(f"{room}/carol", raw)
path, jid = win._muc_cached_avatar(room, "carol", {})
check("a cached avatar file is used by nick without a request",
      path == saved and jid == f"{room}/carol")
check("a known avatar from the previous state wins",
      win._muc_cached_avatar(room, "carol",
                             {"avatar_path": "/x.png",
                              "avatar_jid": "real@x"})
      == ("/x.png", "real@x"))

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All participant vCard tests passed.")
