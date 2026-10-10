"""Tests for the startup presence-OSD throttle (adaptive grace window).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_presence_osd.py
"""
import os
import sys
import time
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = os.path.join("/tmp", "stanza_presosd")
os.environ.setdefault("XDG_CONFIG_HOME", os.path.join(_SCRATCH, "config"))
os.environ.setdefault("XDG_DATA_HOME", os.path.join(_SCRATCH, "data"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.ui.main_window import MainWindow

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Osd:
    def __init__(self):
        self.shows = []

    def show(self, *args, **kwargs):
        self.shows.append((args, kwargs))


class _Icons:
    @staticmethod
    def get_status_icon(_show):
        return None


def _make_fake():
    fake = types.SimpleNamespace(
        _config=types.SimpleNamespace(notifications=types.SimpleNamespace(
            osd_enabled=True, osd_status="any")),
        _osd_status_seen=set(),
        _presence_osd_grace_until=time.monotonic() + 5.0,
        _osd=_Osd(),
        _icons=_Icons(),
    )
    fake._roster_name = lambda jid: jid
    return fake


def _call(fake, jid, new, old):
    MainWindow._maybe_osd_status(fake, jid, new, old)


# 1. the initial replay is silent --------------------------------------------
fake = _make_fake()
for i in range(50):
    _call(fake, f"user{i}@example.com", "online", "offline")
check("the initial presence replay shows no OSD", fake._osd.shows == [])
check("the replay seeds the seen set", len(fake._osd_status_seen) == 50)
check("the replay keeps extending the grace window",
      fake._presence_osd_grace_until > time.monotonic() + 1.0)

# 2. a repeat presence of a seen contact is still silent ---------------------
_call(fake, "user0@example.com", "away", "online")
check("a replayed resource change stays silent", fake._osd.shows == [])

# 3. once the burst stops, a real transition shows an OSD --------------------
fake._presence_osd_grace_until = 0.0     # the tail has elapsed
_call(fake, "user0@example.com", "offline", "online")
check("a real transition after the burst shows an OSD",
      len(fake._osd.shows) == 1)

# 4. no OSD when the status did not change -----------------------------------
before = len(fake._osd.shows)
_call(fake, "user0@example.com", "online", "online")
check("an unchanged status shows no OSD", len(fake._osd.shows) == before)

# 5. the mode gate (never) suppresses it -------------------------------------
fake2 = _make_fake()
fake2._config.notifications.osd_status = "never"
fake2._presence_osd_grace_until = 0.0
fake2._osd_status_seen.add("x@example.com")
_call(fake2, "x@example.com", "offline", "online")
check("osd_status=never shows nothing", fake2._osd.shows == [])

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All presence-OSD tests passed.")
