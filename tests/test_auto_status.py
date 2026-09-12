"""Auto-status and roster status-combo tests.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_auto_status.py
"""
import os
import sys
import tempfile
import time

_SCRATCH = tempfile.mkdtemp(prefix="stanza_status_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets
from stanza_im.ui.main_window import MainWindow

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _FakeClient:
    def __init__(self):
        self.sent = []

    def send_presence(self, show=None, status="", priority=None):
        self.sent.append(show)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
win = MainWindow(app)
win._idle_timer.stop()

client = _FakeClient()
win._client = client
win._config.status.auto_away = True
win._config.status.away_minutes = 1
win._config.status.auto_xa = True
win._config.status.xa_minutes = 10
win._config.last_status = "online"

# 1. away applies when idle >= away_minutes (and < xa_minutes)
win._last_activity = time.monotonic() - 5 * 60
win._check_auto_status()
check("away applied", client.sent == ["away"])
check("combo shows away", win._status_combo.currentData() == "away")

# 2. repeated tick does not resend the same status
win._check_auto_status()
check("away not re-sent", client.sent == ["away"])

# 3. away -> xa upgrade once idle >= xa_minutes (the reported bug)
win._last_activity = time.monotonic() - 12 * 60
win._check_auto_status()
check("xa applied after away", client.sent == ["away", "xa"])
check("combo shows xa", win._status_combo.currentData() == "xa")

# 4. idempotent at xa
win._check_auto_status()
check("xa not re-sent", client.sent == ["away", "xa"])

# 5. activity reverts to last_status (presence + tray + combo)
ev = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress,
                       QtCore.QPointF(1, 1), QtCore.Qt.MouseButton.LeftButton,
                       QtCore.Qt.MouseButton.LeftButton,
                       QtCore.Qt.KeyboardModifier.NoModifier)
win.eventFilter(win.app, ev)
check("revert to last_status", client.sent == ["away", "xa", "online"])
check("applied reset to None", win._auto_status_applied is None)
check("combo back to online", win._status_combo.currentData() == "online")

# 6. session start syncs combo to config.last_status without extra presence
win._config.last_status = "dnd"
win._on_session_started()
check("combo synced at session start", win._status_combo.currentData() == "dnd")
check("no presence from programmatic sync", client.sent == ["away", "xa", "online"])
check("last_status untouched by signal leak", win._config.last_status == "dnd")

# 7. manual selection still works and resets the auto flag
win._status_combo.setCurrentIndex(win._status_combo.findData("away"))
check("manual change sends presence", client.sent[-1] == "away")
check("manual change resets applied", win._auto_status_applied is None)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
