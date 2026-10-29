"""A failed call keeps its window and can redial in the same media mode."""
import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_call_redial_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.ui.call_window import CallWindow  # noqa: E402
from stanza_im.ui.main_window import MainWindow  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Tray:
    def __init__(self):
        self.messages = []

    def show_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class _Rtp:
    def __init__(self):
        self.stopped = []
        self.preview = []

    def stop_call_preview(self, sid):
        self.stopped.append(sid)


win = MainWindow.__new__(MainWindow)
win._tray = _Tray()
win._client = SimpleNamespace(rtp_calls=_Rtp(),
                              set_call_local_preview=lambda *a: None)
win._call_windows = {}
win._on_call_requested = lambda jid, video=False: \
    win._call_windows.__setitem__("new", (jid, video))

cw = CallWindow("old", "Bob", video=True, peer_jid="bob@example.com")
cw.redial_requested.connect(lambda *a: win._on_call_redial(*a))
win._call_windows["old"] = cw
win._on_call_failed("old", "bob@example.com/desk", "connection failed", True)
check("a failed call keeps its window", "old" in win._call_windows)
check("the failed window shows redial", cw._failed and cw._redial_btn.isVisibleTo(cw))
cw._redial_btn.click()
check("redial starts a new call in the same mode",
      win._call_windows.get("new") == ("bob@example.com", True))
check("redial closes the old window", "old" not in win._call_windows and cw.isHidden())

# A failure without an existing window still reaches the tray.
win._call_windows.clear()
win._on_call_failed("", "bob@example.com/desk", "no answer", False)
check("a failure without a window uses the tray", bool(win._tray.messages))

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All call-redial tests passed")
