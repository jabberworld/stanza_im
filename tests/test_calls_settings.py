"""Call codec/bitrate/resolution settings and the media helpers.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_calls_settings.py
"""
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

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All call-settings tests passed.")
