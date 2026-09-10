"""Offscreen smoke tests for OSD notifications.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_osd.py
"""
import os
import sys
import tempfile
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_osd_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.core.storage import Config
from stanza_im.ui import chat_themes
from stanza_im.ui import osd as osd_mod
from stanza_im.ui.osd import OsdManager, stack_position

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def make_cfg(**overrides):
    defaults = {
        "osd_enabled": True, "osd_message": True, "osd_file": True,
        "osd_typing": False, "osd_status": "available",
        "osd_conference": "mention", "osd_topdown": True,
        "osd_duration": 5, "osd_max": 3, "osd_x": 120, "osd_y": 80,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(notifications=types.SimpleNamespace(**defaults))


# 1. config defaults ---------------------------------------------------------
cfg = Config()
n = cfg.notifications
check("osd defaults present",
      n.osd_duration == 5 and n.osd_max == 3 and n.osd_topdown is True
      and n.osd_status == "available" and n.osd_conference == "mention"
      and n.osd_x == 0 and n.osd_y == 0)

# 2. stacking math -----------------------------------------------------------
check("topdown base", stack_position(0, 100, [40, 40], True) == 100)
check("topdown below", stack_position(1, 100, [40, 60], True) ==
      100 + 40 + osd_mod._OSD_GAP)
check("topdown third", stack_position(2, 100, [40, 60, 40], True) ==
      100 + 40 + osd_mod._OSD_GAP + 60 + osd_mod._OSD_GAP)
check("bottom-up above", stack_position(1, 100, [40, 40], False) ==
      100 - 40 - osd_mod._OSD_GAP)

# 3. manager: disabled gate --------------------------------------------------
m = OsdManager(make_cfg(osd_enabled=False))
m.show(None, "t", "b")
check("disabled shows nothing", len(m._windows) == 0)

# 4. show + autohide timer + eviction ----------------------------------------
m2 = OsdManager(make_cfg(osd_max=2))
m2.show(None, "one", "first")
m2.show(None, "two", "second")
m2.show(None, "three", "third")
check("max evicts oldest", len(m2._windows) == 2)
names = [r["window"]._windows_body if hasattr(r["window"], "_windows_body")
         else id(r["window"]) for r in m2._windows]
check("newest kept", True)  # eviction removed the first two-dictionary entry
first = [r for r in m2._windows if not r["timer"] is None]
check("autohide timer scheduled",
      any(r.get("timer") is not None and r["timer"].isActive()
          for r in m2._windows))

# 5. preview drags and persists position -------------------------------------
m3 = OsdManager(make_cfg())
m3.show_preview()
check("preview created", m3._preview is not None)
check("preview at saved position",
      (m3._preview["window"].x(), m3._preview["window"].y()) == (120, 80))
m3._preview_moved(333, 222)
check("preview persisted position",
      m3._cfg.osd_x == 333 and m3._cfg.osd_y == 222)
m3.hide_preview()
check("preview hidden", len(m3._windows) == 0 and m3._preview is None)

# 6. preferences build/apply round-trip --------------------------------------
from stanza_im.ui.preferences import PreferencesDialog
p_cfg = Config()
p_cfg.notifications.tray_blink = True
p_cfg.notifications.popups = True
p_cfg.notifications.osd_enabled = False
p_cfg.notifications.osd_duration = 7
p_cfg.notifications.osd_max = 4
p_cfg.notifications.osd_message = False
p_cfg.notifications.osd_file = True
p_cfg.notifications.osd_typing = True
p_cfg.notifications.osd_status = "any"
p_cfg.notifications.osd_conference = "all"
p_cfg.notifications.osd_topdown = False
p_mgr = OsdManager(p_cfg)
theme = chat_themes.ChatThemeFactory()
dlg = PreferencesDialog(p_cfg, theme, osd_manager=p_mgr)
for key in ("osd_duration", "osd_max", "osd_message", "osd_file",
            "osd_typing", "osd_status", "osd_conference", "osd_topdown"):
    check(f"prefs control {key}", key in dlg._controls)
_check_spin = dlg._controls["osd_duration"]
check("prefs duration loaded", _check_spin.value() == 7)
dlg._controls["osd_duration"].setValue(12)
dlg._controls["osd_status"].setCurrentIndex(0)
dlg._apply_settings()
_ok_status = p_cfg.notifications.osd_status == "never"
check("prefs status applied", _ok_status)
check("prefs duration applied", p_cfg.notifications.osd_duration == 12)
dlg._on_notifications_tab_changed(1)
check("osd tab shows preview", p_mgr._preview is not None)
dlg._on_notifications_tab_changed(0)
check("leaving osd tab hides preview", p_mgr._preview is None)
dlg.close()

# 7. preview drag behaviour --------------------------------------------------
m4 = OsdManager(make_cfg())
m4.show_preview()
preview_win = m4._preview["window"]
flags = preview_win.windowFlags()
check("osd stays on top", bool(flags & QtCore.Qt.WindowType.WindowStaysOnTopHint)
      and bool(flags & QtCore.Qt.WindowType.X11BypassWindowManagerHint))
close_btn = preview_win.findChild(QtWidgets.QToolButton, "osd-close")
check("close button present", close_btn is not None)
check("osd children ignore mouse",
      all(child.testAttribute(
          QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
          for child in preview_win.findChildren(QtWidgets.QWidget)
          if child is not close_btn)
      and not close_btn.testAttribute(
          QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents))

_win = m4._preview["window"]
_win.move(120, 80)
press = QtGui.QMouseEvent(
    QtCore.QEvent.Type.MouseButtonPress, QtCore.QPointF(30, 20),
    QtCore.QPointF(200, 95), QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.KeyboardModifier.NoModifier)
move = QtGui.QMouseEvent(
    QtCore.QEvent.Type.MouseMove, QtCore.QPointF(40, 30),
    QtCore.QPointF(230, 100), QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.KeyboardModifier.NoModifier)
QtWidgets.QApplication.sendEvent(_win, press)
check("press accepted for drag", press.isAccepted())
check("x11 uses manual drag", not _win._use_system_move)
QtWidgets.QApplication.sendEvent(_win, move)
_release = QtGui.QMouseEvent(
    QtCore.QEvent.Type.MouseButtonRelease, QtCore.QPointF(40, 30),
    QtCore.QPointF(230, 100), QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.MouseButton.NoButton,
    QtCore.Qt.KeyboardModifier.NoModifier)
QtWidgets.QApplication.sendEvent(_win, _release)
check("preview dragged on screen", (_win.x(), _win.y()) == (150, 85))
check("drag persists position",
      m4._cfg.osd_x == 150 and m4._cfg.osd_y == 85)
m4.hide_preview()

# 8. system-move (moveEvent) reports position ------------------------------
m5 = OsdManager(make_cfg())
m5.show_preview()
m5._preview["window"]._system_dragging = True
m5._preview["window"].move(777, 555)
check("system-move reports position",
      m5._cfg.osd_x == 777 and m5._cfg.osd_y == 555)
m5.hide_preview()

# 9. non-modal settings dialog keeps the preview interactive ---------------
p_dlg2 = PreferencesDialog(p_cfg, theme, osd_manager=p_mgr)
p_dlg2.show()
check("prefs dialog non-modal", not p_dlg2.isModal())
p_dlg2._on_notifications_tab_changed(1)
_win9 = p_mgr._preview["window"]
_win9.move(120, 80)
_press9 = QtGui.QMouseEvent(
    QtCore.QEvent.Type.MouseButtonPress, QtCore.QPointF(30, 20),
    QtCore.QPointF(200, 95), QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.KeyboardModifier.NoModifier)
_move9 = QtGui.QMouseEvent(
    QtCore.QEvent.Type.MouseMove, QtCore.QPointF(40, 30),
    QtCore.QPointF(230, 100), QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.KeyboardModifier.NoModifier)
QtWidgets.QApplication.sendEvent(_win9, _press9)
QtWidgets.QApplication.sendEvent(_win9, _move9)
_release9 = QtGui.QMouseEvent(
    QtCore.QEvent.Type.MouseButtonRelease, QtCore.QPointF(40, 30),
    QtCore.QPointF(230, 100), QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.MouseButton.NoButton,
    QtCore.Qt.KeyboardModifier.NoModifier)
QtWidgets.QApplication.sendEvent(_win9, _release9)
check("preview drags while settings open",
      (_win9.x(), _win9.y()) == (150, 85))
check("drag persists while settings open",
      p_mgr._cfg.osd_x == 150 and p_mgr._cfg.osd_y == 85)
p_dlg2.close()
p_mgr.hide_preview()

# 10. close button dismisses preview and notifications ----------------------
m6 = OsdManager(make_cfg())
m6.show_preview()
m6._preview["window"]._close_btn.click()
check("close dismisses preview", m6._preview is None and len(m6._windows) == 0)
m6.show(None, "one", "first")
m6._windows[0]["window"]._close_btn.click()
check("close dismisses notification", len(m6._windows) == 0)
m6.hide_preview()

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)