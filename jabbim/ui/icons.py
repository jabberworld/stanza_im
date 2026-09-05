"""Icon cache with LRU eviction and lazy loading."""
from __future__ import annotations

import os
import time

from PyQt6 import QtGui, QtCore

from jabbim.include.constants import (
    STATUS_DIR_16, STATUS_DIR_32, ACTIONS_DIR_16, CATEGORIES_DIR_16,
)


class IconCache:
    """LRU cache for QPixmap icons with automatic stale eviction."""

    def __init__(self, max_size: int = 200, stale_ttl: float = 60.0):
        self._cache: dict[str, QtGui.QPixmap] = {}
        self._access_times: dict[str, float] = {}
        self._max_size = max_size
        self._stale_ttl = stale_ttl
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._evict_stale)
        self._timer.start(30_000)

    # ── Public API ────────────────────────────────────────────────

    def get(self, path: str) -> QtGui.QPixmap:
        """Return the QPixmap for *path*, loading from disk if needed."""
        if path in self._cache:
            self._access_times[path] = time.monotonic()
            return self._cache[path]
        pixmap = QtGui.QPixmap(path)
        if not pixmap.isNull():
            self._cache[path] = pixmap
            self._access_times[path] = time.monotonic()
            self._evict_if_needed()
        return pixmap

    def get_status_icon(self, show: str, size: str = "16x16") -> QtGui.QPixmap:
        """Return the standard Jabber status icon for *show*."""
        base = STATUS_DIR_16 if size == "16x16" else STATUS_DIR_32
        key_file = {
            "online": "jabber-online.png",
            "chat": "jabber-chat.png",
            "away": "jabber-away.png",
            "xa": "jabber-xa.png",
            "dnd": "jabber-dnd.png",
            "offline": "jabber-offline.png",
        }
        filename = key_file.get(show, "jabber-offline.png")
        return self.get(os.path.join(base, filename))

    def get_action_icon(self, name: str) -> QtGui.QPixmap:
        """Return an icon from images/16x16/actions/."""
        return self.get(os.path.join(ACTIONS_DIR_16, f"{name}.png"))

    def get_category_icon(self, name: str) -> QtGui.QPixmap:
        """Return an icon from images/16x16/categories/."""
        return self.get(os.path.join(CATEGORIES_DIR_16, f"{name}.png"))

    def clear(self) -> None:
        """Drop all cached pixmaps."""
        self._cache.clear()
        self._access_times.clear()

    # ── Eviction ─────────────────────────────────────────────────

    def _evict_stale(self) -> None:
        now = time.monotonic()
        stale = [k for k, t in self._access_times.items() if now - t > self._stale_ttl]
        for k in stale:
            self._cache.pop(k, None)
            self._access_times.pop(k, None)

    def _evict_if_needed(self) -> None:
        while len(self._cache) > self._max_size:
            oldest = min(self._access_times, key=self._access_times.get)
            self._cache.pop(oldest, None)
            self._access_times.pop(oldest, None)


# Module-level singleton (created after QApplication)
icons: IconCache | None = None


def init_icons() -> IconCache:
    """Create and return the global IconCache singleton."""
    global icons
    icons = IconCache()
    return icons
