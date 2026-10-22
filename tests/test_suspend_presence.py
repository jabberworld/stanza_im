"""Presence around system sleep: offline before suspend, status on wake.

The monitor itself listens to the system D-Bus (logind/UPower); these tests
drive the MainWindow handlers with fakes and check the monitor degrades to a
no-op without a bus.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_suspend_presence.py
"""
import inspect
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_suspend_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load, tr
from stanza_im.ui import suspend_monitor as monitor_mod
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])


class _FakeXmpp:
    def __init__(self, connected=True):
        self.connected = connected

    def is_connected(self):
        return self.connected


class _FakeClient:
    def __init__(self, connected=True):
        self.xmpp = _FakeXmpp(connected)
        self.calls = []

    def send_presence(self, show=None, status="", priority=None):
        self.calls.append((show, status))

    def set_pep_sweep_paused(self, paused):
        pass


class _FakeCombo:
    def __init__(self, show):
        self.show = show

    def currentData(self):
        return self.show


def make_window(show="away", connected=True, opt=True):
    win = MainWindow.__new__(MainWindow)
    cfg = Config.defaults()
    cfg.connection.offline_on_suspend = bool(opt)
    cfg.status.message = "working"
    cfg.last_status = show
    win._config = cfg
    win._client = _FakeClient(connected)
    win._status_combo = _FakeCombo(show)
    win._suspend_active = False
    win._suspend_show = ""
    win._restore_status_after_session = ""
    win._last_activity = 0.0
    win._auto_status_applied = None
    win._tray_icons = []
    win._combo_values = []
    win._set_tray_status_icon = lambda value: win._tray_icons.append(value)
    win._set_status_combo = lambda value: win._combo_values.append(value)
    return win


# 1. suspend sends the dedicated offline text ------------------------------
win = make_window("away")
check("the option is enabled by default",
      Config.defaults().connection.offline_on_suspend is True)
win._on_system_suspend()
check("suspend sends the dedicated offline status",
      win._client.calls == [("offline", tr("status_suspend"))])
check("the pre-sleep status is remembered",
      win._suspend_active is True and win._suspend_show == "away")
win._on_system_suspend()
check("a repeated suspend does nothing", len(win._client.calls) == 1)

win._on_system_resume()
check("resume restores the status and the user's message",
      win._client.calls[-1] == ("away", "working"))
check("resume updates the tray and the combo",
      win._tray_icons == ["away"] and win._combo_values == ["away"])
win._on_system_resume()
check("a repeated resume does nothing", len(win._client.calls) == 2)

# 2. disabled / offline / disconnected are no-ops -------------------------
off = make_window("away", opt=False)
off._on_system_suspend()
check("the option turns the behaviour off", off._client.calls == [])

already = make_window("offline")
already._on_system_suspend()
check("an already offline account is left alone", already._client.calls == [])

nolink = make_window("away", connected=False)
nolink._on_system_suspend()
check("a disconnected client sends nothing", nolink._client.calls == [])

noresume = make_window("away")
noresume._on_system_resume()
check("resume without a suspend does nothing", noresume._client.calls == [])

# 3. a stream lost during sleep restores on the next session ---------------
woke = make_window("dnd")
woke._on_system_suspend()
woke._client.xmpp.connected = False
woke._on_system_resume()
check("a lost stream defers the restore",
      woke._client.calls == [("offline", tr("status_suspend"))]
      and woke._restore_status_after_session == "dnd")
woke._client.xmpp.connected = True
woke._restore_suspended_presence()
check("the deferred status is sent after the reconnect",
      woke._client.calls[-1] == ("dnd", "working")
      and woke._restore_status_after_session == "")

# 4. auto-status never fires while suspended ------------------------------
sleeping = make_window("online")
sleeping._config.status.auto_away = True
sleeping._config.status.away_minutes = 1
sleeping._suspend_active = True
sleeping._check_auto_status()
check("auto-status is paused while suspended", sleeping._client.calls == [])

# 5. the monitor and its D-Bus sources ------------------------------------
monitor = monitor_mod.SuspendMonitor()
check("the monitor reports its availability as a bool",
      isinstance(monitor.available(), bool))
check("the monitor exposes both transition signals",
      hasattr(monitor, "suspending") and hasattr(monitor, "resumed"))
src = inspect.getsource(monitor_mod)
check("the monitor listens to logind PrepareForSleep",
      "org.freedesktop.login1" in src and "PrepareForSleep" in src)
check("the monitor has the UPower fallback",
      "org.freedesktop.UPower" in src and "Sleeping" in src)
# The duplicate logind/UPower transitions collapse into one signal per edge.
edges = []
monitor.suspending.connect(lambda: edges.append("sleep"))
monitor.resumed.connect(lambda: edges.append("wake"))
monitor._on_logind(True)
monitor._on_upower(True)
monitor._on_logind(False)
check("one signal per sleep edge", edges == ["sleep", "wake"])

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All suspend-presence tests passed.")
