"""A thin draggable bar that resizes a field vertically.

Shared by the chat message input (dragged to grow/shrink it) and the history
manager's search-results list: the bar sits on a field edge and emits the new
height while dragged.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets


class VerticalResizeHandle(QtWidgets.QFrame):
    """A thin (6px) draggable bar; emits the new field height while dragged.

    ``invert`` selects the drag direction: with the default the bar sits on the
    field's **top** edge (like the chat input), so dragging up grows the field;
    with ``invert=True`` it sits on the field's **bottom** edge, so dragging
    down grows it.
    """

    height_changed = QtCore.pyqtSignal(int)

    def __init__(self, parent=None, get_height=None, invert: bool = False):
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setCursor(QtCore.Qt.CursorShape.SizeVerCursor)
        self.setStyleSheet("background: rgba(0, 0, 0, 0.05);")
        self._get_height = get_height or (lambda: 60)
        self._invert = bool(invert)
        self._press_y: float | None = None
        self._press_h = 60
        self.setMouseTracking(True)

    def _resized_height(self, dy: float) -> int:
        """New field height for a vertical drag delta *dy*."""
        return int(self._press_h + dy if self._invert
                   else self._press_h - dy)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press_y = float(event.globalPosition().y())
            self._press_h = int(self._get_height())
            self.grabMouse()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._press_y is None:
            return
        dy = float(event.globalPosition().y()) - self._press_y
        self.height_changed.emit(self._resized_height(dy))
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._press_y is not None:
            self.releaseMouse()
        self._press_y = None
