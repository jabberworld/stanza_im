"""Offscreen tests for MUC voice requests (XEP-0045 §7.13).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_voice.py
"""
import asyncio
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_voice_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slixmpp
from PyQt6 import QtWidgets

from stanza_im.core.client import _muc_voice_request
from stanza_im.core.storage import Config
from stanza_im.i18n import en, load as i18n_load, ru
from stanza_im.ui.main_window import MainWindow, _VoiceRequestRow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _msg(frm: str, inner: str, mtype: str = "groupchat") -> slixmpp.Message:
    raw = (f"<message xmlns='jabber:client' type='{mtype}' "
           f"from='{frm}' to='me'>{inner}</message>")
    return slixmpp.Message(xml=ET.fromstring(raw))


# 1. Protocol parsing --------------------------------------------------------
MUC_USER = "http://jabber.org/protocol/muc#user"
MUC_REQUEST = "http://jabber.org/protocol/muc#request"
voice = _msg("room@conf.example/guest",
             f"<x xmlns='{MUC_USER}'><item affiliation='member'/></x>")
check("a legacy voice request is parsed",
      _muc_voice_request(voice) == {
          "room": "room@conf.example", "nick": "guest",
          "from": "room@conf.example/guest"})
# The standard data-form shape (XEP-0045 §7.13).
form = _msg("room@conf.example/guest",
            "<x xmlns='jabber:x:data' type='submit'>"
            f"<field var='FORM_TYPE'><value>{MUC_REQUEST}</value></field>"
            "<field var='muc#role' type='list-single'>"
            "<value>participant</value></field></x>")
check("a data-form voice request is parsed",
      _muc_voice_request(form) == {
          "room": "room@conf.example", "nick": "guest",
          "from": "room@conf.example/guest"})
invite = _msg("room@conf.example",
              f"<x xmlns='{MUC_USER}'><invite from='a@b/c'/></x>", "normal")
check("a mediated invite is not a voice request",
      _muc_voice_request(invite) is None)
other = _msg("room@conf.example/guest",
             f"<x xmlns='{MUC_USER}'><item role='participant'/></x>")
check("a non-member item is not a voice request",
      _muc_voice_request(other) is None)


# 2. Sending a request -------------------------------------------------------
# A client-supplied ``from`` makes the server close the stream with
# ``invalid-from`` ("Improper 'from' attribute"), so it must never be set.
from stanza_im.core.client import JabberClient, NS_MUC_USER  # noqa: E402


class _FakeXMPP:
    def __init__(self, owner):
        self._owner = owner

    def Message(self):
        m = slixmpp.Message()
        self._owner.messages.append(m)
        return m


class _ReqClient(JabberClient):
    def __init__(self):
        self.messages = []
        self.xmpp = _FakeXMPP(self)


class _FakeMuc:
    def __init__(self):
        self.roles = []

    async def set_role(self, room, nick, role, reason=""):
        self.roles.append((room, nick, role))


class _GrantClient(JabberClient):
    def __init__(self):
        self._muc = _FakeMuc()
        self.xmpp = type("X", (), {"plugin": {"xep_0045": self._muc}})()


gc = _GrantClient()
asyncio.get_event_loop().run_until_complete(
    gc.grant_voice("room@conf.example", "guest", "guest@x"))
check("grant_voice asks for the participant role (XEP-0045 §8.3)",
      gc._muc.roles == [("room@conf.example", "guest", "participant")])


req = _ReqClient()
check("request_voice refuses an empty room",
      req.request_voice("") is False)
check("request_voice accepts a room",
      req.request_voice("room@conf.example") is True)
sent = req.messages[-1]
xml = sent.xml
check("the voice message is not sent with a 'from'",
      xml.get("from") is None)
check("the voice message targets the room",
      xml.get("to") == "room@conf.example")
check("the voice message has no groupchat type",
      (xml.get("type") or "") != "groupchat")
_x = xml.find("{jabber:x:data}x")
_fields = {f.get("var"): f for f in (_x if _x is not None else [])}
_fmt = _fields.get("FORM_TYPE")
check("the voice request carries the muc#request FORM_TYPE",
      _fmt is not None and next(
          (c.text for c in _fmt if c.tag == "{jabber:x:data}value"), "")
      == MUC_REQUEST)
_role = _fields.get("muc#role")
check("the voice request asks for the participant role",
      _role is not None and next(
          (c.text for c in _role if c.tag == "{jabber:x:data}value"), "")
      == "participant")


# 3. MainWindow gating + events ---------------------------------------------
cfg = Config()
cfg.save()
w = MainWindow(app)


class _StubClient:
    def __init__(self):
        self.granted = []
        self.requested = []

    def __getattr__(self, _name):
        return lambda *a, **k: None

    async def grant_voice(self, room, nick, jid=""):
        self.granted.append((room, nick, jid))

    def request_voice(self, room):
        self.requested.append(room)
        return True

    def supports_calls(self, *a, **k):
        return False

    def client_icon(self, *a, **k):
        return ""


stub = _StubClient()
w._client = stub
room = "room@conf.example"
w._conference_roster.add(room)
w._muc_self_nicks[room] = "me"

# Not a moderator -> the request must be ignored entirely.
w._muc_users[room] = {"me": {"nick": "me", "role": "participant",
                             "affiliation": "none"}}
before = w._events_list.count()
w._on_muc_voice_request(room, "guest@x", "guest")
check("a non-moderator does not see the request",
      w._events_list.count() == before)

# Moderator -> a request row with grant/refuse.
w._muc_users[room]["me"] = {"nick": "me", "role": "moderator",
                            "affiliation": "owner"}
w._on_muc_voice_request(room, "guest@x", "guest")
row = w._events_list.itemWidget(w._events_list.item(w._events_list.count() - 1))
check("a moderator gets a voice-request row",
      isinstance(row, _VoiceRequestRow) and row.jid == "guest@x"
      and row.nick == "guest")
row.granted.emit(room, "guest", "guest@x")
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.05))
check("grant calls client.grant_voice with the nick",
      stub.granted == [(room, "guest", "guest@x")])
check("the row is marked granted after grant",
      "granted" in row._result.text().lower()
      or row._result.text() != "")

# Refuse only marks the row (no stanza).
row2 = None
w._on_muc_voice_request(room, "other@x", "other")
row2 = w._events_list.itemWidget(w._events_list.item(w._events_list.count() - 1))
row2.refused.emit(room, "other", "other@x")
check("refuse does not send anything to the server",
      stub.granted == [(room, "guest", "guest@x")]
      and row2._result.text() != "")

# 4. Button gating -----------------------------------------------------------
w._chat_window.open_groupchat(room, "me", "Room")
cw = w._chat_window.get_chat(room)
w._muc_users[room]["me"] = {"nick": "me", "role": "visitor",
                            "affiliation": "none"}
w._muc_room_features[room] = {"muc_membersonly"}
w._apply_voice_request(room)
check("a visitor in a moderated room sees an enabled button",
      not cw._voice_btn.isHidden() and cw._voice_btn.isEnabled())
w._muc_room_features[room] = set()
w._apply_voice_request(room)
check("an unmoderated room hides the button", cw._voice_btn.isHidden())
w._muc_room_features[room] = {"muc_membersonly"}
w._muc_users[room]["me"] = {"nick": "me", "role": "participant",
                            "affiliation": "member"}
w._apply_voice_request(room)
check("a non-visitor does not see the button", cw._voice_btn.isHidden())

# 5. i18n --------------------------------------------------------------------
check("the voice strings are translated",
      en.STRINGS.get("muc_ask_voice") and ru.STRINGS.get("muc_ask_voice"))
check("en and ru have the same keys", set(en.STRINGS) == set(ru.STRINGS))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All MUC voice tests passed.")
