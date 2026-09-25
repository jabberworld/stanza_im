"""Offscreen tests for the caps node -> client icon mapping.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_clients.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_clients_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.core.client import JabberClient, NS_CAPS, _caps_node
from stanza_im.include import clients

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── mapping file / loader ────────────────────────────────────────
entries = clients.load_clients()
check("the mapping file parses into entries", len(entries) > 100)
check("entries are caps<TAB>name<TAB>icon triples",
      all(len(entry) == 3
          and entry[0].startswith(("http://", "https://", "urn:"))
          for entry in entries))

check("a plain caps node maps to its client",
      clients.find_client("http://gajim.org") == ("Gajim", "gajim.png"))
check("the longest prefix wins",
      clients.find_client("http://gajim.org/caps")
      == ("Gajim (old)", "gajim.png"))
check("https nodes are matched too",
      clients.find_client("https://conversations.im")
      == ("Conversations", "conversations.png"))
check("an unknown node yields None",
      clients.find_client("urn:example:unknown") is None)
check("an empty node yields None",
      clients.find_client("") is None and clients.find_client(None) is None)


# ── icon paths ───────────────────────────────────────────────────
check("the mapped icon resolves to a file",
      clients.icon_path("gajim.png", 16).endswith(
          os.path.join("clients", "16x16", "gajim.png")))
check("a missing icon yields an empty path",
      clients.icon_path("nope.png", 16) == "")
check("client_icon_for combines both steps",
      clients.client_icon_for("http://psi-im.org/caps").endswith(
          os.path.join("16x16", "psi.png")))
check("client_icon_for returns empty for unknown nodes",
      clients.client_icon_for("urn:nope") == "")

missing = [entry[2] for entry in entries
           if entry[2] and not clients.icon_path(entry[2], 16)]
check("most mapped icons exist (missing: %s)"
      % (", ".join(sorted(set(missing))[:5]) or "none"),
      len(missing) < len(entries) * 0.25)


# ── caps node extraction / client_icon ───────────────────────────
class _FakePresence:
    def __init__(self, xml):
        self.xml = xml


def _presence_xml(node):
    xml = ET.Element("presence")
    if node:
        ET.SubElement(xml, f"{{{NS_CAPS}}}c", node=node, ver="v", hash="sha-1")
    return xml


check("the caps node is read from the presence",
      _caps_node(_FakePresence(_presence_xml("http://gajim.org")))
      == "http://gajim.org")
check("a presence without caps yields an empty node",
      _caps_node(_FakePresence(_presence_xml(""))) == "")

client = JabberClient.__new__(JabberClient)
client.contacts = {}
client.groupchats = {}
contact = client.get_contact("alice@example.com")
contact.resources["phone"] = {"show": "away", "priority": 5,
                              "caps_node": "urn:unknown"}
contact.resources["desktop"] = {"show": "online", "priority": 1,
                                "caps_node": "http://psi-im.org/caps"}
check("client_icon picks the best resource with a known caps node",
      client.client_icon("alice@example.com").endswith(
          os.path.join("16x16", "psi.png")))
check("client_icon is empty without a known caps node",
      client.client_icon("bob@example.com") == "")

client.groupchats = {"room@conf.example": object()}
check("client_icon is empty for conferences",
      client.client_icon("room@conf.example") == "")

client.roster = {"alice@example.com": {"subscription": "to"}}
check("the roster subscription is exposed",
      client.subscription("alice@example.com") == "to"
      and client.subscription("alice@example.com/phone") == "to")
check("an unknown JID has no subscription",
      client.subscription("bob@example.com") == "")


# ── MUC presence must not pollute a room's resources ─────────────
class _FakePres:
    def __init__(self, xml):
        self.xml = xml

    def __getitem__(self, key):
        return {"from": "room@conf.example/nick", "type": "available"}.get(
            key, "")


muc_xml = ET.Element("presence")
ET.SubElement(muc_xml, "{http://jabber.org/protocol/muc#user}x")
emitted = []
guard_client = JabberClient.__new__(JabberClient)
guard_client.emit = lambda *args: emitted.append(args)
guard_client.presences = {}
guard_client.contacts = {}
guard_client._on_presence(_FakePres(muc_xml))
check("a MUC occupant presence is ignored by _on_presence",
      emitted == [] and guard_client.presences == {})


# ── music icon + MUC sidebar sizing ──────────────────────────────
from stanza_im.include import pep  # noqa: E402
from stanza_im.ui.chat_widget import _FadeLabel, _ParticipantList  # noqa: E402

check("the tune icon exists",
      bool(pep.tune_icon_path()) and os.path.exists(pep.tune_icon_path()))

participants = _ParticipantList()
check("the participant list fills the width (no h-scroll)",
      participants.resizeMode() == QtWidgets.QListView.ResizeMode.Adjust
      and participants.horizontalScrollBarPolicy()
      == QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

fade = _FadeLabel("a very long nickname")
check("the fade label keeps a small minimum width",
      fade.minimumSizeHint().width() < 40
      and fade.sizePolicy().horizontalPolicy()
      == QtWidgets.QSizePolicy.Policy.Ignored)


# ── static wiring ────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(_root, *parts), encoding="utf-8") as fh:
        return fh.read()


style = _read("stanza_im", "ui", "roster_style.py")
check("the roster style draws the client icon after the avatar",
      "client_icon" in style and "_show_clients" in style
      and "CLIENT_ICON_SIZE" in style)
check("the client icon option is in set_options",
      "show_clients" in style)

widget = _read("stanza_im", "ui", "roster_widget.py")
check("the roster widget can update the client icon",
      "def set_client_icon" in widget)

mw = _read("stanza_im", "ui", "main_window.py")
check("the main window applies the client option and tooltip icon",
      'roster_show_clients' in mw and "client_icon_for" in mw
      and "set_client_icon" in mw)

prefs = _read("stanza_im", "ui", "preferences.py")
check("the preferences roster tab has the clients checkbox",
      'roster_show_clients' in prefs
      and 'prefs_roster_show_clients' in prefs)
check("the preferences appearance page has the conferences tab",
      'prefs_appearance_muc' in prefs
      and '"muc_show_avatars"' in prefs and '"muc_show_clients"' in prefs)
check("the dead chat mood/music options are removed",
      '"show_mood"' not in prefs and '"show_music"' not in prefs)

chat_widget = _read("stanza_im", "ui", "chat_widget.py")
check("MUC participant rows can show client icons",
      "client_icon_for" in chat_widget and "_show_muc_clients" in chat_widget
      and "set_muc_participant_options" in chat_widget)
check("the participant tooltip falls back to the caps client name",
      "find_client(caps_node)" in chat_widget)

# ── participant tooltip shows the client (icon + name) ───────────
from stanza_im.ui.chat_widget import ChatWidget  # noqa: E402
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402

cw = ChatWidget("room@conf.example", "Room", ChatThemeFactory(), is_muc=True)
_unknown = "urn:xmpp:client:unknown"
html = cw._participant_tooltip({"nick": "bob", "caps_node": _unknown})
check("an unknown caps node leaves the tooltip without a client line",
      tr_client not in html if (tr_client := __import__(
          "stanza_im.i18n", fromlist=["tr"]).tr("tooltip_client")) else True)
html2 = cw._participant_tooltip(
    {"nick": "bob", "caps_node": "http://psi-im.org/caps"})
check("a known caps node adds the client name to the tooltip",
      "Psi" in html2)
cw.detach()

chat_window = _read("stanza_im", "ui", "chat_window.py")
check("the chat window applies the participant options",
      "set_muc_participant_options" in chat_window)

check("the main window applies the conference options",
      "def _apply_conference_options" in mw
      and "set_muc_participant_options" in mw)
check("MUC rows use the fading nickname label",
      "_FadeLabel" in chat_widget and "setTextColor" in chat_widget)
check("the MUC sidebar width is persisted",
      "muc_participant_width" in _read("stanza_im", "core", "storage.py")
      and "set_muc_participant_width" in chat_window
      and "participant_width_changed" in chat_widget
      and "participant_width_changed" in mw)
check("the roster tooltip and vCard show the subscription",
      "tooltip_subscription" in mw
      and '"subscription"' in _read("stanza_im", "ui", "vcard_dialog.py")
      and "def subscription" in _read("stanza_im", "core", "client.py"))
check("a 1:1 chat applies the peer's call support on open",
      "def _apply_call_support" in mw and "_apply_call_support(jid)" in mw)
check("the block/report menu section is separated",
      'supports_blocking", lambda: False)():\n                menu.addSeparator()'
      in mw)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
