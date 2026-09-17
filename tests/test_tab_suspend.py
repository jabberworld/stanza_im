"""Offscreen tests for idle tab suspension (P7).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_tab_suspend.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_suspend_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_window import ChatWindow
from stanza_im.ui.main_window import MainWindow

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 1. ChatWidget suspend/resume ------------------------------------------------
cw = ChatWindow(ChatThemeFactory())
a = cw.open_chat("a@example.com", "A")
b = cw.open_chat("b@example.com", "B")
b.add_message(sender="B", body="hello", timestamp="12:00:00",
              direction="incoming")

check("current tab refuses suspension",
      cw.suspend_tab("b@example.com") is False)
check("inactive tab suspends", cw.suspend_tab("a@example.com") is True)
check("tab reported suspended", cw.is_suspended("a@example.com"))

# messages keep being accepted while suspended (no crash, no render)
a.add_message(sender="A", body="while asleep", timestamp="12:00:01",
              direction="incoming")
check("message while suspended kept", any(
    m.get("body") == "while asleep" for m in a._messages))

cw.resume_tab("a@example.com")
check("tab resumed", not cw.is_suspended("a@example.com"))
check("view recreated", not isinstance(a._view, type(None))
      and a._view.height() >= 0)

# 2. MainWindow scheduler gates ----------------------------------------------
class _FakeClient:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._client = _FakeClient()   # _maybe_suspend_tabs only checks for None
win._config.chat.idle_unload_minutes = 10

win._chat_window.open_chat("c@example.com", "C")   # current
win._chat_window.open_chat("d@example.com", "D")   # current (opened last)
win._tab_activity.clear()                          # everything idle
win._unread_jids = {"c@example.com"}               # C has unread

win._maybe_suspend_tabs()
check("current tab not suspended by scheduler",
      not win._chat_window.is_suspended("d@example.com"))
check("unread tab not suspended", not win._chat_window.is_suspended("c@example.com"))

win._unread_jids.clear()
idx = win._chat_window._tab_widget.indexOf(
    win._chat_window.get_chat("c@example.com"))
win._chat_window._tab_widget.setCurrentIndex(idx)   # make C current
win._maybe_suspend_tabs()
check("cold tab suspended by scheduler",
      win._chat_window.is_suspended("d@example.com"))
check("current tab stays awake",
      not win._chat_window.is_suspended("c@example.com"))

# opening a suspended tab again wakes it
win._chat_window._tab_widget.setCurrentIndex(
    win._chat_window._tab_widget.indexOf(
        win._chat_window.get_chat("d@example.com")))
check("switching to a tab resumes it",
      not win._chat_window.is_suspended("d@example.com"))

# 3. threshold 0 disables suspension -----------------------------------------
win._config.chat.idle_unload_minutes = 0
win._tab_activity.clear()
win._maybe_suspend_tabs()
check("threshold 0 keeps tabs loaded",
      not win._chat_window.is_suspended("c@example.com"))

# 4. main-process housekeeping ------------------------------------------------
win._trim_main_process_memory()   # must not raise
_mw_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "ui", "main_window.py"), encoding="utf-8").read()
check("housekeeping uses malloc_trim", "malloc_trim" in _mw_src)
check("housekeeping runs on a timer", "_memory_timer" in _mw_src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All tab-suspend tests passed.")
