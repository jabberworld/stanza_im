"""Tests for the chat smiley picker (emoticon-set source + popup).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_smiley_picker.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_smiley_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.include import emoticons
from stanza_im.ui.smiley_picker import (
    EmoticonSetSource, SmileyPicker, UnicodeEmojiSource)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

# 1. the emoticon-set helper returns ordered (code, path) pairs ----------------
sets = emoticons.discover_sets()
check("at least one emoticon set is bundled", bool(sets))
check("the default set is bundled",
      any(s["id"] == "default/smileys.cfg" for s in sets))
skin = "default/smileys.cfg"
items = emoticons.set_items(skin)
check("set_items returns pairs", bool(items) and all(
    isinstance(c, str) and isinstance(p, str) for c, p in items))
check("set_items paths exist", all(os.path.isfile(p) for _c, p in items))
# One row per distinct image: aliases like ":)" and ":-)" share the file.
_paths = [p for _c, p in items]
check("set_items has no duplicate images", len(_paths) == len(set(_paths)))
_by_file = {os.path.basename(p): c for c, p in items}
check("the longest alias is kept for a shared image",
      _by_file.get("smile16.png") == ":-)"
      and _by_file.get("wink16.png") == ";-)")


def _longest(mapping):
    best = {}
    for code, fn in mapping.items():
        if fn not in best or len(code) > len(best[fn]):
            best[fn] = code
    return best


_item = emoticons.get_set(skin)
check("preview_items also de-duplicates",
      len(emoticons.preview_items(skin, 10))
      == min(10, len(_longest(_item["mapping"]))))

# 2. the source turns them into (token, icon) entries --------------------------
source = EmoticonSetSource(skin)
entries = source.entries()
check("EmoticonSetSource yields entries", bool(entries))
check("entry tokens are the plain-text codes",
      all(isinstance(tok, str) and tok for tok, _ic in entries))
check("entry icons are non-null", all(not ic.isNull() for _t, ic in entries))

# 3. the placeholder unicode source is safe ------------------------------------
check("UnicodeEmojiSource is a no-op for now",
      UnicodeEmojiSource().entries() == [])

# 4. the picker builds a button per entry and emits the chosen token -----------
picker = SmileyPicker(source, None)
chosen = []
picker.smiley_chosen.connect(chosen.append)
buttons = picker.findChildren(QtWidgets.QToolButton)
check("one button per smiley", len(buttons) == len(entries))
check("buttons carry the code as tooltip",
      all(b.toolTip() for b in buttons))
picker._choose(entries[0][0])
check("choosing emits the token", chosen == [entries[0][0]])
picker.close()

# 5. ChatWidget wires the button and inserts the code as plain text ------------
import inspect
from stanza_im.ui import chat_widget as cw

src = inspect.getsource(cw)
check("the toolbar adds a smiley button",
      "_smiley_btn" in src and "smiley.svg" in src)
check("the picker is opened from the button",
      "_open_smiley_picker" in src)
check("the picked code is inserted into the input",
      "insertPlainText(token)" in src)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All smiley-picker tests passed.")
