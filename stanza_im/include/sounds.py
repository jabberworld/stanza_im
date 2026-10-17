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
import math
import os
import struct
import tempfile
import wave

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


def effect_path(rel: str) -> str:
    """Absolute path of a loose effect file (e.g. ``effects/ringtone.wav``)."""
    return os.path.join(SOUNDS_DIR, rel)


#: Call-progress tones: (frequency Hz, tone ms, silence ms, cycles).
_CALL_TONES = {
    "ringback": (425.0, 1000, 3000, 1),   # long beeps while the peer is alerted
    "busy": (425.0, 300, 300, 6),         # fast beeps on a rejected call
}


def generate_tone_wav(path: str, frequency: float, on_ms: int, off_ms: int,
                      cycles: int, sample_rate: int = 8000) -> bool:
    """Write a mono 16-bit WAV with *cycles* of (tone *on_ms* / silence *off_ms*)."""
    try:
        on_n = max(1, int(sample_rate * on_ms / 1000))
        off_n = max(0, int(sample_rate * off_ms / 1000))
        step = 2.0 * math.pi * frequency / sample_rate
        frames = bytearray()
        for _ in range(max(1, cycles)):
            for i in range(on_n):
                frames += struct.pack(
                    "<h", int(0.5 * 32767 * math.sin(step * i)))
            frames += b"\x00\x00" * off_n
        with wave.open(path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(bytes(frames))
        return True
    except (OSError, wave.Error) as exc:
        logger.warning("Could not write call tone %s: %s", path, exc)
        return False


def call_tone_path(kind: str) -> str:
    """Generate (once) and return the ringback/busy tone WAV path (or "")."""
    spec = _CALL_TONES.get(kind)
    if spec is None:
        return ""
    uid = getattr(os, "getuid", lambda: 0)()
    path = os.path.join(tempfile.gettempdir(), f"stanza-im-{kind}-{uid}.wav")
    if not os.path.isfile(path) and not generate_tone_wav(path, *spec):
        return ""
    return path


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
