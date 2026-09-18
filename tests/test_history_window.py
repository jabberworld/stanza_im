"""Offscreen tests for the history window / paging split.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_history_window.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_hist_win_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget, _HISTORY_MAX, _HISTORY_PAGE
from stanza_im.ui.preferences import PreferencesDialog

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 1. the setting defines the window, paging stays a small page ---------------
tab = ChatWidget("hist@example.com", "Hist", ChatThemeFactory())
tab.set_history([], 200, False)
check("setting defines the window", tab._window_size == 200)
check("paging step stays capped at one page", tab._batch_size() == _HISTORY_PAGE)

tab._window_size = 30
check("page never exceeds the window", tab._batch_size() == 30)

# 2. refresh size is capped by the in-memory history cap --------------------
captured = {}

tab._refresh_history_async = lambda size: captured.__setitem__("size", size)
tab._start_task = lambda coro: None
tab._window_size = 1000
tab.refresh_history()
check("refresh capped by _HISTORY_MAX",
      captured.get("size") == min(2000, _HISTORY_MAX))
tab.detach()

# 3. Preferences expose only the Chat-page control with a 1000 max ----------
cfg = Config()
dlg = PreferencesDialog(cfg, ChatThemeFactory())
spin = dlg._controls["history_limit_chat"]
check("chat history spin range is 10..1000",
      spin.minimum() == 10 and spin.maximum() == 1000)
check("no duplicate history control on the Application page",
      "history_limit" not in dlg._controls)
dlg.close()

# 4. the initial load no longer clamps the window to a page -----------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
check("initial load passes the window (not the page cap)",
      "set_history(entries, window, exhausted)" in _mw_src)
check("old blanket clamp removed", "_HISTORY_BATCH_LIMIT" not in _mw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All history-window tests passed.")
