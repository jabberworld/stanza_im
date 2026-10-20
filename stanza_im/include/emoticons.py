"""Discover and render emoticon sets described by ``smileys*.cfg`` files."""
from __future__ import annotations

import base64
import os
import re

from stanza_im.include.constants import EMOTICONS_DIR

_LINE_RE = re.compile(r"'(.+)'='(.+)'\s*$")
_SETS: dict[str, dict] | None = None
_MAP_CACHE: dict[str, dict[str, str]] = {}

#: Pseudo-skin selecting the unicode-emoji picker instead of a ``smileys*.cfg``
#: set.  It must never fall back to the default set (that would replace text
#: codes with images), so every lookup treats it as an empty mapping.
UNICODE_SKIN = "unicode"

#: Pseudo-skin turning smiley rendering off entirely (no images and no unicode
#: replacement).  Like :data:`UNICODE_SKIN` it must never fall back to the
#: default set, so every lookup treats it as an empty mapping.
NO_SKIN = "none"

#: Prefix of the removed ``resources/emoticons/none`` set; old configs stored
#: ``none/smileys.cfg`` for "off", which now maps to :data:`NO_SKIN`.
_LEGACY_OFF_PREFIX = "none/"


def normalize_skin(skin: str) -> str:
    """Map the legacy ``none/…`` set ids to :data:`NO_SKIN`."""
    if skin == NO_SKIN or skin.startswith(_LEGACY_OFF_PREFIX):
        return NO_SKIN
    return skin


def _data_uri(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")
    except OSError:
        return None


def _header_value(lines: list[str], key: str) -> str:
    prefix = f"'{key}'="
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip("'")
    return ""


def _parse_cfg(path: str, skin: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [line.strip() for line in fh]
    except OSError:
        lines = []
    header = lines[:lines.index("[emoticons]")] if "[emoticons]" in lines else lines
    name = _header_value(header, "name") or skin
    mapping = {}
    active = False
    for line in lines:
        if line == "[emoticons]":
            active = True
            continue
        if active and line.startswith("["):
            break
        if active:
            match = _LINE_RE.match(line)
            if match:
                mapping.setdefault(match.group(1), match.group(2))
    return {"id": f"{skin}/{os.path.basename(path)}", "name": name,
            "directory": os.path.dirname(path), "mapping": mapping,
            "front_image": _header_value(header, "frontImage")}


def discover_sets() -> list[dict]:
    global _SETS
    if _SETS is None:
        _SETS = {}
        for root, _dirs, files in os.walk(EMOTICONS_DIR):
            for filename in sorted(files):
                if filename.startswith("smileys") and filename.endswith(".cfg"):
                    skin = os.path.relpath(root, EMOTICONS_DIR)
                    item = _parse_cfg(os.path.join(root, filename), skin)
                    if normalize_skin(item["id"]) == NO_SKIN:
                        continue
                    _SETS[item["id"]] = item
    return list(_SETS.values())


def get_set(skin: str) -> dict | None:
    skin = normalize_skin(skin)
    if skin in (UNICODE_SKIN, NO_SKIN):
        return None
    sets = {item["id"]: item for item in discover_sets()}
    if skin in sets:
        return sets[skin]
    return next((item for item in sets.values() if item["id"].startswith("default/")), None)


def _load_map(skin: str) -> dict[str, str]:
    skin = normalize_skin(skin)
    if skin in _MAP_CACHE:
        return _MAP_CACHE[skin]
    if skin in (UNICODE_SKIN, NO_SKIN):
        _MAP_CACHE[skin] = {}
        return {}
    item = get_set(skin)
    resolved = {}
    if item:
        for code, filename in item["mapping"].items():
            uri = _data_uri(os.path.join(item["directory"], filename))
            if uri:
                resolved[code] = uri
    _MAP_CACHE[skin] = resolved
    return resolved


#: Unicode emoji for each default-set image, keyed by its file name.  Used to
#: turn a text smiley (``:)``, ``:-D``, ``(K)`` …) into the matching emoji when
#: the ``unicode`` skin is active.  The map is derived from the ``default``
#: theme's semantics (one emoji per image).
_UNICODE_BY_FILE = {
    "devil16.png": "😈", "smile16.png": "🙂", "coolglasses16.png": "😎",
    "wink16.png": "😉", "biggrin16.png": "😁", "unhappy16.png": "🙁",
    "cry16.png": "😢", "frowning16.png": "😕", "blush16.png": "😊",
    "angry16.png": "😠", "bat16.png": "🦇", "kiss16.png": "😘",
    "stare16.png": "😐", "tongue16.png": "😛", "oh16.png": "😮",
    "heart16.png": "❤️", "pussy16.png": "🐱", "cuffs16.png": "⛓️",
    "moon16.png": "🌙", "lamp16.png": "💡", "music16.png": "🎵",
    "beer16.png": "🍺", "brflower16.png": "🌷", "boy16.png": "👦",
    "girl16.png": "👧", "mail16.png": "✉️", "thumbdown16.png": "👎",
    "photo16.png": "📷", "thumbup16.png": "👍", "hugleft16.png": "🤗",
    "brheart16.png": "💔", "flower16.png": "🌸", "drink16.png": "🍸",
    "phone16.png": "📞", "coffee16.png": "☕", "hugright16.png": "🤗",
    "star16.png": "⭐", "rainbow16.png": "🌈",
}

_UNICODE_MAP_CACHE: dict[str, str] | None = None


def unicode_map() -> dict[str, str]:
    """``{text code: unicode emoji}`` derived from the default theme.

    Every text alias of an image maps to that image's emoji, so ``:)`` and
    ``:-)`` both become 🙂.
    """
    global _UNICODE_MAP_CACHE
    if _UNICODE_MAP_CACHE is not None:
        return _UNICODE_MAP_CACHE
    item = get_set("default/smileys.cfg")
    result: dict[str, str] = {}
    if item:
        for code, filename in item["mapping"].items():
            emoji = _UNICODE_BY_FILE.get(filename)
            if emoji:
                result.setdefault(code, emoji)
    _UNICODE_MAP_CACHE = result
    return result


def _code_pattern(mapping: dict[str, str]) -> "re.Pattern[str]":
    """A regex matching any text code of *mapping* (longest codes first)."""
    return re.compile("|".join(re.escape(code)
                               for code in sorted(mapping, key=len, reverse=True)))


def _boundary_ok(text: str, start: int, end: int) -> bool:
    """True when the code at ``text[start:end]`` is not glued to a word.

    A smiley is only converted when it is not directly adjacent to a letter or
    digit (any script), so ``200:/bla`` and ``Привет:)`` stay intact while
    ``:):):)`` and ``:).`` convert.
    """
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return not (before.isalnum() or after.isalnum())


def _sub_guarded(pattern: "re.Pattern[str]", render, text: str) -> str:
    """Replace every match that is *not* adjacent to a letter/digit."""
    return pattern.sub(
        lambda match: (render(match.group(0))
                       if _boundary_ok(text, match.start(), match.end())
                       else match.group(0)), text)


def _replace_with_unicode(text: str) -> str:
    mapping = unicode_map()
    if not mapping:
        return text
    return _sub_guarded(_code_pattern(mapping), mapping.__getitem__, text)


def _file_codes(mapping: dict[str, str]) -> dict[str, str]:
    """Map each target image file to a single (longest) text code.

    Several text aliases (``:)`` and ``:-)``) usually point at the same image;
    a picker/preview list keyed by the code would then show that image once per
    alias.  Keying by the file and keeping the longest alias collapses them to
    one row while still rendering every alias in the message text.
    """
    result: dict[str, str] = {}
    for code, filename in mapping.items():
        current = result.get(filename)
        if current is None or len(code) > len(current):
            result[filename] = code
    return result


def preview_items(skin: str, limit: int = 10) -> list[tuple[str, str]]:
    """Up to *limit* ``(code, image_path)`` pairs, one per distinct image."""
    item = get_set(skin)
    if not item:
        return []
    result = []
    for filename, code in _file_codes(item["mapping"]).items():
        if len(result) >= limit:
            break
        path = os.path.join(item["directory"], filename)
        if os.path.isfile(path):
            result.append((code, path))
    return result


def set_items(skin: str) -> list[tuple[str, str]]:
    """Every ``(code, image_path)`` pair of a set, one per distinct image."""
    item = get_set(skin)
    if not item:
        return []
    result: list[tuple[str, str]] = []
    for filename, code in _file_codes(item["mapping"]).items():
        path = os.path.join(item["directory"], filename)
        if os.path.isfile(path):
            result.append((code, path))
    return result


def emoticon_codes(skin: str = "default/smileys.cfg") -> list[str]:
    return sorted(_load_map(skin), key=len, reverse=True)


def smile_to_html(text: str, skin: str = "default/smileys.cfg",
                  unicode_replace: bool = False) -> str:
    skin = normalize_skin(skin)
    if skin == NO_SKIN:
        return text
    if skin == UNICODE_SKIN:
        # No image set: optionally replace the text codes with unicode emoji.
        return _replace_with_unicode(text) if unicode_replace else text
    mapping = _load_map(skin)
    if not mapping:
        return text
    return _sub_guarded(
        _code_pattern(mapping),
        lambda code: (f'<img src="{mapping[code]}" alt="{code}" '
                      'style="vertical-align:middle" width="16" height="16">'),
        text)


def clear_cache() -> None:
    global _SETS
    _SETS = None
    _MAP_CACHE.clear()
