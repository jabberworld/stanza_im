"""Offscreen tests for the tray icon context menu.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_tray_menu.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_tray_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load, tr
from stanza_im.ui.icons import init_icons
from stanza_im.ui.tray import TrayIcon, _STATUS_KEYS

i18n_load("ru")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


tray = TrayIcon(icons=init_icons())
menu = tray._menu
actions = menu.actions()


def is_sep(action):
    return action.isSeparator()


def is_action(action, text):
    return not action.isSeparator() and action.text() == text


# ── Structure and order ────────────────────────────────────────────
check("menu starts with show/hide", is_action(actions[0], tr("tray_show")))
check("settings next to show/hide",
      is_action(actions[1], tr("menu_preferences")))
check("separator after show/settings block", is_sep(actions[2]))

status_slice = actions[3:3 + len(_STATUS_KEYS)]
check("exactly the roster statuses between separators",
      [a.text() for a in status_slice]
      == [tr(f"status_{k}") for k in _STATUS_KEYS])
check("second separator after statuses",
      is_sep(actions[3 + len(_STATUS_KEYS)]))
check("quit is last item", is_action(actions[-1], tr("tray_quit")))
check("menu has exactly two separators",
      sum(1 for a in actions if is_sep(a)) == 2)
check("menu has no unexpected extra items",
      len(actions) == 1 + 1 + len(_STATUS_KEYS) + 1 + 2)


# ── Status actions: checkable + icons ──────────────────────────────
def status_action(key):
    for a in status_slice:
        if a.text() == tr(f"status_{key}"):
            return a
    return None


check("status actions are checkable",
      all(status_action(k).isCheckable() for k in _STATUS_KEYS))
check("status actions carry the same icons as the roster",
      all(not status_action(k).icon().isNull() for k in _STATUS_KEYS))


# ── Signals ────────────────────────────────────────────────────────
received_status = []
received_settings = []
tray.status_requested.connect(received_status.append)
tray.settings_requested.connect(lambda: received_settings.append(True))

status_action("away").trigger()
check("status action emits status_requested('away')",
      received_status == ["away"])

settings_item = actions[1]
settings_item.trigger()
check("settings action emits settings_requested", received_settings == [True])

tray.set_current_status("dnd")
menu.aboutToShow.emit()
check("current status marked in menu",
      status_action("dnd").isChecked()
      and all(not status_action(k).isChecked()
              for k in _STATUS_KEYS if k != "dnd"))
tray.set_current_status("bogus")
check("unknown show normalized to offline",
      tray._current_status == "offline")
tray.set_current_status("online")
menu.aboutToShow.emit()
check("checkmark follows set_current_status",
      status_action("online").isChecked()
      and not status_action("dnd").isChecked())


# ── No icons passed: menu still builds ─────────────────────────────
tray_bare = TrayIcon()
check("menu builds without icons cache",
      len(tray_bare._menu.actions()) == 1 + 1 + len(_STATUS_KEYS) + 1 + 2)
check("status icons null without icons cache",
      all(tray_bare._status_actions[k].icon().isNull() for k in _STATUS_KEYS))


print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)