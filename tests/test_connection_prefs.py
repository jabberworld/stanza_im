"""Connection preferences tests: priority mapping, config round-trip,
manual values preserved when switching to auto (no network required).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_connection_prefs.py
"""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_conn_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets
from stanza_im.core.storage import Config
from stanza_im.core.client import JabberClient
from stanza_im.i18n import load as load_i18n
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.preferences import PreferencesDialog

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


# ── preferences apply and preserve manual values ──────────────────

dlg = PreferencesDialog(cfg, ChatThemeFactory(), client=None)
controls = dlg._controls

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
dlg._apply_settings()

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


print("\nAll tests passed ✓" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
