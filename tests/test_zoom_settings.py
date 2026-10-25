"""Service-browser / preferences-navigation zoom settings.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_zoom_settings.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_zoom_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.core.storage import Config  # noqa: E402
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.preferences import PreferencesDialog  # noqa: E402

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


cfg = Config()
check("the zoom settings default to the system font",
      getattr(cfg.appearance, "prefs_nav_font_size", -1) == 0
      and getattr(cfg.appearance, "service_browser_font_size", -1) == 0)

dlg = PreferencesDialog(cfg, ChatThemeFactory())
app.processEvents()
check("the section navigator starts at the default 24 px icons",
      dlg._sections.iconSize().width() == 24)
dlg._on_nav_zoom(18)
app.processEvents()
check("Ctrl+wheel changes the section font",
      dlg._sections.font().pointSize() == 18)
check("Ctrl+wheel scales the section icons",
      dlg._sections.iconSize().width() == 48)
check("Ctrl+wheel persists the section size immediately",
      cfg.appearance.prefs_nav_font_size == 18)
check("the navigator width grows with the zoom",
      dlg._sections.width() >= 190)
dlg._ensure_all_pages()
check("the font setting row exists",
      "prefs_nav_font_size" in dlg._controls.keys()
      and "service_browser_font_size" in dlg._controls.keys())
cfg.appearance.prefs_nav_font_size = 0
dlg._apply_nav_font()
check("a zero size falls back to the system navigator font",
      dlg._sections.iconSize().width() == 24)
dlg._controls["prefs_nav_font_size"].setValue(20)
dlg._controls["service_browser_font_size"].setValue(18)
dlg._apply_settings()
check("Apply stores both zoom settings",
      cfg.appearance.prefs_nav_font_size == 20
      and cfg.appearance.service_browser_font_size == 18)
dlg.close()

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All zoom-settings tests passed.")
