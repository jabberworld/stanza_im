"""Offscreen tests for XEP-0410 MUC self-ping.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_selfping.py
"""
import asyncio
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_selfping_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

asyncio.set_event_loop(asyncio.new_event_loop())

from PyQt6 import QtWidgets

import slixmpp

from stanza_im.i18n import load as i18n_load
from stanza_im.core import client as client_mod
from stanza_im.core.client import JabberClient

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _GI:
    def __init__(self, joined=True, nick="me", password=""):
        self.joined = joined
        self.nick = nick
        self.password = password


def _iq_error(condition):
    exc = slixmpp.exceptions.IqError.__new__(slixmpp.exceptions.IqError)
    exc.condition = condition
    return exc


def _run(client, room):
    asyncio.get_event_loop().run_until_complete(client._self_ping_room(room))


client = JabberClient("me@example.com/r", "pw")


def _install(send_impl):
    def factory(*args, **kwargs):
        iq = slixmpp.Iq()
        async def _send(*a, **k):
            return send_impl()
        iq.send = _send
        return iq
    client.xmpp.Iq = factory


# ── activity tracking ────────────────────────────────────────────
client._mark_muc_activity("room@muc")
check("activity recorded", "room@muc" in client._muc_last_activity)


# ── self-ping outcomes ───────────────────────────────────────────
def _scenario(room, send_impl):
    joined = []
    client.join_muc = lambda *a, **k: joined.append(a)
    client.groupchats = {room: _GI()}
    client._muc_last_activity = {room: time.monotonic() - 1000}
    client._muc_self_ping_busy = set()
    _install(send_impl)
    _run(client, room)
    return joined


joined = _scenario("ok@muc", lambda: None)
check("successful self-ping does not rejoin", joined == [])
check("successful self-ping refreshes activity",
      time.monotonic() - client._muc_last_activity["ok@muc"] < 5)

joined = _scenario("unavailable@muc",
                   lambda: (_ for _ in ()).throw(_iq_error("service-unavailable")))
check("service-unavailable means still joined", joined == [])

joined = _scenario("notfound@muc",
                   lambda: (_ for _ in ()).throw(_iq_error("item-not-found")))
check("item-not-found means still joined", joined == [])

joined = _scenario("timeout@muc",
                   lambda: (_ for _ in ()).throw(slixmpp.exceptions.IqTimeout()))
check("timeout defers the self-ping", joined == [])

joined = _scenario("dead@muc",
                   lambda: (_ for _ in ()).throw(_iq_error("not-acceptable")))
check("not-acceptable triggers a rejoin", len(joined) == 1
      and joined[0][0] == "dead@muc")


# ── idle loop selects the silent room ────────────────────────────
async def _loop_probe():
    old_interval = client_mod._MUC_SELF_PING_INTERVAL
    client_mod._MUC_SELF_PING_INTERVAL = 0.01
    pings = []

    async def fake_ping(room):
        pings.append(room)

    client._self_ping_room = fake_ping
    client._muc_self_ping_busy = set()
    client._muc_last_activity = {
        "idle@muc": time.monotonic() - client_mod._MUC_SELF_PING_IDLE - 10,
        "fresh@muc": time.monotonic(),
    }
    client.groupchats = {"idle@muc": _GI(), "fresh@muc": _GI()}
    client.xmpp.is_connected = lambda: True
    task = asyncio.get_event_loop().create_task(client._muc_self_ping_loop())
    await asyncio.sleep(0.06)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    client_mod._MUC_SELF_PING_INTERVAL = old_interval
    return pings


pings = asyncio.get_event_loop().run_until_complete(_loop_probe())
check("loop pings only the silent room",
      pings == ["idle@muc"])


# ── static wiring ────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_root, "stanza_im", "core", "client.py"),
          encoding="utf-8") as fh:
    src = fh.read()
check("self-ping started on session start",
      "self._start_muc_self_ping()" in src
      and "self._stop_muc_self_ping()" in src)
check("self-ping uses a 15-minute idle window",
      "_MUC_SELF_PING_IDLE = 900.0" in src)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
