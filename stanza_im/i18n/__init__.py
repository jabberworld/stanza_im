"""Lightweight translation system using plain Python dicts."""
from __future__ import annotations

import importlib
import locale
import os

_current: dict[str, str] = {}
_lang: str = "en"


def _detect_language() -> str:
    """Best-effort detection of the system language."""
    lang_env = os.environ.get("LANG", os.environ.get("LANGUAGE", ""))
    if not lang_env:
        try:
            lang_env = locale.getlocale()[0] or ""
        except Exception:
            lang_env = ""
    short = lang_env.split(".")[0].split("_")[0].lower()
    return short or "en"


def current_language() -> str:
    """Return the short code of the loaded language (e.g. ``"ru"``)."""
    return _lang


def _plugin_strings(lang: str) -> dict[str, str]:
    """Merge every plugin's ``strings/<lang>.py`` STRINGS dict.

    Plugins keep their own UI strings next to their code.  A broken or missing
    file is skipped so one plugin can never break language loading.
    """
    merged: dict[str, str] = {}
    folder = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "plugins")
    try:
        entries = sorted(os.listdir(folder))
    except OSError:
        return merged
    for name in entries:
        if name.startswith(("_", ".")):
            continue
        module = f"stanza_im.plugins.{name}.strings.{lang}"
        try:
            mod = importlib.import_module(module)
        except (ModuleNotFoundError, AttributeError, ImportError):
            continue
        strings = getattr(mod, "STRINGS", None)
        if isinstance(strings, dict):
            merged.update(strings)
    return merged


def load(lang: str | None = None) -> None:
    """Load translation strings for *lang* (default: auto-detect)."""
    global _current, _lang
    lang = lang or _detect_language()
    try:
        mod = importlib.import_module(f"stanza_im.i18n.{lang}")
        strings = dict(mod.STRINGS)
        _lang = lang
    except (ModuleNotFoundError, AttributeError):
        try:
            mod = importlib.import_module("stanza_im.i18n.en")
            strings = dict(mod.STRINGS)
            _lang = "en"
        except (ModuleNotFoundError, AttributeError):
            strings = {}
            _lang = "en"
    # Plugin strings are merged on top of the core ones (a plugin may not
    # override core keys, so core wins on a collision).
    for key, value in _plugin_strings(_lang).items():
        strings.setdefault(key, value)
    _current = strings


def available_languages() -> list[tuple[str, str]]:
    """Return ``(code, native_name)`` for every packaged translation.

    Discovered from the ``stanza_im/i18n/*.py`` modules so a new language file
    shows up automatically.  The native name is read from the module's
    ``LANGUAGE_NAME`` when present, else the upper-cased code.
    """
    import os
    folder = os.path.dirname(__file__)
    out: list[tuple[str, str]] = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        code = name[:-3]
        native = code.upper()
        try:
            mod = importlib.import_module(f"stanza_im.i18n.{code}")
            native = getattr(mod, "LANGUAGE_NAME", native)
        except (ModuleNotFoundError, AttributeError):
            continue
        out.append((code, native))
    return out


def tr(key: str, **kwargs) -> str:
    """Translate *key*, optionally formatting with *kwargs*.

    Falls back to the key itself when no translation is found.
    """
    template = _current.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template
