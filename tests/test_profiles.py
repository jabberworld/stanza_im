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

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All profile tests passed.")
