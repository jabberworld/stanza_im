"""Offscreen tests for the connection-state UI (progress + reconnect).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_connection_state.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_conn_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.ui.main_window import MainWindow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()

# The connection UI lives in the roster's bottom panel (above the status
# combo), not in a window status bar.
check("the connection widgets exist",
      hasattr(win, "_conn_progress") and hasattr(win, "_reconnect_btn")
      and hasattr(win, "_reconnect_timer"))
check("no window status bar is used", not hasattr(win, "_status_bar"))


def shown(widget):
    return not widget.isHidden()


# Reconnecting: the button carries the countdown, the bar is visible.
win._on_reconnecting(2, 15)
check("reconnecting shows the countdown on the button",
      shown(win._reconnect_btn) and "15" in win._reconnect_btn.text())
check("the progress bar is visible while reconnecting",
      shown(win._conn_progress))
win._tick_reconnect()
check("the countdown ticks down", "14" in win._reconnect_btn.text())

# A live session drops the reconnect affordance and the bar.
win._clear_status()
check("a live session hides the reconnect button",
      not shown(win._reconnect_btn) and not shown(win._conn_progress))

# Offline offers a manual reconnect.
win._set_offline_status()
check("offline offers a manual reconnect",
      shown(win._reconnect_btn)
      and win._reconnect_btn.text() == tr("reconnect_now"))

# The connect progress is determinate (0-100) for the login stages.
win._connect_progress_active = True
win._conn_progress_value = 0
win._set_conn_progress(80)
check("the connect progress is determinate",
      win._conn_progress.minimum() == 0 and win._conn_progress.maximum() == 100
      and win._conn_progress.value() == 80)

# The initial connect is terminal and monotonic: the post-session stage in
# _connect_async (which runs after _on_session_started) must not resurrect it.
win._set_conn_progress(60)
check("the connect progress never steps backwards",
      win._conn_progress.value() == 80)
win._finish_connect_progress()
check("finishing the connect hides the bar", not shown(win._conn_progress))
win._set_conn_progress(60)
check("a late progress write cannot resurrect the bar",
      not shown(win._conn_progress))

# Offline private storage (notes) must not wait for the IQ timeout.
import asyncio

from stanza_im.ui.notes_widget import NotesWidget


class _OfflineXmpp:
    def is_connected(self):
        return False


class _OfflineClient:
    xmpp = _OfflineXmpp()

    async def get_notes(self):
        raise AssertionError("get_notes must not run while offline")


notes = NotesWidget(lambda: _OfflineClient(), lambda coro: coro)
asyncio.new_event_loop().run_until_complete(notes._load_async())
check("offline notes fetch is skipped", notes._notes == [])

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All connection-state tests passed.")
