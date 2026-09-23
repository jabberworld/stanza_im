"""Offscreen tests for the service browser info dialog and feature mapping.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_service_browser.py
"""
import asyncio
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_service_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.core.client import (
    NS_DISCO_INFO, NS_LAST, NS_STATS, JabberClient)
from stanza_im.core.server_features import (
    describe_feature, describe_features, service_details)

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── feature -> XEP mapping ───────────────────────────────────────
check("a known feature maps to its XEP",
      describe_feature("jabber:iq:version") == "XEP-0092: Software Version")
check("a sub-feature maps by prefix",
      describe_feature("http://jabber.org/protocol/pubsub#access-open")
      == "XEP-0060: Publish-Subscribe")
check("a namespaced feature maps to its XEP",
      describe_feature("urn:xmpp:mam:2")
      == "XEP-0313: Message Archive Management")
check("an unknown feature is shown verbatim",
      describe_feature("urn:example:unknown") == "urn:example:unknown")
check("features are sorted and de-duplicated",
      describe_features(["urn:xmpp:mam:2", "jabber:iq:version",
                         "urn:xmpp:mam:1", "zzz"])
      == ["XEP-0092: Software Version", "XEP-0313: Message Archive Management",
          "zzz"])


# ── XEP-0039 statistics / XEP-0012 uptime ────────────────────────
class _Result:
    def __init__(self, xml):
        self.xml = xml


class _FakeIq:
    def __init__(self, owner):
        self.xml = ET.Element("iq")
        self.attrs = {}
        self._owner = owner

    def __setitem__(self, key, value):
        self.attrs[key] = value

    def __getitem__(self, key):
        return self.attrs.get(key)

    async def send(self, *args, **kwargs):
        return _Result(self._owner._results.pop(0))


class _FakeXmpp:
    def __init__(self, results):
        self._results = list(results)
        self.sent = []

    def Iq(self):
        iq = _FakeIq(self)
        self.sent.append(iq)
        return iq


def _stats_list_xml():
    x = ET.Element("iq")
    query = ET.SubElement(x, f"{{{NS_STATS}}}query")
    for name in ("time/uptime", "users/online"):
        ET.SubElement(query, f"{{{NS_STATS}}}stat").set("name", name)
    return x


def _stats_values_xml():
    x = ET.Element("iq")
    query = ET.SubElement(x, f"{{{NS_STATS}}}query")
    ET.SubElement(query, f"{{{NS_STATS}}}stat", name="time/uptime",
                  units="seconds", value="3054635")
    ET.SubElement(query, f"{{{NS_STATS}}}stat", name="users/online",
                  units="users", value="365")
    return x


stats_client = JabberClient.__new__(JabberClient)
stats_client.xmpp = _FakeXmpp([_stats_list_xml(), _stats_values_xml()])
stats = asyncio.run(stats_client.get_server_stats("example.com"))
check("statistics are requested by name and parsed",
      stats == [{"name": "time/uptime", "units": "seconds",
                 "value": "3054635"},
                {"name": "users/online", "units": "users", "value": "365"}])

uptime_xml = ET.Element("iq")
ET.SubElement(uptime_xml, f"{{{NS_LAST}}}query").set("seconds", "3054635")
uptime_client = JabberClient.__new__(JabberClient)
uptime_client.xmpp = _FakeXmpp([uptime_xml])
check("uptime is parsed from jabber:iq:last",
      asyncio.run(uptime_client.get_server_uptime("example.com")) == 3054635)

empty_client = JabberClient.__new__(JabberClient)
empty_client.xmpp = _FakeXmpp([ET.Element("iq")])
check("no statistics yields an empty list",
      asyncio.run(empty_client.get_server_stats("example.com")) == [])


class _RaisingIq:
    def __init__(self):
        self.xml = ET.Element("iq")
        self.attrs = {}

    def __setitem__(self, key, value):
        self.attrs[key] = value

    async def send(self, *args, **kwargs):
        raise RuntimeError("service-unavailable")


class _RaisingXmpp:
    def Iq(self):
        return _RaisingIq()


fail_client = JabberClient.__new__(JabberClient)
fail_client.xmpp = _RaisingXmpp()
check("a failing uptime query is swallowed",
      asyncio.run(fail_client.get_server_uptime("example.com")) is None)
check("a failing statistics query is swallowed",
      asyncio.run(fail_client.get_server_stats("example.com")) == [])


# ── service_details (features + XEP-0157 contacts) ───────────────
NS_DATA = "jabber:x:data"
SERVER_INFO = "http://jabber.org/network/serverinfo"


def _service_xml():
    x = ET.Element(f"{{{NS_DISCO_INFO}}}query")
    for var in ("jabber:iq:version", "http://jabber.org/protocol/stats",
                "jabber:iq:last"):
        ET.SubElement(x, f"{{{NS_DISCO_INFO}}}feature", var=var)
    ET.SubElement(x, f"{{{NS_DISCO_INFO}}}identity", category="server",
                  type="im", name="ejabberd")
    form = ET.SubElement(x, f"{{{NS_DATA}}}x", type="result")
    fmt = ET.SubElement(form, f"{{{NS_DATA}}}field", var="FORM_TYPE",
                        type="hidden")
    ET.SubElement(fmt, f"{{{NS_DATA}}}value").text = SERVER_INFO
    abuse = ET.SubElement(form, f"{{{NS_DATA}}}field",
                          var="abuse-addresses", type="list-multi")
    ET.SubElement(abuse, f"{{{NS_DATA}}}value").text = "xmpp:abuse@example.com"
    return x


class _FakeDisco:
    def __init__(self, xml):
        self._xml = xml

    async def get_info(self, jid=None, node=None):
        return _Result(self._xml)


class _DetailsXmpp:
    def __init__(self, xml):
        self._xml = xml

    def __getitem__(self, key):
        return _FakeDisco(self._xml)


details_client = JabberClient.__new__(JabberClient)
details_client.xmpp = _DetailsXmpp(_service_xml())
details = asyncio.run(service_details(details_client, "example.com"))
check("service_details returns the features and contacts",
      "jabber:iq:version" in details["features"]
      and details["contacts"] == [("abuse-addresses",
                                   ["xmpp:abuse@example.com"])]
      and details["identity"]["name"] == "ejabberd")


# ── dialog smoke ─────────────────────────────────────────────────
class _FakeVersion:
    async def get_version(self, jid):
        return {"software_version": {"name": "ejabberd", "version": "24.06",
                                     "os": "Linux"}}


class _DialogXmpp(_DetailsXmpp):
    def __init__(self, xml):
        super().__init__(xml)
        self._results = [_stats_list_xml(), _stats_values_xml(), uptime_xml]

    def __getitem__(self, key):
        if key == "xep_0030":
            return _FakeDisco(self._xml)
        if key == "xep_0092":
            return _FakeVersion()
        raise KeyError(key)

    def Iq(self):
        return _FakeIq(self)


class _DialogClient:
    jid_str = "me@example.com"

    def __init__(self):
        self.xmpp = _DialogXmpp(_service_xml())

    async def get_entity_version(self, jid):
        info = await self.xmpp["xep_0092"].get_version(jid)
        version = info["software_version"]
        return {"software": version["name"], "version": version["version"],
                "os": version["os"]}

    async def get_server_stats(self, jid):
        return await JabberClient.get_server_stats(self, jid)

    async def _server_stat_names(self, jid):
        return await JabberClient._server_stat_names(self, jid)

    async def get_server_uptime(self, jid):
        return await JabberClient.get_server_uptime(self, jid)


from stanza_im.ui.service_info_dialog import ServiceInfoDialog  # noqa: E402
from stanza_im.ui.service_browser import ServiceBrowserDialog  # noqa: E402


async def _dialog_smoke():
    dialog = ServiceInfoDialog(_DialogClient(), "example.com")
    for _ in range(6):
        await asyncio.sleep(0)
    return dialog


dialog = asyncio.run(_dialog_smoke())
check("the info dialog has the three tabs",
      dialog._tabs.count() == 3
      and dialog._tabs.tabText(0) == "Information"
      and dialog._tabs.tabText(1) == "Capabilities"
      and dialog._tabs.tabText(2) == "Contacts")
info_text = dialog._info_edit.toPlainText()
check("the information tab shows version, stats and uptime",
      "ejabberd" in info_text and "time/uptime" in info_text
      and "3054635" in info_text)
check("the information tab shows the entity category/type",
      "Entity:" in info_text and "server / im" in info_text)
check("the capabilities tab maps features to XEPs",
      "XEP-0092: Software Version" in dialog._caps_edit.toPlainText())
check("the contacts tab lists the XEP-0157 address",
      dialog._contacts == [("abuse-addresses", ["xmpp:abuse@example.com"])])

dialog._tabs.setCurrentIndex(1)
dialog._on_copy()
check("copy uses the active tab",
      QtWidgets.QApplication.clipboard().text()
      == dialog._caps_edit.toPlainText())


# ── static wiring ────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(_root, *parts), encoding="utf-8") as fh:
        return fh.read()


browser = _read("stanza_im", "ui", "service_browser.py")
check("the browser button is renamed and gets an info button",
      "service_browse_action" in browser and "info.svg" in browser
      and "def _open_info" in browser)
check("the browser forwards xmpp: contact links",
      "xmpp_uri_requested" in browser
      and "dialog.contact_uri_clicked.connect(self.xmpp_uri_requested.emit)"
      in browser)
check("weather gateways get the weather icon",
      ServiceBrowserDialog._icon_for(
          None, {"category": "gateway", "type": "weather"})
      == "weather-online.png")
check("rss gateways keep the rss icon",
      ServiceBrowserDialog._icon_for(
          None, {"category": "gateway", "type": "rss"})
      == "rss-online.png")

mw = _read("stanza_im", "ui", "main_window.py")
check("the main window routes the browser's xmpp: links",
      "dlg.xmpp_uri_requested.connect(self._on_xmpp_uri)" in mw)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
