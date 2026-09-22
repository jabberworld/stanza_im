"""Offscreen tests for XEP-0016 privacy lists / XEP-0191 blocking / XEP-0377.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_privacy.py
"""
import asyncio
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_privacy_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.core import privacy
from stanza_im.core.client import (
    NS_BLOCKING, NS_PRIVACY, NS_REPORTING, JabberClient)

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── XEP-0016 parsing ─────────────────────────────────────────────
_lists_xml = ET.fromstring(
    '<iq><query xmlns="jabber:iq:privacy">'
    '<active name="blocked"/><default name="blocked"/>'
    '<list name="blocked"/><list name="friends"/></query></iq>')
lists = privacy.parse_lists(_lists_xml)
check("lists parse active/default/names",
      lists == {"active": "blocked", "default": "blocked",
                "lists": ["blocked", "friends"]})

_list_xml = ET.fromstring(
    '<iq><query xmlns="jabber:iq:privacy"><list name="blocked">'
    '<item type="jid" order="110" action="deny" value="a@b">'
    '<presence-in/><message/><presence-out/></item>'
    '<item type="jid" order="120" action="deny" value="c@d"/>'
    '</list></query></iq>')
items = privacy.parse_list(_list_xml, "blocked")
check("items parse type/value/action/order",
      items[0]["type"] == "jid" and items[0]["value"] == "a@b"
      and items[0]["action"] == "deny" and items[0]["order"] == 110)
check("item stanza flags parse",
      items[0]["message"] and items[0]["presence_in"]
      and items[0]["presence_out"] and not items[0]["iq"])
check("an item without children means all stanzas",
      not any(items[1][key] for key in
              ("message", "iq", "presence_in", "presence_out")))


# ── XEP-0016 building ────────────────────────────────────────────
built = privacy.list_query("blocked", items)
tags = [el.tag for el in built.iter()]
check("the list query uses the privacy namespace",
      built.tag == f"{{{NS_PRIVACY}}}query"
      and f"{{{NS_PRIVACY}}}list" in tags)
check("presence-out is written (slixmpp writes presence-in)",
      f"{{{NS_PRIVACY}}}presence-out" in tags
      and f"{{{NS_PRIVACY}}}presence-in" in tags)
check("the active query carries the name",
      privacy.active_query("blocked").find(
          f"{{{NS_PRIVACY}}}active").get("name") == "blocked")
check("an empty list query removes the list",
      len(list(privacy.list_query("x", []))) == 1
      and len(list(privacy.list_query("x", []).find(
          f"{{{NS_PRIVACY}}}list"))) == 0)
check("a new item goes before the existing ones",
      privacy.next_order(items) == 100 and privacy.next_order([]) == 100)
check("items sort by ascending order",
      [i["order"] for i in privacy.sort_items(
          [{"order": 130}, {"order": 110}, {"order": 120}])]
      == [110, 120, 130])


# ── client: feature gates ────────────────────────────────────────
client = JabberClient.__new__(JabberClient)
client._server_features = None
check("feature gates are optimistic before the probe",
      client.supports_privacy() and client.supports_blocking()
      and client.supports_reports())
client._server_features = {NS_PRIVACY, NS_BLOCKING}
check("feature gates follow the probed features",
      client.supports_privacy() and client.supports_blocking()
      and not client.supports_reports())


# ── client: blocklist pushes ─────────────────────────────────────
class _Jid:
    def __init__(self, value):
        self._value = value

    def __str__(self):
        return self._value


class _PushIq:
    def __init__(self, items):
        self._items = items

    def __getitem__(self, key):
        return {"items": self._items}


events = []
client.emit = lambda name, *args: events.append((name, args))
client._apply_block_push(_PushIq([{"jid": _Jid("a@b")},
                                  {"jid": _Jid("c@d")}]), "block")
check("a block push replaces the blocklist",
      client._blocked == {"a@b", "c@d"}
      and events[-1] == ("blocklist_updated", ({"a@b", "c@d"},)))
client._apply_block_push(_PushIq([]), "unblock")
check("an unblock push clears the blocklist", client._blocked == set())


# ── client: block/unblock/report ─────────────────────────────────
class _FakeBlocking:
    def __init__(self):
        self.calls = []

    async def block(self, jid):
        self.calls.append(("block", str(jid)))

    async def unblock(self, jid):
        self.calls.append(("unblock", str(jid)))


class _FakeReports:
    SPAM = "urn:xmpp:reporting:spam"
    ABUSE = "urn:xmpp:reporting:abuse"


class _FakeIq:
    def __init__(self):
        self.xml = ET.Element("iq")
        self.attrs = {}

    def __setitem__(self, key, value):
        self.attrs[key] = value

    def __getitem__(self, key):
        return self.attrs.get(key)

    async def send(self, *args, **kwargs):
        return None


class _FakeXmpp:
    def __init__(self):
        self.plugins = {"xep_0191": _FakeBlocking(),
                        "xep_0377": _FakeReports()}
        self.sent = []

    def __getitem__(self, key):
        return self.plugins[key]

    def Iq(self):
        iq = _FakeIq()
        self.sent.append(iq)
        return iq


client.xmpp = _FakeXmpp()
client._blocked = set()
asyncio.run(client.block_contact("a@b"))
check("block_contact calls XEP-0191 and records the JID",
      client.xmpp["xep_0191"].calls == [("block", "a@b")]
      and client._blocked == {"a@b"})
asyncio.run(client.unblock_contact("a@b"))
check("unblock_contact calls XEP-0191 and drops the JID",
      client.xmpp["xep_0191"].calls[-1] == ("unblock", "a@b")
      and client._blocked == set())

asyncio.run(client.report_contact("spam@b", "spam", "stop it"))
report = client.xmpp.sent[-1].xml.find(
    f"{{{NS_BLOCKING}}}block/{{{NS_BLOCKING}}}item/{{{NS_REPORTING}}}report")
check("report_contact blocks with a report element",
      client.xmpp.sent[-1].xml.find(f"{{{NS_BLOCKING}}}block") is not None
      and report is not None
      and report.get("reason") == "urn:xmpp:reporting:spam")
text = report.find(f"{{{NS_REPORTING}}}text")
check("report_contact carries the optional text with xml:lang",
      text is not None and text.text == "stop it"
      and text.get("{http://www.w3.org/XML/1998/namespace}lang") != "")
asyncio.run(client.report_contact("abuse@b", "abuse"))
abuse = client.xmpp.sent[-1].xml.find(
    f"{{{NS_BLOCKING}}}block/{{{NS_BLOCKING}}}item/{{{NS_REPORTING}}}report")
check("report_contact maps the abuse reason",
      abuse.get("reason") == "urn:xmpp:reporting:abuse")

# ── UI: rule description / dialogs ───────────────────────────────
from stanza_im.ui.privacy_rule_dialog import (  # noqa: E402
    PrivacyRuleDialog, describe_item)
from stanza_im.ui.privacy_lists_dialog import PrivacyListsDialog  # noqa: E402
from stanza_im.ui.blocked_contacts_dialog import (  # noqa: E402
    BlockedContactsDialog)
from stanza_im.ui.report_dialog import ReportDialog  # noqa: E402
from stanza_im.ui.roster_style import UserItem  # noqa: E402
from stanza_im.ui.roster_widget import RosterWidget  # noqa: E402

described = describe_item(
    {"type": "jid", "value": "a@b", "action": "deny", "order": 1,
     "message": True, "iq": False, "presence_in": True, "presence_out": True})
check("a rule is described in words",
      'JID "a@b"' in described and "deny" in described
      and "messages" in described)
check("a rule without stanza flags means all",
      describe_item({"type": "jid", "value": "c@d", "action": "deny"})
      .endswith("all"))
check("an all-JID rule has no type value",
      describe_item({"type": "", "value": "", "action": "allow"})
      .startswith("If all"))

rule = PrivacyRuleDialog(["a@b"], ["Friends"])
rule._set_type("jid")
rule._value.setCurrentText("a@b")
rule._checks["message"].setChecked(True)
built_rule = rule.result_item()
check("the rule dialog builds a JID deny rule",
      built_rule["type"] == "jid" and built_rule["value"] == "a@b"
      and built_rule["action"] == "deny" and built_rule["message"]
      and not built_rule["iq"])
rule._set_type("subscription")
rule._value.setCurrentIndex(3)
check("the subscription value maps to both",
      rule.result_item()["value"] == "both")
rule._set_type("")
check("the all type disables the value widget",
      rule._value.isEnabled() is False and rule.result_item()["type"] == "")

check("the report dialog defaults to spam",
      ReportDialog("a@b").reason() == "spam")


class _FakePrivacyClient:
    def __init__(self):
        self._blocked = {"a@b"}
        self.active = "blocked"
        self.lists = ["blocked", "friends"]
        self.items = {
            "blocked": [{"type": "jid", "value": "a@b", "action": "deny",
                         "order": 110, "message": True, "iq": False,
                         "presence_in": True, "presence_out": True}],
            "friends": [],
        }
        self.calls = []

    async def get_privacy_lists(self):
        return {"active": self.active, "default": "",
                "lists": list(self.lists)}

    async def get_privacy_list(self, name):
        return list(self.items.get(name, []))

    async def set_privacy_list(self, name, items):
        self.calls.append(("set", name))
        self.items[name] = list(items)

    async def remove_privacy_list(self, name):
        self.calls.append(("remove", name))
        self.items.pop(name, None)

    async def set_active_privacy_list(self, name):
        self.calls.append(("active", name))
        self.active = name

    def get_roster_snapshot(self):
        return [{"jid": "a@b", "name": "Alice", "groups": ["Friends"]},
                {"jid": "c@d", "name": "", "groups": []}]

    def supports_reports(self):
        return True

    def supports_blocking(self):
        return True

    async def get_blocked_jids(self):
        return set(self._blocked)

    async def block_contact(self, jid):
        self._blocked.add(str(jid))

    async def unblock_contact(self, jid):
        self._blocked.discard(str(jid))

    async def report_contact(self, jid, reason, text):
        self.calls.append(("report", jid, reason, text))


async def _privacy_dialog_smoke():
    dialog = PrivacyListsDialog(_FakePrivacyClient())
    for _ in range(6):
        await asyncio.sleep(0)
    return dialog


privacy_dialog = asyncio.run(_privacy_dialog_smoke())
check("the privacy dialog lists the server lists",
      privacy_dialog._list_combo.count() == 2
      and privacy_dialog._active_combo.findData("blocked") >= 0)
check("the privacy dialog renders the localized rules",
      privacy_dialog._rules.count() == 1
      and 'JID "a@b"' in privacy_dialog._rules.item(0).text())


async def _blocked_dialog_smoke():
    dialog = BlockedContactsDialog(_FakePrivacyClient())
    for _ in range(3):
        await asyncio.sleep(0)
    return dialog


blocked_dialog = asyncio.run(_blocked_dialog_smoke())
check("the blocked dialog lists the blocked JID with its roster name",
      blocked_dialog._list.count() == 1
      and "Alice" in blocked_dialog._list.item(0).text())


# ── UI: roster strikethrough state ───────────────────────────────
widget = RosterWidget()
widget.add_user(UserItem(jid="a@b", name="Alice", group="G1"))
widget.add_user(UserItem(jid="a@b", name="Alice", group="G2"))
widget.set_blocked("a@b", True)
check("set_blocked marks every row of the contact",
      all(user.blocked for user in widget._users if user.jid == "a@b"))
widget.set_blocked("a@b", False)
check("set_blocked clears the state",
      not any(user.blocked for user in widget._users))


# ── static wiring ────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(_root, *parts), encoding="utf-8") as fh:
        return fh.read()


prefs = _read("stanza_im", "ui", "preferences.py")
check("the preferences connection page has the two privacy buttons",
      "_btn_privacy_lists" in prefs and "_btn_blocked" in prefs
      and "_on_privacy_lists" in prefs and "_on_blocked_contacts" in prefs)

mw = _read("stanza_im", "ui", "main_window.py")
check("the roster menu blocks/reports contacts",
      "ctx_block" in mw and "ctx_report" in mw
      and "def _on_toggle_block" in mw and "def _on_report_contact" in mw)
check("the blocklist push updates the roster",
      "def _on_blocklist_updated" in mw
      and 'c.on("blocklist_updated"' in mw)

style = _read("stanza_im", "ui", "roster_style.py")
check("blocked contacts are struck through", "setStrikeOut(True)" in style)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
