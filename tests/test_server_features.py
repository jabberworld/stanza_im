"""Offscreen tests for the server-capabilities report and Help menu.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_server_features.py
"""
import asyncio
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_server_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.core.client import _stream_feature_namespaces
from stanza_im.core.server_features import (
    SERVER_INFO_NODE, SERVER_XEPS, collect_server_features,
    evaluate_server_xeps, parse_server_contacts)
from stanza_im.ui.connection_info_dialog import connection_info_lines

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── preset list ──────────────────────────────────────────────────
_xeps = [entry.xep for entry in SERVER_XEPS]
check("preset holds the server-relevant XEPs",
      {"XEP-0045", "XEP-0198", "XEP-0237", "XEP-0280", "XEP-0313",
       "XEP-0352", "XEP-0363", "XEP-0386", "XEP-0388", "XEP-0402",
       "XEP-0490"} <= set(_xeps))
check("preset is sorted by XEP number", _xeps == sorted(_xeps))
check("no duplicate XEPs in the preset", len(_xeps) == len(set(_xeps)))
check("every entry uses a known source",
      all(entry.source in ("disco", "account", "stream", "commands")
          for entry in SERVER_XEPS))
_entries = {entry.xep: entry for entry in SERVER_XEPS}
check("XEP-0490 checks the server-assist feature only",
      _entries["XEP-0490"].source == "account"
      and _entries["XEP-0490"].keys == ("urn:xmpp:mds:server-assist:0",))
check("XEP-0402 checks the compat features only",
      _entries["XEP-0402"].keys
      == ("urn:xmpp:bookmarks:1#compat",
          "urn:xmpp:bookmarks:1#compat-pep"))
check("XEP-0401 is discovered via ad-hoc commands",
      _entries["XEP-0401"].source == "commands")


# ── stream feature namespace extraction ──────────────────────────
class _FakeFeatures:
    def __init__(self, xml):
        self.xml = xml


_sf = ET.Element("{http://etherx.jabber.org/streams}features")
ET.SubElement(_sf, "{urn:ietf:params:xml:ns:xmpp-bind}bind")
ET.SubElement(_sf, "{urn:xmpp:sm:3}sm")
ET.SubElement(_sf, "{urn:xmpp:features:rosterver}ver")
ET.SubElement(_sf, "{urn:xmpp:csi:0}csi")
check("stream features keep the namespace, not the {ns}tag",
      _stream_feature_namespaces(_FakeFeatures(_sf))
      == {"urn:ietf:params:xml:ns:xmpp-bind", "urn:xmpp:sm:3",
          "urn:xmpp:features:rosterver", "urn:xmpp:csi:0"})


# ── pure evaluation ──────────────────────────────────────────────
empty = {row["xep"]: row for row in evaluate_server_xeps({})}
check("an empty context marks everything unsupported",
      not any(row["supported"] for row in empty.values()))
check("an unsupported upload has no size detail",
      empty["XEP-0363"]["detail"] == "")

ctx = {
    "disco": {"http://jabber.org/protocol/muc", "urn:xmpp:carbons:2",
              "urn:xmpp:http:upload", "urn:xmpp:sid:0"},
    "account": {"http://jabber.org/protocol/pubsub",
                "http://jabber.org/protocol/pubsub#publish-options"},
    "stream": {"urn:xmpp:sm:3", "urn:xmpp:features:rosterver"},
    "commands": {"urn:xmpp:invite#invite"},
    "login": "SCRAM-SHA-256",
    "upload_max": 10 * 1024 * 1024,
}
rows = {row["xep"]: row for row in evaluate_server_xeps(ctx)}
check("a disco feature marks the XEP supported",
      rows["XEP-0045"]["supported"] and rows["XEP-0280"]["supported"])
check("a stream feature marks the XEP supported",
      rows["XEP-0198"]["supported"] and rows["XEP-0237"]["supported"])
check("PEP is read from the account's pubsub features",
      rows["XEP-0163"]["supported"])
check("XEP-0359 is read from the account",
      rows["XEP-0359"]["supported"])
check("XEP-0401 is read from the ad-hoc commands",
      rows["XEP-0401"]["supported"])
check("XEP-0490 stays unsupported without server-assist",
      not rows["XEP-0490"]["supported"])
check("XEP-0402 needs the compat feature",
      not rows["XEP-0402"]["supported"])
check("an absent feature stays unsupported",
      not rows["XEP-0258"]["supported"]
      and not rows["XEP-0386"]["supported"])
check("the upload prefix match accepts the bare namespace",
      rows["XEP-0363"]["supported"])
check("the upload limit is shown as a human size",
      rows["XEP-0363"]["detail"] == "10.0 MB")

assisted = dict(ctx)
assisted["account"] = ctx["account"] | {"urn:xmpp:mds:server-assist:0"}
_assisted = {row["xep"]: row for row in evaluate_server_xeps(assisted)}
check("XEP-0490 is supported with server-assist",
      _assisted["XEP-0490"]["supported"])


# ── collecting from a client ─────────────────────────────────────
NS_DATA = "jabber:x:data"
NS_DISCO_INFO = "http://jabber.org/protocol/disco#info"
UPLOAD_MAX = 25 * 1024 * 1024


def _serverinfo_form(contacts):
    form = ET.Element(f"{{{NS_DATA}}}x", type="result")
    fmt = ET.SubElement(form, f"{{{NS_DATA}}}field", var="FORM_TYPE",
                        type="hidden")
    ET.SubElement(fmt, f"{{{NS_DATA}}}value").text = SERVER_INFO_NODE
    for var, values in contacts.items():
        field = ET.SubElement(form, f"{{{NS_DATA}}}field", var=var,
                              type="list-multi")
        for value in values:
            ET.SubElement(field, f"{{{NS_DATA}}}value").text = value
    return form


def _features_xml(features, server_name="", contacts=None):
    x = ET.Element(f"{{{NS_DISCO_INFO}}}query")
    for var in features:
        ET.SubElement(x, f"{{{NS_DISCO_INFO}}}feature", var=var)
    if server_name:
        ET.SubElement(x, f"{{{NS_DISCO_INFO}}}identity", category="server",
                      type="im", name=server_name)
    if contacts:
        x.append(_serverinfo_form(contacts))
    return x


def _upload_xml(max_size):
    x = ET.Element(f"{{{NS_DISCO_INFO}}}query")
    ET.SubElement(x, f"{{{NS_DISCO_INFO}}}feature",
                  var="urn:xmpp:http:upload:0")
    form = ET.SubElement(x, f"{{{NS_DATA}}}x", type="result")
    field = ET.SubElement(form, f"{{{NS_DATA}}}field", var="max-file-size")
    value = ET.SubElement(field, f"{{{NS_DATA}}}value")
    value.text = str(max_size)
    return x


_MAPPING = {
    "example.com": _features_xml(
        {"http://jabber.org/protocol/commands", "urn:xmpp:blocking",
         "urn:xmpp:mam:2", "urn:xmpp:carbons:2"}, server_name="ejabberd",
        contacts={"abuse-addresses": ["xmpp:abuse@example.com",
                                      "mailto:abuse@example.com"],
                  "support-addresses": ["https://example.com/support"]}),
    "me@example.com": _features_xml(
        {"http://jabber.org/protocol/pubsub",
         "http://jabber.org/protocol/pubsub#publish-options",
         "urn:xmpp:sid:0", "urn:xmpp:bookmarks:1#compat",
         "urn:xmpp:bookmarks-conversion:0",
         "urn:xmpp:pep-vcard-conversion:0"}),
    "conference.example.com": _features_xml(
        {"http://jabber.org/protocol/muc"}),
    "upload.example.com": _upload_xml(UPLOAD_MAX),
}


class _FakeInfo:
    def __init__(self, xml):
        self.xml = xml


class _FakeDisco:
    def __init__(self, mapping):
        self._mapping = mapping

    async def get_info(self, jid=None, node=None):
        return _FakeInfo(self._mapping.get(jid))


class _FakeVersion:
    async def get_version(self, jid):
        return {"software_version": {"name": "ejabberd",
                                     "version": "24.06"}}


class _FakeXmpp:
    def __init__(self, mapping):
        self._disco = _FakeDisco(mapping)
        self.plugin = {"xep_0092": _FakeVersion()}
        self.stream_feature_ns = {"urn:xmpp:sm:3", "urn:xmpp:csi:0"}

    def __getitem__(self, key):
        if key == "xep_0030":
            return self._disco
        raise KeyError(key)


class _FakeClient:
    jid_str = "me@example.com"

    def __init__(self):
        self.xmpp = _FakeXmpp(_MAPPING)

    def connection_info(self):
        return {"sasl": "SCRAM-SHA-256"}

    async def discover_conference_service(self):
        return "conference.example.com"

    async def _http_upload_service(self):
        return "upload.example.com"

    async def get_commands_list(self, jid):
        return [{"jid": jid, "node": "urn:xmpp:invite#invite",
                 "name": "Invite"}]


collected = asyncio.run(collect_server_features(_FakeClient()))
check("collect keeps the domain", collected["domain"] == "example.com")
check("collect merges the domain and component features",
      {"urn:xmpp:blocking", "http://jabber.org/protocol/muc",
       "urn:xmpp:http:upload:0"} <= collected["disco"])
check("collect keeps the account features separately",
      "urn:xmpp:sid:0" in collected["account"]
      and "http://jabber.org/protocol/pubsub" in collected["account"])
check("collect keeps the stream features",
      "urn:xmpp:csi:0" in collected["stream"])
check("collect keeps the ad-hoc command nodes",
      collected["commands"] == {"urn:xmpp:invite#invite"})
check("collect keeps the login mechanism",
      collected["login"] == "SCRAM-SHA-256")
check("collect builds the software string",
      collected["software"] == "ejabberd 24.06")
check("collect keeps the upload limit",
      collected["upload_max"] == UPLOAD_MAX)
check("collect keeps the XEP-0157 server contacts",
      collected["contacts"] == [
          ("abuse-addresses", ["xmpp:abuse@example.com",
                               "mailto:abuse@example.com"]),
          ("support-addresses", ["https://example.com/support"])])

check("server contacts parse in the XEP field order",
      parse_server_contacts(_MAPPING["example.com"]) == collected["contacts"])
check("a missing serverinfo form yields no contacts",
      parse_server_contacts(None) == []
      and parse_server_contacts(ET.Element("iq")) == [])

collected_rows = {row["xep"]: row for row in
                  evaluate_server_xeps(collected)}
check("collected context drives the report",
      collected_rows["XEP-0045"]["supported"]
      and collected_rows["XEP-0313"]["supported"]
      and collected_rows["XEP-0352"]["supported"]
      and collected_rows["XEP-0163"]["supported"]
      and collected_rows["XEP-0401"]["supported"]
      and collected_rows["XEP-0363"]["detail"] == "25.0 MB"
      and not collected_rows["XEP-0490"]["supported"]
      and not collected_rows["XEP-0386"]["supported"])


# ── connection info lines ────────────────────────────────────────
check("no connection yields the not-connected line",
      connection_info_lines(None) == ["Not connected."])
info = {"mode": "starttls", "tls_version": "TLSv1.3", "cipher": "AES",
        "sasl": "SCRAM-SHA-256", "keepalive": True, "sm": "enabled",
        "csi": "active", "host": "xmpp.example.com", "port": 5222}
joined = "\n".join(connection_info_lines(info))
check("connection info lists the mode, SASL and server",
      "STARTTLS" in joined and "SCRAM-SHA-256" in joined
      and "xmpp.example.com:5222" in joined)


# ── dialogs render the report ────────────────────────────────────
from stanza_im.ui.connection_info_dialog import ConnectionInfoDialog  # noqa: E402
from stanza_im.ui.server_info_dialog import ServerInfoDialog  # noqa: E402

conn_dialog = ConnectionInfoDialog(info)
check("the connection dialog shows the info lines",
      "SCRAM-SHA-256" in conn_dialog._text.toPlainText())


async def _dialog_smoke():
    dialog = ServerInfoDialog(_FakeClient())
    for _ in range(5):
        await asyncio.sleep(0)
    return dialog


server_dialog = asyncio.run(_dialog_smoke())
check("the server dialog lists every preset XEP",
      server_dialog._tree.topLevelItemCount() == len(SERVER_XEPS))
check("the server dialog renders the contacts section",
      len(server_dialog._contacts) == 2
      and server_dialog._contacts_box.isVisibleTo(server_dialog))
check("the server dialog header names the software",
      "ejabberd" in server_dialog._header.text()
      and "SCRAM-SHA-256" in server_dialog._header.text())
_first = server_dialog._tree.topLevelItem(0)
check("supported rows are green, unsupported rows are red",
      _first.text(0) == "XEP-0045"
      and _first.foreground(2).color().name() == "#1b8a2f")


# ── static wiring ────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(_root, *parts), encoding="utf-8") as fh:
        return fh.read()


client_src = _read("stanza_im", "core", "client.py")
check("the stream features keep their namespaces",
      "self.stream_feature_ns = _stream_feature_namespaces(features)"
      in client_src)

mw = _read("stanza_im", "ui", "main_window.py")
check("the Help menu wires the three info entries",
      "menu_connection_info" in mw and "menu_certificate_info" in mw
      and "menu_server_info" in mw)
check("the info handlers exist",
      "def _on_connection_info" in mw and "def _on_certificate_info" in mw
      and "def _on_server_info" in mw)
check("the info entries start disabled and follow the session",
      "self._set_info_actions_enabled(False)" in mw
      and "self._set_info_actions_enabled(True)" in mw)
check("the server dialog is opened non-modally",
      "ServerInfoDialog(self._client, self)" in mw
      and "WA_DeleteOnClose" in mw)

prefs = _read("stanza_im", "ui", "preferences.py")
check("the preferences tooltip shares the info lines",
      "connection_info_lines(info)" in prefs)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
