"""Offscreen tests for the optional pyenchant spell checker.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_spellcheck.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_spell_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtGui, QtWidgets  # noqa: E402

from stanza_im.core.storage import Config  # noqa: E402
from stanza_im.ui import spellcheck  # noqa: E402
from stanza_im.ui.chat_widget import _ChatInput  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


class FakeDict:
    def __init__(self, accepted=(), suggestions=None):
        self.accepted = set(accepted)
        self.suggestions = list(suggestions or ())
        self.checked = []
        self.personal = []

    def check(self, word):
        self.checked.append(word)
        return word in self.accepted

    def suggest(self, word):
        return list(self.suggestions)

    def add_to_personal(self, word):
        self.personal.append(word)
        self.accepted.add(word)
        return True


# 1. tokenization and ignored regions ---------------------------------------
text = ("привет hello helo http://example.com/a @nick #tag /me "
        "mail@example.com 123 abc_def")
words = [word for word, _start, _end in spellcheck.iter_words(text)]
check("URLs, e-mail, mentions, commands and ids are not words",
      "example" not in words and "nick" not in words and "tag" not in words
      and "mail" not in words and "123" not in words and "abc_def" not in words)
span = spellcheck.word_span_at("hello wrld", 7)
check("word_at finds a token and its offsets", span == ("wrld", 6, 10))


# 2. a missing script dictionary does not underline that script -------------
en = FakeDict({"hello"})
service_en = spellcheck.SpellCheckService(["en_US"], [en])
missed = [word for word, _s, _e in spellcheck.iter_misspelled(
    "привет hello helo", service_en)]
check("Cyrillic is skipped when only an English dictionary exists",
      missed == ["helo"])
check("the skipped Cyrillic word never reaches the dictionary",
      "привет" not in en.checked)


# 3. multiple dictionaries and suggestions ----------------------------------
ru = FakeDict({"привет"}, ["привет"])
service_multi = spellcheck.SpellCheckService(
    ["ru_RU", "en_US"], [ru, en])
missed = [word for word, _s, _e in spellcheck.iter_misspelled(
    "привет превет hello helo", service_multi)]
check("a word is accepted by any active dictionary",
      "привет" not in missed and "hello" not in missed)
check("misspellings in either script are found",
      missed == ["превет", "helo"])
suggestions = service_multi.suggest("превет")
check("suggestions are merged", "привет" in suggestions)


# 4. personal dictionary and highlighter formatting ------------------------
check("add_to_personal reaches every active dictionary",
      service_multi.add_to_personal("превет")
      and ru.personal == ["превет"] and en.personal == ["превет"])

doc = QtGui.QTextDocument()
highlighter = spellcheck.SpellCheckHighlighter(doc, service_en)
doc.setPlainText("hello helo")
highlighter.rehighlight()
app.processEvents()
formats = doc.findBlockByNumber(0).layout().formats()
check("the misspelled word is highlighted",
      len(formats) == 1 and formats[0].start == 6
      and formats[0].length == 4)
fmt = formats[0].format
check("the underline is the red spell-check wave",
      fmt.underlineStyle()
      == QtGui.QTextCharFormat.UnderlineStyle.SpellCheckUnderline
      and fmt.underlineColor().name() == spellcheck.UNDERLINE_COLOR)
highlighter.set_service(None)
app.processEvents()
check("disabling the service clears the marks",
      not doc.findBlockByNumber(0).layout().formats())


# 5. input replacement keeps the rest of the text ---------------------------
editor = _ChatInput()
editor.set_spellcheck(service_en)
editor.setPlainText("hello helo")
editor._replace_spelling(6, 10, "hello")
check("a suggestion replaces only the misspelled token",
      editor.toPlainText() == "hello hello")


# 5b. automatic and explicit language resolution ----------------------------
from unittest.mock import patch  # noqa: E402

with patch.object(spellcheck, "languages",
                  return_value=["de_DE", "en_US", "ru_RU"]):
    auto = spellcheck.resolve_languages([], "ru", "ru_RU")
    explicit = spellcheck.resolve_languages(["de", "ru"], "ru", "ru_RU")
check("auto languages are locale + English without duplicates",
      auto == ["ru_RU", "en_US"])
check("explicit languages resolve to installed tags",
      explicit == ["de_DE", "ru_RU"])

# 6. defaults and optional availability -------------------------------------
cfg = Config()
check("spell checking is enabled by default", cfg.chat.spellcheck_enabled)
check("the default language list is automatic", cfg.chat.spellcheck_languages == [])
if not spellcheck.module_available():
    check("without pyenchant the service is unavailable",
          not spellcheck.available()
          and spellcheck.SpellCheckService.from_tags(["en_US"]) is None)
else:
    check("with pyenchant installed the service can be created",
          spellcheck.SpellCheckService.from_tags(["en_US"]) is not None)


if FAILURES:
    print("\n%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll spell-check tests passed.")
