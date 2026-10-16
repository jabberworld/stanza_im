"""Offscreen tests for the unicode-emoji smiley theme.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_smiley_unicode.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_smiley_unicode_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.include import emoji_data, emoticons
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui import smiley_picker
from stanza_im.ui.chat_widget import ChatWidget

i18n_load("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# The pseudo-skin must never fall back to the default set (that would replace
# text codes with images), so every lookup is empty.
check("unicode skin is a named constant", emoticons.UNICODE_SKIN == "unicode")
check("unicode skin has no set", emoticons.get_set(emoticons.UNICODE_SKIN) is None)
check("unicode skin has no picker items",
      emoticons.set_items(emoticons.UNICODE_SKIN) == [])
check("unicode skin has no preview",
      emoticons.preview_items(emoticons.UNICODE_SKIN) == [])
check("unicode skin does not substitute text codes",
      emoticons.smile_to_html(":-)", emoticons.UNICODE_SKIN) == ":-)")

# The placeholder source is gone (the reaction picker is reused instead).
check("UnicodeEmojiSource was removed",
      not hasattr(smiley_picker, "UnicodeEmojiSource"))

# The catalogue the reused reaction picker draws from is non-empty.
check("the emoji catalogue is available", len(emoji_data.all_emoji()) > 50)

# The unicode smiley skin opens the reaction-style emoji picker (through the
# main window), while a normal theme still uses the image grid popup.
cw = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
requests = []
cw.emoji_picker_requested.connect(lambda x, y: requests.append((x, y)))

cw._theme.set_emoticon_skin(emoticons.UNICODE_SKIN)
cw._open_smiley_picker()
check("unicode skin requests the emoji picker", len(requests) == 1)

cw._theme.set_emoticon_skin("")
cw._open_smiley_picker()
check("a theme skin does not request the emoji picker", len(requests) == 1)

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All smiley-unicode tests passed.")
