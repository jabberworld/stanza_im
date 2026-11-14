"""Ukrainian translation parity and loading checks.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_i18n_uk.py
"""
import importlib.util
import os
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.i18n import (
    available_languages, current_language, en, load as i18n_load, ru, uk,
)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def fields(value):
    return {
        (field, format_spec, conversion)
        for _, field, format_spec, conversion
        in string.Formatter().parse(str(value))
        if field
    }


def plugin_strings(plugin, lang):
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "stanza_im", "plugins", plugin, "strings", f"{lang}.py")
    spec = importlib.util.spec_from_file_location(
        f"_stanza_test_{plugin}_{lang}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.STRINGS


check("Ukrainian language name is native", uk.LANGUAGE_NAME == "Українська")
check("Ukrainian dictionary has every English key",
      set(uk.STRINGS) == set(en.STRINGS))
check("Ukrainian dictionary has every Russian key",
      set(uk.STRINGS) == set(ru.STRINGS))
check("Ukrainian dictionary is complete",
      len(uk.STRINGS) == 1785)
check("only the gateway default string is empty",
      [key for key, value in uk.STRINGS.items() if value == ""]
      == ["add_contact_gateway_default"])

for key, value in en.STRINGS.items():
    if fields(value) != fields(uk.STRINGS[key]):
        check(f"placeholder fields match: {key}", False)
        break
else:
    check("every placeholder and format spec matches", True)

for key, value in en.STRINGS.items():
    if "&" in str(value) and "&" not in str(uk.STRINGS[key]):
        check(f"menu mnemonic preserved: {key}", False)
        break
else:
    check("every menu mnemonic is preserved", True)

for key, value in en.STRINGS.items():
    if "\n" in str(value) and "\n" not in str(uk.STRINGS[key]):
        check(f"newline preserved: {key}", False)
        break
else:
    check("every multiline string keeps its newline", True)

for plugin in ("notes", "attention", "digest"):
    en_strings = plugin_strings(plugin, "en")
    ru_strings = plugin_strings(plugin, "ru")
    uk_strings = plugin_strings(plugin, "uk")
    check(f"{plugin}: uk has the en keys",
          set(uk_strings) == set(en_strings))
    check(f"{plugin}: uk has the ru keys",
          set(uk_strings) == set(ru_strings))
    for key, value in en_strings.items():
        if fields(value) != fields(uk_strings[key]):
            check(f"{plugin}: placeholder fields match: {key}", False)
            break
    else:
        check(f"{plugin}: every placeholder matches", True)

languages = dict(available_languages())
check("Ukrainian is listed with its native name",
      languages.get("uk") == "Українська")

old_lang = os.environ.get("LANG")
old_language = os.environ.get("LANGUAGE")
os.environ["LANG"] = "uk_UA.UTF-8"
try:
    from stanza_im import i18n
    check("LANG=uk_UA auto-detects Ukrainian",
          i18n._detect_language() == "uk")
finally:
    if old_lang is None:
        os.environ.pop("LANG", None)
    else:
        os.environ["LANG"] = old_lang
    if old_language is None:
        os.environ.pop("LANGUAGE", None)
    else:
        os.environ["LANGUAGE"] = old_language

i18n_load("uk")
check("Ukrainian loads", current_language() == "uk")
check("core strings translate",
      i18n.tr("status_online") == "У мережі"
      and i18n.tr("chat_send") == "Надіслати")
check("placeholders format in Ukrainian",
      i18n.tr("status_changed", status="У мережі")
      == "Статус змінено: У мережі")
check("plugin strings are merged",
      i18n.tr("notes_open") == "Відкрити"
      and i18n.tr("plugin_category_tools") == "Інструменти"
      and i18n.tr("attention_menu") == "Привернути увагу")

merged = {}
for lang in ("en", "ru", "uk"):
    i18n_load(lang)
    merged[lang] = set(i18n._current)
check("merged en/ru/uk dictionaries have the same keys",
      merged["en"] == merged["ru"] == merged["uk"])
i18n_load("en")

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All Ukrainian translation tests passed")
