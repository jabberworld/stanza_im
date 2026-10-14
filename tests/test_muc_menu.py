"""Offscreen tests for the MUC participant context menu.

The «Изменить роль» / «Изменить ранг» submenus must mark the occupant's
current role/affiliation with a checkmark.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_menu.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_mucmenu_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _submenu(menu, title):
    for act in menu.actions():
        sub = act.menu()
        if sub is not None and sub.title() == title:
            return sub
    return None


def _checked(submenu):
    return {act.text(): act.isChecked() for act in submenu.actions()}


def _enabled(submenu):
    return {act.text(): act.isEnabled() for act in submenu.actions()}


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
win._client = None
win._muc_self_nicks = {"room@conf.example": "me"}


def _open_menu(our_role, our_aff, target):
    win._muc_users = {
        "room@conf.example": {
            "me": {"role": our_role, "affiliation": our_aff},
            "bob": target,
        }
    }
    captured = {}
    orig = QtWidgets.QMenu.exec
    QtWidgets.QMenu.exec = lambda self, *a: captured.setdefault("menu", self)
    try:
        win._on_muc_participant_context("room@conf.example", "bob", None)
    finally:
        QtWidgets.QMenu.exec = orig
    return captured["menu"]


# 1. current role/affiliation are checkmarked --------------------------------
menu = _open_menu("moderator", "owner",
                  {"role": "participant", "affiliation": "member",
                   "real_jid": "bob@example.com/x"})
role_menu = _submenu(menu, tr("muc_user_change_role"))
aff_menu = _submenu(menu, tr("muc_user_change_affiliation"))
check("role submenu exists", role_menu is not None)
check("affiliation submenu exists", aff_menu is not None)

roles = _checked(role_menu)
check("participant role checked", roles.get(tr("muc_role_participant")) is True)
check("visitor role not checked", roles.get(tr("muc_role_visitor")) is False)
check("moderator role not checked", roles.get(tr("muc_role_moderator")) is False)

affs = _checked(aff_menu)
check("member affiliation checked", affs.get(tr("muc_affiliation_member")) is True)
check("owner affiliation not checked", affs.get(tr("muc_affiliation_owner")) is False)
check("none affiliation not checked", affs.get(tr("muc_affiliation_none")) is False)

# 2. moderator sees enabled actions ------------------------------------------
check("role actions enabled for moderator",
      all(_enabled(role_menu).values()))
check("affiliation actions enabled for owner",
      all(_enabled(aff_menu).values()))

# 3. a plain participant cannot manage; the checked item still marks state ----
menu = _open_menu("participant", "none",
                  {"role": "visitor", "affiliation": "none",
                   "real_jid": "bob@example.com/x"})
role_menu = _submenu(menu, tr("muc_user_change_role"))
aff_menu = _submenu(menu, tr("muc_user_change_affiliation"))
check("visitor role checked", _checked(role_menu).get(tr("muc_role_visitor")) is True)
check("role actions disabled for participant",
      not any(_enabled(role_menu).values()))
check("none affiliation checked", _checked(aff_menu).get(tr("muc_affiliation_none")) is True)

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All MUC-menu tests passed.")
