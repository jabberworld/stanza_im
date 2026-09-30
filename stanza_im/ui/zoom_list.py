"""Reusable list widget with Ctrl+wheel font zoom and empty-click deselect."""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets


class ZoomListWidget(QtWidgets.QListWidget):
    """A list that supports Ctrl+wheel font zoom and clears selection on a
    click over empty space."""

    font_zoom_requested = QtCore.pyqtSignal(int)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        from stanza_im.ui.font_zoom import wheel_font_size
        size = wheel_font_size(self.font(), event)
        if size is not None:
            self.font_zoom_requested.emit(size)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if self.itemAt(event.position().toPoint()) is None:
            # ``clearSelection`` alone leaves the *current* item set, so a
            # ``currentItem()``-based lookup would keep the selection alive.
            self.clearSelection()
            self.setCurrentItem(None)
        super().mousePressEvent(event)
