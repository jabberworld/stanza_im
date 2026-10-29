"""Icon painter for the call network-quality indicator."""
from __future__ import annotations

from PyQt6 import QtCore, QtGui

_LEVEL_COLORS = {
    1: "#c0392b",
    2: "#d39b2a",
    3: "#6aa84f",
    4: "#2e9e44",
}
_UNKNOWN_COLOR = "#9aa0a6"


def network_icon(level: int, size: int = 20) -> QtGui.QIcon:
    """Draw four signal bars, filling *level* of them."""
    level = max(0, min(4, int(level or 0)))
    size = max(12, int(size or 20))
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        color = QtGui.QColor(
            _LEVEL_COLORS.get(level, _UNKNOWN_COLOR))
        active = color if level else QtGui.QColor(_UNKNOWN_COLOR)
        inactive = QtGui.QColor(_UNKNOWN_COLOR)
        inactive.setAlpha(95)
        gap = max(1.0, size * 0.08)
        bar = max(1.5, (size - gap * 5) / 4.0)
        bottom = size - 2.0
        for index in range(4):
            height = size * (0.22 + index * 0.20)
            x = 2.0 + index * (bar + gap)
            painter.fillRect(
                QtCore.QRectF(x, bottom - height, bar, height),
                active if index < level else inactive)
    finally:
        painter.end()
    return QtGui.QIcon(pixmap)
