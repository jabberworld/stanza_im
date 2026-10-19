"""Offscreen tests for screen sharing (camera <-> screen, region picker).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_screen_share.py
"""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_ss_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402

from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.xmpp import media  # noqa: E402
from stanza_im.ui.call_window import CallWindow, MujiCallWindow  # noqa: E402
from stanza_im.ui.screen_region_dialog import ScreenRegionDialog  # noqa: E402

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _image(w=200, h=100):
    img = QtGui.QImage(w, h, QtGui.QImage.Format.Format_RGB888)
    img.fill(QtGui.QColor(0, 128, 255))
    return img


# 1. QImage -> av.VideoFrame -------------------------------------------------
_frame = media._qimage_to_frame(_image(), 0)
check("a QImage becomes a yuv420p frame",
      _frame is not None and _frame.width == 200 and _frame.height == 100
      and _frame.format.name == "yuv420p")
_scaled = media._qimage_to_frame(_image(), 100)
check("max_width scales the frame down",
      _scaled is not None and _scaled.width == 100 and _scaled.height == 50)
check("an invalid image yields no frame",
      media._qimage_to_frame(None, 0) is None)


# 2. the capture track switches camera <-> screen ----------------------------
media._grab_screen_image = lambda region=None: _image()
_track = media._VideoCaptureTrack("", screen_fps=5, screen_max_width=0)
_track.set_source("screen", (0, 0, 200, 100))
_shot = asyncio.new_event_loop().run_until_complete(_track.recv())
check("the screen source yields the grabbed frame",
      _shot.width == 200 and _shot.height == 100)
check("the track reports the screen source", _track._source == "screen")
_track.set_source("camera")
check("switching back selects the camera", _track._source == "camera")
# throttle: the second recv within 1/fps reuses the same grab
_grabs = []


def _counting_grab(region=None):
    _grabs.append(1)
    return _image()


media._grab_screen_image = _counting_grab
_track.set_source("screen", (0, 0, 200, 100))
asyncio.new_event_loop().run_until_complete(_track.recv())
asyncio.new_event_loop().run_until_complete(_track.recv())
check("the screen grab is throttled to screen_fps", len(_grabs) == 1)
_track.stop()


# 3. JingleRtpManager.set_screen_share reaches the call ----------------------
from stanza_im.xmpp.jingle_rtp import JingleRtpManager  # noqa: E402


class _Call:
    def __init__(self):
        self.calls = []

    def set_video_source(self, mode, region=None):
        self.calls.append((mode, region))


class _Session:
    def __init__(self, sid, muji_room=""):
        self.sid = sid
        self.muji_room = muji_room
        self.call = _Call()


class _Client:
    def __init__(self):
        self.events = []

    def emit(self, name, *args):
        self.events.append((name, args))


_mgr = JingleRtpManager.__new__(JingleRtpManager)
_mgr.client = _Client()
_s1 = _Session("sid1")
_s2 = _Session("sid2", muji_room="room@conf")
_mgr.sessions = {"sid1": _s1, "sid2": _s2}
_mgr.set_screen_share("sid1", "screen", (0, 0, 100, 50))
check("a 1:1 screen share reaches its call",
      _s1.call.calls == [("screen", (0, 0, 100, 50))])
check("the other session is untouched", _s2.call.calls == [])
_mgr.set_screen_share("room@conf", "screen", None)
check("a Muji screen share reaches every room session",
      _s2.call.calls == [("screen", None)])
_mgr.set_screen_share("sid1", "camera")
check("stopping switches back to the camera",
      _s1.call.calls[-1] == ("camera", None))
check("a share emits call_screen_share",
      _mgr.client.events and _mgr.client.events[-1][0] == "call_screen_share")


# 4. the region dialog -------------------------------------------------------
_dlg = ScreenRegionDialog()
check("the overlay spans the screen", not _dlg.geometry().isNull())
check("the overlay is opaque (no compositor needed)",
      not _dlg.testAttribute(
          QtCore.Qt.WidgetAttribute.WA_TranslucentBackground))
check("no region before a drag", _dlg.region() is None)
_origin = _dlg.geometry().topLeft()
_dlg._origin = QtCore.QPoint(20, 30)
_dlg._rect = QtCore.QRect(20, 30, 120, 80)
_region = _dlg.region()
check("a dragged rectangle becomes a region",
      _region is not None and _region[2] >= 8 and _region[3] >= 8)
check("the region starts at the global position",
      _region[0] == _origin.x() + 20 and _region[1] == _origin.y() + 30)


# 5. the call windows emit video_mode_requested -----------------------------
_cw = CallWindow("sid1", "Bob", video=True)
_seen = []
_cw.video_mode_requested.connect(lambda sid, mode: _seen.append((sid, mode)))
_cw._request_mode("region")
check("a 1:1 call emits its sid + mode", _seen == [("sid1", "region")])
_cw.set_video_mode("screen")
check("the combo reflects the screen mode",
      _cw._video_mode == "screen"
      and _cw._video_actions["screen"].isChecked()
      and not _cw._video_actions["camera"].isChecked())
_cw.set_video_mode("off")
check("the combo reflects the off mode", _cw._video_mode == "off")
check("the combo offers all four modes",
      set(_cw._video_actions) == {"off", "camera", "region", "screen"})
_mw = MujiCallWindow("room@conf", self_nick="me")
_seen2 = []
_mw.video_mode_requested.connect(lambda room, mode: _seen2.append((room, mode)))
_mw._on_video_mode("screen")
check("a Muji window emits its room + mode",
      _seen2 == [("room@conf", "screen")])
_mw._on_video_mode("off")
check("a Muji 'off' disables the global camera", _mw._all_cam is False)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All screen-share tests passed.")
