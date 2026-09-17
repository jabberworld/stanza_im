"""Offscreen tests for the interface mode (separate / unified chat layout).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_interface_mode.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_iface_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.main_window import MainWindow
from stanza_im.ui.preferences import PreferencesDialog

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 1. config default and preference round-trip -------------------------------
cfg = Config()
check("default interface mode is separate",
      getattr(cfg.appearance, "interface_mode", None) == "separate")
cfg.appearance.interface_mode = "separate"
cfg.save()

dlg = PreferencesDialog(cfg, ChatThemeFactory())
combo = dlg._controls["interface_mode"]
check("prefs exposes interface_mode", combo is not None)
check("prefs combo offers both modes",
      sorted([combo.itemData(i) for i in range(combo.count())])
      == ["separate", "unified"])
combo.setCurrentIndex(combo.findData("unified"))
dlg._apply_settings()
check("apply stores unified", cfg.appearance.interface_mode == "unified")
dlg.close()

# 2. live switch on a MainWindow --------------------------------------------
cfg.appearance.interface_mode = "separate"
cfg.save()

win = MainWindow(app)
win._idle_timer.stop()
check("separate: no splitter", win._chat_splitter is None)
check("separate: chat is a top-level window", win._chat_window.isWindow())
check("separate: roster page in stack",
      win._stack.indexOf(win._roster_page) >= 0)

win._config.appearance.interface_mode = "unified"
win._apply_interface_mode()
check("unified: splitter created", win._chat_splitter is not None)
check("unified: chat embedded (not a window)",
      not win._chat_window.isWindow())
check("unified: splitter holds the chat",
      win._chat_splitter.indexOf(win._chat_window) >= 0)
check("unified: splitter holds the roster",
      win._chat_splitter.indexOf(win._roster_page) >= 0)
check("unified: stack shows the splitter",
      win._stack.currentWidget() is win._chat_splitter)

# opening a chat must not pop a separate window
win._chat_window.open_chat("bob@example.com", "Bob")
check("unified: chat tab opened", win._chat_window.has_chat("bob@example.com"))
check("unified: stays embedded after open",
      not win._chat_window.isWindow())
check("unified: chat area visibility follows the main window",
      win._chat_area_visible() == win.isVisible())

# closing the last tab keeps the embedded widget in place
win._chat_window.close_chat("bob@example.com")
check("unified: no tabs left", win._chat_window.tab_count() == 0)
check("unified: stays embedded after close",
      not win._chat_window.isWindow())

# switching back detaches the chat into its own window
win._config.appearance.interface_mode = "separate"
win._apply_interface_mode()
check("separate again: splitter gone", win._chat_splitter is None)
check("separate again: chat is a window", win._chat_window.isWindow())
check("separate again: roster page restored in stack",
      win._stack.indexOf(win._roster_page) >= 0)
win._chat_window.close()

# 3. construction honours a saved unified mode ------------------------------
cfg2 = Config()
cfg2.appearance.interface_mode = "unified"
cfg2.save()
win2 = MainWindow(app)
win2._idle_timer.stop()
check("constructor unified: splitter exists", win2._chat_splitter is not None)
check("constructor unified: chat embedded",
      not win2._chat_window.isWindow())
win2._chat_window.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All interface-mode tests passed.")
