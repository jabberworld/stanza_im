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
from stanza_im.core.server_features import (
    SERVER_XEPS, collect_server_features, evaluate_server_xeps)
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
      all(entry.source in ("disco", "stream") for entry in SERVER_XEPS))


# ── pure evaluation ──────────────────────────────────────────────
empty = {row["xep"]: row for row in evaluate_server_xeps({})}
check("an empty context marks everything unsupported",
      not any(row["supported"] for row in empty.values()))
check("an unsupported upload has no size detail",
      empty["XEP-0363"]["detail"] == "")

ctx = {
    "disco": {"http://jabber.org/protocol/muc", "urn:xmpp:carbons:2",
              "urn:xmpp:http:upload", "jabber:iq:register"},
    "stream": {"urn:xmpp:sm:3", "urn:xmpp:features:rosterver"},
    "login": "SCRAM-SHA-256",
    "upload_max": 10 * 1024 * 1024,
}
rows = {row["xep"]: row for row in evaluate_server_xeps(ctx)}
check("a disco feature marks the XEP supported",
      rows["XEP-0045"]["supported"] and rows["XEP-0280"]["supported"])
check("a stream feature marks the XEP supported",
      rows["XEP-0198"]["supported"] and rows["XEP-0237"]["supported"])
check("an absent feature stays unsupported",
      not rows["XEP-0258"]["supported"]
      and not rows["XEP-0386"]["supported"])
check("the upload prefix match accepts the bare namespace",
      rows["XEP-0363"]["supported"])
check("the upload limit is shown as a human size",
      rows["XEP-0363"]["detail"] == "10.0 MB")


# ── collecting from a client ─────────────────────────────────────
NS_DATA = "jabber:x:data"
NS_DISCO_INFO = "http://jabber.org/protocol/disco#info"


def _disco_xml():
    x = ET.Element(f"{{{NS_DISCO_INFO}}}query")
    for var in ("http://jabber.org/protocol/muc", "urn:xmpp:blocking",
                "urn:xmpp:mam:2", "urn:xmpp:sid:0"):
        ET.SubElement(x, f"{{{NS_DISCO_INFO}}}feature", var=var)
    ET.SubElement(x, f"{{{NS_DISCO_INFO}}}identity", category="server",
                  type="im", name="ejabberd")
    return x


class _FakeInfo:
    def __init__(self, xml):
        self.xml = xml


class _FakeDisco:
    async def get_info(self, jid=None):
        return _FakeInfo(_disco_xml())


class _FakeVersion:
    async def get_version(self, jid):
        return {"software_version": {"name": "ejabberd",
                                     "version": "24.06"}}


class _FakeXmpp:
    def __init__(self):
        self.plugin = {"xep_0092": _FakeVersion()}
        self.stream_feature_ns = {"urn:xmpp:sm:3", "urn:xmpp:csi:0"}

    def __getitem__(self, key):
        if key == "xep_0030":
            return _FakeDisco()
        raise KeyError(key)


class _FakeClient:
    jid_str = "me@example.com"

    def __init__(self):
        self.xmpp = _FakeXmpp()

    def connection_info(self):
        return {"sasl": "SCRAM-SHA-256"}

    async def http_upload_limit(self):
        return 25 * 1024 * 1024


collected = asyncio.run(collect_server_features(_FakeClient()))
check("collect keeps the domain", collected["domain"] == "example.com")
check("collect keeps the disco features",
      {"urn:xmpp:blocking", "urn:xmpp:mam:2"} <= collected["disco"])
check("collect keeps the stream features",
      "urn:xmpp:csi:0" in collected["stream"])
check("collect keeps the login mechanism",
      collected["login"] == "SCRAM-SHA-256")
check("collect builds the software string",
      collected["software"] == "ejabberd 24.06")
check("collect keeps the upload limit",
      collected["upload_max"] == 25 * 1024 * 1024)

collected_rows = {row["xep"]: row for row in
                  evaluate_server_xeps(collected)}
check("collected context drives the report",
      collected_rows["XEP-0191"]["supported"]
      and collected_rows["XEP-0313"]["supported"]
      and collected_rows["XEP-0352"]["supported"]
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
