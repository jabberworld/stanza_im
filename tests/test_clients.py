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

from PyQt6 import QtWidgets

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

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
