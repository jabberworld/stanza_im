"""Tests for JID normalisation in forms (paste of xmpp: URIs and resources).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_jid_normalize.py
"""
import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_jid_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.include.xmpp_uri import normalize_jid, split_jid
from stanza_im.ui.jid_edit import JidLineEdit, RoomJidEdit

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _paste(edit, text):
    mime = QtCore.QMimeData()
    mime.setText(text)
    edit.insertFromMimeData(mime)


# 1. the pure helper ---------------------------------------------------------
check("a plain JID is unchanged",
      normalize_jid("user@example.com") == "user@example.com")
check("an xmpp: URI loses its scheme",
      normalize_jid(" xmpp:user@example.com ") == "user@example.com")
check("the resource is dropped by default",
      normalize_jid("xmpp:user@example.com/phone") == "user@example.com")
check("the resource is kept on request",
      normalize_jid("xmpp:user@example.com/Phone", resource=True)
      == "user@example.com/Phone")
check("the domain is lower-cased, the localpart kept",
      normalize_jid("xmpp:User@Example.COM/Res") == "User@example.com")
check("a URI query is dropped",
      normalize_jid("xmpp:user@example.com?message") == "user@example.com")
check("a bare URI query is dropped",
      normalize_jid("user@example.com?message") == "user@example.com")
check("an address-less URI is empty",
      normalize_jid("xmpp:?message;body=hi") == "")
check("percent-encoded addresses are decoded",
      normalize_jid("xmpp:room%40conf.example?join") == "room@conf.example")
check("an empty or non-string value is empty",
      normalize_jid("") == "" and normalize_jid(None) == ""
      and normalize_jid("xmpp:") == "")
check("split_jid returns the localpart and domain",
      split_jid("xmpp:room@conf.example/nick") == ("room", "conf.example"))
check("split_jid handles a localpart only", split_jid("room") == ("room", ""))
check("split_jid handles a bare room with a query",
      split_jid("room@conf.example?join") == ("room", "conf.example"))

# 2. JidLineEdit -------------------------------------------------------------
edit = JidLineEdit()
_paste(edit, "xmpp:user@example.com/phone")
check("pasting into a JID field strips the scheme and resource",
      edit.text() == "user@example.com")
check("jid() normalises typed text",
      (edit.setText("  xmpp:User@EXAMPLE.com/res  "), edit.jid())[1]
      == "User@example.com")

res_edit = JidLineEdit(resource=True)
_paste(res_edit, "xmpp:user@example.com/phone")
check("a resource-aware field keeps the resource",
      res_edit.text() == "user@example.com/phone"
      and res_edit.jid() == "user@example.com/phone")

# 3. RoomJidEdit -------------------------------------------------------------
room_edit = RoomJidEdit()
splits = []
room_edit.split.connect(lambda room, server: splits.append((room, server)))
_paste(room_edit, "xmpp:room@conf.example/nick")
check("pasting a full room JID keeps the localpart",
      room_edit.text() == "room")
check("pasting a full room JID reports the server",
      splits == [("room", "conf.example")])
bare_edit = RoomJidEdit()
bare_splits = []
bare_edit.split.connect(lambda room, server: bare_splits.append((room, server)))
_paste(bare_edit, "another")
check("pasting a bare room name does not split",
      bare_edit.text() == "another" and not bare_splits)
room_edit.setText("typed@conf.example")
check("room() splits a typed JID", room_edit.room()
      == ("typed", "conf.example"))

# 4. dialogs -----------------------------------------------------------------
from stanza_im.ui.add_contact_dialog import AddContactDialog
from stanza_im.ui.bookmark_dialog import BookmarkDialog
from stanza_im.ui.conference_dialog import JoinConferenceDialog
from stanza_im.ui.create_conference_dialog import CreateConferenceDialog
from stanza_im.ui.hats_dialog import HatAssignDialog
from stanza_im.ui.privacy_rule_dialog import PrivacyRuleDialog

contact = AddContactDialog([], SimpleNamespace(), jid="xmpp:Alice@Example.COM/phone")
check("the add-contact dialog normalises its JID",
      contact.collect()["jid"] == "Alice@example.com")
contact.deleteLater()

privacy = PrivacyRuleDialog([], [], item={
    "type": "jid", "value": "xmpp:User@Example.COM/res", "action": "deny"})
check("a privacy rule keeps the resource but drops the scheme",
      privacy.result_item()["value"] == "User@example.com/res")
privacy.deleteLater()

hats = HatAssignDialog([], [])
hats._manual.setText("xmpp:a@Example.COM/r, b@Example.COM")
check("hats manual JIDs are normalised",
      hats.jids() == ["a@example.com", "b@example.com"])
hats.deleteLater()

bookmark = BookmarkDialog(bookmark={}, default_nick="me")
bookmark._room.setText("xmpp:room@conf.example/nick")
check("a bookmark pasted with a full JID has no doubled domain",
      bookmark.collect()["jid"] == "room@conf.example")
bookmark.deleteLater()

create = CreateConferenceDialog(["conf.example"], default_server="conf.example")
_paste(create._address, "xmpp:room@other.example/nick")
check("pasting a full JID fills the create-conference server",
      create._address.text() == "room"
      and create._server.currentText() == "other.example")
_data = create.collect()
check("the create-conference result is split",
      _data["room"] == "room" and _data["server"] == "other.example")
create.deleteLater()

join = JoinConferenceDialog(SimpleNamespace(jid_str="me@example.com"),
                            ["conf.example"], [], room="room",
                            server="conf.example")
join._room.setText("room@other.example")
_join = join.collect()
check("a typed full JID wins in the join dialog",
      _join["room"] == "room" and _join["server"] == "other.example")
join.deleteLater()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All JID-normalisation tests passed.")
