"""Icon cache with LRU eviction and lazy loading."""
from __future__ import annotations

import os
import time

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.include.constants import (
    STATUS_DIR_16, STATUS_DIR_32, find_icon_sized,
)


class IconCache:
    """LRU cache for QPixmap icons.

    The TTL is disabled by default: icon files are immutable and a changed
    avatar (same file name) is announced through :meth:`forget`, so reloading
    everything every minute only churned disk I/O and native pixmaps.
    """

    def __init__(self, max_size: int = 512, stale_ttl: float = 0.0):
        self._cache: dict[str, QtGui.QPixmap] = {}
        self._access_times: dict[str, float] = {}
        self._max_size = max_size
        self._stale_ttl = stale_ttl
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._evict_stale)
        if self._stale_ttl > 0:
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
            # Green-bulb variants of the online/free-for-chat icons; the blue
            # originals (jabber-online.png / jabber-chat.png) stay on disk.
            "online": "jabber-online-green.png",
            "chat": "jabber-chat-green.png",
            "away": "jabber-away.png",
            "xa": "jabber-xa.png",
            "dnd": "jabber-dnd.png",
            "offline": "jabber-offline.png",
        }
        filename = key_file.get(show, "jabber-offline.png")
        return self.get(os.path.join(base, filename))

    def get_action_icon(self, name: str,
                        size: int = 16) -> QtGui.QPixmap:
        """Return an action icon (scalable first, then sized dirs)."""
        return self.get_icon_pixmap(name, size)

    def get_category_icon(self, name: str,
                          size: int = 16) -> QtGui.QPixmap:
        """Return a category/action icon rendered at *size* logical pixels."""
        dpr = self._screen_dpr()
        path = find_icon_sized(name, size, dpr)
        if not path:
            return QtGui.QPixmap()
        target = max(1, int(round(int(size or 16) * dpr)))
        pixmap = QtGui.QIcon(path).pixmap(target, target)
        if (not pixmap.isNull()
                and (pixmap.width() < target or pixmap.height() < target)):
            # QIcon does not upscale a single small pixmap; the icon would
            # keep its 16/22 px size while the other icons scale.
            pixmap = pixmap.scaled(
                target, target,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
        if dpr != 1.0 and not pixmap.isNull():
            pixmap.setDevicePixelRatio(dpr)
        return pixmap

    def get_icon(self, name: str, size: int = 16,
                 dpr: float | None = None) -> QtGui.QIcon:
        """A QIcon whose source is chosen for the logical *size* and DPR."""
        dpr = self._screen_dpr() if dpr is None else float(dpr)
        path = find_icon_sized(name, size, dpr)
        return QtGui.QIcon(path) if path else QtGui.QIcon()

    def get_icon_pixmap(self, name: str, size: int = 16,
                        dpr: float | None = None) -> QtGui.QPixmap:
        """Render an icon at ``size`` logical pixels for the current screen."""
        dpr = self._screen_dpr() if dpr is None else float(dpr)
        path = find_icon_sized(name, size, dpr)
        if not path:
            return QtGui.QPixmap()
        target = max(1, int(round(int(size or 16) * dpr)))
        pixmap = QtGui.QIcon(path).pixmap(target, target)
        if (not pixmap.isNull()
                and (pixmap.width() < target or pixmap.height() < target)):
            # QIcon does not upscale a single small pixmap; the icon would
            # keep its 16/22 px size while the other icons scale.
            pixmap = pixmap.scaled(
                target, target,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
        if dpr != 1.0 and not pixmap.isNull():
            pixmap.setDevicePixelRatio(dpr)
        return pixmap

    @staticmethod
    def _screen_dpr() -> float:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return 1.0
        screen = app.primaryScreen()
        try:
            return float(screen.devicePixelRatio()) if screen else 1.0
        except Exception:
            return 1.0

    def forget(self, path: str) -> None:
        """Drop one cached file (its content changed under the same name)."""
        self._cache.pop(path, None)
        self._access_times.pop(path, None)

    def clear(self) -> None:
        """Drop all cached pixmaps."""
        self._cache.clear()
        self._access_times.clear()

    # ── Eviction ─────────────────────────────────────────────────

    def _evict_stale(self) -> None:
        if self._stale_ttl <= 0:
            return
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
