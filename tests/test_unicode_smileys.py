"""Tests for the text-smiley → unicode-emoji substitution.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_unicode_smileys.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_unicode_smileys_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.include import emoticons
from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# The map is derived from the default theme's image semantics.
mapping = emoticons.unicode_map()
check("the map covers the common smileys",
      mapping.get(":)") == "🙂" and mapping.get(":-D") == "😁"
      and mapping.get(";)") == "😉")
check("aliases of one image share its emoji",
      mapping.get(":)") == mapping.get(":-)"))
check("a pictogram code maps too", mapping.get("(K)") == "😘")

# smile_to_html: no-op without the option, substitution with it.
check("unicode skin is a no-op when the option is off",
      emoticons.smile_to_html("hi :)", emoticons.UNICODE_SKIN) == "hi :)")
check("unicode skin substitutes when the option is on",
      emoticons.smile_to_html("hi :) :-D", emoticons.UNICODE_SKIN,
                              unicode_replace=True) == "hi 🙂 😁")
check("a theme skin still renders images",
      "<img" in emoticons.smile_to_html("hi :)", "default/smileys.cfg"))

# The theme factory wires the option through to the message body.
factory = ChatThemeFactory()
factory.set_emoticon_skin(emoticons.UNICODE_SKIN)
factory.set_unicode_smiley_replace(True)
html = factory._body_fragment("hi :)")
check("the factory substitutes in unicode mode", "🙂" in html)
factory.set_unicode_smiley_replace(False)
check("the factory keeps plain text when off",
      "🙂" not in factory._body_fragment("hi :)"))

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All unicode-smiley tests passed.")
