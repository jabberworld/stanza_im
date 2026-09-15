"""Offscreen tests for extended-presence PEP support.

Covers XEP-0080 (location), XEP-0107 (mood), XEP-0108 (activity) and XEP-0118
(tune): payload build/parse, the bundled icon packs, PEP event handling and
publishing, the profile "Status" tab, the roster tooltip, the mood/activity
menu and the status-message dialog.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_pep_statuses.py
"""
import asyncio
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_pep_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

import slixmpp

from stanza_im.core.client import JabberClient, ContactInfo
from stanza_im.i18n import load as i18n_load, tr
from stanza_im.include import pep

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── 1. payload build/parse ------------------------------------------------
mood = pep.build_mood("happy", "great day")
parsed = pep.parse_mood(mood)
check("mood round-trip",
      parsed["key"] == "happy" and parsed["text"] == "great day")
check("empty mood clears", len(pep.build_mood("")) == 0)

activity = pep.build_activity("relaxing", "partying")
parsed = pep.parse_activity(activity)
check("activity round-trip",
      parsed["group"] == "relaxing" and parsed["sub"] == "partying")
check("group-only activity",
      pep.parse_activity(pep.build_activity("working"))["group"] == "working")

tune = ET.fromstring(
    "<tune xmlns='%s'><artist>A</artist><title>T</title>"
    "<source>Album</source></tune>" % pep.NS_TUNE)
check("tune parse",
      pep.parse_tune(tune) == {"artist": "A", "title": "T",
                               "source": "Album"})

loc = ET.fromstring(
    "<geoloc xmlns='%s'><locality>Berlin</locality>"
    "<country>DE</country><lat>52.5</lat><lon>13.4</lon></geoloc>"
    % pep.NS_GEOLOC)
check("geoloc parse", pep.parse_geoloc(loc)["locality"] == "Berlin")

# ── 2. summary ------------------------------------------------------------
summary = pep.format_summary({
    "mood": {"key": "happy", "text": ""},
    "activity": {"group": "relaxing", "sub": "partying", "text": ""},
    "tune": {"artist": "A", "title": "T"},
    "location": {"locality": "Berlin", "country": "DE"},
})
check("summary mood", summary["mood"] == tr("mood_happy"))
check("summary activity",
      summary["activity"] == "%s \u203a %s" % (tr("activity_group_relaxing"),
                                               tr("activity_partying")))
check("summary tune", summary["tune"] == "A \u2014 T")
check("summary location", summary["location"] == "Berlin, DE")

# ── 3. icon packs ---------------------------------------------------------
moods = pep.mood_icons()
acts = pep.activity_icons()
check("mood icons discovered", len(moods) >= 60 and "happy" in moods)
check("activity icons discovered",
      "cooking" in acts and "doing_chores" in acts)
check("default mood icon exists", bool(pep.default_icon("mood")))

# ── 4. PEP event handling -------------------------------------------------
client = JabberClient("me@example.com/res", "pw")
events = []
client.on("contact_pep_updated", lambda *a: events.append(a))
msg = slixmpp.Message()
msg["type"] = "headline"
msg["from"] = "bob@example.com/phone"
event = ET.SubElement(msg.xml, "{http://jabber.org/protocol/pubsub#event}event")
items = ET.SubElement(event, "{http://jabber.org/protocol/pubsub#event}items")
items.set("node", pep.NS_MOOD)
item = ET.SubElement(items, "{http://jabber.org/protocol/pubsub#event}item")
mood_el = ET.SubElement(item, "{%s}mood" % pep.NS_MOOD)
ET.SubElement(mood_el, "{%s}happy" % pep.NS_MOOD)
client._maybe_pep_event(msg)
check("pep event stored",
      client.pep_data.get("bob@example.com", {}).get("mood", {}).get("key")
      == "happy")
check("pep event emitted",
      events == [("bob@example.com", "mood",
                  {"key": "happy", "text": ""})])

# ── 4a. bodyless pubsub#event routing (live PEP/MDS delivery) ------------
# slixmpp only fires the `message` event for stanzas with a <body>, so live
# PEP notifications (bodyless <message><event/>) are dropped unless a stanza
# handler routes them. Verify the registered "PEP Event" matcher does this.
from slixmpp.xmlstream.handler import CoroutineCallback

_client2 = JabberClient("me@example.com/res", "pw")
_handlers = {getattr(h, "name", ""): h for h in
             _client2.xmpp._XMLStream__handlers}
check("bodyless PEP handler registered",
      isinstance(_handlers.get("PEP Event"), CoroutineCallback))
check("bodyless PEP handler matches PEP event",
      _handlers["PEP Event"].match(msg))
check("IM handler ignores bodyless PEP event",
      not _handlers["IM"].match(msg))
_events2 = []
_client2.on("contact_pep_updated", lambda *a: _events2.append(a))


async def _run_pep_handler():
    await _handlers["PEP Event"]._pointer(msg)


asyncio.run(_run_pep_handler())
check("routed PEP event stored",
      _client2.pep_data.get("bob@example.com", {}).get("mood", {}).get("key")
      == "happy")
check("routed PEP event emitted",
      _events2 == [("bob@example.com", "mood",
                    {"key": "happy", "text": ""})])
_mds_msg = slixmpp.Message()
_mds_msg["type"] = "headline"
_mds_msg["from"] = "me@example.com/other"
_ev2 = ET.SubElement(_mds_msg.xml,
                     "{http://jabber.org/protocol/pubsub#event}event")
_it2 = ET.SubElement(_ev2,
                     "{http://jabber.org/protocol/pubsub#event}items")
_it2.set("node", "urn:xmpp:mds:displayed:0")
_item2 = ET.SubElement(_it2,
                       "{http://jabber.org/protocol/pubsub#event}item")
_sid = ET.SubElement(_item2, "{urn:xmpp:sid:0}stanza-id")
_sid.set("id", "abc123")
_sid.set("by", "me@example.com")
check("bodyless PEP handler matches MDS event",
      _handlers["PEP Event"].match(_mds_msg))

# ── 5. publishing ---------------------------------------------------------
published = []


async def _fake_publish(node, payload):
    published.append((node, payload.tag))


client._publish_pep = _fake_publish


async def _publish():
    client.publish_mood("happy")
    client.publish_activity("working", "coding")
    await asyncio.sleep(0)


asyncio.run(_publish())
check("mood published",
      (pep.NS_MOOD, "{%s}mood" % pep.NS_MOOD) in published)
check("activity published",
      (pep.NS_ACTIVITY, "{%s}activity" % pep.NS_ACTIVITY) in published)

# ── 6. profile status tab + roster tooltip + bottom bar -------------------
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.vcard_dialog import VCardInfoDialog
from stanza_im.ui.status_message_dialog import StatusMessageDialog

win = MainWindow(app)
win._idle_timer.stop()
win._tray.hide()

mood_actions = win._pep_btn.menu().actions()
check("bottom bar has pep + status buttons",
      win._pep_btn is not None and win._status_msg_btn is not None)
check("pep menu has mood/activity",
      [a.text() for a in mood_actions] == [tr("pep_mood"), tr("pep_activity")])
check("activity submenu has groups",
      len(mood_actions[1].menu().actions()) >= 11)


class _FakeClient:
    def __init__(self):
        self.pep_data = {
            "bob@example.com": {
                "mood": {"key": "happy", "text": ""},
                "tune": {"artist": "A", "title": "T"},
            }
        }
        self.presence = []

    def get_contact(self, jid):
        contact = ContactInfo(jid)
        contact.status = "hello"
        return contact

    def send_presence(self, **kwargs):
        self.presence.append(kwargs)

    def set_client_active(self, *_a):
        pass

    def fetch_pep(self, *_a):
        pass


win._client = _FakeClient()
html, _avatar = win._roster_tooltip("bob@example.com")
check("tooltip shows mood", tr("pep_mood") in html and "happy" in html)
check("tooltip shows tune", tr("pep_now_playing") in html and "A \u2014 T" in html)

win._config.status.message = "my status"
win._send_presence("away")
check("presence includes status message",
      win._client.presence == [{"show": "away", "status": "my status"}])

status_dlg = VCardInfoDialog("bob@example.com", {},
                             status={"mood": "Happy", "tune": "A \u2014 T"})
labels = [w.text() for w in status_dlg.findChildren(QtWidgets.QLabel)]
check("profile status tab shows mood", "Happy" in labels)
check("profile status tab shows tune", "A \u2014 T" in labels)
status_dlg.close()

sm = StatusMessageDialog("old text")
check("status dialog prefilled", sm._edit.toPlainText() == "old text")
sm._edit.setPlainText("new text")
check("status dialog returns text", sm.text() == "new text")
sm.close()

# ── 7. roster mood/activity icons + appearance prefs tabs ----------------
from PyQt6 import QtCore, QtGui
from stanza_im.ui.roster_style import UserItem, RosterStyle
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.preferences import PreferencesDialog
from stanza_im.core.storage import Config

win._roster.clear()
win._client.pep_data["bob@example.com"] = {
    "mood": {"key": "happy", "text": ""},
    "activity": {"group": "working", "sub": "coding"},
}
win._roster.add_user(UserItem(
    jid="bob@example.com", name="Bob",
    group=tr("roster_group_ungrouped")))
win._on_contact_pep_updated(
    "bob@example.com/resource", "mood",
    {"key": "happy", "text": ""})
check("roster mood icon set", win._roster._users[0].mood == "happy")
check("roster activity icon set",
      win._roster._users[0].activity == "coding")
win._client.pep_data["bob@example.com"]["activity"] = {
    "group": "relaxing", "sub": ""}
win._on_contact_pep_updated(
    "bob@example.com", "activity",
    {"group": "relaxing", "sub": ""})
check("roster activity group fallback",
      win._roster._users[0].activity == "relaxing")
win._client.pep_data["bob@example.com"]["mood"] = {
    "key": "", "text": ""}
win._on_contact_pep_updated(
    "bob@example.com", "mood", {"key": "", "text": ""})
check("roster mood icon cleared", win._roster._users[0].mood == "")
win._roster.clear()

style = RosterStyle(show_mood=True, show_activity=True)
img = QtGui.QPixmap(200, 40)
pt = QtGui.QPainter(img)
u = UserItem(jid="bob@example.com", name="Bob",
             group=tr("roster_group_ungrouped"),
             mood="happy", activity="coding")
style.paint_user(pt, u, QtCore.QRect(0, 0, 200, 40), False)
pt.end()
check("roster paint with pep icons ok", not img.isNull())
style.set_options(show_avatars=False, show_activity=False,
                  show_mood=False)
check("roster options toggle off",
      style._show_avatars is False
      and style._show_activity is False
      and style._show_mood is False)
img2 = QtGui.QPixmap(200, 40)
pt2 = QtGui.QPainter(img2)
style.paint_user(pt2, u, QtCore.QRect(0, 0, 200, 40), False)
pt2.end()
check("roster paint without pep icons ok", not img2.isNull())

cfg2 = Config()
p_dlg = PreferencesDialog(cfg2, ChatThemeFactory())
for key in ("roster_show_avatars", "roster_show_activity",
            "roster_show_mood"):
    check(f"prefs roster control {key}", key in p_dlg._controls)
check("prefs roster options default on",
      p_dlg._controls["roster_show_mood"].isChecked()
      and p_dlg._controls["roster_show_avatars"].isChecked())
appearance_tabs = [w for w in p_dlg.findChildren(QtWidgets.QTabWidget)
                   if w.count() >= 3
                   and w.tabText(0) == tr("prefs_appearance_themes")]
check("appearance has roster tab",
      appearance_tabs
      and appearance_tabs[0].tabText(1) == tr("prefs_appearance_roster"))
check("misc tab lasts", appearance_tabs
      and appearance_tabs[0].tabText(
          appearance_tabs[0].count() - 1) == tr("prefs_appearance_misc"))
p_dlg._controls["roster_show_mood"].setChecked(False)
p_dlg._controls["roster_show_avatars"].setChecked(False)
p_dlg._apply_settings()
check("roster prefs applied",
      cfg2.appearance.roster_show_mood is False
      and cfg2.appearance.roster_show_avatars is False
      and cfg2.appearance.roster_show_activity is True)
p_dlg.close()

win.close()

print("\nAll tests passed" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
