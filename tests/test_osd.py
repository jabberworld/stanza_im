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

from PyQt6 import QtWidgets

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

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)