"""Palette-aware colours: dark Qt theme, roster, nav, tooltip and chat.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_dark_theme.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_dark_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui import theme

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

DARK = QtGui.QPalette()
for role, value in (
        (QtGui.QPalette.ColorRole.Window, "#202124"),
        (QtGui.QPalette.ColorRole.WindowText, "#e8eaed"),
        (QtGui.QPalette.ColorRole.Base, "#17181a"),
        (QtGui.QPalette.ColorRole.AlternateBase, "#25272a"),
        (QtGui.QPalette.ColorRole.Text, "#e8eaed"),
        (QtGui.QPalette.ColorRole.Button, "#2a2c2f"),
        (QtGui.QPalette.ColorRole.ButtonText, "#e8eaed"),
        (QtGui.QPalette.ColorRole.Mid, "#70757a"),
        (QtGui.QPalette.ColorRole.Highlight, "#3b6ea8"),
        (QtGui.QPalette.ColorRole.HighlightedText, "#ffffff")):
    DARK.setColor(role, QtGui.QColor(value))
app.setPalette(DARK)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


BASE = app.palette().color(QtGui.QPalette.ColorRole.Base)
WINDOW = app.palette().color(QtGui.QPalette.ColorRole.Window)
TEXT = app.palette().color(QtGui.QPalette.ColorRole.Text)

check("dark palette detected", theme.is_dark())
check("dark background gets light text",
      theme.contrasting_text(BASE) == QtGui.QColor("#ffffff"))
check("light custom background gets dark text",
      theme.contrasting_text(QtGui.QColor("#ffffff"))
      == QtGui.QColor("#000000"))


# ── Roster ─────────────────────────────────────────────────────────
from stanza_im.ui.roster_style import RosterStyle, UserItem
from stanza_im.ui.roster_widget import RosterWidget

style = RosterStyle()
check("roster default fill follows palette Base",
      style.fill_color() == BASE)
check("roster default group fill follows palette Window",
      style.group_fill_color() == WINDOW)
check("roster default name uses palette Text",
      style._text_on(BASE) == TEXT)
light = RosterStyle("#ffffff", "#f0f0f0")
check("custom light roster uses dark text",
      light._text_on(QtGui.QColor("#ffffff"), custom=True)
      == QtGui.QColor("#000000"))

roster = RosterWidget()
roster.resize(240, 90)
roster.add_group("G")
roster.add_user(UserItem(jid="alice@example.org", name="Alice",
                         group="G", status="online", icon_key="online",
                         status_message="hello"))
image = QtGui.QImage(240, 90, QtGui.QImage.Format.Format_ARGB32)
image.fill(QtCore.Qt.GlobalColor.transparent)
roster.render(image)
check("roster paints the dark palette Base",
      image.pixelColor(1, style.GROUP_HEIGHT + 4) == BASE)
check("roster group paints the palette Window",
      image.pixelColor(1, 4) == WINDOW)


# ── Preferences navigation ────────────────────────────────────────
from stanza_im.core.storage import Config
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.preferences import PreferencesDialog, _ColorButton

dlg = PreferencesDialog(Config(), ChatThemeFactory())
nav_style = dlg._sections.styleSheet()
check("preferences nav uses palette base", "palette(base)" in nav_style)
check("preferences nav has no forced white", "white" not in nav_style.lower())
dlg.close()

btn = _ColorButton(allow_auto=True, role=QtGui.QPalette.ColorRole.Base)
check("auto colour stores an empty value", btn.color() == "")
btn.set_color("#ffffff")
check("explicit colour is stored", btn.color() == "#ffffff")
btn.set_color("")
check("colour can return to system", btn.color() == "")


# ── Tooltip ───────────────────────────────────────────────────────
from stanza_im.ui import tooltip

tip = tooltip._window()
tip._apply_style()
tip_style = tip.styleSheet()
check("tooltip follows the dark application palette",
      BASE.name() in tip_style and "#ffffdc" not in tip_style)
tip.close()


# ── Chat background contrast ──────────────────────────────────────
factory = ChatThemeFactory()
factory.set_chat_bg_color(BASE.name())
page = factory.generate_page([], "")
check("system chat background is injected", BASE.name() in page)
check("dark chat background gets light text",
      "color: #ffffff !important" in page)
factory.set_chat_bg_color("#ffffff")
page = factory.generate_page([], "")
check("light custom chat background gets dark text",
      "color: #000000 !important" in page)
check("light chat separator keeps the old #ccc",
      factory._chat_separator_color == "#cccccc")
check("light chat page uses the old separator",
      "border-top-color: #cccccc" in page)

factory.set_chat_bg_color(BASE.name())
page = factory.generate_page([], "")
check("dark chat separator is not the muted text colour",
      factory._chat_separator_color != factory._chat_muted_color)
separator = QtGui.QColor(factory._chat_separator_color)
check("dark chat separator stays subtle",
      0.15 < separator.lightnessF() < 0.4)
check("dark chat page uses the subtle separator",
      f"border-top-color: {factory._chat_separator_color}" in page)


# ── MUC nickname colours ──────────────────────────────────────────
from stanza_im.ui.nick_colors import NickColorAllocator

nicks = NickColorAllocator(dark=True)
nick_colors = [nicks.color_for(f"u{i}") for i in range(20)]
check("dark-theme nicks avoid near-black colours",
      all(QtGui.QColor(color).lightnessF() > 0.45 for color in nick_colors))
check("dark-theme nicks stay distinct", len(set(nick_colors)) == 20)
light_nicks = NickColorAllocator(dark=False)
check("light-theme nicks keep the original dark palette",
      light_nicks.color_for("alice") == "#000000")


# ── Separators / resize handle ────────────────────────────────────
from stanza_im.ui.resize_handle import VerticalResizeHandle

handle = VerticalResizeHandle()
check("resize handle follows palette mid",
      "palette(mid)" in handle.styleSheet())


print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All tests passed")
