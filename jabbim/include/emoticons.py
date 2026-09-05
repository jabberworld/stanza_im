"""Emoticon handling: parse smileys.cfg and inline emoticons into chat HTML.

Uses the 16x16 set from ``resources/emoticons/default/``.  Images are
embedded as PNG data-URIs so they render in both QWebEngineView and any
base-URL mode, with no per-file I/O at render time.
"""
from __future__ import annotations

import base64
import os
import re

from jabbim.include.constants import EMOTICONS_DIR

DEFAULT_SKIN = "default"

_LINE_RE = re.compile(r"'(.+)'='(.+)'")
_map: dict[str, str] | None = None


def _data_uri(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _load_map() -> dict[str, str]:
    """Build ``{code: data-uri}`` from smileys.cfg (cached)."""
    global _map
    if _map is not None:
        return _map
    cfg = os.path.join(EMOTICONS_DIR, DEFAULT_SKIN, "smileys.cfg")
    mapping: dict[str, str] = {}
    if os.path.isfile(cfg):
        in_section = False
        try:
            with open(cfg, encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if line == "[emoticons]":
                        in_section = True
                        continue
                    if in_section and line.startswith("[") and line.endswith("]"):
                        break
                    if not in_section:
                        continue
                    m = _LINE_RE.match(line)
                    if m:
                        code, filename = m.group(1), m.group(2)
                        if code not in mapping:
                            mapping[code] = filename
        except OSError:
            mapping = {}
    resolved: dict[str, str] = {}
    for code, filename in mapping.items():
        uri = _data_uri(os.path.join(EMOTICONS_DIR, DEFAULT_SKIN, filename))
        if uri:
            resolved[code] = uri
    _map = resolved
    return _map


def emoticon_codes() -> list[str]:
    """All known emoticon codes, longest first (for matching order)."""
    return sorted(_load_map(), key=len, reverse=True)


def smile_to_html(text: str) -> str:
    """Replace emoticon codes in already-escaped HTML text with <img> tags."""
    mapping = _load_map()
    if not mapping:
        return text
    for code in sorted(mapping, key=len, reverse=True):
        if code in text:
            text = text.replace(
                code,
                f'<img src="{mapping[code]}" alt="{code}" '
                f'style="vertical-align:middle" width="16" height="16">',
            )
    return text


def clear_cache() -> None:
    """Drop the cached emoticon map (used in tests)."""
    global _map
    _map = None