"""Tests for the startup/memory performance settings (new tab + flags).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_performance_prefs.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_perf_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.app import apply_chromium_flags, chromium_flags_for
from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.preferences import PreferencesDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. config defaults ---------------------------------------------------------
cfg = Config()
perf = cfg.performance
check("performance defaults present",
      perf.defer_ui_build is True and perf.omemo_load_mode == "lazy"
      and perf.calls_load_mode == "lazy"
      and perf.webengine_mode == "full"
      and perf.webengine_memory_mode == "moderate"
      and perf.webengine_cache_mb == 50)

# 1b. subsystem off switches -------------------------------------------------
from stanza_im.include import constants as constants_mod  # noqa: E402
_orig_webengine = constants_mod.webengine_available()
constants_mod.set_webengine_enabled(False)
check("webengine can be disabled", constants_mod.webengine_available() is False)
constants_mod.set_webengine_enabled(True)
check("webengine restored",
      constants_mod.webengine_available() == _orig_webengine)

from stanza_im.xmpp.omemo import availability  # noqa: E402
availability.set_disabled(True)
check("omemo disabled flag",
      availability.disabled() is True and availability.AVAILABLE is False
      and availability.verify() is False)
check("omemo disabled summary", "disabled" in availability.summary())
availability.set_disabled(False)
check("omemo re-enabled after clearing", availability.disabled() is False)

# 2. Chromium flag sets ------------------------------------------------------
check("off mode has no flags", chromium_flags_for("off") == ())
moderate = chromium_flags_for("moderate")
check("moderate limits renderer processes",
      "--renderer-process-limit=1" in moderate)
check("moderate caps the V8 heap",
      "--js-flags=--max-old-space-size=128" in moderate)
check("moderate does not disable the GPU", "--disable-gpu" not in moderate)
aggressive = chromium_flags_for("aggressive")
check("aggressive adds --disable-gpu",
      "--disable-gpu" in aggressive
      and "--renderer-process-limit=1" in aggressive)
check("an unknown mode falls back to moderate",
      chromium_flags_for("bogus") == moderate)

# 3. apply_chromium_flags sets the env var, but respects a user override -----
saved = os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
try:
    apply_chromium_flags("moderate")
    check("apply sets QTWEBENGINE_CHROMIUM_FLAGS",
          "--renderer-process-limit=1"
          in os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""))
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--my-own-flag"
    apply_chromium_flags("aggressive")
    check("a user-set flag list is not overwritten",
          os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] == "--my-own-flag")
finally:
    os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
    if saved is not None:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = saved

# 4. the Preferences tab exposes and applies the settings --------------------
dlg = PreferencesDialog(cfg, ChatThemeFactory())
dlg._ensure_all_pages()
for key in ("defer_ui_build", "omemo_load_mode", "calls_load_mode",
            "webengine_mode", "webengine_memory_mode", "webengine_cache_mb"):
    check(f"prefs control {key}", key in dlg._controls)
check("the controls load the current values",
      dlg._controls["defer_ui_build"].isChecked()
      and dlg._controls["omemo_load_mode"].currentData() == "lazy"
      and dlg._controls["webengine_mode"].currentData() == "full"
      and dlg._controls["webengine_memory_mode"].currentData() == "moderate"
      and dlg._controls["webengine_cache_mb"].value() == 50)
check("the load selectors offer Off",
      dlg._controls["omemo_load_mode"].findData("off") >= 0
      and dlg._controls["calls_load_mode"].findData("off") >= 0)
check("the web engine selector offers all three modes",
      dlg._controls["webengine_mode"].findData("full") >= 0
      and dlg._controls["webengine_mode"].findData("no_preview") >= 0
      and dlg._controls["webengine_mode"].findData("off") >= 0)
dlg._controls["defer_ui_build"].setChecked(False)
dlg._controls["omemo_load_mode"].setCurrentIndex(
    dlg._controls["omemo_load_mode"].findData("off"))
dlg._controls["calls_load_mode"].setCurrentIndex(
    dlg._controls["calls_load_mode"].findData("off"))
dlg._controls["webengine_mode"].setCurrentIndex(
    dlg._controls["webengine_mode"].findData("no_preview"))
dlg._controls["webengine_memory_mode"].setCurrentIndex(
    dlg._controls["webengine_memory_mode"].findData("aggressive"))
dlg._controls["webengine_cache_mb"].setValue(120)
dlg._apply_settings()
check("apply writes the settings to the config",
      cfg.performance.defer_ui_build is False
      and cfg.performance.omemo_load_mode == "off"
      and cfg.performance.calls_load_mode == "off"
      and cfg.performance.webengine_mode == "no_preview"
      and cfg.performance.webengine_memory_mode == "aggressive"
      and cfg.performance.webengine_cache_mb == 120)
dlg.close()

# 5. the call manager honours the "off" mode ---------------------------------
from stanza_im.xmpp.jingle_rtp import JingleRtpManager  # noqa: E402


class _CallClient:
    calls_load_mode = "off"


check("calls are unavailable when off",
      JingleRtpManager(_CallClient()).available is False)

# 6. the Devices page never pulls aiortc when calls are off ------------------
import sys as _sys  # noqa: E402
_sys.modules.pop("stanza_im.xmpp.media", None)
_sys.modules.pop("stanza_im.ui.device_test", None)
_sys.modules.pop("aiortc", None)
cfg.performance.calls_load_mode = "off"
dlg2 = PreferencesDialog(cfg, ChatThemeFactory())
dlg2._ensure_all_pages()
check("Devices page does not import xmpp.media when calls are off",
      "stanza_im.xmpp.media" not in _sys.modules)
check("Devices page does not import device_test when calls are off",
      "stanza_im.ui.device_test" not in _sys.modules)
dlg2.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All performance-prefs tests passed.")
