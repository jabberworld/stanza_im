"""Call state follows the media connection, not the SDP accept.

The UI used to show "In call" and start the duration when the session-accept
arrived, several seconds before ICE/DTLS connected.  Now the session is
"connecting" until the peer connection reports "connected".

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_call_state.py
"""
import inspect
import os
import sys
import tempfile
from types import SimpleNamespace

_SCRATCH = tempfile.mkdtemp(prefix="stanza_callstate_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.i18n import en, ru
from stanza_im.ui.main_window import MainWindow
from stanza_im.xmpp.jingle_rtp import JingleRtpManager

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


class _Client:
    def __init__(self):
        self.emitted = []

    def emit(self, *args):
        self.emitted.append(args)


def manager():
    mgr = JingleRtpManager.__new__(JingleRtpManager)
    mgr.client = _Client()
    mgr.terminated = []
    mgr.closed = []
    mgr._terminate = lambda s, r, send=False: mgr.terminated.append((s.sid, r))
    mgr._close_session = lambda s, state, reason="": \
        mgr.closed.append((s.sid, state, reason))
    return mgr


mgr = manager()
session = SimpleNamespace(sid="s1", peer_full="rain@example.com/phone",
                          state="accepted")
mgr._on_media_state(session, "connection", "checking")
check("checking does not mark the call active",
      mgr.client.emitted == [] and session.state == "accepted")
mgr._on_media_state(session, "connection", "connected")
check("connected promotes the call to active",
      session.state == "active"
      and mgr.client.emitted == [
          ("call_state", "s1", "rain@example.com/phone", "active")])
mgr._on_media_state(session, "connection", "connected")
check("a repeated connected event does not duplicate the state",
      len(mgr.client.emitted) == 1)

failed = SimpleNamespace(sid="s2", peer_full="rain@example.com/phone",
                         state="accepted")
mgr._on_media_state(failed, "connection", "failed")
check("a failed media connection reports the failure",
      ("call_failed", "rain@example.com/phone", "connection failed")
      in mgr.client.emitted
      and mgr.terminated == [("s2", "connectivity-error")]
      and mgr.closed == [("s2", "failed", "connectivity-error")])

# The answerer emits "connecting" (not "active") on the session accept.
accept_src = inspect.getsource(JingleRtpManager._accept)
check("the answerer emits connecting before media connects",
      '"connecting"' in accept_src)
accept_in_src = inspect.getsource(JingleRtpManager._on_session_accept)
check("the caller emits connecting after the session-accept",
      '"connecting"' in accept_in_src)
check("both call paths wire the media state callback",
      inspect.getsource(JingleRtpManager._send_session_initiate).count(
          "on_state=lambda kind, state") == 1
      and accept_src.count("on_state=lambda kind, state") == 1)

state_src = inspect.getsource(MainWindow._on_call_state)
check("the UI shows a ringing label", "call_ringing" in state_src)
check("the UI shows connecting before the call is established",
      "call_connecting" in state_src)
_active_block = state_src.split('if state == "active":', 1)[1]
_connecting_block = state_src.split(
    'if state == "connecting":', 1)[1].split('if state == "active":', 1)[0]
check("the UI starts the duration only when active",
      "call_active" in _active_block
      and "start_duration" in _active_block
      and "start_duration" not in _connecting_block)
check("the Muji window duration starts from the first active session",
      "start_duration" not in inspect.getsource(MainWindow._on_muji_joined)
      and "start_duration" in state_src)

check("the active label is localized",
      en.STRINGS["call_active"] == "Call established"
      and ru.STRINGS["call_active"] == "Соединение установлено")
check("the ringing label is localized",
      en.STRINGS["call_ringing"] == "Ringing…"
      and ru.STRINGS["call_ringing"] == "Звоним…")

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All call-state tests passed.")
