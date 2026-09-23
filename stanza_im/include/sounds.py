"""Sound notification themes from ``resources/sounds/``.

Each theme is a directory with a ``default.cfg`` describing it:

    [header]
    name="Default Jabbim Sound Pack"
    [sounds]
    message = chat2.wav
    new_message = chat1.wav
    ...

``theme_sounds(id)`` resolves the event keys to absolute WAV paths.  Playback
lives in :mod:`stanza_im.ui.sounds`.
"""
from __future__ import annotations

import configparser
import logging
import os

from stanza_im.include.constants import SOUNDS_DIR

logger = logging.getLogger(__name__)

THEME_FILE = "default.cfg"
DEFAULT_THEME = "default"

# The event keys a theme may define (``start`` is currently unused).
EVENTS = ("new_message", "message", "ft_start", "ft_finish",
          "contact_offline", "contact_online", "message_send", "start")


def _strip(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _read_cfg(theme_id: str) -> configparser.ConfigParser | None:
    path = os.path.join(SOUNDS_DIR, theme_id, THEME_FILE)
    if not os.path.isfile(path):
        return None
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError) as exc:
        logger.warning("Could not read sound theme %s: %s", theme_id, exc)
        return None
    return parser


def theme_name(theme_id: str) -> str:
    """Human-readable theme name (falls back to the directory id)."""
    parser = _read_cfg(theme_id)
    if parser is not None and parser.has_section("header"):
        name = _strip(parser.get("header", "name", fallback=""))
        if name:
            return name
    return theme_id


def discover_themes() -> list[dict]:
    """Return ``[{"id": …, "name": …}]`` for every sound theme.

    ``default`` is always first; the rest keep the directory order.
    """
    themes: list[dict] = []
    try:
        entries = sorted(os.scandir(SOUNDS_DIR), key=lambda e: e.name)
    except OSError:
        return themes
    for entry in entries:
        if not entry.is_dir():
            continue
        if not os.path.isfile(os.path.join(entry.path, THEME_FILE)):
            continue
        themes.append({"id": entry.name, "name": theme_name(entry.name)})
    themes.sort(key=lambda item: (item["id"] != DEFAULT_THEME, item["id"]))
    return themes


def theme_sounds(theme_id: str) -> dict[str, str]:
    """Map the theme's event keys to absolute WAV paths (missing files dropped)."""
    parser = _read_cfg(theme_id)
    if parser is None or not parser.has_section("sounds"):
        return {}
    result: dict[str, str] = {}
    for event in EVENTS:
        filename = _strip(parser.get("sounds", event, fallback=""))
        if not filename:
            continue
        path = os.path.join(SOUNDS_DIR, theme_id, filename)
        if os.path.isfile(path):
            result[event] = path
    return result
