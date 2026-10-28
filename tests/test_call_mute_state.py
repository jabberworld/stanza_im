"""Pre-connection mute/deafen state survives call binding.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_call_mute_state.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_call_mute_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.xmpp import jingle_rtp as jr  # noqa: E402
from stanza_im.xmpp import media  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Client:
    def __init__(self):
        self.events = []

    def emit(self, name, *args):
        self.events.append((name,) + args)


class _Call:
    def __init__(self):
        self.calls = []

    def set_audio_enabled(self, enabled):
        self.calls.append(("audio", enabled))

    def set_remote_audio_enabled(self, enabled):
        self.calls.append(("remote", enabled))

    def set_video_enabled(self, enabled):
        self.calls.append(("video", enabled))

    def set_local_preview(self, enabled):
        self.calls.append(("preview", enabled))


def _fresh():
    mgr = jr.JingleRtpManager.__new__(jr.JingleRtpManager)
    mgr.client = _Client()
    mgr.sessions = {}
    session = jr.CallSession(
        sid="s1", peer_bare="bob@example.com",
        peer_full="bob@example.com/phone", self_full="me@example.com/desk",
        initiator=True)
    mgr.sessions["s1"] = session
    return mgr, session


def _saved_before_bind():
    mgr, session = _fresh()
    mgr.set_call_audio("s1", False)
    mgr.set_call_audio_receive("s1", False)
    mgr.set_call_video("s1", False)
    return mgr, session


mgr, session = _fresh()
check("a new session starts with audio, remote audio and video enabled",
      session.audio_enabled and session.remote_audio_enabled
      and session.video_enabled)

mgr, session = _saved_before_bind()
check("audio state is stored before an engine call exists",
      session.audio_enabled is False)
check("remote audio state is stored before an engine call exists",
      session.remote_audio_enabled is False)
check("video state is stored before an engine call exists",
      session.video_enabled is False)

call = _Call()
mgr._bind_call(session, call)
check("pre-connection states reach the engine on bind",
      call.calls == [("audio", False), ("remote", False),
                     ("video", False), ("preview", False)])
check("the bound session gets the engine call", session.call is call)
check("call_bound is emitted after the states are applied",
      mgr.client.events[-1] == ("call_bound", "s1"))

mgr.set_call_audio("s1", True)
mgr.set_call_audio_receive("s1", True)
mgr.set_call_video("s1", True)
check("later toggles still reach the bound engine",
      call.calls[-3:] == [("audio", True), ("remote", True),
                          ("video", True)])

if media.HAS_AIORTC:
    engine = media.AiortcCall.__new__(media.AiortcCall)
    engine._local_audio = None
    engine._audio_play = None
    engine._local_video = None
    engine._audio_enabled = True
    engine._remote_audio_enabled = True
    engine._video_enabled = True
    engine.set_audio_enabled(False)
    engine.set_remote_audio_enabled(False)
    engine.set_video_enabled(False)
    check("the engine remembers states with no tracks yet",
          engine._audio_enabled is False
          and engine._remote_audio_enabled is False
          and engine._video_enabled is False)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All call mute-state tests passed")
