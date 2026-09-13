"""In-memory per-conference color allocation for MUC nicknames.

The participant → color map is session-only by design: it is built from the
roster currently present in a conference and is discarded when the client
restarts or the room is left and re-joined.  Colors start from a fixed dark
palette of maximally distinguishable shades (black, red, green, blue, ...)
and become closer together as the number of participants grows.
"""
from __future__ import annotations

import re
import unicodedata

from PyQt6 import QtGui

_PALETTE = [
    "#000000",
    "#c62828",   # dark red
    "#2e7d32",   # dark green
    "#1565c0",   # dark blue
    "#4527a0",   # deep purple
    "#ef6c00",   # orange
    "#00838f",   # teal
    "#ad1457",   # maroon
    "#5d4037",   # brown
    "#37474f",   # blue grey
    "#827717",   # olive
    "#283593",   # indigo
    "#00695c",   # dark cyan
    "#b71c1c",   # red
    "#4a148c",   # purple
]

_GOLDEN_ANGLE = 137.508
_FALLBACK_SATURATION = 0.55
_FALLBACK_LIGHTNESS = 0.30


def normalize_nick(nick: str) -> str:
    """Normalize a room nick for color-map keying.

    Same rules as ``ChatWidget._same_nick``: Unicode NFKC + whitespace
    collapsing + case folding, so "Alice  " and "alice" share one color.
    """
    return re.sub(r"\s+", " ",
                  unicodedata.normalize("NFKC", nick or "").strip().casefold())


def _dark_hsl(index: int) -> str:
    """Golden-angle dark color for participants beyond the fixed palette."""
    hue = (index * _GOLDEN_ANGLE) % 360
    color = QtGui.QColor.fromHslF(
        hue / 360.0, _FALLBACK_SATURATION, _FALLBACK_LIGHTNESS)
    return color.name()


class NickColorAllocator:
    """Assigns a stable distinct dark color per participant key.

    ``color_for(key)`` returns the same color for the same key during the
    lifetime of this instance.  ``prune(active_keys)`` releases colors of
    participants that left so new arrivals can reuse them (same participant
    re-joining may therefore get a different color, which is allowed).
    """

    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._used: list[str] = []
        self._freed: list[str] = []
        self._next_index = 0

    def color_for(self, key: str) -> str:
        """Return the color bound to *key*, allocating one on first sight."""
        key = key or ""
        existing = self._map.get(key)
        if existing is not None:
            return existing
        color = self._freed.pop() if self._freed else self._next_color()
        self._map[key] = color
        self._used.append(color)
        return color

    def prune(self, active_keys) -> None:
        """Release colors for keys that are no longer present."""
        active = set(k or "" for k in active_keys)
        stale = [key for key in self._map if key not in active]
        for key in stale:
            color = self._map.pop(key)
            try:
                self._used.remove(color)
            except ValueError:
                pass
            self._freed.append(color)

    def reset(self) -> None:
        """Forget all bindings (room re-join)."""
        self._map.clear()
        self._used.clear()
        self._freed.clear()
        self._next_index = 0

    def _next_color(self) -> str:
        if self._next_index < len(_PALETTE):
            color = _PALETTE[self._next_index]
        else:
            color = _dark_hsl(self._next_index)
        self._next_index += 1
        return color