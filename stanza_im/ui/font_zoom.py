"""Ctrl+wheel font-size adjustment shared by the input, roster and MUC list.

Ctrl+wheel over a widget changes only the *point size* of its font (the family
stays whatever the settings chose), clamped to a sane range.  The owning widget
is expected to persist the new size and to relay it to the preferences dialog
so its spin box stays in sync.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui

FONT_MIN = 6
FONT_MAX = 48


def clamp_font_size(size: int) -> int:
    """Clamp a font point size to the supported range."""
    return max(FONT_MIN, min(FONT_MAX, int(size or 0)))


def wheel_font_size(font: QtGui.QFont, event: QtGui.QWheelEvent) -> int | None:
    """Return the new point size for a Ctrl+wheel *event*, or ``None``.

    A plain (non-Ctrl) wheel or a zero delta returns ``None`` so the caller can
    fall through to the default handling.
    """
    if not (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
        return None
    delta = event.angleDelta().y()
    if not delta:
        return None
    base = font.pointSize()
    if base <= 0:
        base = font.pointSizeF() or 0
        if base <= 0:
            base = 10
    step = 1 if delta > 0 else -1
    return clamp_font_size(int(round(base)) + step)


class FontZoomMixin:
    """Mixin adding Ctrl+wheel font resizing to a widget.

    ``font_zoom_requested(size)`` is emitted with the new point size; the
    owning code applies it (keeping the family) and persists it.
    """

    font_zoom_requested = QtCore.pyqtSignal(int)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        size = wheel_font_size(self.font(), event)
        if size is not None:
            self.font_zoom_requested.emit(size)
            event.accept()
            return
        super().wheelEvent(event)
