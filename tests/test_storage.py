"""Tests for the TOML config store (core/storage.py).

Covers the writer's UTF-8 handling of non-BMP characters (emoji) and a full
round-trip of every configuration section.  No Qt is required.

Run with:
    python3 tests/test_storage.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_storage_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tomllib

from stanza_im.core.storage import Config
from stanza_im.include.constants import CONFIG_FILE

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. Emoji round-trip (regression: non-BMP chars must not be escaped) ----------
cfg = Config()
cfg.emoji.recent = ["😀", "❤️", "👍", "🎉"]
cfg.save()

with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
    raw = fh.read()
check("config file has no surrogate escapes", "\\ud83d" not in raw
      and "\\u2764" not in raw)
check("config file holds literal emoji", "😀" in raw)

with open(CONFIG_FILE, "rb") as fh:
    parsed = tomllib.load(fh)
check("config parses as valid TOML", "emoji" in parsed)
check("emoji.recent parsed back",
      parsed["emoji"]["recent"] == ["😀", "❤️", "👍", "🎉"])

reloaded = Config()
check("emoji.recent survives a reload",
      reloaded.emoji.recent == ["😀", "❤️", "👍", "🎉"])


# 2. Non-ASCII in a plain string scalars --------------------------------------
cfg2 = Config()
cfg2.status.message = "Привет, мир 😀"
cfg2.save()
cfg3 = Config()
check("cyrillic + emoji status message round-trips",
      cfg3.status.message == "Привет, мир 😀")


# 3. Every configuration section round-trips ----------------------------------
cfg4 = Config()
cfg4.save()
baseline = Config()

# Mutate one representative value per section, then reload and compare.
cfg4.jid = "user@example.com"
cfg4.password = "s3cret"
cfg4.save_password = True
cfg4.auto_connect = True
cfg4.last_status = "away"
cfg4.window.width = 777
cfg4.window.maximized = True
cfg4.chat.tab_title_length = 42
cfg4.chat.media_preview = "all"
cfg4.chat.text_scale = 1.25
cfg4.chat_window.width = 888
cfg4.media_viewer.height = 555
cfg4.map.tile_cache_mb = 128
cfg4.application.history_limit = 123
cfg4.connection.priority = 64
cfg4.connection.tls_mode = "normal"
cfg4.connection.csi = False
cfg4.notifications.osd_enabled = False
cfg4.notifications.popups = "off"
cfg4.status.auto_away = True
cfg4.ui.close_to_tray = False
cfg4.appearance.roster_font = "DejaVu Sans"
cfg4.appearance.roster_font_size = 12
cfg4.emoji.recent = ["😀", "🚀"]
cfg4.save()

cfg5 = Config()
check("scalar root keys round-trip",
      cfg5.jid == "user@example.com"
      and cfg5.save_password is True
      and cfg5.auto_connect is True
      and cfg5.last_status == "away")
check("window section round-trips",
      cfg5.window.width == 777 and cfg5.window.maximized is True)
check("chat section round-trips",
      cfg5.chat.tab_title_length == 42
      and cfg5.chat.media_preview == "all"
      and abs(cfg5.chat.text_scale - 1.25) < 1e-9)
check("chat_window / media_viewer round-trip",
      cfg5.chat_window.width == 888 and cfg5.media_viewer.height == 555)
check("map section round-trips", cfg5.map.tile_cache_mb == 128)
check("application section round-trips",
      cfg5.application.history_limit == 123)
check("connection section round-trips",
      cfg5.connection.priority == 64
      and cfg5.connection.tls_mode == "normal"
      and cfg5.connection.csi is False)
check("notifications section round-trips",
      cfg5.notifications.osd_enabled is False
      and cfg5.notifications.popups == "off")
check("status section round-trips", cfg5.status.auto_away is True)
check("ui section round-trips", cfg5.ui.close_to_tray is False)
check("appearance section round-trips",
      cfg5.appearance.roster_font == "DejaVu Sans"
      and cfg5.appearance.roster_font_size == 12)
check("emoji section round-trips", cfg5.emoji.recent == ["😀", "🚀"])

# Every default section must still be present after a reload and untouched
# keys must keep their defaults.
missing = [key for key in baseline.as_dict() if key not in cfg5.as_dict()]
check("no configuration section is lost on reload", not missing)
check("untouched default survives (chat.show_avatars)",
      cfg5.chat.show_avatars is True)
check("untouched default survives (window.height)",
      cfg5.window.height == baseline.window.height)


# 4. Booleans / numbers / nested tables stay typed ----------------------------
check("true stays a boolean", isinstance(cfg5.auto_connect, bool))
check("int stays an int", isinstance(cfg5.window.width, int))
check("float stays a float", isinstance(cfg5.chat.text_scale, float))
check("nested table is an attribute object",
      hasattr(cfg5.window, "width"))


print()
if FAILURES:
    print(f"{len(FAILURES)} test(s) FAILED: {FAILURES}")
    sys.exit(1)
print("All tests passed.")
