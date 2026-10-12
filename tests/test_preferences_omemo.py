"""Preferences must not crash on Apply when OMEMO is unavailable.

The OMEMO tab omits its controls without OMEMO; Apply used to read them
unconditionally and raise ``KeyError: 'blind_trust'``.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_preferences_omemo.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_prefomemo_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.core.storage import Config  # noqa: E402
from stanza_im.i18n import load as load_i18n  # noqa: E402
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.preferences import PreferencesDialog  # noqa: E402
from stanza_im.xmpp.omemo import availability  # noqa: E402

load_i18n("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# Force the "OMEMO unavailable" path regardless of the test environment.
saved = (availability.AVAILABLE, availability.MISSING,
         availability.MISSING_MODULES)
availability.AVAILABLE = False
availability.MISSING = ["oldmemo"]
availability.MISSING_MODULES = ["oldmemo"]

try:
    cfg = Config()
    cfg.omemo.blind_trust = False
    cfg.omemo.alias_sync = True
    cfg.omemo.auto_enable = False

    dlg = PreferencesDialog(cfg, ChatThemeFactory(), client=None)
    dlg._ensure_all_pages()
    check("the OMEMO controls are absent without OMEMO",
          "blind_trust" not in dlg._controls)

    crashed = None
    try:
        dlg._apply_settings()
    except Exception as exc:  # noqa: BLE001
        crashed = exc
    check("Apply does not crash without OMEMO", crashed is None)
    check("the stored OMEMO settings are preserved",
          cfg.omemo.blind_trust is False
          and cfg.omemo.alias_sync is True
          and cfg.omemo.auto_enable is False)
    _texts = " ".join(w.text() for w in dlg.findChildren(QtWidgets.QLabel)
                      if hasattr(w, "text"))
    check("no distribution install command is shown",
          "apt" not in _texts.lower())
    check("the unavailable note is shown",
          "OMEMO is not available" in _texts)
    check("the missing modules are listed",
          "Missing Python modules" in _texts)
    dlg.close()
finally:
    (availability.AVAILABLE, availability.MISSING,
     availability.MISSING_MODULES) = saved

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All preferences-omemo tests passed.")
