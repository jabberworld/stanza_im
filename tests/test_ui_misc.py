"""Offscreen tests for the misc UI changes.

Covers: logout back to the login page, the tooltip avatar size setting,
the Ctrl+wheel font zoom of the input/roster/participant font, and the
account-bound unread state used by the tray.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_ui_misc.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_misc_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import font_zoom
from stanza_im.ui import icons as icons_mod
from stanza_im.ui import tooltip as tooltip_mod
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget, _ParticipantList
from stanza_im.ui.main_window import MainWindow, _PAGE_LOGIN
from stanza_im.ui.roster_widget import RosterWidget

i18n_load("en")
icons_mod.init_icons()
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _wheel(delta: int, ctrl: bool = True) -> QtGui.QWheelEvent:
    mod = (QtCore.Qt.KeyboardModifier.ControlModifier if ctrl
           else QtCore.Qt.KeyboardModifier.NoModifier)
    return QtGui.QWheelEvent(
        QtCore.QPointF(5, 5), QtCore.QPointF(5, 5),
        QtCore.QPoint(0, 0), QtCore.QPoint(0, delta),
        QtCore.Qt.MouseButton.NoButton, mod,
        QtCore.Qt.ScrollPhase.NoScrollPhase, False)


# 1. font-zoom helper ---------------------------------------------------------
check("a plain wheel is ignored",
      font_zoom.wheel_font_size(QtGui.QFont(), _wheel(120, ctrl=False)) is None)
check("an empty delta is ignored",
      font_zoom.wheel_font_size(QtGui.QFont(), _wheel(0)) is None)
font = QtGui.QFont()
font.setPointSize(12)
check("Ctrl+wheel up increases the size",
      font_zoom.wheel_font_size(font, _wheel(120)) == 13)
check("Ctrl+wheel down decreases the size",
      font_zoom.wheel_font_size(font, _wheel(-120)) == 11)
font.setPointSize(font_zoom.FONT_MAX)
check("the size is clamped to the maximum",
      font_zoom.wheel_font_size(font, _wheel(120)) == font_zoom.FONT_MAX)
font.setPointSize(font_zoom.FONT_MIN)
check("the size is clamped to the minimum",
      font_zoom.wheel_font_size(font, _wheel(-120)) == font_zoom.FONT_MIN)


# 2. emitter widgets ----------------------------------------------------------
cw = ChatWidget("room@conf.example", "Room", ChatThemeFactory(), is_muc=True)
shown = []
cw.input_font_zoom_requested.connect(lambda s: shown.append(("input", s)))
cw.participant_font_zoom_requested.connect(
    lambda s: shown.append(("part", s)))
cw._input.setFont(QtGui.QFont("", 11))
cw._input.wheelEvent(_wheel(120))
check("Ctrl+wheel on the input emits the new size",
      ("input", 12) in shown)
cw._users_list.setFont(QtGui.QFont("", 11))
cw._users_list.wheelEvent(_wheel(120))
check("Ctrl+wheel on the participant list emits the new size",
      ("part", 12) in shown)
cw._input.wheelEvent(_wheel(120, ctrl=False))
check("a plain wheel does not change the input font",
      shown.count(("input", 12)) == 1)

# Ctrl+wheel over a participant *row* (a setItemWidget child) must work too.
cw.update_muc_users(
    [{"nick": "bob", "show": "online", "role": "participant"}], self_nick="")
from stanza_im.ui.chat_widget import _ParticipantRow, _FadeLabel  # noqa: E402
row = cw._users_list.findChildren(_ParticipantRow)[0]
row_label = row.findChild(_FadeLabel)
cw.set_participant_font("", 20)
cw._users_list.setFont(QtGui.QFont("", 20))
before = shown.count(("part", 21))
cw._participant_wheel_font_zoom(_wheel(120))
check("Ctrl+wheel over a participant row emits the new size",
      shown.count(("part", 21)) > before)
check("the row watches its child labels for wheel events",
      row_label is not None)  # the filter is installed in _add_muc_user_row

roster = RosterWidget()
roster_shown = []
roster.roster_font_zoom_requested.connect(roster_shown.append)
roster.setFont(QtGui.QFont("", 11))
roster.wheelEvent(_wheel(120))
check("Ctrl+wheel on the roster emits the new size", roster_shown == [12])
cw.detach()

# New tabs inherit the remembered input font (Ctrl+wheel persistence).
from stanza_im.ui.chat_window import ChatWindow  # noqa: E402
cw_win = ChatWindow(ChatThemeFactory(), ChatThemeFactory())
cw_win.set_input_font("", 19)
tab = cw_win.open_chat("bob@example.com", "Bob")
check("a new 1:1 tab inherits the input font",
      tab._input.font().pointSize() == 19)
cw_win.set_participant_font("", 17)
muc = cw_win.open_groupchat("room@conf.example", "me", "Room")
check("a new MUC tab inherits the input font",
      muc._input.font().pointSize() == 19)
cw_win.close_all()

# _FadeLabel draws the text with its own font (a painter on a bare pixmap
# otherwise uses the application default, so the nick never resized).
from stanza_im.ui.chat_widget import _FadeLabel  # noqa: E402
_fl = _FadeLabel("Xg")
_f = QtGui.QFont(); _f.setPointSize(24); _fl.setFont(_f)
_pm = QtGui.QPixmap(120, 60); _pm.fill(QtCore.Qt.GlobalColor.transparent)
_p = QtGui.QPainter(_pm)
_p.setFont(_fl.font())
_p.drawText(QtCore.QRect(0, 0, 120, 60),
            QtCore.Qt.AlignmentFlag.AlignVCenter
            | QtCore.Qt.AlignmentFlag.AlignLeft, "Xg")
_p.end()
_img = _pm.toImage()
_rows = [y for y in range(60)
         if any(_img.pixelColor(x, y).alpha() > 0 for x in range(120))]
check("the fade label font is large enough to matter",
      _fl.font().pointSize() == 24 and (_rows and max(_rows) - min(_rows) > 6))


# 3. tooltip avatar size ------------------------------------------------------
tooltip_mod.set_avatar_size(96)
check("the tooltip avatar size is applied",
      tooltip_mod._AVATAR_SIZE[0] == 96)
tooltip_mod.set_avatar_size(0)
check("a zero size falls back to the default 64",
      tooltip_mod._AVATAR_SIZE[0] == 64)
check("the config default tooltip avatar size is 64",
      Config().appearance.tooltip_avatar_size == 64)

# The spin range reaches 256 (Preferences → Appearance → «Разное»).
from stanza_im.ui.preferences import PreferencesDialog  # noqa: E402
_pdlg = PreferencesDialog(Config(), ChatThemeFactory())
check("the tooltip avatar spin allows up to 256",
      _pdlg._controls["tooltip_avatar_size"].maximum() == 256)
_pdlg.deleteLater()


# 3b. saved fonts are applied at startup --------------------------------------
_start_cfg = Config()
_start_cfg.appearance.input_font_size = 21
_start_cfg.appearance.participant_font_size = 23
_start_cfg.save()
_swin = MainWindow(app)
_swin._idle_timer.stop()
_swin._suspend_timer.stop()
_swin._memory_timer.stop()
_start_tab = _swin._chat_window.open_chat("x@example.com", "X")
check("the saved input font is applied at startup (new tab)",
      _start_tab._input.font().pointSize() == 21)
check("the saved participant font is applied at startup",
      _swin._chat_window._participant_font == ("", 23))
# A zoom handler pushes the change to ChatWindow (all tabs + new ones).
_swin._on_input_font_zoom(27)
check("input zoom updates ChatWindow for new tabs",
      _swin._chat_window._input_font == ("", 27))
check("input zoom updates the open tab",
      _start_tab._input.font().pointSize() == 27)
_swin._on_participant_font_zoom(29)
check("participant zoom updates ChatWindow",
      _swin._chat_window._participant_font == ("", 29))
# Restore the default state for the logout checks below.
_start_cfg.appearance.input_font_size = 0
_start_cfg.appearance.participant_font_size = 0
_start_cfg.save()
_swin._chat_window.close_all()


# 4. logout returns to the login page -----------------------------------------
win = MainWindow(app)
win._idle_timer.stop()
win._suspend_timer.stop()
win._memory_timer.stop()
win._client = None
win._unread_counts = {"bob@example.com": 3}
win._unread_total = 3
win._unread_jids = {"bob@example.com"}
win._tray.start_blinking()
win._stack.setCurrentIndex(2)  # roster page


class _FakeClient:
    def __init__(self):
        self.disconnected = False

    def flush_roster_cache(self):
        pass

    async def disconnect(self):
        self.disconnected = True


fake = _FakeClient()
win._client = fake
scheduled = []
_orig_start = win._start_task


def _capture(coro):
    scheduled.append(coro)
    coro.close()


win._start_task = _capture
win._logout()
win._start_task = _orig_start
check("logout returns to the login page",
      win._stack.currentIndex() == _PAGE_LOGIN)
check("logout drops the client reference", win._client is None)
check("logout schedules a disconnect", len(scheduled) == 1)
check("logout clears the live unread total", win._unread_total == 0)
check("logout stops the tray blink", not win._tray._blink_active)
check("logout keeps the unread counters on disk",
      __import__("stanza_im.core.unread_state",
                 fromlist=["load"]).load() == {"bob@example.com": 3})
win._chat_window.close()

# Logout refills the saved password on the login form.
win._config.jid = "bob@example.com"
win._config.password = "s3cret"
win._config.save_password = True
win._client = _FakeClient()
win._start_task = _capture
win._logout()
win._start_task = _orig_start
check("logout refills the saved password",
      win._login._pw_edit.text() == "s3cret")
win._config.save_password = False
win._config.password = ""
win._chat_window.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All misc UI tests passed.")
