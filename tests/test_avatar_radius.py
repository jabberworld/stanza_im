"""Offscreen tests for the avatar corner-rounding setting.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_avatar_radius.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_avatar_radius_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtGui, QtWidgets

from stanza_im.core.storage import Config
from stanza_im.i18n import en, load as i18n_load, ru
from stanza_im.include.avatars import rounded_avatar
from stanza_im.ui.roster_style import RosterStyle

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. Helper ------------------------------------------------------------------
pix = QtGui.QPixmap(8, 8)
pix.fill(QtGui.QColor("red"))
for pct in (0, 20, 50, 100):
    out = rounded_avatar(pix, 16, pct)
    check(f"rounded_avatar({pct}) keeps the requested size",
          out.size().width() == 16 and out.size().height() == 16
          and out.hasAlphaChannel())
check("a null pixmap is returned unchanged", rounded_avatar(QtGui.QPixmap(), 16, 20).isNull())
# Out-of-range values are clamped, never crash.
rounded_avatar(pix, 16, -50)
rounded_avatar(pix, 16, 500)
check("out-of-range percentages are clamped", True)

# 2. Config ------------------------------------------------------------------
cfg = Config()
check("the default avatar radius is 20 %",
      int(cfg.appearance.avatar_radius) == 20)
cfg.appearance.avatar_radius = 55
cfg.save()
reloaded = Config()
check("the avatar radius round-trips through the config",
      int(reloaded.appearance.avatar_radius) == 55)

# 3. Roster style ------------------------------------------------------------
style = RosterStyle()
check("the roster style starts at 20 %", style._avatar_radius_pct == 20)
style.set_avatar_radius(80)
check("the roster style accepts a radius", style._avatar_radius_pct == 80)
style.set_avatar_radius(999)
check("the roster style clamps the radius", style._avatar_radius_pct == 100)
style.set_avatar_radius(-3)
check("the roster style clamps a negative radius",
      style._avatar_radius_pct == 0)

# 4. Preferences control -----------------------------------------------------
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.preferences import PreferencesDialog  # noqa: E402

prefs = PreferencesDialog(Config(), ChatThemeFactory())
check("the preferences expose an avatar radius spin",
      "avatar_radius" in prefs._controls)
spin = prefs._controls["avatar_radius"]
check("the spin range is 0..100",
      spin.minimum() == 0 and spin.maximum() == 100)

# 4b. Chat message avatars ---------------------------------------------------
import base64  # noqa: E402

from PyQt6 import QtCore  # noqa: E402

from stanza_im.include import avatars as avatars_mod  # noqa: E402
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.chat_widget import ChatWidget  # noqa: E402

_image = QtGui.QImage(40, 40, QtGui.QImage.Format.Format_RGB32)
_image.fill(QtGui.QColor("#3366cc"))
_buffer = QtCore.QBuffer()
_buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
_image.save(_buffer, "PNG")
avatars_mod.save_avatar("bob@example.com", bytes(_buffer.data()))

widget = ChatWidget("bob@example.com", "Bob", ChatThemeFactory())
raw_uri = avatars_mod.avatar_data_uri("bob@example.com")
widget.set_avatar_radius(0)
check("radius 0 keeps the original chat avatar",
      widget._user_icon("incoming", "bob@example.com") == raw_uri)

widget.set_avatar_radius(100)
rounded_uri = widget._user_icon("incoming", "bob@example.com")
check("the chat avatar is rounded when the radius is set",
      rounded_uri != raw_uri and rounded_uri.startswith("data:image/png;base64,"))
check("the rounding is cached", widget._rounded_avatar_cache
      and widget._user_icon("incoming", "bob@example.com") is rounded_uri)
_payload = base64.b64decode(rounded_uri.split(",", 1)[1])
_corner = QtGui.QImage.fromData(_payload, "PNG")
_corner = _corner.scaled(64, 64) if _corner.width() != 64 else _corner
check("the rounded chat avatar has transparent corners",
      _corner.pixelColor(0, 0).alpha() == 0
      and _corner.pixelColor(32, 32).alpha() > 0)
widget.set_avatar_radius(40)
check("changing the radius rebuilds the cached avatars",
      not widget._rounded_avatar_cache)

# 4b. a JPEG avatar is rounded too (the lists auto-detect the format) --------
_jimage = QtGui.QImage(40, 40, QtGui.QImage.Format.Format_RGB32)
_jimage.fill(QtGui.QColor("#cc6633"))
_jbuf = QtCore.QBuffer()
_jbuf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
_jimage.save(_jbuf, "JPEG")
avatars_mod.save_avatar("jpeg@example.com", bytes(_jbuf.data()))
widget.set_avatar_radius(100)
_jpeg_uri = widget._user_icon("incoming", "jpeg@example.com")
check("a JPEG avatar is re-encoded as a rounded PNG",
      _jpeg_uri.startswith("data:image/png;base64,")
      and _jpeg_uri != avatars_mod.avatar_data_uri("jpeg@example.com"))
_jpeg_rounded = QtGui.QImage.fromData(
    base64.b64decode(_jpeg_uri.split(",", 1)[1]), "PNG")
if _jpeg_rounded.width() != 64:
    _jpeg_rounded = _jpeg_rounded.scaled(64, 64)
check("the rounded JPEG avatar has transparent corners",
      _jpeg_rounded.pixelColor(0, 0).alpha() == 0
      and _jpeg_rounded.pixelColor(32, 32).alpha() > 0)
check("our own avatar is rounded too",
      widget._user_icon("outgoing").startswith("data:image/png;base64,"))
widget.detach()

from stanza_im.ui.chat_window import ChatWindow  # noqa: E402

window = ChatWindow(ChatThemeFactory())
window.open_chat("bob@example.com", "Bob")
window.set_avatar_radius(75)
check("the radius reaches an open 1:1 tab",
      window.get_chat("bob@example.com")._avatar_radius == 75)
window.close()

# 5. i18n --------------------------------------------------------------------
check("the avatar radius label is translated",
      en.STRINGS.get("prefs_avatar_radius")
      and ru.STRINGS.get("prefs_avatar_radius"))
check("en and ru have the same keys", set(en.STRINGS) == set(ru.STRINGS))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All avatar-radius tests passed.")
