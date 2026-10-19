"""Tests for the font preferences (alignment, stretch) and Ctrl+wheel zoom.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_font_prefs.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_font_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402

from stanza_im.core.storage import Config  # noqa: E402
from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.main_window import MainWindow  # noqa: E402
from stanza_im.ui.preferences import PreferencesDialog  # noqa: E402

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. the font-size spin reads its text from the start and stretches ----------
dlg = PreferencesDialog(Config(), ChatThemeFactory())
dlg._ensure_all_pages()
spin = dlg._controls["roster_font_size"]
check("the font-size spin aligns its text to the left",
      bool(spin.lineEdit().alignment() & QtCore.Qt.AlignmentFlag.AlignLeft))
check("the font-size spin expands with the dialog",
      spin.sizePolicy().horizontalPolicy()
      == QtWidgets.QSizePolicy.Policy.Expanding)
combo = dlg._controls["roster_font"]
check("the font-family combo expands with the dialog",
      combo.sizePolicy().horizontalPolicy()
      == QtWidgets.QSizePolicy.Policy.Expanding)
check("the tooltip font row exists", "tooltip_font" in dlg._controls)
dlg.close()

# 1b. the tooltip popup follows the tooltip font setting ---------------------
from stanza_im.ui import tooltip as tooltip_mod  # noqa: E402

tooltip_mod.set_font("Monospace", 14)
tw = tooltip_mod._window()
tw.set_content("<b>x</b>", None)
check("the tooltip popup uses the configured font",
      tw._label.font().family() == "Monospace"
      and tw._label.font().pointSize() == 14)
tooltip_mod.set_font("", 0)

# 2. Ctrl+wheel over a tab bar / the menu bar zooms that font ----------------
mw = MainWindow.__new__(MainWindow)
mw._config = Config()
mw._prefs_dialog = None
_applied = []
mw._apply_widget_fonts = lambda: _applied.append(True)


def _wheel():
    return QtGui.QWheelEvent(
        QtCore.QPointF(5, 5), QtCore.QPointF(5, 5),
        QtCore.QPoint(0, 0), QtCore.QPoint(0, 120),
        QtCore.Qt.MouseButton.NoButton,
        QtCore.Qt.KeyboardModifier.ControlModifier,
        QtCore.Qt.ScrollPhase.NoScrollPhase, False)


check("a Ctrl+wheel over a tab bar is handled",
      mw._handle_widget_font_wheel(QtWidgets.QTabBar(), _wheel()))
check("the tab font size is persisted",
      mw._config.appearance.tab_font_size > 0)
check("the tab font is re-applied", bool(_applied))
check("a Ctrl+wheel over the menu bar is handled",
      mw._handle_widget_font_wheel(QtWidgets.QMenuBar(), _wheel()))
check("the menu font size is persisted",
      mw._config.appearance.menu_font_size > 0)
check("a Ctrl+wheel over a plain widget is ignored",
      not mw._handle_widget_font_wheel(QtWidgets.QLabel(), _wheel()))

# 3. the input placeholder is drawn with the widget font ----------------------
from stanza_im.ui.chat_widget import _ChatInput  # noqa: E402

app.setStyleSheet("QMenuBar, QMenu { font-size: 12pt; }")   # non-empty app QSS


def _hint_height(px: int) -> int:
    widget = _ChatInput()
    widget.resize(400, 120)
    widget.set_placeholder("Send")
    font = QtGui.QFont(QtWidgets.QApplication.font())
    font.setPointSize(px)
    widget.setFont(font)
    image = QtGui.QImage(widget.size(), QtGui.QImage.Format.Format_RGB32)
    widget.render(image)
    ys = [y for y in range(6, image.height() - 6)
          for x in range(6, image.width() - 6)
          if image.pixelColor(x, y).red() < 210]
    return (max(ys) - min(ys) + 1) if ys else 0


_small, _big = _hint_height(9), _hint_height(24)
check("the input placeholder scales with the widget font",
      _small > 0 and _big > _small * 2)
_hint = _ChatInput()
_hint.set_placeholder("Send")
check("the input placeholder text is exposed", _hint.placeholderText() == "Send")
app.setStyleSheet("")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All font-prefs tests passed.")
