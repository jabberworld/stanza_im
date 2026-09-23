"""Connection preferences tests: priority mapping, config round-trip,
manual values preserved when switching to auto (no network required).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_connection_prefs.py
"""
import asyncio
import ast
import hashlib
import inspect
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_conn_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtGui, QtWidgets
from stanza_im.core.storage import Config
from stanza_im.core.client import (JabberClient, tls_flags, order_tls_first,
                                    filter_plus_mechs)
from stanza_im.i18n import load as load_i18n
from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.preferences import PreferencesDialog
from stanza_im.ui.certificate_dialog import CertificateDialog, certificate_lines

load_i18n("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


# ── status-dependent priority ─────────────────────────────────────

def priority(mode, value, show):
    client = object.__new__(JabberClient)
    client.priority_mode = mode
    client.priority = value
    return client._effective_priority(show)


check("status: online -> 50", priority("status", 0, "online") == 50)
check("status: chat -> 50", priority("status", 0, "chat") == 50)
check("status: away -> 40", priority("status", 0, "away") == 40)
check("status: xa -> 30", priority("status", 0, "xa") == 30)
check("status: dnd -> 0", priority("status", 0, "dnd") == 0)
check("status: default/None -> 50", priority("status", 0, None) == 50)
check("manual: uses the value", priority("manual", 77, "away") == 77)
check("manual: clamps high", priority("manual", 999, "online") == 127)
check("manual: clamps low", priority("manual", -999, "online") == -128)


# ── tls_flags: TLS / STARTTLS selector mapping ────────────────────

direct = tls_flags("direct", "always")
check("direct: only direct TLS",
      direct == {"enable_direct_tls": True, "enable_starttls": False,
                 "enable_plaintext": False, "require_starttls": False})

prefer_always = tls_flags("prefer", "always")
check("prefer+always: direct first, STARTTLS required",
      prefer_always["enable_direct_tls"] and prefer_always["enable_starttls"]
      and not prefer_always["enable_plaintext"]
      and prefer_always["require_starttls"])

prefer_if = tls_flags("prefer", "opportunistic")
check("prefer+opportunistic: plaintext allowed",
      prefer_if["enable_direct_tls"] and prefer_if["enable_starttls"]
      and prefer_if["enable_plaintext"]
      and not prefer_if["require_starttls"])

prefer_never = tls_flags("prefer", "never")
check("prefer+never: direct TLS then plaintext",
      prefer_never["enable_direct_tls"] and not prefer_never["enable_starttls"]
      and prefer_never["enable_plaintext"])

normal = tls_flags("normal", "always")
check("normal: no direct TLS",
      not normal["enable_direct_tls"] and normal["enable_starttls"]
      and not normal["enable_plaintext"] and normal["require_starttls"])

normal_never = tls_flags("normal", "never")
check("normal+never: plaintext only",
      not normal_never["enable_direct_tls"]
      and not normal_never["enable_starttls"]
      and normal_never["enable_plaintext"])

_records = [("xmpp-client", "h", "1.2.3.4", 5222),
            ("xmpps-client", "h", "1.2.3.4", 5223)]
_ordered = order_tls_first(_records, {"xmpps-client"})
check("SRV order: direct TLS record first",
      _ordered[0][0] == "xmpps-client" and _ordered[1][0] == "xmpp-client")
check("SRV order: no tls services -> unchanged",
      order_tls_first(_records, set()) == _records)


# ── filter_plus_mechs: SCRAM-*-PLUS only when binding works ───────

_mechs = {"PLAIN", "SCRAM-SHA-1-PLUS", "SCRAM-SHA-1"}
check("mechs: TLS1.3 without tls-exporter drops -PLUS",
      filter_plus_mechs(_mechs, "TLSv1.3", ["tls-unique"])
      == {"PLAIN", "SCRAM-SHA-1"})
check("mechs: TLS1.3 with tls-exporter keeps -PLUS",
      filter_plus_mechs(_mechs, "TLSv1.3", ["tls-unique", "tls-exporter"])
      == _mechs)
check("mechs: TLS1.2 keeps -PLUS (tls-unique)",
      filter_plus_mechs(_mechs, "TLSv1.2", ["tls-unique"]) == _mechs)


# ── connection_info: mode / TLS / SASL / keepalive ────────────────

from types import SimpleNamespace


class _FakeXmpp:
    def __init__(self, features, sock=None):
        self.features = features
        self.socket = sock
        self.custom_address = ("xmpp.linuxoid.in", 5223)
        self.boundjid = SimpleNamespace(domain="linuxoid.in")
        self.default_domain = "linuxoid.in"
        self.default_port = 5222
        self.plugin = {"feature_mechanisms": SimpleNamespace(
            mech=SimpleNamespace(name="SCRAM-SHA-1-PLUS"))}


def _info(features, sock):
    client = object.__new__(JabberClient)
    client.xmpp = _FakeXmpp(features, sock)
    client.keepalive = True
    client.stream_management = False
    client.csi = False
    return client.connection_info()


info_plain = _info(set(), object())
check("info: no TLS -> plain", info_plain["mode"] == "plain")
check("info: SASL mechanism reported", info_plain["sasl"] == "SCRAM-SHA-1-PLUS")
check("info: keepalive reported", info_plain["keepalive"] is True)
check("info: server reported",
      info_plain["host"] == "xmpp.linuxoid.in" and info_plain["port"] == 5223)

info_st = _info({"starttls"}, object())
check("info: STARTTLS detected", info_st["mode"] == "starttls")


class _FakeTlsSocket:
    _CERT = {
        "subject": ((("commonName", "xmpp.linuxoid.in"),),
                    (("organizationName", "Linuxoid"),)),
        "issuer": ((("commonName", "Test CA"),),
                   (("organizationName", "CA Org"),)),
        "notBefore": "Jan  1 00:00:00 2020 GMT",
        "notAfter": "Jan  1 00:00:00 2030 GMT",
        "serialNumber": "0A1B2C",
        "subjectAltName": (("DNS", "xmpp.linuxoid.in"),
                           ("DNS", "linuxoid.in")),
    }

    def version(self):
        return "TLSv1.3"

    def cipher(self):
        return ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

    def getpeercert(self, binary_form=False):
        if binary_form:
            return b"DERBYTES"
        return self._CERT


import stanza_im.core.client as _client_mod
_orig_is_tls = _client_mod._is_tls
_client_mod._is_tls = lambda sock: sock is not None
try:
    info_direct = _info(set(), _FakeTlsSocket())
finally:
    _client_mod._is_tls = _orig_is_tls
check("info: direct TLS detected", info_direct["mode"] == "direct")
check("info: TLS version reported", info_direct["tls_version"] == "TLSv1.3")
check("info: cipher reported",
      info_direct["cipher"] == "TLS_AES_256_GCM_SHA384")

_cert = info_direct["cert"]
_expected_fp = ":".join(
    hashlib.sha256(b"DERBYTES").hexdigest().upper()[i:i + 2]
    for i in range(0, 64, 2))
check("info: cert available and verified",
      _cert["available"] and _cert["verified"])
check("info: cert subject CN/O",
      _cert["subject_cn"] == "xmpp.linuxoid.in"
      and _cert["subject_o"] == "Linuxoid")
check("info: cert issuer CN", _cert["issuer_cn"] == "Test CA")
check("info: cert serial", _cert["serial"] == "0A1B2C")
check("info: cert SANs",
      _cert["sans"] == ["xmpp.linuxoid.in", "linuxoid.in"])
check("info: cert SHA-256 fingerprint",
      _cert["fingerprint"] == _expected_fp)
check("info: cert validity window",
      _cert["expired"] is False and _cert["days_left"] > 0)
check("info: plain connection has no certificate", info_plain["cert"] == {})

_lines = certificate_lines(_cert)
check("certificate lines include the subject",
      any("xmpp.linuxoid.in" in line for line in _lines))
check("certificate lines include the fingerprint",
      any(_expected_fp in line for line in _lines))
check("certificate lines report absence",
      certificate_lines({}) == [tr("conn_info_cert_none")])

_cert_dialog = CertificateDialog("xmpp.linuxoid.in", _cert)
check("certificate dialog shows the fingerprint",
      _expected_fp in _cert_dialog._text.toPlainText())
_cert_dialog.close()


_fake = _FakeXmpp(set(), _FakeTlsSocket())
_fake.custom_address = ("linuxoid.in", 5222)
_fake._connected_target = ("xmpp.linuxoid.in", 5223, True)
client = object.__new__(JabberClient)
client.xmpp = _fake
client.keepalive = True
client.stream_management = False
client.csi = False
info_target = client.connection_info()
check("info: actual SRV target preferred over default",
      info_target["host"] == "xmpp.linuxoid.in"
      and info_target["port"] == 5223)


# ── _drop_unusable_plus_mechs integration ─────────────────────────

from stanza_im.core.client import _StanzaXMPP


class _Features:
    def __init__(self):
        self._d = {"features": {"mechanisms"},
                   "mechanisms": ["PLAIN", "SCRAM-SHA-1-PLUS", "SCRAM-SHA-1"]}

    def __getitem__(self, key):
        return self._d[key]


class _VersionedSock:
    def version(self):
        return "TLSv1.3"


_stanza = object.__new__(_StanzaXMPP)
_stanza.socket = _VersionedSock()
_plugin = SimpleNamespace()
_stanza.plugin = {"feature_mechanisms": _plugin}
_client_mod._is_tls = lambda sock: True
try:
    _stanza._drop_unusable_plus_mechs(_Features())
finally:
    _client_mod._is_tls = _orig_is_tls
check("mechs: -PLUS excluded via _drop_unusable_plus_mechs",
      _plugin.use_mechs == {"PLAIN", "SCRAM-SHA-1"})



# ── the two discover methods must not collide (regression) ────────
# A duplicate `discover_services` in JabberClient shadowed the transfer
# discovery and made the background task fail with a TypeError.

check("service-browser discover_services(server) intact",
      "server" in inspect.signature(JabberClient.discover_services).parameters)
check("transfer discovery has a distinct name",
      "force" in inspect.signature(
          JabberClient.discover_transfer_services).parameters)
check("transfer discovery is a coroutine",
      inspect.iscoroutinefunction(JabberClient.discover_transfer_services))
check("discover names resolve to different callables",
      JabberClient.discover_services is not JabberClient.discover_transfer_services)

_source = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "stanza_im", "core", "client.py")
with open(_source, encoding="utf-8") as _fh:
    _tree = ast.parse(_fh.read())
_methods = [
    node.name
    for cls in ast.walk(_tree)
    if isinstance(cls, ast.ClassDef) and cls.name == "JabberClient"
    for node in cls.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
]
_dups = sorted({name for name in _methods if _methods.count(name) > 1})
check("no duplicate method names in JabberClient", not _dups)


# ── config defaults ───────────────────────────────────────────────

cfg = Config()
conn = cfg.connection
check("default resource_mode=hostname", conn.resource_mode == "hostname")
check("default priority_mode=status", conn.priority_mode == "status")
check("default priority=50", conn.priority == 50)
check("default proxy_mode=none", conn.proxy_mode == "none")
check("default file_proxy_mode=auto", conn.file_proxy_mode == "auto")
check("default file_proxy_manual empty", conn.file_proxy_manual == "")
check("default stun_turn_mode=auto", conn.stun_turn_mode == "auto")
check("default stun_turn_manual empty", conn.stun_turn_manual == "")
check("default keepalive=True", conn.keepalive is True)
check("default tls_mode=prefer", conn.tls_mode == "prefer")
check("default starttls_mode=always", conn.starttls_mode == "always")
check("default csi=True", conn.csi is True)
check("default csi_keep_active_for_typing_osd=False",
      conn.csi_keep_active_for_typing_osd is False)


# ── preferences apply and preserve manual values ──────────────────

from stanza_im.ui import icons as _icons_mod

_icons_mod.init_icons()
dlg = PreferencesDialog(cfg, ChatThemeFactory(), client=None)
controls = dlg._controls

_pep = controls["pep_sweep_interval"]
check("pep sweep is a selector, not a spin",
      isinstance(_pep, QtWidgets.QComboBox))
check("pep sweep options are 0/30/60/120/300 s",
      [_pep.itemData(i) for i in range(_pep.count())]
      == [0, 30, 60, 120, 300])

# ── info icon on the information affordances ──────────────────────
check("info.svg exists and loads",
      not QtGui.QIcon(find_icon("info.svg")).isNull())
check("PreferencesDialog._info_icon is not null",
      not PreferencesDialog._info_icon().isNull())
check("certificate button uses the info icon",
      not dlg._cert_btn.icon().isNull())
check("connection info label uses the info icon",
      not dlg._conn_info.pixmap().isNull())
check("STUN/TURN info label uses the info icon",
      not dlg._stun_info.pixmap().isNull())
check("CSI keep-active option has an info tooltip",
      hasattr(dlg, "_csi_keep_info")
      and bool(dlg._csi_keep_info.toolTip()))

# ── section icons / tab title length / popups / widths ─────────────
_secs = dlg._sections
check("the renamed sections carry icons",
      all(not _secs.item(i).icon().isNull() for i in (0, 4, 5, 6, 8, 9)))
check("tab title length left the application page",
      "tab_title_length" not in controls
      and "tab_title_length_chat" in controls)
check("popups is a three-option selector",
      isinstance(controls["popups"], QtWidgets.QComboBox)
      and [controls["popups"].itemData(i)
           for i in range(controls["popups"].count())]
      == ["off", "system", "system_messages"])
check("numeric selectors share a fixed width",
      controls["idle_unload_minutes"].maximumWidth() == 90
      and controls["history_limit_chat"].maximumWidth() == 90)
check("combo selectors share a fixed width",
      controls["osd_status"].maximumWidth() == 260
      and controls["devices_video_input"].maximumWidth() == 260)

controls["file_proxy_mode"].setCurrentIndex(
    controls["file_proxy_mode"].findData("manual"))
controls["file_proxy_manual"].setText("proxy.example.org")
# Switch back to auto: the manual value must stay untouched.
controls["file_proxy_mode"].setCurrentIndex(
    controls["file_proxy_mode"].findData("auto"))
controls["stun_turn_mode"].setCurrentIndex(
    controls["stun_turn_mode"].findData("manual"))
controls["stun_turn_manual"].setText("turn.example.org:3478")
controls["resource_mode"].setCurrentIndex(
    controls["resource_mode"].findData("manual"))
controls["resource"].setText("myresource")
controls["priority_mode"].setCurrentIndex(
    controls["priority_mode"].findData("manual"))
controls["priority"].setValue(64)
controls["proxy_mode"].setCurrentIndex(
    controls["proxy_mode"].findData("socks5"))
controls["proxy_host"].setText("socks.example.net")
controls["proxy_port"].setValue(1080)
check("encrypt selector enabled in prefer mode",
      controls["starttls_mode"].isEnabled())
controls["tls_mode"].setCurrentIndex(controls["tls_mode"].findData("direct"))
check("encrypt selector disabled for TLS-only",
      not controls["starttls_mode"].isEnabled())
controls["tls_mode"].setCurrentIndex(controls["tls_mode"].findData("normal"))
controls["starttls_mode"].setCurrentIndex(
    controls["starttls_mode"].findData("opportunistic"))
controls["keepalive"].setChecked(False)
controls["csi_keep_active_for_typing_osd"].setChecked(True)
controls["pep_sweep_interval"].setCurrentIndex(
    controls["pep_sweep_interval"].findData(120))
dlg._apply_settings()

check("apply: tls_mode saved", cfg.connection.tls_mode == "normal")
check("apply: starttls_mode saved",
      cfg.connection.starttls_mode == "opportunistic")
check("apply: keepalive saved", cfg.connection.keepalive is False)
check("apply: csi_keep_active saved",
      cfg.connection.csi_keep_active_for_typing_osd is True)
check("apply: pep sweep selector saved as int",
      cfg.connection.pep_sweep_interval == 120)

check("apply: file_proxy_mode saved",
      cfg.connection.file_proxy_mode == "auto")
check("apply: manual file proxy preserved in auto mode",
      cfg.connection.file_proxy_manual == "proxy.example.org")
check("apply: stun manual saved",
      cfg.connection.stun_turn_manual == "turn.example.org:3478")
check("apply: resource_mode saved",
      cfg.connection.resource_mode == "manual")
check("apply: priority_mode/manual saved",
      cfg.connection.priority_mode == "manual" and cfg.connection.priority == 64)
check("apply: proxy saved",
      cfg.connection.proxy_mode == "socks5"
      and cfg.connection.proxy_host == "socks.example.net"
      and cfg.connection.proxy_port == 1080)

# Round-trip through the TOML file.
reloaded = Config()
check("round-trip: proxy persisted",
      reloaded.connection.proxy_mode == "socks5")
check("round-trip: manual file proxy persisted",
      reloaded.connection.file_proxy_manual == "proxy.example.org")
check("round-trip: priority persisted", reloaded.connection.priority == 64)
check("round-trip: tls_mode persisted",
      reloaded.connection.tls_mode == "normal")
check("round-trip: keepalive persisted",
      reloaded.connection.keepalive is False)


# ── discovery refresh button ──────────────────────────────────────

check("refresh button exists", hasattr(dlg, "_btn_discovery_refresh"))
check("refresh button disabled without client",
      not dlg._btn_discovery_refresh.isEnabled())


class _FakeClient:
    def __init__(self):
        self.refreshed = 0

    def discovered_services(self):
        return None

    def on(self, *_args):
        pass

    async def refresh_services(self):
        self.refreshed += 1
        return {}


fake = _FakeClient()
dlg2 = PreferencesDialog(cfg, ChatThemeFactory(), client=fake)
check("refresh button enabled with client",
      dlg2._btn_discovery_refresh.isEnabled())

asyncio.run(dlg2._run_refresh_discovery())
check("refresh button triggers discovery", fake.refreshed == 1)
check("refresh button restored after run",
      dlg2._btn_discovery_refresh.isEnabled())


# ── certificate info icon in the connection page ──────────────────

class _CertClient:
    def __init__(self, info):
        self._info = info

    def connection_info(self):
        return self._info

    def discovered_services(self):
        return None

    def on(self, *_args):
        pass


check("cert button disabled without a client",
      not PreferencesDialog(cfg, ChatThemeFactory(), client=None)
      ._cert_btn.isEnabled())
dlg3 = PreferencesDialog(cfg, ChatThemeFactory(),
                         client=_CertClient(info_direct))
check("cert button enabled with certificate data",
      dlg3._cert_btn.isEnabled())
check("cert button tooltip shows the subject",
      "xmpp.linuxoid.in" in dlg3._cert_btn.toolTip())
check("cert button caches the certificate",
      dlg3._cert_data.get("subject_cn") == "xmpp.linuxoid.in")

dlg4 = PreferencesDialog(cfg, ChatThemeFactory(),
                         client=_CertClient(info_st))
check("cert button disabled without TLS", not dlg4._cert_btn.isEnabled())


# ── XEP-0198 / XEP-0352 support ───────────────────────────────────

check("default stream_management=True", conn.stream_management is True)
check("default csi=True", conn.csi is True)

sm_client = JabberClient("u@example.org", "p",
                         stream_management=True, csi=True)
check("SM plugin registered", "xep_0198" in sm_client.xmpp.plugin)
check("CSI plugin registered", "xep_0352" in sm_client.xmpp.plugin)

off_client = JabberClient("u@example.org", "p",
                          stream_management=False, csi=False)
check("SM plugin absent when disabled", "xep_0198" not in off_client.xmpp.plugin)
check("CSI plugin absent when disabled", "xep_0352" not in off_client.xmpp.plugin)


# ── set_csi_config applies the preference live ────────────────────

class _FakeCsiPlugin:
    def __init__(self, xmpp):
        self.xmpp = xmpp
        self.enabled = False

    def send_active(self):
        self.xmpp.calls.append(("active",))

    def send_inactive(self):
        self.xmpp.calls.append(("inactive",))


class _FakeCsiXmpp:
    def __init__(self, features=("csi",)):
        self.plugin = {}
        self.features = set(features)
        self.calls = []

    def register_plugin(self, name):
        self.plugin[name] = _FakeCsiPlugin(self)
        self.calls.append(("register", name))

    def unregister_plugin(self, name):
        self.plugin.pop(name, None)
        self.calls.append(("unregister", name))

    def add_event_handler(self, event, *_args):
        self.calls.append(("handler", event))


def _csi_client(csi):
    client = object.__new__(JabberClient)
    client.csi = bool(csi)
    client._csi_enabled = False
    client._csi_handler_registered = bool(csi)
    client._client_active = True
    client.xmpp = _FakeCsiXmpp()
    client._events = []
    client.emit = lambda *a: client._events.append(a)
    client.connection_info = lambda: {"mode": "plain"}
    if csi:
        client.xmpp.register_plugin("xep_0352")
    return client


_en = _csi_client(csi=False)
_en.xmpp._session_started = True
_en.set_csi_config(True)
check("set_csi_config(True) registers the plugin",
      "xep_0352" in _en.xmpp.plugin)
check("set_csi_config(True) enables CSI on a supporting server",
      _en.csi is True and _en._csi_enabled is True)
check("set_csi_config(True) emits csi_enabled",
      ("csi_enabled",) in _en._events)

_dis = _csi_client(csi=True)
_dis.xmpp._session_started = True
_dis._csi_enabled = True
_dis.set_csi_config(False)
check("set_csi_config(False) tells the server we are active",
      ("active",) in _dis.xmpp.calls)
check("set_csi_config(False) unregisters the plugin",
      ("unregister", "xep_0352") in _dis.xmpp.calls
      and _dis.csi is False and _dis._csi_enabled is False)

# Event mapping slixmpp -> app.
_events = []
sm_client.on("sm_enabled", lambda: _events.append("sm"))
sm_client.on("stream_resumed", lambda: _events.append("resumed"))
sm_client.on("sm_failed", lambda: _events.append("failed"))
sm_client.xmpp.event("sm_enabled", None)
sm_client.xmpp.event("session_resumed", None)
sm_client.xmpp.event("sm_failed", None)
check("SM events mapped", _events == ["sm", "resumed", "failed"])

# set_client_active drives the CSI plugin.
_calls = []
csi_plugin = sm_client.xmpp.plugin["xep_0352"]
csi_plugin.enabled = True
csi_plugin.send_active = lambda: _calls.append("active")
csi_plugin.send_inactive = lambda: _calls.append("inactive")
sm_client._csi_enabled = True
sm_client._client_active = True
sm_client.xmpp._session_started = True
sm_client.set_client_active(False)
check("CSI inactive sent", _calls == ["inactive"])
check("CSI state inactive", sm_client.csi_state() == "inactive")
sm_client.set_client_active(True)
check("CSI active sent", _calls == ["inactive", "active"])
check("CSI state active", sm_client.csi_state() == "active")

sm_info = sm_client.connection_info()
check("connection_info has sm/csi",
      "sm" in sm_info and "csi" in sm_info)

check("no resume expected without sm_id", not sm_client.resume_expected())
sm_client.xmpp.plugin["xep_0198"].sm_id = "x"
check("resume expected with sm_id", sm_client.resume_expected())


print("\nAll tests passed ✓" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
