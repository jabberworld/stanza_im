"""Discover and render emoticon sets described by ``smileys*.cfg`` files."""
from __future__ import annotations

import base64
import os
import re

from jabbim.include.constants import EMOTICONS_DIR

_LINE_RE = re.compile(r"'(.+)'='(.+)'\s*$")
_SETS: dict[str, dict] | None = None
_MAP_CACHE: dict[str, dict[str, str]] = {}


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
                    _SETS[item["id"]] = item
    return list(_SETS.values())


def get_set(skin: str) -> dict | None:
    sets = {item["id"]: item for item in discover_sets()}
    if skin in sets:
        return sets[skin]
    return next((item for item in sets.values() if item["id"].startswith("default/")), None)


def _load_map(skin: str) -> dict[str, str]:
    if skin in _MAP_CACHE:
        return _MAP_CACHE[skin]
    item = get_set(skin)
    resolved = {}
    if item:
        for code, filename in item["mapping"].items():
            uri = _data_uri(os.path.join(item["directory"], filename))
            if uri:
                resolved[code] = uri
    _MAP_CACHE[skin] = resolved
    return resolved


def preview_items(skin: str, limit: int = 10) -> list[tuple[str, str]]:
    item = get_set(skin)
    if not item:
        return []
    result = []
    for code, filename in list(item["mapping"].items())[:limit]:
        path = os.path.join(item["directory"], filename)
        if os.path.isfile(path):
            result.append((code, path))
    return result


def emoticon_codes(skin: str = "default/smileys.cfg") -> list[str]:
    return sorted(_load_map(skin), key=len, reverse=True)


def smile_to_html(text: str, skin: str = "default/smileys.cfg") -> str:
    mapping = _load_map(skin)
    if not mapping:
        return text
    pattern = re.compile("|".join(re.escape(code)
                                  for code in sorted(mapping, key=len, reverse=True)))
    return pattern.sub(lambda match: (
        f'<img src="{mapping[match.group(0)]}" alt="{match.group(0)}" '
        'style="vertical-align:middle" width="16" height="16">'), text)


def clear_cache() -> None:
    global _SETS
    _SETS = None
    _MAP_CACHE.clear()
