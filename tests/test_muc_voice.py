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
voice = _msg("room@conf.example/guest",
             f"<x xmlns='{MUC_USER}'><item affiliation='member'/></x>")
check("a voice request is parsed",
      _muc_voice_request(voice) == {
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
class _SendClient:
    def __init__(self):
        self.sent = []

    def __getattr__(self, _name):
        return lambda *a, **k: None


from stanza_im.core.client import JabberClient  # noqa: E402


class _ReqClient(JabberClient):
    def __init__(self):
        self.sent = []

    def send(self, *a, **k):
        pass


req = _ReqClient()
# JabberClient with no xmpp would fail; use the static-ish build via monkeypatch.
check("request_voice refuses an empty room",
      req.request_voice("") is False)


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

    async def grant_voice(self, room, jid):
        self.granted.append((room, jid))

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
      isinstance(row, _VoiceRequestRow) and row.jid == "guest@x")
row.granted.emit(room, "guest@x")
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.05))
check("grant calls client.grant_voice", stub.granted == [(room, "guest@x")])
check("the row is marked granted after grant",
      "granted" in row._result.text().lower()
      or row._result.text() != "")

# Refuse only marks the row (no stanza).
row2 = None
w._on_muc_voice_request(room, "other@x", "other")
row2 = w._events_list.itemWidget(w._events_list.item(w._events_list.count() - 1))
row2.refused.emit(room, "other@x")
check("refuse does not send anything to the server",
      stub.granted == [(room, "guest@x")] and row2._result.text() != "")

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
