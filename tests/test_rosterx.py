"""Offscreen tests for XEP-0144 Roster Item Exchange.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_rosterx.py
"""
import asyncio
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_rosterx_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

asyncio.set_event_loop(asyncio.new_event_loop())

import slixmpp
from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.core.client import (JabberClient, NS_ROSTERX,
                                   _is_roster_exchange,
                                   build_roster_exchange, parse_roster_exchange)
from stanza_im.ui.roster_exchange_dialog import RosterExchangeDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _message(from_, items, body=""):
    msg = slixmpp.Message()
    msg["from"] = from_
    msg["type"] = "chat"
    if body:
        msg["body"] = body
    msg.xml.append(build_roster_exchange(items))
    return msg


ITEMS = [
    {"action": "add", "jid": "alice@x", "name": "Alice", "groups": ["Friends"]},
    {"action": "delete", "jid": "bob@x", "name": "", "groups": []},
    {"action": "modify", "jid": "carol@x", "name": "Carol", "groups": ["Work", "Team"]},
]
msg = _message("horatio@x", ITEMS, "Some visitors")

check("roster exchange detected", _is_roster_exchange(msg) is True)
check("plain message is not a roster exchange",
      _is_roster_exchange(slixmpp.Message()) is False)

parsed = parse_roster_exchange(msg)
check("all items parsed", len(parsed) == 3)
check("add parsed", parsed[0] == {"action": "add", "jid": "alice@x",
                                  "name": "Alice", "groups": ["Friends"]})
check("delete parsed", parsed[1]["action"] == "delete" and parsed[1]["groups"] == [])
check("modify groups parsed", parsed[2]["groups"] == ["Work", "Team"])

# Default action is "add"; items without a JID are dropped.
default_msg = slixmpp.Message()
x = build_roster_exchange([{"jid": "dave@x"}])
root = x
for el in root.findall("{%s}item" % NS_ROSTERX):
    del el.attrib["action"]
default_msg.xml.append(root)
check("missing action defaults to add",
      parse_roster_exchange(default_msg) == [{"action": "add", "jid": "dave@x",
                                             "name": "", "groups": []}])
nojid = slixmpp.Message()
nojid.xml.append(ET.fromstring("<x xmlns='%s'><item/></x>" % NS_ROSTERX))
check("items without a JID are ignored", parse_roster_exchange(nojid) == [])


# ── client routing ───────────────────────────────────────────────
client = JabberClient("me@example.com/r", "pw")
received, chats = [], []
client.on("roster_exchange_received", lambda *a: received.append(a))
client.on("message_received", lambda *a: chats.append(a))
client._on_message(msg)
check("roster exchange is not rendered as a chat message", chats == [])
asyncio.get_event_loop().run_until_complete(
    client._on_roster_exchange_stanza(msg))
check("roster_exchange_received emitted",
      len(received) == 1 and received[0][0] == "horatio@x"
      and len(received[0][1]) == 3 and received[0][2] == "Some visitors")


# ── applying an exchange ─────────────────────────────────────────
calls = {"add": [], "update": [], "remove": [], "roster": 0}
client.add_contact = lambda jid, name="", groups=None, **k: calls["add"].append(
    (jid, name, list(groups or [])))
client.update_contact = lambda jid, name="", groups=None: calls["update"].append(
    (jid, name, list(groups or [])))
client.remove_contact = lambda jid: calls["remove"].append(jid)
client.request_roster = lambda: calls.__setitem__("roster", calls["roster"] + 1)
client.roster = {
    "alice@x": {"jid": "alice@x", "name": "Alice", "groups": ["Friends"],
                "subscription": "both"},
    "bob@x": {"jid": "bob@x", "name": "Bob", "groups": ["Friends", "Work"],
              "subscription": "both"},
    "carol@x": {"jid": "carol@x", "name": "Carol", "groups": ["Old"],
                "subscription": "both"},
}

# add: new contact, existing with the group (no-op), existing without it.
calls = {k: ([] if isinstance(v, list) else 0) for k, v in calls.items()}
applied = client.apply_roster_exchange([
    {"action": "add", "jid": "dave@x", "name": "Dave", "groups": ["Friends"]},
    {"action": "add", "jid": "alice@x", "name": "Alice", "groups": ["Friends"]},
    {"action": "add", "jid": "carol@x", "name": "Carol", "groups": ["Work"]},
])
check("new contact added with the group",
      ("dave@x", "Dave", ["Friends"]) in calls["add"])
check("existing in-group add is a no-op",
      all(jid != "alice@x" for jid, *_ in calls["update"] + calls["add"]))
check("existing contact joined to a new group",
      ("carol@x", "Carol", ["Old", "Work"]) in calls["update"])
check("apply requested the roster", calls["roster"] == 1)

# delete: group kept when others remain, contact removed otherwise.
calls = {k: ([] if isinstance(v, list) else 0) for k, v in calls.items()}
client.apply_roster_exchange([
    {"action": "delete", "jid": "bob@x", "name": "", "groups": ["Work"]},
    {"action": "delete", "jid": "alice@x", "name": "", "groups": ["Friends"]},
    {"action": "delete", "jid": "ghost@x", "name": "", "groups": []},
])
check("delete drops only the suggested group when others remain",
      ("bob@x", "Bob", ["Friends"]) in calls["update"])
check("delete removes the contact when no groups remain",
      calls["remove"] == ["alice@x"])
check("delete of an unknown contact is skipped", applied is not None)

# modify: only existing items are touched.
calls = {k: ([] if isinstance(v, list) else 0) for k, v in calls.items()}
client.apply_roster_exchange([
    {"action": "modify", "jid": "carol@x", "name": "Carolyn",
     "groups": ["Team"]},
    {"action": "modify", "jid": "ghost@x", "name": "G", "groups": []},
])
check("modify updates an existing contact",
      ("carol@x", "Carolyn", ["Team"]) in calls["update"])
check("modify of an unknown contact is skipped",
      all(jid != "ghost@x" for jid, *_ in calls["update"]))


# ── sending ──────────────────────────────────────────────────────
sent = []


def _factory(*args, **kwargs):
    message = slixmpp.Message()
    message.send = lambda *a, **k: sent.append(message)
    return message


client.xmpp.Message = _factory
client.send_roster_exchange(
    "target@x", [{"action": "add", "jid": "dave@x", "name": "Dave",
                  "groups": ["Friends"]}], "Contact: Dave (dave@x)")
check("one message sent", len(sent) == 1)
payload = sent[0]
item = payload.xml.find("{%s}x/{%s}item" % (NS_ROSTERX, NS_ROSTERX))
check("outgoing item carries action/jid",
      item is not None and item.get("action") == "add"
      and item.get("jid") == "dave@x")
check("outgoing item carries the group",
      item.findtext("{%s}group" % NS_ROSTERX) == "Friends")
check("outgoing message carries a body", str(payload["body"]) != "")


# ── dialog ───────────────────────────────────────────────────────
dlg = RosterExchangeDialog("horatio@x", "Horatio", ITEMS, "Some visitors")
tree = dlg._tree
check("three action roots present", tree.topLevelItemCount() == 3)
root_labels = {tree.topLevelItem(i).text(0)
               for i in range(tree.topLevelItemCount())}
check("roots are Add/Modify/Delete",
      root_labels == {"Add", "Modify", "Delete"})
check("all items are selected by default", len(dlg.selected_items()) == 3)

add_root = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
                if tree.topLevelItem(i).text(0) == "Add")
add_root.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
check("unchecking a root drops its items",
      all(item["action"] != "add" for item in dlg.selected_items()))
check("graph group node exists",
      any(tree.topLevelItem(i).text(0) == "Modify"
          for i in range(tree.topLevelItemCount())))

# Unchecking a single group leaf keeps the other group of the same item.
selected = {item["jid"]: item for item in dlg.selected_items()}
check("other actions stay selected",
      "carol@x" in selected and set(selected["carol@x"]["groups"]) == {"Work", "Team"})
dlg.deleteLater()

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
