"""Offscreen tests for the client reconnect engine.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_reconnect.py
"""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_reconnect_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import JabberClient

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


class _FakeXMPP:
    plugin = {}

    def __init__(self):
        self.connected = False

    def is_connected(self):
        return self.connected

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _client(connect_after: int):
    class _C(JabberClient):
        def __init__(self):
            self.events = []
            self._reconnect_enabled = True
            self._shutting_down = False
            self._reconnect_task = None
            self._reconnect_handle = None
            self._reconnect_attempt = 0
            self.attempts = 0
            self.stream_management = False

        def emit(self, name, *a, **k):
            self.events.append((name, a))

        def _start_task(self, coro):
            return loop.create_task(coro)

    c = _C()
    c.xmpp = _FakeXMPP()
    c._RECONNECT_BACKOFF = (0.01, 0.01, 0.01)

    async def _connect():
        c.attempts += 1
        if c.attempts < connect_after:
            raise RuntimeError("down")
        c.xmpp.connected = True

    c.connect_async = _connect
    return c


# 1. The loop retries with backoff until connected and emits events.
c = _client(connect_after=3)
loop.run_until_complete(asyncio.wait_for(c._reconnect_loop(), timeout=5))
names = [n for n, _ in c.events]
check("reconnect retries until connected", c.attempts == 3)
check("reconnecting is emitted per attempt",
      names.count("reconnecting") == 3)
check("reconnect_failed is emitted on failures",
      names.count("reconnect_failed") == 2)
check("reconnected is emitted at the end", names[-1] == "reconnected")

# 2. The backoff ladder caps at 30 s with no attempt limit.
check("the backoff ladder grows and caps at 30 s",
      JabberClient._RECONNECT_BACKOFF[-1] == 30.0)
# 3. resume_expected is based on the XEP-0198 sm_id (no phantom flag).
rc = _client(connect_after=1)
rc.stream_management = True
rc.xmpp.plugin = {"xep_0198": type("P", (), {"sm_id": None})()}
check("resume_expected is False without sm_id",
      rc.resume_expected() is False)
rc.xmpp.plugin["xep_0198"].sm_id = "abc"
check("resume_expected is True with sm_id",
      rc.resume_expected() is True)
check("resume_expected is False without stream management",
      _client(1).resume_expected() is False)

# 4. An explicit disconnect cancels the loop and disables reconnect.
cc = _client(connect_after=999)
loop.run_until_complete(asyncio.wait_for(cc.disconnect(), timeout=5))
check("disconnect disables reconnect", cc._reconnect_enabled is False)
check("disconnect marks shutting down", cc._shutting_down is True)
check("disconnect cancels any pending reconnect task",
      cc._reconnect_task is None)

# 5. A resume cancels a scheduled reconnect (via _cancel_reconnect).
rr = _client(connect_after=999)
rr._reconnect_handle = loop.call_later(30, lambda: None)
rr._cancel_reconnect()
check("a resumed session cancels the reconnect handle",
      rr._reconnect_handle is None)

# 6. UI status bar + reconnect button ---------------------------------------
from PyQt6 import QtWidgets  # noqa: E402
from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.core.storage import Config  # noqa: E402

i18n_load("en")
_qt = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
from stanza_im.ui.main_window import MainWindow  # noqa: E402

w = MainWindow(_qt)


class _UIClient:
    def on(self, *a, **k):
        pass

    def resume_expected(self):
        return True

    def manual_reconnect(self):
        pass

    def disconnect(self):
        pass


w._client = _UIClient()
check("the status bar starts hidden", w._status_bar.isHidden())
check("the reconnect button starts hidden", w._reconnect_btn.isHidden())
w._on_disconnected()  # resume expected -> busy, no button yet
check("a resumable drop shows the busy bar but no button",
      not w._status_bar.isHidden() and w._reconnect_btn.isHidden())
w._on_reconnecting(2, 5.0)
check("reconnecting shows the attempt and the button",
      "2" in w._status_label.text() and not w._reconnect_btn.isHidden())
w._on_reconnect_failed(3)
check("a failed attempt keeps the offline state + button",
      w._status_label.text() != "" and not w._reconnect_btn.isHidden())
w._on_reconnected()
check("a reconnect clears the bar and button",
      w._status_bar.isHidden() and w._reconnect_btn.isHidden())

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All reconnect tests passed.")
