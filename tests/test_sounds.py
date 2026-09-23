"""Offscreen tests for sound notification themes and the Sounds preferences.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_sounds.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_sounds_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.include import sounds
from stanza_im.ui import icons as icons_mod
from stanza_im.ui.chat_themes import ChatThemeFactory, mentions_nick
from stanza_im.ui.preferences import PreferencesDialog
from stanza_im.ui.sounds import SoundPlayer

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── theme discovery / parsing ────────────────────────────────────
themes = sounds.discover_themes()
check("all packaged sound themes are discovered",
      [t["id"] for t in themes] == ["default", "future", "xylo"])
check("a theme carries its display name",
      themes[0]["name"] == "Default Jabbim Sound Pack")
check("an unnamed theme falls back to its id",
      themes[1]["name"] == "future")

mapping = sounds.theme_sounds("default")
check("every event maps to an existing file",
      set(mapping) == set(sounds.EVENTS)
      and all(os.path.isfile(p) for p in mapping.values()))
check("an unknown theme has no sounds",
      sounds.theme_sounds("nope") == {})

check("the config default theme is valid",
      os.path.isdir(os.path.join(sounds.SOUNDS_DIR,
                                 Config().notifications.sound_theme)))

# ── SoundPlayer (Qt Multimedia is optional) ──────────────────────
player = SoundPlayer()
player.set_theme("xylo")
check("set_theme stores the theme and its sounds",
      player._theme == "xylo" and bool(player._sounds))
try:
    player.play("message")
    player.play("message", "default")
    player.play("no-such-event")
    player.stop()
    player_ok = True
except Exception:
    player_ok = False
check("play never raises (no-op without Qt Multimedia)", player_ok)

# ── mention matcher (shared with the highlight) ──────────────────
check("a bounded nick matches", mentions_nick("hi Rain: hello", "rain"))
check("a substring of a word does not match",
      not mentions_nick("brain storm", "rain"))
check("punctuation after the nick matches",
      mentions_nick("rain?", "rain"))
check("an empty nick never matches", not mentions_nick("rain", ""))

# ── Sounds preferences tab ───────────────────────────────────────
icons_mod.init_icons()
cfg = Config()
cfg.notifications.sound_theme = "future"
dlg = PreferencesDialog(cfg, ChatThemeFactory(), client=None)
controls = dlg._controls

theme = controls["sound_theme"]
check("the sound theme selector lists the themes",
      isinstance(theme, QtWidgets.QComboBox)
      and [theme.itemData(i) for i in range(theme.count())]
      == ["default", "future", "xylo"])
check("the saved theme is preselected", theme.currentData() == "future")

sound_keys = ("sound_first_message", "sound_any_message", "sound_muc_mention",
              "sound_on_send", "sound_ft_start", "sound_ft_finish",
              "sound_contact_online", "sound_contact_offline")
check("all eight sound options exist and are enabled",
      all(k in controls and controls[k].isEnabled() for k in sound_keys))
check("no option label starts with the old leading word",
      all("Звук" not in controls[k].text()
          and not controls[k].text().startswith("Play sound")
          for k in sound_keys))
check("each option is preceded by a preview button",
      sum(1 for b in dlg.findChildren(QtWidgets.QToolButton)
          if b.toolTip() == tr("prefs_sound_preview_tip")) == len(sound_keys))

controls["sound_theme"].setCurrentIndex(theme.findData("xylo"))
controls["sound_contact_online"].setChecked(True)
dlg._apply_settings()
check("apply stores the theme and the option",
      cfg.notifications.sound_theme == "xylo"
      and cfg.notifications.sound_contact_online is True)

dlg.deleteLater()

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
