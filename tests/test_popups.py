"""Offscreen tests for the tray popups mode (notifications.popups).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_popups.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_popups_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.tray import (
    POPUPS_OFF, POPUPS_SYSTEM, POPUPS_SYSTEM_MESSAGES, TrayIcon,
    normalize_popups_mode)

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── normalize_popups_mode ────────────────────────────────────────
check("a legacy True becomes system+messages",
      normalize_popups_mode(True) == POPUPS_SYSTEM_MESSAGES)
check("a legacy False becomes off",
      normalize_popups_mode(False) == POPUPS_OFF)
check("a mode string is kept",
      normalize_popups_mode(POPUPS_OFF) == POPUPS_OFF
      and normalize_popups_mode(POPUPS_SYSTEM_MESSAGES) == POPUPS_SYSTEM_MESSAGES)
check("a missing/unknown value defaults to system only",
      normalize_popups_mode(None) == POPUPS_SYSTEM
      and normalize_popups_mode("bogus") == POPUPS_SYSTEM)
check("the config default is system only",
      __import__("stanza_im.core.storage", fromlist=["Config"]).Config()
      .notifications.popups == POPUPS_SYSTEM)


# ── TrayIcon gating ──────────────────────────────────────────────
tray = TrayIcon()
shown = []
tray._tray.showMessage = lambda *args: shown.append(args)


def _show(kind):
    shown.clear()
    tray.show_message("t", "m", kind=kind)
    return bool(shown)


tray.set_popups_mode(POPUPS_OFF)
check("off hides system balloons", _show("system") is False)
check("off hides message balloons", _show("message") is False)

tray.set_popups_mode(POPUPS_SYSTEM)
check("system shows system balloons", _show("system") is True)
check("system hides message balloons", _show("message") is False)

tray.set_popups_mode(POPUPS_SYSTEM_MESSAGES)
check("system+messages shows system balloons", _show("system") is True)
check("system+messages shows message balloons", _show("message") is True)

tray.set_popups_mode(True)  # legacy value through the same normaliser
check("a legacy mode is normalised on set",
      tray.popups_mode() == POPUPS_SYSTEM_MESSAGES)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
