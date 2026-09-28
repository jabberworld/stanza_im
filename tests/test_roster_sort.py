"""Offscreen tests for the roster sort-by-status option.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_roster_sort.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_rsort_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core.storage import Config
from stanza_im.ui.roster_widget import RosterWidget
from stanza_im.ui.roster_style import UserItem

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _user(name, status):
    return UserItem(jid=f"{name}@x", name=name, group="G", status=status,
                    status_message="", icon_key=status)


cfg = Config()
check("roster_sort_by_status defaults on",
      cfg.appearance.roster_sort_by_status is True)
check("roster_show_offline defaults on",
      cfg.appearance.roster_show_offline is True)
cfg.appearance.roster_sort_by_status = False
cfg.appearance.roster_show_offline = False
cfg.save()
reloaded = Config()
check("both flags persist",
      reloaded.appearance.roster_sort_by_status is False
      and reloaded.appearance.roster_show_offline is False)

r = RosterWidget()
r.add_group("G")
for name, status in (("Zoe", "online"), ("Ann", "dnd"), ("Bob", "chat"),
                     ("Carl", "away"), ("Dan", "xa"), ("Eve", "offline")):
    r.add_user(_user(name, status))


def _order():
    return [u.name for u in r._sorted_users["G"]]


r.set_sort_by_status(True)
check("status sort: chat, online, away, xa, dnd, offline",
      _order() == ["Bob", "Zoe", "Carl", "Dan", "Ann", "Eve"])
r.set_sort_by_status(False)
check("plain sort is alphabetical",
      _order() == ["Ann", "Bob", "Carl", "Dan", "Eve", "Zoe"])

r2 = RosterWidget()
r2.add_group("G")
for name in ("Zoe", "Ann", "Mia"):
    r2.add_user(_user(name, "online"))
r2.set_sort_by_status(True)
check("same status falls back to the alphabet",
      [u.name for u in r2._sorted_users["G"]] == ["Ann", "Mia", "Zoe"])

r3 = RosterWidget()
r3.add_group("G")
r3.add_user(_user("B", "away"))
r3.add_user(_user("A", "online"))
r3.add_user(_user("C", ""))
r3.set_sort_by_status(True)
check("online ranks above away (empty maps to online)",
      [u.name for u in r3._sorted_users["G"]] == ["A", "C", "B"])

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All roster-sort tests passed.")
