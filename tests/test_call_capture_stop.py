"""Stopping a camera capture must not close PyAV under an active decode.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_call_capture_stop.py
"""
import os
import sys
import tempfile

os.environ["XDG_DATA_HOME"] = os.path.join(
    tempfile.mkdtemp(prefix="stanza_capture_stop_"), "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.xmpp import media  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Container:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def decode(self, stream):
        return iter(())


class _Loop:
    def __init__(self):
        self.callback = None

    def call_soon_threadsafe(self, callback):
        self.callback = callback


def _track(container, inflight):
    track = media._VideoCaptureTrack.__new__(media._VideoCaptureTrack)
    track._container = container
    track._stream = object()
    track._decode_inflight = inflight
    track._decode_loop = None
    track._pending_close = None
    track._stopped = False
    return track


if not media.HAS_AIORTC:
    print("SKIP: aiortc is unavailable")
    raise SystemExit(0)

container = _Container()
track = _track(container, inflight=True)
track.stop()
check("an in-flight decode is not closed under the executor",
      not container.closed and track._container is container)
track._on_decode_finished()
check("the deferred close happens after the worker finishes",
      container.closed and track._container is None)
check("the stopped track is marked", track._stopped)

container = _Container()
track = _track(container, inflight=False)
track.stop()
check("a capture with no active decode closes immediately", container.closed)

container = _Container()
track = _track(container, inflight=True)
track._on_decode_finished()
check("a worker finishing without stop keeps the capture", not container.closed)

container = _Container()
track = _track(container, inflight=True)
loop = _Loop()
track._decode_loop = loop
track._next_frame()
check("the worker schedules its completion on the owning loop",
      loop.callback == track._on_decode_finished)
track.stop()
check("the worker-completion callback is what closes the deferred capture",
      not container.closed)
track._on_decode_finished()
check("the deferred capture is closed by the scheduled callback",
      container.closed)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All capture-stop tests passed")
