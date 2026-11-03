"""Optional pyenchant-based spell checking for the chat input.

The module deliberately imports ``enchant`` only when the feature is enabled
or the preferences page asks for the available languages.  Without the
optional dependency, ``libenchant`` or any installed dictionary the rest of
the client keeps working unchanged.
"""
from __future__ import annotations

import importlib.util
import logging
import re
import threading

from PyQt6 import QtCore, QtGui

logger = logging.getLogger(__name__)

UNDERLINE_COLOR = "#e53935"

# Words are Unicode word characters with optional apostrophes/hyphens inside.
# Tokens containing digits or underscores are skipped later: a code fragment
# or an ID is never a spelling error.
_WORD_RE = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)

# Regions which must never produce spell-check marks.  Each substitution keeps
# the original length so token offsets still point into the original text.
_IGNORED_RE = (
    re.compile(r"(?:(?:https?|ftp|aesgcm|xmpp|geo):)[^\s<>\"']+", re.I),
    re.compile(r"\bwww\.[^\s<>\"']+", re.I),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?<!\w)[@#][^\s,.;:!?()\[\]{}]+"),
    re.compile(r"(?<![\w/])/[A-Za-z][^\s]*"),
)

# Script ranges for the common languages whose dictionaries are installed by
# distro packages.  A language tag is mapped to its script; a word is checked
# only when every script in it is covered by an active dictionary.
_SCRIPT_RANGES = (
    ("Latin", ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F),
               (0x1E00, 0x1EFF))),
    ("Cyrillic", ((0x0400, 0x052F), (0x1C80, 0x1C8F), (0x2DE0, 0x2DFF),
                  (0xA640, 0xA69F))),
    ("Greek", ((0x0370, 0x03FF), (0x1F00, 0x1FFF))),
    ("Hebrew", ((0x0590, 0x05FF),)),
    ("Arabic", ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
                (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    ("Devanagari", ((0x0900, 0x097F),)),
    ("Thai", ((0x0E00, 0x0E7F),)),
    ("Han", ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
             (0x20000, 0x2FA1F))),
    ("Hiragana", ((0x3040, 0x309F),)),
    ("Katakana", ((0x30A0, 0x30FF),)),
    ("Hangul", ((0x1100, 0x11FF), (0xAC00, 0xD7AF))),
)

_LATIN_LANGS = {
    "af", "ca", "cs", "cy", "da", "de", "en", "es", "et", "eu", "fi", "fr",
    "ga", "gl", "hr", "hu", "id", "is", "it", "lb", "lt", "lv", "ms", "mt",
    "nb", "nl", "nn", "no", "pl", "pt", "ro", "sk", "sl", "sq", "sv", "sw",
    "tr", "vi",
}
_CYRILLIC_LANGS = {"be", "bg", "kk", "ky", "mk", "mn", "ru", "sr", "tg", "uk"}
_ARABIC_LANGS = {"ar", "fa", "ps", "sd", "ug", "ur"}
_DEVANAGARI_LANGS = {"hi", "mr", "ne", "sa"}


def module_available() -> bool:
    """Whether the optional Python binding is installed at all."""
    return importlib.util.find_spec("enchant") is not None


def _enchant():
    import enchant  # noqa: PLC0415 - optional dependency, loaded lazily
    return enchant


def available() -> bool:
    """Whether pyenchant and at least one system dictionary are usable."""
    if not module_available():
        return False
    try:
        return bool(_enchant().list_languages())
    except Exception as exc:  # noqa: BLE001 - missing libenchant etc.
        logger.debug("pyenchant is unavailable: %s", exc)
        return False


def languages() -> list[str]:
    """Installed enchant dictionary tags, sorted for the preferences UI."""
    if not module_available():
        return []
    try:
        return sorted(set(_enchant().list_languages()))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not list enchant dictionaries: %s", exc)
        return []


def language_name(tag: str) -> str:
    """A readable label for an enchant tag (``ru_RU`` -> ``русский``)."""
    code = str(tag or "").replace("-", "_")
    try:
        from PyQt6 import QtCore as _QtCore
        name = _QtCore.QLocale(code).nativeLanguageName()
    except Exception:  # noqa: BLE001
        name = ""
    return (name or tag).strip() or tag


def _script_of_char(ch: str) -> str:
    code = ord(ch)
    for name, ranges in _SCRIPT_RANGES:
        for low, high in ranges:
            if low <= code <= high:
                return name
    return ""


def scripts_of_word(word: str) -> set[str]:
    """Every script used by the letters of *word* (empty for unknown)."""
    return {script for ch in word if ch.isalpha()
            for script in (_script_of_char(ch),) if script}


def script_for_tag(tag: str) -> str:
    """The script a language tag normally uses (empty when unknown)."""
    base = str(tag or "").replace("-", "_").split("_", 1)[0].lower()
    if base in _CYRILLIC_LANGS:
        return "Cyrillic"
    if base in _ARABIC_LANGS:
        return "Arabic"
    if base in _DEVANAGARI_LANGS:
        return "Devanagari"
    if base in _LATIN_LANGS:
        return "Latin"
    return {
        "el": "Greek",
        "he": "Hebrew",
        "yi": "Hebrew",
        "th": "Thai",
        "zh": "Han",
        "ja": "Han",
        "ko": "Hangul",
    }.get(base, "")


def _tags_for(base: str, tags: list[str]) -> list[str]:
    """Resolve a short language code to installed enchant tags."""
    base = str(base or "").replace("-", "_").split("_", 1)[0].lower()
    if not base:
        return []
    exact = [tag for tag in tags
             if tag.lower() == base or tag.lower().startswith(base + "_")]
    if exact:
        # Prefer a country variant over the bare tag, but keep availability
        # order stable for the rest.
        exact.sort(key=lambda tag: (0 if "_" in tag else 1, tags.index(tag)))
        return exact[:1]
    return [tag for tag in tags
            if tag.replace("-", "_").split("_", 1)[0].lower() == base][:1]


def resolve_languages(selected=None, ui_language: str = "",
                      system_language: str = "") -> list[str]:
    """Return installed tags for *selected*, or the auto locale + English list."""
    tags = languages()
    if not tags:
        return []
    wanted = [str(tag) for tag in (selected or []) if str(tag)]
    if not wanted:
        wanted = [ui_language, system_language, "en"]
    out: list[str] = []
    for code in wanted:
        match = _tags_for(code, tags)
        if match and match[0] not in out:
            out.append(match[0])
    return out


def mask_ignored(text: str) -> str:
    """Replace URLs, e-mail, mentions and commands with equal-length spaces."""
    masked = str(text or "")
    for pattern in _IGNORED_RE:
        masked = pattern.sub(lambda match: " " * len(match.group(0)), masked)
    return masked


def iter_words(text: str):
    """Yield ``(word, start, end)`` for spell-checkable word spans."""
    masked = mask_ignored(text)
    for match in _WORD_RE.finditer(masked):
        word = text[match.start():match.end()]
        if any(ch.isdigit() or ch == "_" for ch in word):
            continue
        yield word, match.start(), match.end()


def iter_misspelled(text: str, service: SpellCheckService | None):
    """Yield ``(word, start, end)`` for words rejected by the service."""
    if service is None:
        return
    for word, start, end in iter_words(text):
        if not service.check(word):
            yield word, start, end


def word_span_at(text: str, position: int):
    """Return ``(word, start, end)`` at a cursor position, else ``None``."""
    text = str(text or "")
    try:
        position = max(0, int(position))
    except (TypeError, ValueError):
        return None
    for word, start, end in iter_words(text):
        if start < position <= end or start <= position < end:
            return word, start, end
    return None


class SpellCheckService:
    """A small facade over one or more pyenchant dictionaries."""

    def __init__(self, tags: list[str], dictionaries: list):
        self.tags = list(tags)
        self._dicts = list(dictionaries)
        self._covered = {script_for_tag(tag) for tag in self.tags}
        self._covered.discard("")
        self._check_cache: dict[str, bool] = {}
        self._suggest_cache: dict[str, list[str]] = {}

    @classmethod
    def from_tags(cls, tags: list[str]):
        """Build a service, or return ``None`` when no dictionary opened."""
        tags = list(tags or [])
        if not tags or not module_available():
            return None
        try:
            enchant = _enchant()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not import pyenchant: %s", exc)
            return None
        dictionaries = []
        opened = []
        for tag in tags:
            try:
                dictionaries.append(enchant.Dict(tag))
                opened.append(tag)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Could not open spell dictionary %s: %s", tag, exc)
        if not dictionaries:
            return None
        return cls(opened, dictionaries)

    @property
    def covered_scripts(self) -> set[str]:
        return set(self._covered)

    def should_check(self, word: str) -> bool:
        """Whether *word* belongs to a script with an active dictionary."""
        scripts = scripts_of_word(word)
        return bool(scripts) and scripts.issubset(self._covered)

    def check(self, word: str) -> bool:
        """True when any active dictionary accepts *word*."""
        if not self.should_check(word):
            return True
        if word in self._check_cache:
            return self._check_cache[word]
        result = False
        for dictionary in self._dicts:
            try:
                if dictionary.check(word):
                    result = True
                    break
            except Exception as exc:  # noqa: BLE001
                logger.debug("Spell check failed for %r: %s", word, exc)
        self._check_cache[word] = result
        return result

    def suggest(self, word: str, limit: int = 8) -> list[str]:
        """Merged suggestions from every active dictionary."""
        if not self.should_check(word):
            return []
        cached = self._suggest_cache.get(word)
        if cached is not None:
            return list(cached)
        out: list[str] = []
        seen: set[str] = set()
        for dictionary in self._dicts:
            try:
                for item in dictionary.suggest(word):
                    if item and item not in seen:
                        seen.add(item)
                        out.append(item)
                        if len(out) >= limit:
                            break
            except Exception as exc:  # noqa: BLE001
                logger.debug("Spell suggestions failed for %r: %s", word, exc)
            if len(out) >= limit:
                break
        self._suggest_cache[word] = out
        return list(out)

    def add_to_personal(self, word: str) -> bool:
        """Add *word* to the personal word list of every active dictionary."""
        word = str(word or "").strip()
        if not word:
            return False
        added = False
        for dictionary in self._dicts:
            try:
                if dictionary.add_to_personal(word):
                    added = True
            except Exception as exc:  # noqa: BLE001
                logger.debug("Could not add %r to a personal dictionary: %s",
                             word, exc)
        if added:
            self._check_cache.clear()
            self._suggest_cache.clear()
        return added


class SpellCheckHighlighter(QtGui.QSyntaxHighlighter):
    """Red wavy underline for words unknown to the active dictionaries."""

    def __init__(self, document, service: SpellCheckService | None = None):
        super().__init__(document)
        self._service = service
        self._format = QtGui.QTextCharFormat()
        self._format.setUnderlineStyle(
            QtGui.QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        self._format.setUnderlineColor(QtGui.QColor(UNDERLINE_COLOR))

    def set_service(self, service: SpellCheckService | None) -> None:
        self._service = service
        self.rehighlight()

    def service(self) -> SpellCheckService | None:
        return self._service

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        service = self._service
        if service is None:
            return
        for word, start, end in iter_words(text):
            if service.check(word):
                continue
            self.setFormat(start, end - start, self._format)


class SpellCheckLoader(QtCore.QObject):
    """Load dictionaries off the GUI thread and deliver them via a signal."""

    ready = QtCore.pyqtSignal(int, object, object)  # request, service, tags

    def load(self, request: int, selected=None, ui_language: str = "",
             system_language: str = "") -> None:
        selected = list(selected or [])
        thread = threading.Thread(
            target=self._run,
            args=(int(request), selected, str(ui_language or ""),
                  str(system_language or "")),
            daemon=True,
        )
        thread.start()

    def _run(self, request: int, selected: list[str], ui_language: str,
             system_language: str) -> None:
        tags = resolve_languages(
            selected, ui_language=ui_language,
            system_language=system_language)
        service = SpellCheckService.from_tags(tags)
        try:
            self.ready.emit(int(request), service, tags)
        except RuntimeError:
            # The main window may have been closed while the dictionaries
            # were loading.
            pass


def misspelled_at(text: str, position: int,
                  service: SpellCheckService | None):
    """Return ``(word, start, end)`` for a misspelled word at *position*."""
    if service is None:
        return None
    span = word_span_at(text, position)
    if span is None:
        return None
    word, start, end = span
    if not service.should_check(word) or service.check(word):
        return None
    return word, start, end
