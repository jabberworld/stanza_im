"""Call codec/bitrate/resolution settings and the media helpers.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_calls_settings.py
"""
import inspect
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_calls_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtGui, QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui import preferences as prefs_mod
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.preferences import PreferencesDialog
from stanza_im.xmpp import media

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


# 1. config defaults ---------------------------------------------------------
cfg = Config.defaults()
check("the call codec defaults are present",
      cfg.calls.audio_codec == "auto" and cfg.calls.video_codec == "auto"
      and cfg.calls.audio_bitrate_kbps == 96
      and cfg.calls.video_bitrate_kbps == 500
      and cfg.calls.video_max_height == 0)
check("the screen box default is Full HD",
      cfg.devices.screen_share_max_width == 1920
      and cfg.devices.screen_share_max_height == 1080)
check("a legacy width-only box becomes 16:9",
      prefs_mod._screen_box(1600, 0) == (1600, 900)
      and prefs_mod._screen_box(400, 300) == (400, 300))

# 2. codec preference order --------------------------------------------------
check("auto keeps aiortc's order",
      media._ordered_codecs("video", "auto") == [])
vp8 = media._ordered_codecs("video", "vp8")
check("VP8 is moved first", vp8 and vp8[0].mimeType == "video/VP8")
h264 = media._ordered_codecs("video", "h264")
check("H264 is moved first", h264 and h264[0].mimeType == "video/H264")
pcmu = media._ordered_codecs("audio", "pcmu")
check("PCMU is moved first", pcmu and pcmu[0].mimeType == "audio/PCMU")
check("an unknown codec leaves the order alone",
      media._ordered_codecs("video", "bogus") == [])

# 3. encoder bitrate defaults and live update -------------------------------
from aiortc.codecs.opus import OpusEncoder  # noqa: E402
from aiortc.codecs.vpx import Vp8Encoder  # noqa: E402

media.set_media_defaults(audio_kbps=64, video_kbps=300)
opus = OpusEncoder()
vp8_encoder = Vp8Encoder()
check("the Opus bitrate comes from the settings",
      opus.codec.bit_rate == 64000)
check("the VP8 bitrate comes from the settings",
      vp8_encoder.target_bitrate == 300000)
media.set_media_defaults(video_kbps=900)
check("a live video bitrate update reaches the encoder",
      vp8_encoder.target_bitrate == 900000)
media.set_media_defaults(audio_kbps=96, video_kbps=500)

# 4. frames are only ever downscaled ---------------------------------------
big = QtGui.QImage(1920, 1080, QtGui.QImage.Format.Format_RGB32)
big.fill(QtGui.QColor("#123456"))
frame = media._qimage_to_frame(big, 1280, 720)
check("a large capture fits the box",
      frame is not None and frame.width == 1280 and frame.height == 720)
small = QtGui.QImage(400, 300, QtGui.QImage.Format.Format_RGB32)
small.fill(QtGui.QColor("#654321"))
frame = media._qimage_to_frame(small, 1280, 720)
check("a small capture is sent unchanged",
      frame is not None and frame.width == 400 and frame.height == 300)
odd = QtGui.QImage(401, 301, QtGui.QImage.Format.Format_RGB32)
odd.fill(QtGui.QColor("#222222"))
frame = media._qimage_to_frame(odd)
check("odd dimensions are trimmed for yuv420p, not upscaled",
      frame is not None and frame.width == 400 and frame.height == 300)

import av  # noqa: E402

camera = av.VideoFrame(1920, 1080, "yuv420p")
limited = media._limit_video_frame(camera, 720)
check("the camera cap downscales to the preset",
      limited.width == 1280 and limited.height == 720)
small_camera = av.VideoFrame(640, 480, "yuv420p")
check("a smaller camera frame is kept",
      media._limit_video_frame(small_camera, 720) is small_camera)

# 5. the Preferences section -------------------------------------------------
cfg = Config.defaults()
dlg = PreferencesDialog(cfg, ChatThemeFactory())
dlg._ensure_all_pages()
check("the section is called Calls",
      dlg._sections.item(2).text() == "Calls")
page = dlg._pages[2]
check("the Calls section has three tabs",
      isinstance(page, QtWidgets.QTabWidget) and page.count() == 3
      and [page.tabText(i) for i in range(3)]
      == ["Devices", "Codecs", "Screen"])
for key in ("calls_audio_codec", "calls_video_codec",
            "calls_audio_bitrate_kbps", "calls_video_bitrate_kbps",
            "calls_video_max_height", "devices_screen_resolution",
            "devices_screen_share_fps"):
    check(f"prefs control {key}", key in dlg._controls)
check("the codec controls load the defaults",
      dlg._controls["calls_audio_codec"].currentData() == "auto"
      and dlg._controls["calls_video_codec"].currentData() == "auto"
      and dlg._controls["calls_audio_bitrate_kbps"].value() == 96
      and dlg._controls["calls_video_bitrate_kbps"].value() == 500)
check("the resolution presets are offered",
      dlg._controls["calls_video_max_height"].findData(720) >= 0
      and dlg._controls["devices_screen_resolution"].findData(
          "1280x720") >= 0)
dlg._controls["calls_audio_codec"].setCurrentIndex(
    dlg._controls["calls_audio_codec"].findData("opus"))
dlg._controls["calls_video_codec"].setCurrentIndex(
    dlg._controls["calls_video_codec"].findData("h264"))
dlg._controls["calls_audio_bitrate_kbps"].setValue(64)
dlg._controls["calls_video_bitrate_kbps"].setValue(800)
dlg._controls["calls_video_max_height"].setCurrentIndex(
    dlg._controls["calls_video_max_height"].findData(720))
dlg._controls["devices_screen_resolution"].setCurrentIndex(
    dlg._controls["devices_screen_resolution"].findData("1280x720"))
dlg._controls["devices_screen_share_fps"].setCurrentIndex(
    dlg._controls["devices_screen_share_fps"].findData(10))
dlg._apply_settings()
check("apply writes the codec settings",
      cfg.calls.audio_codec == "opus" and cfg.calls.video_codec == "h264"
      and cfg.calls.audio_bitrate_kbps == 64
      and cfg.calls.video_bitrate_kbps == 800
      and cfg.calls.video_max_height == 720)
check("apply writes the screen box",
      cfg.devices.screen_share_max_width == 1280
      and cfg.devices.screen_share_max_height == 720
      and cfg.devices.screen_share_fps == 10)

# A legacy custom value stays selectable instead of being reset.
cfg2 = Config.defaults()
cfg2.devices.screen_share_max_width = 1600
cfg2.devices.screen_share_max_height = 0
cfg2.calls.video_max_height = 900
dlg2 = PreferencesDialog(cfg2, ChatThemeFactory())
dlg2._ensure_all_pages()
check("a custom screen box is shown",
      dlg2._controls["devices_screen_resolution"].currentData() == "1600x900")
check("a custom camera height is shown",
      dlg2._controls["calls_video_max_height"].currentData() == 900)
dlg2.close()
dlg.close()

# 5b. camera source mode (the driver's resolution/frame-rate list) ---------
check("a camera mode parses into v4l2 options",
      media._v4l2_open_options("1280x720@30:mjpeg")
      == {"video_size": "1280x720", "framerate": "30",
          "input_format": "mjpeg"})
check("an explicit resolution without a format parses too",
      media._v4l2_open_options("640x480@15")
      == {"video_size": "640x480", "framerate": "15"})
check("auto has no v4l2 options", media._v4l2_open_options("") == {})
modes = media.camera_formats("")
check("the camera format probe never raises", isinstance(modes, list))
if not media.HAS_QTMM:
    check("no camera modes without Qt Multimedia", modes == [])

cfg3 = Config.defaults()
check("the camera mode defaults to auto", cfg3.devices.camera_mode == "")
cfg3.devices.camera_mode = "1280x720@30:mjpeg"
dlg3 = PreferencesDialog(cfg3, ChatThemeFactory())
dlg3._ensure_all_pages()
check("the camera mode control is present",
      "devices_camera_mode" in dlg3._controls)
check("a stored custom camera mode stays selected",
      dlg3._controls["devices_camera_mode"].currentData()
      == "1280x720@30:mjpeg")
dlg3._apply_settings()
check("apply keeps the camera mode",
      cfg3.devices.camera_mode == "1280x720@30:mjpeg")
dlg3.close()

# 6. live video quality (bitrate + resolution, no renegotiation) -----------
from stanza_im.xmpp.jingle_rtp import JingleRtpManager  # noqa: E402


class _QualityCall:
    def __init__(self):
        self.bitrate = None
        self.height = None

    def set_video_bitrate(self, kbps):
        self.bitrate = kbps

    def set_video_quality(self, height):
        self.height = height


class _QualitySession:
    def __init__(self, sid, muji_room=""):
        self.sid = sid
        self.muji_room = muji_room
        self.call = _QualityCall()


sid_session = _QualitySession("sid-1")
room_sessions = [_QualitySession("sid-2", "room@conf.example"),
                 _QualitySession("sid-3", "room@conf.example")]
mgr = JingleRtpManager.__new__(JingleRtpManager)
mgr.sessions = {s.sid: s for s in [sid_session] + room_sessions}
mgr.set_call_video_quality("sid-1", 200, 720)
check("a single call gets the live bitrate and resolution",
      sid_session.call.bitrate == 200 and sid_session.call.height == 720)
mgr.set_call_video_quality("room@conf.example", 1000, 480)
check("a Muji room applies the quality to all its sessions",
      all(s.call.bitrate == 1000 and s.call.height == 480
          for s in room_sessions))

from stanza_im.xmpp.media import AiortcCall  # noqa: E402


class _FakeTrack:
    def __init__(self):
        self.height = None
        self.box = None

    def set_max_height(self, height):
        self.height = height

    def set_screen_box(self, width, height):
        self.box = (width, height)


call = AiortcCall.__new__(AiortcCall)
call._local_video = _FakeTrack()
call.set_video_quality(720)
check("the live resolution caps the camera and the screen",
      call._local_video.height == 720 and call._local_video.box == (0, 720))

# The call windows expose the quality menu and emit the choice.
from PyQt6 import QtCore  # noqa: E402
from stanza_im.ui.call_window import CallWindow, MujiCallWindow  # noqa: E402

window = CallWindow("sid-9", "Peer", video=True, video_bitrate=500,
                    max_height=720)
emitted = []
window.quality_requested.connect(lambda *a: emitted.append(a))
window._on_quality(200, 480)
check("the 1:1 call quality menu emits the live choice",
      emitted == [("sid-9", 200, 480)]
      and window._quality_bitrate_actions[200].isChecked()
      and window._quality_height_actions[480].isChecked())
window.close()

muji = MujiCallWindow("room@conf.example", self_nick="me",
                      video_bitrate=500, max_height=0)
muji_emitted = []
muji.quality_requested.connect(lambda *a: muji_emitted.append(a))
muji._on_quality(1000, 720)
check("the Muji quality menu emits for the room",
      muji_emitted == [("room@conf.example", 1000, 720)])
muji.close()

check("the main window wires both quality menus",
      all("quality_requested.connect" in inspect.getsource(
          getattr(MainWindow, name))
          for name in ("_open_call_window", "_on_muji_joined")))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All call-settings tests passed.")
