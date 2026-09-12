"""Offscreen tests for MUC own-nick mention highlighting.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_muc_highlight.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_highlight_")
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


def span(mode=None):
    factory = ChatThemeFactory()
    factory.set_message_styling(False)
    if mode:
        factory.set_highlight_mode(mode)
    return factory


BOTH = 'font-weight:bold;color:#e53935'


def body_of(factory, text, nick="rain", **kw):
    html = factory.render_message("Alice", text, "12:00:00", "incoming",
                                  highlight_nick=nick, **kw)
    return html


# ── Positive matches (punctuation allowed) ─────────────────────────
factory = span()
html = body_of(factory, "hey rain: are you there?")
check("mention with colon highlighted (both)",
      f'<span style="{BOTH}">rain</span>' in html)

html = body_of(factory, "rain? how about lunch")
check("mention at line start with question mark",
      f'<span style="{BOTH}">rain</span>' in html)

html = body_of(factory, "tell rain, ok")
check("mention with comma", f'<span style="{BOTH}">rain</span>' in html)

html = body_of(factory, "(rain) ping")
check("mention in parentheses", f'<span style="{BOTH}">rain</span>' in html)

html = body_of(factory, "good rain")
check("mention at line end", f'<span style="{BOTH}">rain</span>' in html)

html = body_of(factory, "Rain: and RAIN! both match")
check("case-insensitive matching",
      html.count(f'<span style="{BOTH}">') == 2
      and f'<span style="{BOTH}">Rain</span>' in html
      and f'<span style="{BOTH}">RAIN</span>' in html)

# ── Negative matches (letters around the nick) ─────────────────────
for text in ("Ukraine beat them", "the brain is fast", "it rains often",
             "rain2 aside", "rains and storms"):
    html = body_of(factory, text)
    check(f"no highlight for {text!r}", BOTH not in html)


# ── Highlight modes ────────────────────────────────────────────────
html = body_of(span("bold"), "hey rain: go")
check("bold-only mode", '<span style="font-weight:bold">rain</span>' in html
      and BOTH not in html)

html = body_of(span("color"), "hey rain: go")
check("color-only mode", '<span style="color:#e53935">rain</span>' in html
      and "font-weight" not in html)

html = body_of(span("both"), "hey rain: go")
check("bold+color mode (default)",
      f'<span style="{BOTH}">rain</span>' in html)


# ── XEP-0393 styling interplay ─────────────────────────────────────
factory_styled = ChatThemeFactory()
factory_styled.set_highlight_mode("both")
html = factory_styled.render_message(
    "Alice", "say *rain*: later", "12:00:00", "incoming",
    highlight_nick="rain")
check("highlight inside strong span",
      '<strong>*<span style="font-weight:bold;color:#e53935">'
      'rain</span>*</strong>' in html)

html = factory_styled.render_message(
    "Alice", "use `rain` in code", "12:00:00", "incoming",
    highlight_nick="rain")
check("no highlight inside code", BOTH not in html)


# ── No-op without a nick / disabled ────────────────────────────────
html = body_of(span(), "hey rain: go", nick=None)
check("no nick given -> no span", BOTH not in html)

factory_off = span("none")
html = factory_off.render_message("Alice", "hey rain:", "12:00:00",
                                  "incoming", highlight_nick="rain")
check("mode none disables highlight", BOTH not in html)

html = body_of(span(), "hey rain: go", unstyled=True)
check("unstyled path still highlights",
      f'<span style="{BOTH}">rain</span>' in html)


# ── URL containing the nick stays intact ───────────────────────────
url = "https://rain.example.com/page"
html = body_of(factory, f"see {url} now")
check("URL with nick not corrupted and not highlighted",
      f'<a href="{url}">{url}</a>' in html
      and BOTH not in html)

# ── /me action phrase not highlighted ──────────────────────────────
factory_action = span("both")
html = factory_action.render_action("Alice", "waves at rain", "12:00:00")
check("action phrase not highlighted", BOTH not in html)


# ── Config default and preferences wiring ──────────────────────────
from stanza_im.ui.preferences import PreferencesDialog

cfg = Config()
check("appearance default muc_highlight=both",
      getattr(cfg.appearance, "muc_highlight", "") == "both")

dlg = PreferencesDialog(cfg, ChatThemeFactory())
dlg._load_values()
val = dlg._value("muc_highlight")
check("preferences load value", val == "both")

dlg._controls["muc_highlight"].setCurrentIndex(
    dlg._controls["muc_highlight"].findData("color"))
dlg._apply_settings()
check("preferences save value",
      cfg.appearance.muc_highlight == "color")
dlg.close()


# ── ChatWidget wires the MUC self-nick to the view ─────────────────
from stanza_im.ui.chat_widget import ChatWidget

cw = ChatWidget("room@conf/x", "Room", ChatThemeFactory(), is_muc=True)
cw.update_muc_users([{"nick": "rain", "role": "participant"}], self_nick="rain")
check("self nick wired via update_muc_users", cw._view.highlight_nick == "rain")
cw.set_self_nick("rain")
check("set_self_nick keeps view nick", cw._view.highlight_nick == "rain")
cw.close()


print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)