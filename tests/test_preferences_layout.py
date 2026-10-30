"""Geometry checks for the compact Connection advanced/proxy tabs."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_prefs_layout_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.core.storage import Config  # noqa: E402
from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.preferences import (  # noqa: E402
    ADVANCED_COMBO_WIDTH, PROXY_FIELD_WIDTH, PreferencesDialog)

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


dlg = PreferencesDialog(Config.defaults(), ChatThemeFactory())
dlg._ensure_all_pages()
dlg.resize(dlg.minimumSize())
dlg.show()
app.processEvents()
for row in range(dlg._sections.count()):
    if dlg._sections.item(row).text() == "Connection":
        dlg._sections.setCurrentRow(row)
        break
app.processEvents()
tabs = dlg._stack.currentWidget()
tabs.setCurrentIndex(1)
app.processEvents()
check("advanced selectors share a compact width",
      all(dlg._controls[key].width() == ADVANCED_COMBO_WIDTH for key in (
          "resource_mode", "priority_mode", "tls_mode", "starttls_mode",
          "pep_sweep_interval")))
check("resource selector precedes the editable field",
      dlg._controls["resource_mode"].x()
      < dlg._controls["resource"].x())
check("priority selector and value do not overlap",
      dlg._controls["priority_mode"].x()
      + dlg._controls["priority_mode"].width()
      <= dlg._controls["priority"].x())
tabs.setCurrentIndex(2)
app.processEvents()
for prefix in ("file_proxy", "stun_turn"):
    mode = dlg._controls[prefix + "_mode"]
    manual = dlg._controls[prefix + "_manual"]
    check("%s selector/manual field align" % prefix,
          mode.x() == manual.x() and mode.width() == manual.width()
          == PROXY_FIELD_WIDTH)
dlg.close()

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All preferences-layout tests passed")
