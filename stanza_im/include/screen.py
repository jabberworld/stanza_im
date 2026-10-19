"""Screen capture helpers (region / monitor grabs).

Shared by the OSD (its no-compositor backdrop) and the call screen-sharing
track.  Qt is imported lazily so importing the module stays cheap and does not
require a live ``QApplication``.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: ``None`` until the first region grab probes whether ``grabWindow(0, x, y,
#: w, h)`` honours the position on this platform; then ``True``/``False``.
_REGION_GRAB_OK: bool | None = None


def screen_at(pos):
    """The screen containing *pos* (logical coords), else the primary one."""
    from PyQt6 import QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    return app.screenAt(pos) or app.primaryScreen()


def primary_screen():
    from PyQt6 import QtWidgets
    app = QtWidgets.QApplication.instance()
    return app.primaryScreen() if app is not None else None


def wayland() -> bool:
    """True on a Wayland session (screen grabs are usually blocked there)."""
    from PyQt6 import QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is None:
        return False
    return (app.platformName() or "").lower().startswith("wayland")


def region_matches(region, crop) -> bool:
    """True when a region grab equals the same area cropped from a full grab."""
    try:
        ri = region.toImage()
        ci = crop.toImage()
    except Exception:
        return False
    if ri.isNull() or ci.isNull() or ri.size() != ci.size():
        return False
    width, height = ri.width(), ri.height()
    samples = [(1, 1), (width // 2, height // 2), (width - 2, height - 2)]
    for x, y in samples:
        if 0 <= x < width and 0 <= y < height and ri.pixel(x, y) != ci.pixel(x, y):
            return False
    return True


def grab_region(pos, size):
    """Snapshot the screen area at *pos* (logical coords); None on failure.

    Tries a region grab first; some platforms ignore ``x``/``y`` for
    ``window == 0`` (returning the top-left), so on the first capture the
    region is compared against the same area cropped from a full grab and the
    region path is disabled permanently if they differ.
    """
    global _REGION_GRAB_OK
    from PyQt6 import QtCore
    screen = screen_at(pos)
    if screen is None or size.width() <= 0 or size.height() <= 0:
        return None
    origin = screen.geometry().topLeft()
    lx = pos.x() - origin.x()
    ly = pos.y() - origin.y()
    lw = size.width()
    lh = size.height()
    if lx < 0 or ly < 0:
        return None

    region = None
    if _REGION_GRAB_OK is not False:
        try:
            candidate = screen.grabWindow(0, lx, ly, lw, lh)
        except Exception:
            candidate = None
        if candidate is not None and not candidate.isNull():
            dpr = candidate.devicePixelRatio() or 1.0
            for scale in (1.0, dpr):
                if (abs(candidate.width() - lw * scale) <= 2
                        and abs(candidate.height() - lh * scale) <= 2):
                    region = candidate
                    break

    crop = None
    if region is None or _REGION_GRAB_OK is None:
        try:
            shot = screen.grabWindow(0)
        except Exception:
            shot = None
        if shot is not None and not shot.isNull():
            dpr = shot.devicePixelRatio() or 1.0
            x = int(lx * dpr)
            y = int(ly * dpr)
            w = int(lw * dpr)
            h = int(lh * dpr)
            if (x >= 0 and y >= 0 and x + w <= shot.width()
                    and y + h <= shot.height()):
                crop = shot.copy(QtCore.QRect(x, y, w, h))

    if _REGION_GRAB_OK is None and region is not None and crop is not None:
        _REGION_GRAB_OK = region_matches(region, crop)
        if not _REGION_GRAB_OK:
            logger.info("Screen region grab ignores position; "
                        "using full-screen crop")
    if _REGION_GRAB_OK is not False and region is not None:
        return region
    return crop


def grab_screen(screen=None):
    """Full grab of *screen* (the primary one by default); None on failure."""
    screen = screen or primary_screen()
    if screen is None:
        return None
    try:
        shot = screen.grabWindow(0)
    except Exception:
        return None
    if shot is None or shot.isNull():
        return None
    return shot
