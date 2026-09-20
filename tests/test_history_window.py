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

# 0. default history window ---------------------------------------------------
check("history default is 50", Config().chat.history_limit == 50)

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
_prefs_src = open(os.path.join(_root, "stanza_im", "ui", "preferences.py"),
                  encoding="utf-8").read()
check("history setting lives on the Chat General tab",
      'general_form.addRow(tr("prefs_history_limit")' in _prefs_src
      and 'chat_form.addRow(tr("prefs_history_limit")' not in _prefs_src)
_mw_src = open(os.path.join(_root, "stanza_im", "ui", "main_window.py"),
               encoding="utf-8").read()
check("initial load passes the window (not the page cap)",
      "set_history(entries, window, exhausted)" in _mw_src)
check("old blanket clamp removed", "_HISTORY_BATCH_LIMIT" not in _mw_src)

# 5. the "local history cleared" marker reloads from the server --------------
tab2 = ChatWidget("hist2@example.com", "Hist2", ChatThemeFactory())
requests = []
tab2.server_history_requested.connect(lambda *a: requests.append(a))
tab2.history_cleared()
check("cleared marker reset the fetch guard", tab2._server_fetching is False)
html = tab2._view.toHtml()
check("marker link is a server-load control link", "stanza:load:" in html)
tab2._open_link("stanza:load:")
check("marker click requests server history", bool(requests))
tab2.detach()

_cv_src = open(os.path.join(_root, "stanza_im", "ui", "chat_view.py"),
               encoding="utf-8").read()
check("load control link is preventDefaulted and relayed",
      "a.stanza-load" in _cv_src and "__stanzaLoadRef" in _cv_src)
_cw_src = open(os.path.join(_root, "stanza_im", "ui", "chat_widget.py"),
               encoding="utf-8").read()
check("marker uses the stanza-load control class",
      'class="stanza-load"' in _cw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All history-window tests passed.")
