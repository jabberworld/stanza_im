"""Client-capabilities viewer: vCard link, dialog rendering, caps cache.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_client_features.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace

_SCRATCH = tempfile.mkdtemp(prefix="stanza_features_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets  # noqa: E402

from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.ui.resource_tree import resource_tree_html  # noqa: E402

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from stanza_im.core.client import JabberClient  # noqa: E402
from stanza_im.ui.client_features_dialog import (  # noqa: E402
    ClientFeaturesDialog)
from stanza_im.ui.vcard_dialog import VCardInfoDialog  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


BLOCK = {
    "resource": "phone",
    "show": "online",
    "status": "At work",
    "client": "Conversations",
    "version": "2.5.0",
    "os": "Android",
    "tzo": "",
    "caps_node": "https://example.org/caps",
    "full_jid": "alice@example.org/phone",
    "caps_ver": "ver-1",
    "caps_hash": "sha-1",
    "priority": 5,
}

# 1. resource_tree_html links the icon and the resource name ---------------
plain = resource_tree_html([BLOCK])
linked = resource_tree_html(
    [BLOCK], link_prefix="stanza-features:",
    link_title="Show client capabilities")
href = "stanza-features:alice%40example.org%2Fphone"
check("without a prefix the resource tree has no links",
      "<a " not in plain and "phone" in plain)
check("the status icon and the resource name are linked",
      linked.count(f'href="{href}"') == 2 and "phone" in linked)
check("the link carries the hint tooltip",
      'title="Show client capabilities"' in linked)
check("the client block still renders below the link",
      "Conversations" in linked and "At work" in linked)

# 2. vCard Status: a click emits features_requested ------------------------
card = {"jid": "alice@example.org", "fn": "Alice"}
status = {"clients": [BLOCK]}
dialog = VCardInfoDialog("alice@example.org", card, status=status)
seen = []
dialog.features_requested.connect(seen.append)
check("the clients label accepts links",
      bool(dialog._clients_label.textInteractionFlags()
           & QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse))
dialog._clients_label.linkActivated.emit(href)
check("a resource link asks for the client capabilities",
      seen == ["alice@example.org/phone"])
check("the clients label has the click hint",
      bool(dialog._clients_label.toolTip()))

# 3. ClientFeaturesDialog renders features/identities/raw -----------------
features = ["urn:xmpp:jingle:1", "urn:xmpp:ping", "urn:example:debug"]
info = {
    "features": features,
    "identities": [{"category": "client", "type": "phone",
                    "xml_lang": "", "name": "Conversations"}],
    "node": "https://example.org/caps", "ver": "ver-1", "hash": "sha-1",
    "raw": "<query xmlns='http://jabber.org/protocol/disco#info'>"
           "<feature var='urn:xmpp:ping'/></query>",
    "source": "disco",
}
fd = ClientFeaturesDialog(None, "alice@example.org/phone", BLOCK)
fd._render(info)
rows = [fd._features_tree.topLevelItem(i)
        for i in range(fd._features_tree.topLevelItemCount())]
by_ns = {row.text(2): row for row in rows}
check("all announced feature namespaces are listed",
      set(by_ns) == set(features))
check("a known feature is described with its XEP",
      by_ns["urn:xmpp:jingle:1"].text(0) == "XEP-0166"
      and by_ns["urn:xmpp:jingle:1"].text(1) == "Jingle")
check("an unknown feature keeps its namespace",
      by_ns["urn:example:debug"].text(2) == "urn:example:debug")
check("a known feature also keeps its namespace",
      by_ns["urn:xmpp:ping"].text(2) == "urn:xmpp:ping")
check("identities are listed",
      fd._identities_tree.topLevelItemCount() == 1
      and fd._identities_tree.topLevelItem(0).text(2) == "Conversations")
check("the raw tab contains the raw XML",
      "urn:xmpp:ping" in fd._raw.toPlainText()
      and "<query" in fd._raw.toPlainText())
check("the header shows the caps metadata",
      "ver-1" in fd._meta_labels["caps_ver"].text()
      and "disco#info" in fd._meta_labels["source"].text()
      and "sha-1" in fd._meta_labels["caps_hash"].text())
fd._filter.setText("jingle")
hidden = {ns: by_ns[ns].isHidden() for ns in by_ns}
check("the feature filter hides non-matches",
      hidden["urn:example:debug"] and not hidden["urn:xmpp:jingle:1"])
fd._filter.setText("")
check("clearing the filter shows every feature",
      not any(by_ns[ns].isHidden() for ns in by_ns))
fd._on_copy()
check("copy includes the feature namespaces",
      "urn:xmpp:jingle:1" in QtWidgets.QApplication.clipboard().text())

check("the feature/identity counters are formatted",
      fd._counts.text().startswith("Features: 3")
      and "identities: 1" in fd._counts.text()
      and "%(" not in fd._counts.text())

# long values must wrap instead of being clipped to their size hint
long_block = dict(
    BLOCK,
    caps_node="https://psi-im.org/ver/1.5.2286/" + "a" * 64,
    client="Psi+",
    version="1.5.2286 (2026-10-19, 3eac61a5, webengine)",
    os="Linux")
long_dialog = ClientFeaturesDialog(
    None, "alice@example.org/phone", long_block)
long_dialog._render(info)
long_dialog.show()
app.processEvents()
for key, label in long_dialog._meta_labels.items():
    required = (label.heightForWidth(label.width())
                if label.hasHeightForWidth() else label.height())
    check(f"the {key} field is wide enough and not clipped",
          label.width() > 300 and label.height() >= required)
long_dialog.close()

empty = ClientFeaturesDialog(None, "alice@example.org/phone", BLOCK)
empty._render({"features": [], "identities": []})
check("an empty feature list shows the notice",
      not empty._features_empty.isHidden())
check("an empty identity list shows the notice",
      not empty._identities_empty.isHidden())

# 4. caps normalisation and the resource_caps cache path -------------------
class Caps:
    def get_features(self):
        return {"urn:xmpp:jingle:1"}

    def dict_identities(self):
        return [{"category": "client", "type": "phone", "xml_lang": "",
                 "name": "Test"}]

    def get(self, key):
        return "node-1" if key == "node" else None

    xml = None


caps_info = JabberClient._caps_info(Caps())
check("caps info keeps features, identities and node",
      caps_info["features"] == ["urn:xmpp:jingle:1"]
      and caps_info["identities"][0]["name"] == "Test"
      and caps_info["node"] == "node-1"
      and caps_info["source"] == "caps")


class FakeCapsPlugin:
    async def get_verstring(self, jid):
        return "cached-ver"


class FakeClient:
    _known_rooms = set()
    groupchats = {}
    contact_features = {"alice@example.org/phone": {"urn:xmpp:ping"}}
    contact_caps_info = {"alice@example.org/phone": {
        "features": ["urn:xmpp:ping"],
        "identities": [{"category": "client", "type": "phone",
                        "xml_lang": "", "name": "Test"}],
        "node": "node-1", "ver": "cached-ver", "hash": "sha-1",
        "raw": "<query/>", "source": "caps",
    }}

    def __init__(self):
        self.xmpp = SimpleNamespace(plugin={"xep_0115": FakeCapsPlugin()})

    def get_contact(self, bare):
        return SimpleNamespace(resources={
            "phone": {"caps_node": "node-1", "caps_ver": "cached-ver",
                      "caps_hash": "sha-1"}})


async def _caps():
    return await JabberClient.resource_caps(
        FakeClient(), "alice@example.org/phone")


result = asyncio.run(_caps())
check("resource_caps returns the cached feature set",
      result["features"] == ["urn:xmpp:ping"])
check("resource_caps keeps identities, metadata and source",
      result["identities"][0]["name"] == "Test"
      and result["node"] == "node-1" and result["ver"] == "cached-ver"
      and result["hash"] == "sha-1" and result["source"] == "caps")

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All client-features tests passed.")
