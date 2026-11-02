"""Offscreen tests for the incoming-message tab policy.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_chat_open_tab.py
"""
import inspect
import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_open_tab_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import icons as icons_mod
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.preferences import PreferencesDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


check("the default policy is except_low",
      Config().chat.open_incoming_tab == "except_low")


def _win(mode):
    win = MainWindow.__new__(MainWindow)
    win._config = SimpleNamespace(
        chat=SimpleNamespace(open_incoming_tab=mode))
    return win


for mode, low, normal, high in (
        ("always", True, True, True),
        ("except_low", False, True, True),
        ("never", False, False, False)):
    win = _win(mode)
    check(f"{mode}: low priority tab", win._should_open_incoming_tab("low") == low)
    check(f"{mode}: normal priority tab",
          win._should_open_incoming_tab("normal") == normal)
    check(f"{mode}: high priority tab",
          win._should_open_incoming_tab("high") == high)


icons_mod.init_icons()
cfg = Config()
dlg = PreferencesDialog(cfg, ChatThemeFactory())
combo = dlg._controls["open_incoming_tab"]
check("the chat preferences expose the tab policy",
      isinstance(combo, QtWidgets.QComboBox)
      and [combo.itemData(i) for i in range(combo.count())]
      == ["always", "except_low", "never"])
check("the default policy is preselected",
      combo.currentData() == "except_low")
combo.setCurrentIndex(combo.findData("never"))
dlg._apply_settings()
check("apply stores the tab policy", cfg.chat.open_incoming_tab == "never")
dlg.deleteLater()

_received = inspect.getsource(MainWindow._on_message_received)
check("incoming 1:1 messages obey the tab policy",
      "_should_open_incoming_tab" in _received)
_pm = inspect.getsource(MainWindow._on_muc_private_message)
check("incoming private messages obey the tab policy",
      "_should_open_incoming_tab" in _pm
      and "focus=False" in _pm)

if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll open-tab tests passed.")
