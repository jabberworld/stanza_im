"""Offscreen smoke tests for XEP-0249 Direct MUC Invitation.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_xep0249.py
"""
import os
import sys
import asyncio
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_invite_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xml.etree import ElementTree as ET

from PyQt6 import QtWidgets
import slixmpp

from stanza_im.core import client as client_mod
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. send_muc_invite builds the XEP-0249 stanza ----------------------------
sent = []
c = client_mod.JabberClient("me@example.com", "pw")
c.xmpp.send = lambda stanza: sent.append(stanza)

c.send_muc_invite("bob@example.com", "room@conf.example",
                  reason="hi", password="secret")
msg = sent[-1]
x = msg.xml.find("{jabber:x:conference}x")
check("invite is a normal message to the contact",
      msg["type"] == "normal" and msg["to"] == "bob@example.com")
check("invite carries the room jid",
      x is not None and x.get("jid") == "room@conf.example")
check("invite carries password and reason",
      x is not None and x.get("password") == "secret"
      and x.get("reason") == "hi")
check("invite has no body",
      not [el for el in msg.xml if el.tag.split("}")[-1] == "body"])

sent.clear()
c.send_muc_invite("bob@example.com", "room@conf.example")
x = sent[-1].xml.find("{jabber:x:conference}x")
check("invite omits empty password/reason",
      x is not None and x.get("password") is None and x.get("reason") is None)

sent.clear()
c.send_muc_invite("", "room@conf.example")
c.send_muc_invite("bob@example.com", "")
check("invite with empty target/room is skipped", sent == [])

# 2. muc_invite_from_message parses incoming invitations --------------------
NS_MUC_USER = "http://jabber.org/protocol/muc#user"


def _conference_x(message, jid, password="", reason=""):
    x = ET.SubElement(message.xml, "{jabber:x:conference}x")
    x.set("jid", jid)
    if password:
        x.set("password", password)
    if reason:
        x.set("reason", reason)
    return x


def _muc_user_invite(message, frm, reason=""):
    x = ET.SubElement(message.xml, "{%s}x" % NS_MUC_USER)
    invite = ET.SubElement(x, "{%s}invite" % NS_MUC_USER)
    invite.set("from", frm)
    if reason:
        ET.SubElement(invite, "{%s}reason" % NS_MUC_USER).text = reason
    return x


direct = slixmpp.Message()
direct["from"] = "anna@example.com/phone"
_conference_x(direct, "room@conf.example", password="pw", reason="come")
check("direct invite parse",
      client_mod.muc_invite_from_message(direct) == {
          "inviter": "anna@example.com/phone", "room": "room@conf.example",
          "password": "pw", "reason": "come", "mediated": False})

# the mediated stanza seen from another client (XEP-0045 §7.8 + XEP-0249)
real = slixmpp.Message()
real["from"] = "bimroom@conference.jabberworld.info"
real["to"] = "jabbim-test@linuxoid.in"
_muc_user_invite(real, "rain@jabberworld.info/walkbook")
_conference_x(real, "bimroom@conference.jabberworld.info")
check("mediated invite names the real inviter",
      client_mod.muc_invite_from_message(real) == {
          "inviter": "rain@jabberworld.info/walkbook",
          "room": "bimroom@conference.jabberworld.info",
          "password": "", "reason": "", "mediated": True})

# a mediated invite may carry the reason inside <invite>
reasoned = slixmpp.Message()
reasoned["from"] = "room@conf.example"
_muc_user_invite(reasoned, "ann@example.com", reason="join us")
_conference_x(reasoned, "room@conf.example")
check("mediated invite reason comes from <invite>",
      client_mod.muc_invite_from_message(reasoned)["reason"] == "join us")

# a room relay without an <invite> element names no inviter
relay = slixmpp.Message()
relay["from"] = "room@conf.example"
_conference_x(relay, "room@conf.example")
check("a room relay without <invite> has no inviter",
      client_mod.muc_invite_from_message(relay)["inviter"] == "")

plain = slixmpp.Message()
plain["from"] = "anna@example.com"
plain["body"] = "hello"
check("a plain message is not an invite",
      client_mod.muc_invite_from_message(plain) is None)

nojid = slixmpp.Message()
ET.SubElement(nojid.xml, "{jabber:x:conference}x")
check("an invite without a jid is ignored",
      client_mod.muc_invite_from_message(nojid) is None)

# 2b. the stanza handler re-emits the invitation ----------------------------
events = []
c.on("muc_invite_received", lambda *a: events.append(a))
asyncio.get_event_loop().run_until_complete(c._on_muc_invite_stanza(real))
check("incoming invite emits muc_invite_received",
      events == [("rain@jabberworld.info/walkbook",
                  "bimroom@conference.jabberworld.info", "", "")])

# 3. MainWindow "Invite to" submenu ----------------------------------------
class _FakeGC:
    def __init__(self, password=""):
        self.password = password


class _FakeClient:
    def __init__(self):
        self.groupchats = {"room1@conf.example": _FakeGC("pw1")}
        self.invites = []
        self.jid_str = "me@example.com/desk"

    def send_muc_invite(self, jid, room, reason="", password=""):
        self.invites.append((jid, room, reason, password))

    def get_contact(self, jid):
        return None


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
win = MainWindow(app)
win._idle_timer.stop()
win._client = _FakeClient()
win._tray.show_message = lambda *a, **k: None
win._muc_self_nicks = {"room2@conf.example": "me",
                       "room1@conf.example": "me"}
win._muc_names = {"room1@conf.example": "Alpha",
                  "room2@conf.example": "Beta"}

menu = QtWidgets.QMenu()
sub = win._build_invite_menu(menu, "bob@example.com")
actions = sub.actions() if sub is not None else []
check("invite submenu lists the joined conferences",
      [a.text() for a in actions] == ["Alpha", "Beta"])
actions[1].trigger()
check("the chosen room invites the right target",
      win._client.invites == [("bob@example.com", "room2@conf.example",
                               "Join me in the conference", "")])

sub2 = win._build_invite_menu(menu, "bob@example.com",
                              exclude_room="room1@conf.example")
check("the participant's own room is excluded",
      sub2 is not None and [a.text() for a in sub2.actions()] == ["Beta"])

win._invite_to_conference("bob@example.com", "room1@conf.example")
check("the room password is passed when known",
      win._client.invites[-1] == ("bob@example.com", "room1@conf.example",
                                  "Join me in the conference", "pw1"))

win._muc_self_nicks = {}
check("no submenu when we are not in any conference",
      win._build_invite_menu(menu, "bob@example.com") is None)
check("no submenu without a target jid",
      win._build_invite_menu(menu, "") is None)

# 4. inviter label resolution ----------------------------------------------
win._muc_users = {"room1@conf.example": {
    "rain": {"nick": "rain", "real_jid": "rain@jabberworld.info/walkbook"}}}
check("inviter label uses the room nick and jid",
      win._muc_invite_inviter_label(
          "room1@conf.example", "rain@jabberworld.info/walkbook")
      == "rain (rain@jabberworld.info)")
check("unknown inviter yields an empty label",
      win._muc_invite_inviter_label("room1@conf.example", "") == "")
check("inviter without a known nick falls back to the jid",
      win._muc_invite_inviter_label(
          "room1@conf.example", "bob@example.com/walkbook")
      == "bob@example.com")

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
