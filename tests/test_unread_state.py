"""Offscreen tests for unread-counter persistence across restarts.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_unread_state.py
"""
import os
import stat
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_unread_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core import unread_state
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. unread_state round-trip --------------------------------------------------
unread_state.save({"a@x": 3, "b@x": 0, "": 5, "c@x": "bad"})
check("round-trip keeps positive counts only",
      unread_state.load() == {"a@x": 3})
check("state file is 0600",
      stat.S_IMODE(os.stat(unread_state.path()).st_mode) == 0o600)

# Seed a "previous session" state before the window starts.
unread_state.save({"bob@example.com": 2, "room@conf.example": 1})

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 2. MainWindow restores counters --------------------------------------------
win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
check("restored total", win._unread_total == 3)
check("restored jids",
      win._unread_jids == {"bob@example.com", "room@conf.example"})
check("tray blinking restored", win._tray._blink_active)

win._add_roster_item({"jid": "bob@example.com", "name": "Bob",
                      "groups": ["Friends"]})
bob = next(u for u in win._roster._users if u.jid == "bob@example.com")
check("badge restored on the roster row", bob.unread_count == 2)

# 3. bump / reset keep the store and roster in sync --------------------------
win._bump_unread("bob@example.com")
check("bump updates the counter and total",
      win._unread_counts["bob@example.com"] == 3 and win._unread_total == 4)
check("bump updates the roster badge", next(
    u for u in win._roster._users
    if u.jid == "bob@example.com").unread_count == 3)

win._reset_unread("bob@example.com")
check("reset clears the counter",
      "bob@example.com" not in win._unread_counts and win._unread_total == 1)

win._flush_unread()
check("flush persists the current state",
      unread_state.load() == {"room@conf.example": 1})

# 4. static wiring ------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
check("roster rows carry the stored counters",
      "unread_count=self._unread_counts.get(jid, 0)" in _mw_src)
check("quit flushes unread state", "self._flush_unread()" in _mw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All unread-state tests passed.")
