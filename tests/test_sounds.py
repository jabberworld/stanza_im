"""Offscreen tests for sound notification themes and the Sounds preferences.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_sounds.py
"""
import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_sounds_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import load as i18n_load
from stanza_im.i18n import tr
from stanza_im.include import sounds
from stanza_im.ui import icons as icons_mod
from stanza_im.ui.chat_themes import ChatThemeFactory, mentions_nick
from stanza_im.ui.main_window import MainWindow
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
              "sound_contact_online", "sound_contact_offline",
              "sound_call_incoming")
check("all nine sound options exist and are enabled",
      all(k in controls and controls[k].isEnabled() for k in sound_keys))
check("the incoming-call ringtone option is on by default",
      controls["sound_call_incoming"].isChecked())
check("no option label starts with the old leading word",
      all("Звук" not in controls[k].text()
          and not controls[k].text().startswith("Play sound")
          for k in sound_keys))
check("each option is preceded by a preview button",
      sum(1 for b in dlg.findChildren(QtWidgets.QToolButton)
          if b.toolTip() == tr("prefs_sound_preview_tip")) == len(sound_keys))

# Low-priority overrides are opt-in and depend on their parent sounds.
check("low-priority sound options are off by default",
      not controls["sound_low_priority_message"].isChecked()
      and not controls["sound_low_priority_muc"].isChecked())
check("low-priority chat sound is disabled without a parent",
      not controls["sound_low_priority_message"].isEnabled())
check("low-priority conference sound is disabled without a parent",
      not controls["sound_low_priority_muc"].isEnabled())
controls["sound_any_message"].setChecked(True)
check("enabling the chat parent enables its low-priority override",
      controls["sound_low_priority_message"].isEnabled())
controls["sound_muc_mention"].setChecked(True)
check("enabling the mention parent enables its low-priority override",
      controls["sound_low_priority_muc"].isEnabled())
controls["sound_low_priority_message"].setChecked(True)
controls["sound_low_priority_muc"].setChecked(True)
check("the low-priority overrides persist",
      Config().notifications.sound_low_priority_message is False
      and Config().notifications.sound_low_priority_muc is False)

controls["sound_theme"].setCurrentIndex(theme.findData("xylo"))
controls["sound_contact_online"].setChecked(True)
dlg._apply_settings()
check("apply stores the theme and the option",
      cfg.notifications.sound_theme == "xylo"
      and cfg.notifications.sound_contact_online is True
      and cfg.notifications.sound_low_priority_message is True
      and cfg.notifications.sound_low_priority_muc is True)

# The new modifier checkboxes must line up with the existing sound rows.
dlg.show()
dlg._sections.setCurrentRow(7)
dlg.adjustSize()
app.processEvents()
_x_any = controls["sound_any_message"].mapTo(
    dlg, QtCore.QPoint(0, 0)).x()
_x_low = controls["sound_low_priority_message"].mapTo(
    dlg, QtCore.QPoint(0, 0)).x()
_x_mention = controls["sound_muc_mention"].mapTo(
    dlg, QtCore.QPoint(0, 0)).x()
_x_low_muc = controls["sound_low_priority_muc"].mapTo(
    dlg, QtCore.QPoint(0, 0)).x()
check("the low-priority chat checkbox aligns with the other chat sounds",
      _x_low == _x_any)
check("the low-priority conference checkbox aligns with the mention sound",
      _x_low_muc == _x_mention)
dlg.hide()
dlg.deleteLater()

# ── low-priority runtime gating ─────────────────────────────────
class _SoundRecorder:
    def __init__(self):
        self.events = []

    def play(self, event):
        self.events.append(event)


def _sound_window(low_message=False, low_muc=False):
    win = MainWindow.__new__(MainWindow)
    win._config = SimpleNamespace(notifications=SimpleNamespace(
        sound_low_priority_message=low_message,
        sound_low_priority_muc=low_muc,
        sound_first_message=True,
        sound_any_message=True,
        sound_muc_mention=True))
    win._sounds = _SoundRecorder()
    win._chat_window = SimpleNamespace(
        has_chat=lambda _jid: True, current_jid=lambda: "")
    win._chat_area_visible = lambda: False
    return win


win = _sound_window()
MainWindow._notify_incoming_message(win, "bob@example.com", "hi", "low")
check("a low-priority message is silent by default", win._sounds.events == [])
win._config.notifications.sound_low_priority_message = True
MainWindow._notify_incoming_message(win, "bob@example.com", "hi", "low")
check("the low-priority chat override plays the sound",
      win._sounds.events == ["message"])
win._sounds.events.clear()
MainWindow._notify_incoming_message(win, "bob@example.com", "hi", "normal")
check("normal priority still plays", win._sounds.events == ["message"])
check("a low-priority conference mention is opt-in",
      not win._priority_sound_allowed("low", "sound_low_priority_muc"))
win._config.notifications.sound_low_priority_muc = True
check("the low-priority conference override enables the mention sound",
      win._priority_sound_allowed("low", "sound_low_priority_muc"))

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
