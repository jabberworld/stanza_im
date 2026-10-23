"""Offscreen tests for the cross-session roster cache (XEP-0237).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_roster_cache.py
"""
import asyncio
import json
import os
import stat
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_roster_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

asyncio.set_event_loop(asyncio.new_event_loop())

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.core import roster_cache
from stanza_im.core.client import JabberClient

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


ACCOUNT = "me@example.com"
ITEMS = [
    {"jid": "alice@example.com", "name": "Alice", "groups": ["Friends"],
     "from": True, "to": True, "whitelisted": True,
     "pending_out": False, "pending_in": False},
    {"jid": "carol@example.com", "name": "", "groups": [],
     "from": False, "to": True, "whitelisted": False,
     "pending_out": False, "pending_in": False},
]


# ── cache round-trip ─────────────────────────────────────────────
check("missing cache yields None", roster_cache.load(ACCOUNT) is None)
roster_cache.save(ACCOUNT, "v1", ITEMS)
loaded = roster_cache.load(ACCOUNT)
check("round-trip keeps the version", loaded["version"] == "v1")
check("round-trip keeps the items", loaded["items"] == ITEMS)
check("cache file is 0600",
      stat.S_IMODE(os.stat(roster_cache.path(ACCOUNT)).st_mode) == 0o600)

cache_file = roster_cache.path(ACCOUNT)
with open(cache_file, "w", encoding="utf-8") as fh:
    fh.write("{not json")
check("corrupt cache yields None", roster_cache.load(ACCOUNT) is None)
with open(cache_file, "w", encoding="utf-8") as fh:
    json.dump({"version": "v2", "items": "nope"}, fh)
check("malformed items yield None", roster_cache.load(ACCOUNT) is None)
roster_cache.save(ACCOUNT, "v1", ITEMS)


# ── cache file names ─────────────────────────────────────────────
UNI_A = "мария@example.com"
UNI_B = "ольга@example.com"
check("non-ASCII accounts get distinct cache files",
      roster_cache.path(UNI_A) != roster_cache.path(UNI_B))
check("an ASCII account keeps its plain cache name",
      os.path.basename(roster_cache.path(ACCOUNT)) == "me@example.com.json")
check("the account name is case-stable",
      roster_cache.path(UNI_A) == roster_cache.path(UNI_A.upper()))

roster_cache.save(UNI_A, "u1", ITEMS[:1])
with open(roster_cache.path(UNI_A), encoding="utf-8") as fh:
    _payload = json.load(fh)
check("the cache records its account", _payload.get("account") == UNI_A)
check("a non-ASCII cache round-trips",
      roster_cache.load(UNI_A)["version"] == "u1")
with open(roster_cache.path(UNI_A), "w", encoding="utf-8") as fh:
    json.dump({"account": UNI_B, "version": "u2", "items": ITEMS}, fh)
check("a cache written for another account is ignored",
      roster_cache.load(UNI_A) is None)
with open(roster_cache.path(UNI_A), "w", encoding="utf-8") as fh:
    json.dump({"version": "u3", "items": ITEMS}, fh)
check("a legacy cache without an account still loads",
      roster_cache.load(UNI_A)["version"] == "u3")

# ── seeding the live roster ──────────────────────────────────────
client = JabberClient(ACCOUNT + "/desk", "pw")
client._roster_cache = roster_cache.load(ACCOUNT)
client._seed_roster_cache()
cr = client.xmpp.client_roster
check("version seeded into client_roster", cr.version == "v1")
check("roster item seeded",
      cr["alice@example.com"]["name"] == "Alice"
      and list(cr["alice@example.com"]["groups"]) == ["Friends"])
check("subscription derived from from/to",
      cr["alice@example.com"]["subscription"] == "both"
      and cr["carol@example.com"]["subscription"] == "to")
check("snapshot exposes the seeded roster",
      {i["jid"] for i in client.get_roster_snapshot()}
      == {"alice@example.com", "carol@example.com"})
state = {i["jid"]: i for i in client.get_roster_state()}
check("state export carries the subscription flags",
      state["alice@example.com"]["from"] is True
      and state["carol@example.com"]["to"] is True
      and state["alice@example.com"]["whitelisted"] is True)


# ── a "no changes" result keeps the seeded roster ────────────────
iq = client.xmpp.Iq()
iq["type"] = "result"
iq["roster"]["ver"] = "v1"
client.xmpp._handle_roster(iq)
check("empty server result keeps the cached items",
      {i["jid"] for i in client.get_roster_snapshot()}
      == {"alice@example.com", "carol@example.com"})


# ── updates persist the cache ────────────────────────────────────
client.roster = {}
client._on_roster_update(None)
client.flush_roster_cache()
saved = roster_cache.load(ACCOUNT)
check("roster update persists the cache", saved is not None
      and saved["version"] == "v1"
      and {i["jid"] for i in saved["items"]}
      == {"alice@example.com", "carol@example.com"})

# A newer version replaces the cached one.
iq2 = client.xmpp.Iq()
iq2["type"] = "result"
iq2["roster"]["ver"] = "v2"
client.xmpp._handle_roster(iq2)
client.flush_roster_cache()
check("new version replaces the cached version",
      roster_cache.load(ACCOUNT)["version"] == "v2")

# ── the cache is loaded lazily (never by the constructor) ────────
_calls = []
_orig_load = roster_cache.load


def _counting_load(account):
    _calls.append(account)
    return _orig_load(account)


roster_cache.load = _counting_load
try:
    lazy_client = JabberClient("jabber.name", "")
    check("constructing a client does not read the roster cache",
          _calls == [])
    lazy_client._seed_roster_cache()
    check("seeding reads the cache on demand",
          _calls == ["jabber.name"])
finally:
    roster_cache.load = _orig_load


# ── static wiring ────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_root, "stanza_im", "core", "client.py"),
          encoding="utf-8") as fh:
    src = fh.read()
check("session start seeds the cache before requesting",
      "self._seed_roster_cache()\n        self.request_roster()" in src)
check("construction does not eagerly load the roster cache",
      "self._roster_cache = roster_cache.load(self.jid_str)" not in src)
with open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
          encoding="utf-8") as fh:
    mw = fh.read()
check("quit flushes the roster cache",
      "self._client.flush_roster_cache()" in mw)

# ── the UI renders the cache before the client exists ----------------------
from PyQt6 import QtCore, QtGui  # noqa: E402

from stanza_im.core import profiles  # noqa: E402
from stanza_im.include import avatars as avatars_mod  # noqa: E402
from stanza_im.ui.main_window import MainWindow, _PAGE_ROSTER  # noqa: E402

profiles.set_active(ACCOUNT)
roster_cache.save(ACCOUNT, "", ITEMS)

_image = QtGui.QImage(8, 8, QtGui.QImage.Format.Format_RGB32)
_image.fill(QtGui.QColor("#3366cc"))
_buffer = QtCore.QBuffer()
_buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
_image.save(_buffer, "PNG")
avatars_mod.save_avatar("alice@example.com", bytes(_buffer.data()))

win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
check("the cached roster is rendered before the client", 
      win._show_cached_roster(ACCOUNT) is True)
check("the roster page is shown",
      win._stack.currentIndex() == _PAGE_ROSTER)
check("the cached contacts are in the roster",
      {"alice@example.com", "carol@example.com"}
      <= {user.jid for user in win._roster._users})
check("a cached avatar is prefilled",
      any(user.jid == "alice@example.com" and user.avatar_path
          for user in win._roster._users))
check("no cache means no early roster",
      win._show_cached_roster("nobody@example.com") is False)
win.deleteLater()

with open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
          encoding="utf-8") as fh:
    _mw_src = fh.read()
_login_body = _mw_src.split("def _on_login(self", 1)[1].split(
    "\n    def ", 1)[0]
check("login shows the cached roster before creating the client",
      _login_body.index("_show_cached_roster(jid)")
      < _login_body.index("JabberClient("))

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
