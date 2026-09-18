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


def load(lang: str | None = None) -> None:
    """Load translation strings for *lang* (default: auto-detect)."""
    global _current, _lang
    lang = lang or _detect_language()
    try:
        mod = importlib.import_module(f"stanza_im.i18n.{lang}")
        _current = mod.STRINGS
        _lang = lang
    except (ModuleNotFoundError, AttributeError):
        try:
            mod = importlib.import_module("stanza_im.i18n.en")
            _current = mod.STRINGS
            _lang = "en"
        except (ModuleNotFoundError, AttributeError):
            _current = {}
            _lang = "en"


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
