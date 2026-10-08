"""Offscreen tests for the application profile manager.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_profiles.py
"""
import os
import shutil
import stat
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_profiles_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.include import constants
from stanza_im.core import (
    history, known_contacts, profiles, roster_cache, unread_state)
from stanza_im.core.storage import Config

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

DATA_DIR = constants.DATA_DIR
JID = "alice@example.com"

# 1. store CRUD ---------------------------------------------------------------
check("empty registry", profiles.load() == [])
profiles.upsert(profiles.Profile(JID, password="s3cr3t", save_password=True,
                                 host="xmpp.example.com", port=5223,
                                 tls_mode="direct", starttls_mode="never",
                                 proxy_mode="socks5", proxy_host="proxy.local",
                                 proxy_port=1080))
loaded = profiles.load()
check("one profile stored", len(loaded) == 1 and loaded[0].jid == JID)
check("credentials round-trip", loaded[0].password == "s3cr3t"
      and loaded[0].port == 5223 and loaded[0].tls_mode == "direct"
      and loaded[0].proxy_mode == "socks5"
      and loaded[0].proxy_port == 1080)
check("profiles.json is 0600",
      stat.S_IMODE(os.stat(profiles.PROFILES_FILE).st_mode) == 0o600)

profiles.upsert(profiles.Profile(JID, password="new", save_password=False))
loaded = profiles.load()
check("upsert replaces by JID", len(loaded) == 1
      and loaded[0].password == "new" and loaded[0].save_password is False)

profiles.upsert(profiles.Profile("bob@example.com", password="b"))
check("second profile added", len(profiles.load()) == 2)
check("get() by JID", profiles.get(JID) is not None
      and profiles.get("nope@example.com") is None)
profiles.remove(JID)
check("remove drops one", [p.jid for p in profiles.load()] == ["bob@example.com"])

# 2. from_config / apply_to_config -------------------------------------------
cfg = Config()
cfg.jid = JID
cfg.password = "pw"
cfg.save_password = True
conn = cfg.connection
conn.override_host = True
conn.host = "host.example.com"
conn.port = 5223
conn.tls_mode = "direct"
conn.starttls_mode = "never"
conn.proxy_mode = "socks5"
conn.proxy_host = "proxy.example.com"
conn.proxy_port = 1081

profile = profiles.from_config(cfg)
check("from_config copies the account",
      profile.jid == JID and profile.password == "pw"
      and profile.override_host is True and profile.host == "host.example.com"
      and profile.port == 5223 and profile.tls_mode == "direct"
      and profile.proxy_host == "proxy.example.com"
      and profile.proxy_port == 1081)

cfg.jid = "other@example.com"
cfg.password = ""
profiles.apply_to_config(cfg, profile)
check("apply_to_config writes jid/password",
      cfg.jid == JID and cfg.password == "pw" and cfg.save_password is True)
check("apply_to_config writes connection",
      cfg.connection.host == "host.example.com"
      and cfg.connection.port == 5223
      and cfg.connection.tls_mode == "direct"
      and cfg.connection.proxy_mode == "socks5"
      and cfg.connection.proxy_port == 1081)

# 3. per-profile data scoping ------------------------------------------------
profiles.set_active(JID)
check("active profile selected", constants.active_profile() == JID)
check("history dir scoped",
      history.HISTORY_DIR == os.path.join(DATA_DIR, JID, "history"))
check("unread path scoped",
      unread_state.path() == os.path.join(DATA_DIR, JID, "unread.json"))
check("known contacts path scoped",
      known_contacts.path() == os.path.join(DATA_DIR, JID,
                                            "known_contacts.json"))
check("roster cache path scoped",
      roster_cache.path(JID) == os.path.join(DATA_DIR, JID, "roster",
                                             "alice@example.com.json"))

# a contact's DB is created under the profile dir, not the shared one
history.store_message("carol@example.com", "incoming", "hi")
check("contact history lands in the profile dir",
      os.path.isfile(os.path.join(DATA_DIR, JID, "history",
                                  "carol@example.com.sqlite3")))
check("the pool holds the contact connection", bool(history._pool))
profiles.set_active("bob@example.com")
check("switching profiles drops the pooled connections", not history._pool)

# 4. delete_data -------------------------------------------------------------
check("profile data dir exists before delete",
      os.path.isdir(os.path.join(DATA_DIR, JID)))
check("delete_data removes the directory",
      profiles.delete_data(JID)
      and not os.path.isdir(os.path.join(DATA_DIR, JID)))
check("delete_data refuses an empty JID", profiles.delete_data("") is False)

# 5. reset the unscoped layout ----------------------------------------------
profiles.set_active("")
check("no active profile unscopes history",
      history.HISTORY_DIR == os.path.join(DATA_DIR, "history"))
check("no active profile unscopes unread",
      unread_state.path() == os.path.join(DATA_DIR, "unread.json"))

# 6. UI dialogs ---------------------------------------------------------------
from stanza_im.ui.profile_source_dialog import ProfileSourceDialog
from stanza_im.ui.existing_account_dialog import ExistingAccountDialog
from stanza_im.ui.profiles_dialog import ProfilesDialog, ProfileDeleteDialog
from stanza_im.ui.account_registration_dialog import AccountRegistrationDialog

source = ProfileSourceDialog()
source._pick("existing")
check("source dialog returns the choice",
      source.choice() == "existing"
      and source.result() == QtWidgets.QDialog.DialogCode.Accepted)

existing = ExistingAccountDialog()
existing._on_ok()
check("existing dialog refuses an empty JID",
      existing.result() != QtWidgets.QDialog.DialogCode.Accepted
      and existing._status.text())
existing._jid.setText("dave@example.com")
existing._password.setText("pw")
existing._override.setChecked(True)
existing._host.setText("host.example.com")
existing._port.setValue(5223)
_set = existing._tls.findData("direct")
existing._tls.setCurrentIndex(_set)
existing._proxy_mode.setCurrentIndex(
    existing._proxy_mode.findData("socks5"))
existing._proxy_host.setText("proxy.example.com")
existing._proxy_port.setValue(1080)
existing._on_ok()
p = existing.profile()
check("existing dialog builds a Profile",
      p.jid == "dave@example.com" and p.password == "pw"
      and p.override_host is True and p.host == "host.example.com"
      and p.port == 5223 and p.tls_mode == "direct"
      and p.proxy_mode == "socks5" and p.proxy_port == 1080)

delete = ProfileDeleteDialog("dave@example.com")
delete._pick(True)
check("delete dialog reports the data choice",
      delete.delete_with_data() is True
      and delete.result() == QtWidgets.QDialog.DialogCode.Accepted)

# the manager lists the registry and applies the selection
profiles.upsert(profiles.Profile("alice@example.com", password="a"))
profiles.upsert(profiles.Profile("bob@example.com", password="b"))
cfg.jid = "alice@example.com"
manager = ProfilesDialog(cfg)
check("manager lists both profiles", manager._list.count() == 2)
check("manager marks the active profile bold",
      manager._list.item(0).font().bold()
      or manager._list.item(1).font().bold())
check("apply/delete disabled without a selection",
      not manager._apply_btn.isEnabled()
      and not manager._delete_btn.isEnabled())
manager._select("bob@example.com")
check("selecting enables apply/delete",
      manager._apply_btn.isEnabled() and manager._delete_btn.isEnabled())
_emitted = []
manager.activated.connect(_emitted.append)
manager._on_apply()
check("apply emits the selected JID", _emitted == ["bob@example.com"])

# registration dialog does not touch the config when store_account=False
reg = AccountRegistrationDialog(cfg, store_account=False)
check("registration result_profile is None before submitting",
      reg.result_profile() is None)

# the existing-account dialog enables encryption by default (Prefer TLS)
defaults = ExistingAccountDialog()
check("existing dialog defaults to Prefer TLS",
      defaults._tls.currentData() == "prefer")
check("encryption selector is enabled by default",
      defaults._enc.isEnabled())
defaults._tls.setCurrentIndex(defaults._tls.findData("direct"))
check("choosing TLS-only disables the encryption selector",
      not defaults._enc.isEnabled())

# 7. login profile selector ---------------------------------------------------
from stanza_im.ui.login_widget import LoginWidget

cfg.jid = "alice@example.com"
login = LoginWidget(cfg)
check("login selector lists the profiles",
      login._profile_combo.count() == 2)
login._profile_combo.setCurrentIndex(
    login._profile_combo.findData("bob@example.com"))
_applied = []
login.profile_applied.connect(_applied.append)
login._apply_profile()
check("applying a profile writes the active account",
      cfg.jid == "bob@example.com" and cfg.password == "b")
check("applying a profile reloads the form",
      login._jid_edit.text() == "bob@example.com"
      and login._pw_edit.text() == "b")
check("profile_applied is emitted", _applied == ["bob@example.com"])

# the manager button opens the profile manager
_manager_calls = []
login.profiles_requested.connect(lambda: _manager_calls.append(1))
login._profile_manager_btn.click()
check("the login manager button requests the profile manager",
      _manager_calls == [1])

# the status selector sits at the bottom, after the connect button
def _top_index(layout, widget):
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is widget:
            return i
        if item.layout() is not None:
            if _top_index(item.layout(), widget) >= 0:
                return i
    return -1


_lay = login.layout()
check("the status selector is below the connect button",
      _top_index(_lay, login._show_combo)
      > _top_index(_lay, login._connect_btn))
check("the profile selector is above the credentials",
      _top_index(_lay, login._profile_combo)
      < _top_index(_lay, login._jid_edit))

# empty credentials are rejected with a localized message
from stanza_im.i18n import tr
login._jid_edit.setText("")
login._pw_edit.setText("")
login._on_connect()
check("empty credentials show the localized error",
      login._info_label.text() == tr("login_credentials_required"))

# 8. SASL condition is propagated --------------------------------------------
import slixmpp
from stanza_im.core.client import JabberClient

_auth = JabberClient.__new__(JabberClient)
_auth.xmpp = slixmpp.ClientXMPP("me@example.com/r", "pw")
_auth._callbacks = {}
_conds = []
_auth.on("auth_failed", lambda cond: _conds.append(cond))


class _SaslFailure:
    def __getitem__(self, key):
        if key == "condition":
            return "not-authorized"
        raise KeyError(key)


_auth._on_auth_failed(_SaslFailure())
_auth._on_auth_failed()
check("auth_failed carries the SASL condition",
      _conds == ["not-authorized", ""])

# detach() silences a logged-out client so its late events cannot fire
_detached = []
_auth.on("disconnected", lambda: _detached.append(1))
_auth.emit("disconnected")
check("a callback fires before detach", _detached == [1])
_auth.detach()
_auth.emit("disconnected")
check("detach drops every callback", _detached == [1])

# 9. MainWindow wiring (static) ----------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
check("MainWindow selects the active profile at startup",
      "profiles.set_active(self._config.jid)" in _mw_src)
check("Profiles menu action is enabled and wired",
      "profiles_act.triggered.connect(self._on_profiles)" in _mw_src)
check("login submission selects the profile and reloads unread",
      "profiles.set_active(jid)" in _mw_src
      and "self._load_unread_for(jid)" in _mw_src)
check("auth failure distinguishes bad credentials",
      "login_bad_credentials" in _mw_src)
check("logout detaches the old client before its disconnect",
      'getattr(client, "detach", None)' in _mw_src)
check("session start clears a stale status bar",
      "self._clear_status()" in _mw_src.split(
          "def _on_session_started", 1)[1].split("def ", 1)[0])
_on_login_body = _mw_src.split("def _on_login(self", 1)[1].split("def ", 1)[0]
check("login re-activates plugins before wiring the client",
      _on_login_body.index("self._apply_plugins()")
      < _on_login_body.index("self._connect_client_signals()"))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All profile tests passed.")
