"""Auto-status minutes linking tests (xa always > away).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_status_prefs.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_prefs_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets
from stanza_im.core.storage import Config
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.preferences import PreferencesDialog, link_status_minutes

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 1. existing equal saved config is corrected on dialog load ---------------
cfg = Config()
cfg.status.auto_away = True
cfg.status.away_minutes = 20
cfg.status.auto_xa = True
cfg.status.xa_minutes = 20
dlg = PreferencesDialog(cfg, ChatThemeFactory())
away = dlg._controls["away_minutes"]
xa = dlg._controls["xa_minutes"]
check("equal config fixed on load", xa.value() == away.value() + 1
      and xa.value() == 21)

# 2. raising away bumps xa to stay above --------------------------------
away.setValue(30)
check("away up -> xa follows", away.value() == 30 and xa.value() == 31)

# 3. lowering xa below away is clamped up --------------------------------
xa.setValue(5)
check("xa clamped above away", xa.value() == away.value() + 1)

# 4. xa stays strictly greater after both spin ----------------------------
away.setValue(7)
xa.setValue(60)
check("xa far above away kept", xa.value() == 60)
away.setValue(59)
check("away near xa bumps xa", away.value() == 59 and xa.value() == 60)

# 5. boundary: away cannot equal 1440 (xa must be above) -----------------
away.setValue(1440)
check("away capped at 1439", away.value() == 1439 and xa.value() == 1440)

# 6. apply persists the invariant ----------------------------------------
away.setValue(12)
dlg._apply_settings()
check("applied xa > away", cfg.status.xa_minutes > cfg.status.away_minutes
      and cfg.status.away_minutes == 12)

# 7. helper standalone re-links an existing pair --------------------------
cfg2 = Config()
d2 = PreferencesDialog(cfg2, ChatThemeFactory())
d2._controls["away_minutes"].setValue(5)
d2._controls["xa_minutes"].setValue(5)
check("standalone relink fixes equal pair",
      d2._controls["xa_minutes"].value()
      == d2._controls["away_minutes"].value() + 1)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
