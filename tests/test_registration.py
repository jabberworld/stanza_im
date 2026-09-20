"""Offscreen smoke tests for the account-registration dialog.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_registration.py
"""
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


# ── static wiring ────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(_root, *parts), encoding="utf-8") as fh:
        return fh.read()


mw = _read("stanza_im", "ui", "main_window.py")
check("main window wires register_requested",
      "register_requested.connect(self._on_create_account)" in mw)
check("main window opens the dialog",
      "AccountRegistrationDialog" in mw
      and "def _on_create_account" in mw
      and "def _on_account_registered" in mw)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
