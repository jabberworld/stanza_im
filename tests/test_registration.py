"""Offscreen smoke tests for the account-registration dialog.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_registration.py
"""
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_reg_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.core.storage import Config
from stanza_im.core.client import JabberClient
from stanza_im.ui import account_registration_dialog as reg
from stanza_im.ui.account_registration_dialog import (
    AccountRegistrationDialog, load_servers)
from stanza_im.ui.login_widget import LoginWidget
from stanza_im.ui.preferences import PreferencesDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── servers.txt parsing ──────────────────────────────────────────
servers_path = os.path.join(_SCRATCH, "servers.txt")
with open(servers_path, "w", encoding="utf-8") as fh:
    fh.write("# comment\n\njabber.example\n  conference.example  \n")
reg.SERVERS_FILE = servers_path
check("servers.txt parsed with comments/blanks ignored",
      load_servers() == ["jabber.example", "conference.example"])
reg.SERVERS_FILE = os.path.join(_SCRATCH, "missing.txt")
check("missing servers.txt yields an empty list", load_servers() == [])
reg.SERVERS_FILE = servers_path


# ── dialog defaults ──────────────────────────────────────────────
config = Config()
dlg = AccountRegistrationDialog(config)
check("server combo starts empty",
      dlg._server_combo.count() >= 1 and dlg._server_combo.itemText(0) == "")
check("server combo is editable", dlg._server_combo.isEditable() is True)
check("connection default is Prefer TLS",
      dlg._tls.currentData() == "prefer")
check("encryption default is Always",
      dlg._enc.currentData() == "always")
check("proxy default is none", dlg._proxy_mode.currentData() == "none")
check("next button uses the localized label",
      dlg._next_btn.text() == tr("register_next")
      and tr("register_next") != "register_next")
check("host/port disabled until override",
      not dlg._host.isEnabled() and not dlg._port.isEnabled())


# ── credentials extraction ───────────────────────────────────────
dlg._server = "example.com"
check("username is combined with the server",
      dlg._credentials({"username": "bob", "password": "pw"})
      == ("bob@example.com", "pw"))
check("a full JID is kept as-is",
      dlg._credentials({"username": "bob@other.org", "password": "pw"})
      == ("bob@other.org", "pw"))


# ── config persistence ───────────────────────────────────────────
dlg._override.setChecked(True)
dlg._host.setText("xmpp.example.com")
dlg._port.setValue(5223)
dlg._tls.setCurrentIndex(0)  # direct
dlg._enc.setCurrentIndex(2)  # never
dlg._proxy_mode.setCurrentIndex(1)  # socks5
dlg._proxy_host.setText("proxy.example")
dlg._proxy_port.setValue(1080)
dlg._save_config("bob@example.com", "secret")
check("config keeps the account",
      config.jid == "bob@example.com" and config.password == "secret"
      and config.save_password is True)
check("config keeps the connection settings",
      config.connection.override_host is True
      and config.connection.host == "xmpp.example.com"
      and config.connection.port == 5223
      and config.connection.tls_mode == "direct"
      and config.connection.starttls_mode == "never")
check("config keeps the proxy settings",
      config.connection.proxy_mode == "socks5"
      and config.connection.proxy_host == "proxy.example"
      and config.connection.proxy_port == 1080)


# ── get_registration_form resolves XEP-0231 BOB captcha media ────
from xml.etree import ElementTree as ET  # noqa: E402

NS_DATA = "jabber:x:data"
NS_MEDIA = "urn:xmpp:media-element"


class _FakeForm:
    def __init__(self, xml):
        self.xml = xml

    def get_fields(self):
        return list(self.xml.findall(f"{{{NS_DATA}}}field"))


class _FakeRegister:
    def __init__(self, query):
        form_xml = query.find(f"{{{NS_DATA}}}x")
        self.form = _FakeForm(form_xml) if form_xml is not None else None
        self.fields = None
        self.instructions = ""
        self.registered = False
        self.oob = {}

    def __getitem__(self, key):
        return getattr(self, key)


class _FakeIq:
    def __init__(self, query):
        self.xml = ET.Element("iq")
        self.xml.append(query)
        self._register = _FakeRegister(query)

    def __getitem__(self, key):
        return self._register if key == "register" else None


class _Fake0077:
    def __init__(self, iq):
        self._iq = iq

    async def get_registration(self, jid):
        return self._iq


query = ET.fromstring(
    "<query xmlns='jabber:iq:register'>"
    "<x xmlns='jabber:x:data' type='form'>"
    "<field var='ocr' type='text-single' label='OCR'>"
    "<media xmlns='urn:xmpp:media-element'>"
    "<uri type='image/png'>cid:sha1+abc@bob.xmpp.org</uri>"
    "</media></field></x>"
    "<data xmlns='urn:xmpp:bob' cid='sha1+abc@bob.xmpp.org' type='image/png'>"
    "iVBORw0KGgo=</data></query>")
bob_client = JabberClient.__new__(JabberClient)
bob_client.xmpp = {"xep_0077": _Fake0077(_FakeIq(query))}
info = asyncio.run(bob_client.get_registration_form("jabber.ru"))
uri = info["form"].xml.find(f".//{{{NS_MEDIA}}}uri")
check("get_registration_form resolves BOB captcha media",
      uri is not None
      and str(uri.text or "").startswith("data:image/png;base64,"))


# ── legacy fields are a {name: value} map (slixmpp returns a set) ─
class _RegisterIq:
    def __init__(self, register):
        self.xml = ET.Element("iq")
        self._register = register

    def __getitem__(self, key):
        return self._register if key == "register" else None


class _LegacyRegister:
    def __init__(self, fields, form=None):
        self.form = form
        self.fields = set(fields)
        self.instructions = ""
        self.registered = False
        self.oob = {}

    def __getitem__(self, key):
        if key in ("fields", "form", "instructions", "registered", "oob"):
            return getattr(self, key)
        return "" if key in self.fields else None


legacy_client = JabberClient.__new__(JabberClient)
legacy_client.xmpp = {"xep_0077": _Fake0077(
    _RegisterIq(_LegacyRegister(["nick"])))}
legacy_info = asyncio.run(legacy_client.get_registration_form("example.com"))
check("legacy fields become a {name: value} map",
      legacy_info["form"] is None and legacy_info["fields"] == {"nick": ""})

form_query = ET.fromstring(
    "<query xmlns='jabber:iq:register'><nick/>"
    "<x xmlns='jabber:x:data' type='form'>"
    "<field var='muc#register_roomnick' type='text-single'>"
    "<required/></field></x></query>")
form_register = _LegacyRegister(["nick"],
                                form=_FakeForm(form_query.find(f"{{{NS_DATA}}}x")))
form_client = JabberClient.__new__(JabberClient)
form_client.xmpp = {"xep_0077": _Fake0077(_RegisterIq(form_register))}
form_info = asyncio.run(form_client.get_registration_form("conference.example.com"))
check("a data form ignores the legacy fields set (no dict crash)",
      form_info["form"] is not None and form_info["fields"] is None)


# ── login widget ─────────────────────────────────────────────────
login = LoginWidget(config)
check("login link is localized",
      tr("login_create_account") in login._create_label.text()
      and "login_create_account" not in login._create_label.text())
check("login link emits register_requested",
      hasattr(login, "register_requested"))
login.prefill("bob@example.com", "secret")
check("prefill fills JID and password",
      login._jid_edit.text() == "bob@example.com"
      and login._pw_edit.text() == "secret")
check("prefill enables saving the password",
      login._save_pw.isChecked() is True)


# ── preferences icon ─────────────────────────────────────────────
check("preferences register icon is available",
      not PreferencesDialog._register_icon().isNull())


# ── connect_for_registration (PluginManager.get requires a default) ──
class _FakePlugin:
    def __init__(self):
        self.config = {"order": 100}


class _FakePluginManager:
    def get(self, name, default):  # mirrors slixmpp: default is required
        if name == "feature_mechanisms":
            return _FakePlugin()
        return default


class _FakeStream:
    def __init__(self):
        self.plugin = _FakePluginManager()
        self.unregistered = []
        self.handlers = {}

    def unregister_feature(self, name, order):
        self.unregistered.append((name, order))

    def add_event_handler(self, name, callback):
        self.handlers[name] = callback

    def del_event_handler(self, name, callback):
        self.handlers.pop(name, None)

    def event(self, name, *args):
        callback = self.handlers.get(name)
        if callback is not None:
            callback(*args)


reg_client = JabberClient.__new__(JabberClient)
reg_client.xmpp = _FakeStream()


async def _fake_connect():
    reg_client.xmpp.event("stream_negotiated")


reg_client.connect_async = _fake_connect
check("connect_for_registration completes without a default arg",
      asyncio.run(reg_client.connect_for_registration()) is None)
check("connect_for_registration disables SASL",
      reg_client.xmpp.unregistered == [("mechanisms", 100)])
check("stream_negotiated handler is removed",
      "stream_negotiated" not in reg_client.xmpp.handlers)


# ── set_csi_config shares the same PluginManager.get signature ───
class _FakeCsiStream:
    def __init__(self):
        self.plugin = _FakePluginManager()
        self.features = set()
        self.handlers = {}

    def register_plugin(self, name):
        pass

    def add_event_handler(self, name, callback):
        self.handlers[name] = callback


csi_client = JabberClient.__new__(JabberClient)
csi_client.xmpp = _FakeCsiStream()
csi_client.csi = False
csi_client._csi_enabled = False
csi_client._csi_handler_registered = False
csi_client._client_active = True
csi_client.emit = lambda *args, **kwargs: None
csi_client._sync_csi = lambda: None
try:
    csi_client.set_csi_config(True)
    csi_ok = True
except TypeError:
    csi_ok = False
check("set_csi_config does not require a default arg", csi_ok)


# ── result summary rows ──────────────────────────────────────────
dlg._tls.setCurrentIndex(1)   # prefer
dlg._enc.setCurrentIndex(0)   # always
proxy_details = dict(dlg._connection_details())
check("connection details include the encryption mode",
      proxy_details.get(tr("registration_result_encryption"))
      == f'{tr("conn_mode_prefer")} / {tr("enc_always")}')
check("connection details include the proxy",
      proxy_details.get(tr("registration_result_proxy")) == "proxy.example:1080")
check("connection details include the host override",
      proxy_details.get(tr("prefs_host")) == "xmpp.example.com:5223")


class _FormField:
    def __init__(self, **values):
        self._values = values

    def __getitem__(self, key):
        return self._values[key]

    def get(self, key, default=None):
        return self._values.get(key, default)


dlg._form = {"fields": [
    _FormField(type="hidden", var="FORM_TYPE", label="", value="x"),
    _FormField(type="text-single", var="username", label="User", value="bob"),
    _FormField(type="text-private", var="password", label="", value="pw"),
]}
check("submitted data skips hidden fields",
      dlg._submitted_data({}) == [("User", "bob"), ("password", "pw")])
dlg._form = None
check("submitted data lists legacy fields",
      dlg._submitted_data({"username": "bob", "password": "pw"})
      == [("username", "bob"), ("password", "pw")])


# ── result dialog ────────────────────────────────────────────────
from stanza_im.ui.registration_result_dialog import (  # noqa: E402
    RegistrationResultDialog)

rd = RegistrationResultDialog("bob@example.com", "secret",
                              [("Encryption", "Prefer TLS")],
                              [("User", "bob")])
summary = rd.summary()
check("result summary carries the JID, password, details and data",
      "bob@example.com" in summary and "secret" in summary
      and "Encryption: Prefer TLS" in summary and "User: bob" in summary)
check("result buttons are localized",
      rd._copy_btn.text() == tr("registration_result_copy")
      and rd._apply_btn.text() == tr("dialog_apply")
      and rd._close_btn.text() == tr("dialog_close"))
check("apply is the default button", rd._apply_btn.isDefault() is True)
rd._copy()
check("copy puts the summary on the clipboard",
      QtWidgets.QApplication.clipboard().text() == summary)
check("captcha link label is short",
      tr("captcha_open_oob") == "Open page")


# ── apply/close gate on the result dialog ────────────────────────
class _FakeRegClient:
    async def submit_registration(self, server, values, form=None):
        return None


class _LegacyStub:
    @staticmethod
    def values():
        return {"username": "bob", "password": "pw"}


gate = AccountRegistrationDialog(Config())
gate._config.jid = ""
gate._config.password = ""
gate._server = "example.com"
gate._client = _FakeRegClient()
gate._legacy_widget = _LegacyStub()
emitted = []
gate.registered.connect(lambda jid, pw: emitted.append((jid, pw)))
_original_exec = reg.RegistrationResultDialog.exec
reg.RegistrationResultDialog.exec = (
    lambda self: QtWidgets.QDialog.DialogCode.Rejected)
asyncio.run(gate._submit())
check("closing the result dialog keeps the account unsaved",
      not gate._config.jid and emitted == [])
gate._client = _FakeRegClient()
reg.RegistrationResultDialog.exec = (
    lambda self: QtWidgets.QDialog.DialogCode.Accepted)
asyncio.run(gate._submit())
check("applying the result dialog saves and announces the account",
      gate._config.jid == "bob@example.com" and emitted
      == [("bob@example.com", "pw")])
check("applying the result dialog saves the connection settings",
      gate._config.connection.tls_mode == "prefer")
reg.RegistrationResultDialog.exec = _original_exec


# ── static wiring ────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(_root, *parts), encoding="utf-8") as fh:
        return fh.read()


reg_src = _read("stanza_im", "ui", "account_registration_dialog.py")
check("the result dialog gates the config write",
      "RegistrationResultDialog" in reg_src
      and "if result.exec()" in reg_src)
check("registration fits the dialog to the form content",
      "QtCore.QTimer.singleShot(0, lambda: fit_dialog_to_content(self))"
      in reg_src)

service_src = _read("stanza_im", "ui", "registration_dialog.py")
check("the service registration dialog re-fits when shown",
      "def showEvent" in service_src
      and "QtCore.QTimer.singleShot(0, lambda: fit_dialog_to_content(self))"
      in service_src)

form_src = _read("stanza_im", "ui", "data_form_widget.py")
check("data forms render read-only URLs as links only",
      "_link_fields" in form_src and "def _link_label" in form_src
      and "def _link_row" not in form_src)
check("an unlabeled fixed field spans the whole row",
      "layout.addRow(widget)" in form_src)

mw = _read("stanza_im", "ui", "main_window.py")
check("main window wires register_requested",
      "register_requested.connect(self._on_create_account)" in mw)
check("main window opens the dialog",
      "AccountRegistrationDialog" in mw
      and "def _on_create_account" in mw
      and "def _on_account_registered" in mw)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
