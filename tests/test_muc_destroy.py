"""Room destruction (XEP-0045 §10.9) — parsing, event and UI wiring.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_destroy.py
"""
import asyncio
import inspect
import os
import sys
import tempfile
import types

_SCRATCH = tempfile.mkdtemp(prefix="stanza_mucdestroy_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xml.etree import ElementTree as etree

from stanza_im.core.client import JabberClient, _muc_destroy_info

MUC_USER = "http://jabber.org/protocol/muc#user"

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Pres:
    def __init__(self, xml, frm="", ptype=""):
        self.xml = xml
        self._fields = {"from": frm, "type": ptype}

    def __getitem__(self, key):
        return self._fields[key]


def _presence(body: str, frm: str = "room@conf.example/nick",
              ptype: str = "unavailable") -> _Pres:
    return _Pres(etree.fromstring(
        "<presence xmlns='jabber:client' from='%s'>%s</presence>" % (frm, body)),
        frm, ptype)


DESTROY = ("<x xmlns='%s'><destroy jid='alt@conf.example'>"
           "<reason>Gone fishing</reason></destroy></x>" % MUC_USER)

# 1. parser ------------------------------------------------------------------
info = _muc_destroy_info(_presence(DESTROY))
check("destroy reason parsed", info == {"reason": "Gone fishing",
                                        "alternate": "alt@conf.example"})
info = _muc_destroy_info(_presence(
    "<x xmlns='%s'><item affiliation='member'/></x>" % MUC_USER))
check("an ordinary MUC presence is not a destroy", info is None)
check("a bare presence is not a destroy", _muc_destroy_info(_Pres(None)) is None)
info = _muc_destroy_info(_presence(
    "<x xmlns='%s'><destroy/></x>" % MUC_USER))
check("a destroy without reason/alternate", info == {"reason": "",
                                                     "alternate": ""})


# 2. the presence handler emits once and drops the room ----------------------
class _FakeWhiteboard:
    def __init__(self):
        self.dropped = []

    def drop_room(self, room):
        self.dropped.append(room)


class _FakeMuji:
    def handle_presence(self, *a, **k):
        return None


def _fake_client():
    client = JabberClient.__new__(JabberClient)
    client.groupchats = {"room@conf.example": object()}
    client._known_rooms = {"room@conf.example"}
    client._destroyed_rooms = set()
    client.whiteboard = _FakeWhiteboard()
    client.muji = _FakeMuji()
    client.events = []
    client.emit = lambda name, *a: client.events.append((name,) + tuple(a))
    return client


client = _fake_client()
pres = _presence(DESTROY)
client._on_groupchat_presence(pres)
check("muc_destroyed emitted with the reason",
      [e for e in client.events if e[0] == "muc_destroyed"]
      == [("muc_destroyed", "room@conf.example", "Gone fishing",
           "alt@conf.example")])
check("the destroyed room is forgotten",
      "room@conf.example" not in client.groupchats
      and "room@conf.example" not in client._known_rooms)
check("the room's board session is dropped",
      client.whiteboard.dropped == ["room@conf.example"])
check("no per-occupant presence event for a destroy",
      not [e for e in client.events if e[0] == "groupchat_presence"])
client._on_groupchat_presence(_presence(DESTROY))
check("a repeated destroy presence is ignored",
      len([e for e in client.events if e[0] == "muc_destroyed"]) == 1)


# 3. destroy_room sends the XEP-0045 request ---------------------------------
class _FakeMuc:
    def __init__(self):
        self.calls = []

    async def destroy(self, room, reason="", altroom=None):
        self.calls.append((room, reason, altroom))


async def _run_destroy():
    c = JabberClient.__new__(JabberClient)
    c.xmpp = types.SimpleNamespace(plugin={"xep_0045": _FakeMuc()})
    await c.destroy_room("room@conf.example", reason="bye")
    await c.destroy_room("room@conf.example", reason="", alternate="alt@conf")
    return c.xmpp.plugin["xep_0045"].calls


calls = asyncio.run(_run_destroy())
check("destroy_room forwards the reason",
      calls[0] == ("room@conf.example", "bye", None))
check("destroy_room forwards the alternate room",
      calls[1] == ("room@conf.example", "", "alt@conf"))


# 4. UI wiring (source-level) ------------------------------------------------
from stanza_im.ui.main_window import MainWindow

muc_handler = inspect.getsource(MainWindow._on_muc_destroyed)
own_handler = inspect.getsource(MainWindow._on_room_destroyed)
drop = inspect.getsource(MainWindow._drop_room_ui)
check("an incoming destroy keeps the tab open (close_chat=False)",
      "close_chat=False" in muc_handler
      and "close_chat(room)" not in muc_handler)
check("our own destroy closes the tab", "close_chat=True" in own_handler)
check("the cleanup drops the conference roster row",
      "_conference_roster.discard(room)" in drop)
check("the dialog's destroy signal is wired",
      "dialog.room_destroyed.connect(self._on_room_destroyed)"
      in inspect.getsource(MainWindow._on_muc_config_requested))
check("the client event is subscribed",
      'c.on("muc_destroyed", self._on_muc_destroyed)' in
      inspect.getsource(MainWindow._connect_client_signals))

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All room-destroy tests passed.")
