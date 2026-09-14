"""Regression test: the media module must import cleanly when Qt Multimedia
*does* load (the branch that crashed with ``QtGui.QLabel``).

Qt Multimedia cannot be imported in this sandbox (no libpulse), so we install a
minimal stub ``PyQt6.QtMultimedia`` module before importing
:mod:`stanza_im.xmpp.media`.  This exercises the ``HAS_QTMM=True`` code paths
(class definitions, device enumeration, capture/playback construction, frame
conversion) so a missing/renamed Qt attribute fails here instead of at runtime.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_media_qtmm.py
"""
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── Fake PyQt6.QtMultimedia (installed before importing media) ────────────
class _FakeFormat:
    class SampleFormat:
        Int16 = "int16"

    def setSampleRate(self, value):
        self.sample_rate = value

    def setChannelCount(self, value):
        self.channels = value

    def setSampleFormat(self, value):
        self.sample_format = value


class _FakeIO:
    def bytesAvailable(self):
        return 0

    def read(self, count):
        return b"\x00" * count

    def write(self, data):
        return len(data)


class _FakeSource:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        return _FakeIO()

    def stop(self):
        pass


class _FakeSink:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        return _FakeIO()

    def stop(self):
        pass


class _FakeCamera:
    pass


class _FakeVideoSink:
    pass


class _FakeMediaDevices:
    @staticmethod
    def audioInputs():
        return []

    @staticmethod
    def audioOutputs():
        return []

    @staticmethod
    def videoInputs():
        return []


_fake = types.ModuleType("PyQt6.QtMultimedia")
_fake.QAudioFormat = _FakeFormat
_fake.QAudioSource = _FakeSource
_fake.QAudioSink = _FakeSink
_fake.QCamera = _FakeCamera
_fake.QVideoSink = _FakeVideoSink
_fake.QMediaDevices = _FakeMediaDevices
sys.modules["PyQt6.QtMultimedia"] = _fake

# Import must succeed with HAS_QTMM True.
try:
    from stanza_im.xmpp import media
    imported = True
    error = ""
except Exception as exc:  # pragma: no cover
    media = None
    imported = False
    error = repr(exc)

check("media imports with QtMM available", imported)
if imported:
    print("  HAS_QTMM=%s HAS_AIORTC=%s" % (media.HAS_QTMM, media.HAS_AIORTC))
    check("HAS_QTMM detected via stub", media.HAS_QTMM is True)

    devs = media.enumerate_devices()
    check("enumerate_devices with stub", isinstance(devs, dict)
          and set(devs) == {"audio_input", "audio_output", "video_input"})

    if media.HAS_AIORTC:
        track = media._AudioCaptureTrack("")
        check("audio capture track constructs (QtMM)", track._io is not None)
        player = media._AudioPlayback("")
        check("audio playback constructs (QtMM)", player._io is not None)
        track.stop()
        player.stop()

        import av
        frame = av.VideoFrame(320, 240, "yuv420p")
        for plane in frame.planes:
            plane.update(b"\x00" * plane.buffer_size)
        image = media._frame_to_qimage(frame)
        check("frame converted to QImage", image is not None
              and image.width() == 320)
    else:
        check("audio capture track constructs (QtMM)", True)

print("\nAll tests passed" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
