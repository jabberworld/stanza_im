"""Offscreen tests for the "Create conference" dialog and room setup.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_create_conference.py
"""
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_create_conf_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core.client import JabberClient
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.create_conference_dialog import CreateConferenceDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── option → config mapping ──────────────────────────────────────
values = JabberClient.muc_creation_values(
    {"persistent": True, "invisible": True, "members_only": True,
     "anonymous": False, "name": "Team"})
check("persistent maps to persistentroom",
      values["muc#roomconfig_persistentroom"] == 1)
check("invisible negates the public room flag",
      values["muc#roomconfig_publicroom"] == 0)
check("members-only maps to membersonly",
      values["muc#roomconfig_membersonly"] == 1)
check("non-anonymous opens the whois to anyone",
      values["muc#roomconfig_whois"] == "anyone")
check("the name is included when set",
      values["muc#roomconfig_roomname"] == "Team")

defaults = JabberClient.muc_creation_values({})
check("defaults: persistent/members off, public on, whois anyone",
      defaults["muc#roomconfig_persistentroom"] == 0
      and defaults["muc#roomconfig_publicroom"] == 1
      and defaults["muc#roomconfig_membersonly"] == 0
      and defaults["muc#roomconfig_whois"] == "anyone")
check("no empty room-name field is sent",
      "muc#roomconfig_roomname" not in defaults)
check("anonymous maps to moderators-only whois",
      JabberClient.muc_creation_values(
          {"anonymous": True})["muc#roomconfig_whois"] == "moderators")


# ── dialog: defaults, presets, validation ────────────────────────
dlg = CreateConferenceDialog(["conference.example", "muc.example"],
                             "conference.example")
data = dlg.collect()
check("server defaults to the account conference service",
      data["server"] == "conference.example")
check("option defaults: persistent off, invisible off, members off, anon on",
      data["persistent"] is False and data["invisible"] is False
      and data["members_only"] is False and data["anonymous"] is True)

dlg._preset_public()
c = dlg.collect()
check("the Public preset enables anonymity and disables invisible",
      c["anonymous"] is True and c["invisible"] is False)

dlg._preset_calls()
c = dlg.collect()
check("the Calls/OMEMO preset enables members-only and disables anonymity",
      c["members_only"] is True and c["anonymous"] is False)

dlg._preset_private()
c = dlg.collect()
check("the Private preset enables invisible and members-only",
      c["invisible"] is True and c["members_only"] is True)

dlg._address.setText("")
dlg._validate()
check("an empty address is rejected",
      dlg.result() != QtWidgets.QDialog.DialogCode.Accepted)
dlg._address.setText("team")
dlg._validate()
check("a valid address is accepted",
      dlg.result() == QtWidgets.QDialog.DialogCode.Accepted)
check("collect returns the room localpart", dlg.collect()["room"] == "team")
dlg.deleteLater()


# ── created-room detection (XEP-0045 status 201) ─────────────────
class _Presence(dict):
    def __getitem__(self, key):
        if key == "muc":
            return {"status_codes": self.get("_codes", set())}
        return super().__getitem__(key)


class _FakeMuc:
    async def join_muc_wait(self, room, nick, password, timeout):
        pres = _Presence()
        pres["_codes"] = {201}
        return pres, None, [nick], []


class _FakeXmpp:
    def __init__(self, muc=None):
        self.plugin = {"xep_0045": muc or _FakeMuc()}


client = JabberClient.__new__(JabberClient)
client.jid_str = "me@example.com"
from stanza_im.core.client import GroupChatInfo  # noqa: E402
client.groupchats = {"room@conf.example": GroupChatInfo(
    room="room@conf.example", nick="me")}
client.xmpp = _FakeXmpp()
seen = []
client.emit = lambda *args: seen.append(args)
client._muc_subjects = {}
client._muc_join_tasks = {}
client.groupchats["room@conf.example"].pending_history = []

asyncio.get_event_loop().run_until_complete(
    client._join_muc_task("room@conf.example", "me", ""))
joined = next((e for e in seen if e and e[0] == "muc_joined"), None)
check("a 201 join emits muc_joined with created=True",
      joined is not None and joined[4] is True)


# ── an existing room (no 201) is not marked as created ───────────
class _FakeMucExisting(_FakeMuc):
    async def join_muc_wait(self, room, nick, password, timeout):
        pres = _Presence()
        pres["_codes"] = set()
        return pres, None, [nick], []


client.xmpp = _FakeXmpp(muc=_FakeMucExisting())
client.groupchats = {"room@conf.example": GroupChatInfo(
    room="room@conf.example", nick="me")}
client.groupchats["room@conf.example"].pending_history = []
seen.clear()
asyncio.get_event_loop().run_until_complete(
    client._join_muc_task("room@conf.example", "me", ""))
joined = next((e for e in seen if e and e[0] == "muc_joined"), None)
check("an existing room emits created=False",
      joined is not None and joined[4] is False)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
