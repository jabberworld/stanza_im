"""Offscreen tests for the Colors preferences tab (roster/chat backgrounds,
MUC mention highlight) and colorful MUC nicknames.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_colors.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_colors_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.core.storage import Config

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# ── Config defaults ─────────────────────────────────────────────────
cfg = Config()
check("appearance.roster_bg_color default",
      getattr(cfg.appearance, "roster_bg_color", "") == "#ffffff")
check("appearance.roster_group_bg_color default",
      getattr(cfg.appearance, "roster_group_bg_color", "") == "#ececec")
check("appearance.chat_bg_color default",
      getattr(cfg.appearance, "chat_bg_color", "") == "#ffffff")
check("appearance.muc_highlight_color default",
      getattr(cfg.appearance, "muc_highlight_color", "") == "#e53935")
check("appearance.colored_muc_nicks default",
      getattr(cfg.appearance, "colored_muc_nicks", False) is True)
check("appearance.osd_bg_color default",
      getattr(cfg.appearance, "osd_bg_color", "") == "#282828")
check("appearance.osd_font_color default",
      getattr(cfg.appearance, "osd_font_color", "") == "#ffffff")
check("appearance.osd_opacity default",
      int(getattr(cfg.appearance, "osd_opacity", 0)) == 92)

# ── OSD window styling (bg / font color / opacity) ─────────────────
from stanza_im.ui.osd import _OsdWindow

_osd = _OsdWindow(None, "t", "b", bg_color="#112233",
                  font_color="#445566", opacity=50)
_osd_ss = _osd._stylesheet()
_osd_bg = _osd._bubble_color()
check("osd bubble uses the configured color and opacity",
      (_osd_bg.red(), _osd_bg.green(), _osd_bg.blue(), _osd_bg.alpha())
      == (17, 34, 51, 128))
check("osd font color applied", "#445566" in _osd_ss)
_osd.apply_style(bg_color="#000000", opacity=0)
check("osd restyle updates the bubble alpha",
      _osd._bubble_color().alpha() == 0)
_osd.deleteLater()

# ── ChatThemeFactory chat background & highlight color ─────────────
factory = ChatThemeFactory()
factory.set_chat_bg_color("#112233")
page = factory.generate_page([], "")
check("chat bg color injected into page",
      "background-color: #112233 !important" in page
      and "background-image: none !important" in page)

factory.set_chat_bg_color("bogus")
page = factory.generate_page([], "")
check("invalid chat bg kept default", "#112233" not in page)

factory.set_chat_bg_color("")
page = factory.generate_page([], "")
check("cleared chat bg no longer injected", "#112233" not in page)

factory.set_highlight_color("#00ff00")
html = factory.render_message("Alice", "hey rain: go", "12:00:00",
                              "incoming", highlight_nick="rain")
check("custom highlight color used",
      '<span style="font-weight:bold;color:#00ff00">rain</span>' in html)
factory.set_highlight_color("")
html = factory.render_message("Alice", "hey rain: go", "12:00:00",
                              "incoming", highlight_nick="rain")
check("empty highlight color falls back to default",
      '<span style="font-weight:bold;color:#e53935">rain</span>' in html)

# ── RosterStyle colors ─────────────────────────────────────────────
from stanza_im.ui.roster_style import RosterStyle
from stanza_im.ui.roster_widget import RosterWidget

style = RosterStyle("#010203", "#040506")
check("roster bg color", style.bg_color().name() == "#010203")
check("roster group bg color", style.group_bg_color().name() == "#040506")

roster = RosterWidget()
roster.set_style(style)
check("paint uses style colors", roster._style is style)

trailing = RosterWidget()
trailing.set_trailing_groups({"Конференции"})
trailing.add_group("Work")
trailing.add_group("Конференции")
trailing.add_group("Friends")
check("conferences group sorts after the contact groups",
      trailing._sorted_groups == ["Friends", "Work", "Конференции"])

# ── NickColorAllocator ─────────────────────────────────────────────
from stanza_im.ui.nick_colors import NickColorAllocator, normalize_nick

check("normalize_nick collapses whitespace/case",
      normalize_nick("  Alice \u00a0  ") == "alice")
check("normalize_nick NFKC", normalize_nick("\u2170ice") == "iice")

alloc = NickColorAllocator()
c_alice = alloc.color_for("alice")
c_bob = alloc.color_for("bob")
check("alice/bob get distinct colors", c_alice != c_bob)
check("color stable per key",
      alloc.color_for("alice") == c_alice)

alloc.prune(["alice"])
c_bob2 = alloc.color_for("bob")
check("pruned color reused", c_bob2 == c_bob)

alloc.reset()
c_alice2 = alloc.color_for("alice")
check("reset re-allocates first palette color", c_alice2 == "#000000")

many = NickColorAllocator()
colors = {many.color_for(f"u{i}") for i in range(40)}
check("fallback golden-angle adds distinct colors",
      len(colors) == 40 and "#000000" in colors)

# ── ChatWidget colored MUC nicks ───────────────────────────────────
from stanza_im.ui.chat_widget import ChatWidget

cw = ChatWidget("room@conf/x", "Room", ChatThemeFactory(), is_muc=True)
cw.update_muc_users([{"nick": "alice", "role": "participant"},
                     {"nick": "bob", "role": "participant"}])
kwargs = cw._entry_view_kwargs({
    "sender": "alice", "body": "hi", "timestamp": "12:00:00",
    "direction": "incoming"})
alice_color = kwargs["sender_color"]
check("MUC message carries sender color", bool(alice_color))

kwargs_bob = cw._entry_view_kwargs({
    "sender": "bob", "body": "hi", "timestamp": "12:00:00",
    "direction": "incoming"})
check("different nicks get different colors",
      kwargs_bob["sender_color"] != alice_color)

cw.set_colored_muc_nicks(False)
kwargs_off = cw._entry_view_kwargs({
    "sender": "alice", "body": "hi", "timestamp": "12:00:00",
    "direction": "incoming"})
check("colored nicks off -> no sender color", not kwargs_off["sender_color"])
cw.set_colored_muc_nicks(True)
check("colored nicks re-enabled", bool(
    cw._entry_view_kwargs({
        "sender": "alice", "body": "hi", "timestamp": "12:00:00",
        "direction": "incoming"})["sender_color"]))
cw.close()

# 1:1 chat never colors senders
cw11 = ChatWidget("alice@example.com", "Alice", ChatThemeFactory(),
                  is_muc=False)
kw11 = cw11._entry_view_kwargs({
    "sender": "alice", "body": "hi", "timestamp": "12:00:00",
    "direction": "incoming"})
check("1:1 chat has no sender color", not kw11["sender_color"])
cw11.close()

# ── Preferences selectors load/save the new keys ───────────────────
from stanza_im.ui.preferences import PreferencesDialog

dlg = PreferencesDialog(cfg, ChatThemeFactory())
dlg._load_values()
for key in ("roster_bg_color", "roster_group_bg_color", "chat_bg_color",
            "muc_highlight_color", "colored_muc_nicks",
            "osd_bg_color", "osd_font_color", "osd_opacity"):
    check(f"preferences loads {key}", key in dlg._controls)

dlg._set("roster_bg_color", "#000000")
dlg._set("chat_bg_color", "#101010")
dlg._set("muc_highlight_color", "#202020")
dlg._set("colored_muc_nicks", False)
dlg._set("osd_bg_color", "#010203")
dlg._set("osd_font_color", "#040506")
dlg._set("osd_opacity", 40)
dlg._apply_settings()
check("roster_bg_color saved",
      cfg.appearance.roster_bg_color == "#000000")
check("chat_bg_color saved", cfg.appearance.chat_bg_color == "#101010")
check("muc_highlight_color saved",
      cfg.appearance.muc_highlight_color == "#202020")
check("colored_muc_nicks saved", cfg.appearance.colored_muc_nicks is False)
check("osd_bg_color saved", cfg.appearance.osd_bg_color == "#010203")
check("osd_font_color saved", cfg.appearance.osd_font_color == "#040506")
check("osd_opacity saved", int(cfg.appearance.osd_opacity) == 40)
dlg.close()


print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)