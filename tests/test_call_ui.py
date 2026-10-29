"""Offscreen tests for the call UI (incoming dialog, roster naming).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_call_ui.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_callui_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtGui, QtWidgets  # noqa: E402

from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.ui.call_window import (  # noqa: E402
    CallWindow, IncomingCallDialog, MujiCallWindow)
from stanza_im.ui.main_window import MainWindow  # noqa: E402

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. the incoming dialog: accept on the right, reject on the left ------------
dlg = IncomingCallDialog("Bob", "audio")
row = None
for _i in range(dlg.layout().count()):
    _item = dlg.layout().itemAt(_i)
    if _item.layout() is not None and _item.layout().indexOf(dlg._reject) >= 0:
        row = _item.layout()
        break
check("the incoming dialog has a button row", row is not None)
check("the reject button is at the left edge",
      row.itemAt(0).widget() is dlg._reject)
check("a stretch separates the buttons",
      row.itemAt(1).spacerItem() is not None)
check("the accept button is at the right edge",
      row.itemAt(2).widget() is dlg._accept)
dlg.close()

# 2. a call peer resolves to its roster name (bare JID when unknown) ---------
class _User:
    def __init__(self, jid, name):
        self.jid = jid
        self.name = name


class _Roster:
    _users = [_User("bob@example.com", "Bob")]


mw = MainWindow.__new__(MainWindow)
mw._roster = _Roster()
check("a call peer resolves to its roster name",
      mw._call_display_name("bob@example.com/desk") == "Bob")
check("an unnamed roster contact falls back to its JID",
      mw._call_display_name("bob@example.com") == "Bob")
check("an unknown call peer falls back to the bare JID",
      mw._call_display_name("x@y/res") == "x@y")

# 3. the active call window has a mute-the-peer (speaker) button -------------
cw = CallWindow("s1", "Bob", video=False)
check("the call window has a mute-peer button", hasattr(cw, "_hear_btn"))
heard = []
cw.receive_toggled.connect(lambda sid, enabled: heard.append((sid, enabled)))
cw._hear_btn.setChecked(True)
check("muting the peer emits receive_toggled(False)",
      heard == [("s1", False)])
cw._hear_btn.setChecked(False)
check("unmuting the peer emits receive_toggled(True)",
      heard[-1] == ("s1", True))
cw.close()

# A call window opened for an already muted session must show that state
# without emitting a toggle signal while it is being constructed.
mcw = CallWindow("s1m", "Bob", video=False, audio_enabled=False,
                 remote_audio_enabled=False)
_initial_toggles = []
mcw.audio_toggled.connect(lambda *a: _initial_toggles.append(a))
mcw.receive_toggled.connect(lambda *a: _initial_toggles.append(a))
check("a pre-muted call opens with the microphone button checked",
      mcw._mute_btn.isChecked() and mcw._muted)
check("a pre-deafened call opens with the speaker button checked",
      mcw._hear_btn.isChecked() and mcw._hear_muted)
check("opening with stored mute states emits no toggle signal",
      _initial_toggles == [])
mcw.set_muted(False)
mcw.set_hear_muted(False)
check("stored states can be updated without emitting",
      not mcw._mute_btn.isChecked() and not mcw._hear_btn.isChecked()
      and _initial_toggles == [])
mcw.close()

# PiP is on by default for video calls and mirrors the camera preview.
pcw = CallWindow("s1p", "Bob", video=True, pip_enabled=True)
_pip_seen = []
pcw.pip_toggled.connect(lambda *a: _pip_seen.append(a))
check("the video call opens with PiP enabled",
      pcw._pip_btn.isChecked() and pcw._pip_view.isVisibleTo(pcw))
_pip_image = QtGui.QImage(8, 8, QtGui.QImage.Format.Format_RGB888)
pcw.set_local_frame(_pip_image)
check("the PiP view receives the local frame",
      pcw._pip_view._image is _pip_image)
pcw._pip_btn.setChecked(False)
check("turning PiP off emits its state", _pip_seen[-1] == ("s1p", False))
check("the PiP view hides when disabled", not pcw._pip_view.isVisibleTo(pcw))
pcw.close()

# The network icon menu exposes the incoming REMB cap.
icw = CallWindow("s1c", "Bob", video=True, incoming_max=500)
_inc_seen = []
icw.incoming_requested.connect(lambda *a: _inc_seen.append(a))
check("the call opens with the configured incoming cap",
      icw._incoming_actions[500].isChecked())
icw._incoming_actions[200].trigger()
check("the incoming menu emits the chosen cap",
      _inc_seen[-1] == ("s1c", 200)
      and icw._incoming_actions[200].isChecked())
icw.close()


# The incoming prompt can show a small self-view before Accept.
iv = IncomingCallDialog("Bob", "video", sid="call-s", show_self=True)
check("the incoming video prompt has a self-view",
      iv._self_view is not None)
_pip_image2 = QtGui.QImage(8, 8, QtGui.QImage.Format.Format_RGB888)
iv.set_local_frame(_pip_image2)
check("the incoming prompt receives the local preview frame",
      iv._self_view._image is _pip_image2)
iv.close()


def _has_quality_menu(cw):
    return (hasattr(cw, "_quality_bitrate_actions")
            and hasattr(cw, "_quality_height_actions")
            and 200 in cw._quality_bitrate_actions)


qcw = CallWindow("s1q", "Bob", video=True)
check("outgoing quality actions live in the network menu",
      _has_quality_menu(qcw) and not hasattr(qcw, "_quality_btn"))
qcw.close()


def _pip_geometry(cw):
    cw.resize(700, 500)
    cw.show()
    app.processEvents()
    cw._video_view.resize(320, 240)
    cw._position_pip()
    return cw._pip_view.geometry(), cw._video_view.content_rect()


_pip_rect, _content_rect = _pip_geometry(pcw if not pcw.isHidden() else
                                         CallWindow("s1geo", "Bob",
                                                    video=True))
check("PiP stays inside the displayed video rectangle",
      _pip_rect.width() >= 64 and _pip_rect.height() >= 36
      and _content_rect.contains(_pip_rect))

# A failed call keeps its window and offers a redial in the same media mode.
rcw = CallWindow("s1r", "Bob", video=True, peer_jid="bob@example.com")
_redial_seen = []
rcw.redial_requested.connect(lambda *a: _redial_seen.append(a))
rcw.show_failed("connection failed")
check("a failed call shows the redial button",
      rcw._redial_btn.isVisibleTo(rcw) and rcw._failed)
check("a failed call hides the media controls",
      not rcw._mute_btn.isVisible() and not rcw._network_btn.isVisible()
      and not rcw._pip_view.isVisibleTo(rcw))
rcw._redial_btn.click()
check("redial carries the sid, peer JID and video mode",
      _redial_seen[-1] == ("s1r", "bob@example.com", True))
rcw.close()

# 1:1 call controls are flat and the strip keeps its own width.
fcw = CallWindow("s1f", "Bob", video=True)
_flat_btns = (fcw._mute_btn, fcw._hear_btn, fcw._video_btn, fcw._pip_btn,
              fcw._network_btn, fcw._info_btn, fcw._hangup_btn)
check("all 1:1 call controls are flat",
      all(b.autoRaise() for b in _flat_btns))
check("the 1:1 control strip has its own minimum width",
      fcw._controls_widget.minimumWidth()
      >= fcw._controls_widget.sizeHint().width())
fcw.resize(fcw.minimumSize())
fcw.layout().activate()
check("the 1:1 control strip stays compact and centred",
      fcw._controls_widget.width()
      <= fcw._controls_widget.sizeHint().width() + 1)
check("the 1:1 controls stay below the video at minimum size",
      fcw._controls_widget.geometry().top()
      >= fcw._video_view.geometry().bottom())
fcw.close()

# Muji controls (global and per-participant) follow the same flat style.
mwnd = MujiCallWindow("room@example.com")
check("Muji global controls are flat",
      mwnd._leave_btn.autoRaise() and mwnd._all_mic_btn.isFlat()
      and mwnd._all_recv_btn.isFlat() and mwnd._video_btn.autoRaise())
mwnd.close()


# 4. the call dialogs show an avatar (or the placeholder) --------------------
def _has_avatar_label(widget):
    return any(not lbl.pixmap().isNull()
               for lbl in widget.findChildren(QtWidgets.QLabel))


ad = IncomingCallDialog("Bob", "audio")
check("the incoming dialog shows an avatar", _has_avatar_label(ad))
ad.close()
acw = CallWindow("s2", "Bob", video=False)
check("the audio call window shows an avatar", _has_avatar_label(acw))
acw.close()
vcw = CallWindow("s3", "Bob", video=True)
check("a video call window has no avatar", not _has_avatar_label(vcw))
vcw.close()

# 5. the call duration (MM:SS, HH:MM:SS past an hour) ------------------------
from stanza_im.include.utils import format_duration  # noqa: E402

check("a short duration is MM:SS", format_duration(65) == "01:05")
check("a long duration is HH:MM:SS", format_duration(3725) == "1:02:05")
check("a negative duration is clamped", format_duration(-5) == "00:00")

dcw = CallWindow("s4", "Bob", video=False)
dcw.start_duration()
check("starting the duration shows the counter",
      not dcw._duration_label.isHidden()
      and dcw._duration_label.text() == "00:00")
dcw.stop_duration()
check("stopping the duration halts the timer",
      not dcw._duration_timer.isActive())
dcw.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All call-UI tests passed.")
