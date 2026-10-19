"""Full-screen overlay to pick a screen-capture rectangle.

The dialog spans the whole virtual desktop with a dimmed, translucent
background; the user drags a rectangle (the dimming is cleared inside it) and
``Esc`` cancels.  :meth:`region` returns the ``(x, y, w, h)`` rectangle in
global screen coordinates, clamped to the monitor that holds its top-left
corner (a region grab is relative to one screen).
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr

_MIN_SIDE = 8


class ScreenRegionDialog(QtWidgets.QDialog):
    """Drag a screen rectangle; ``Accepted`` carries it via :meth:`region`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.setWindowTitle(tr("screen_region_title"))
        self._origin = None
        self._rect = QtCore.QRect()
        geometry = QtCore.QRect()
        for screen in QtWidgets.QApplication.screens():
            geometry = geometry.united(screen.geometry())
        if not geometry.isNull():
            self.setGeometry(geometry)

    # ── interaction ───────────────────────────────────────────────
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._rect = QtCore.QRect(self._origin, QtCore.QSize())
            self.update()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._origin is not None:
            self._rect = QtCore.QRect(
                self._origin, event.position().toPoint()).normalized()
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if (self._origin is not None
                and event.button() == QtCore.Qt.MouseButton.LeftButton):
            self._rect = QtCore.QRect(
                self._origin, event.position().toPoint()).normalized()
            if (self._rect.width() >= _MIN_SIDE
                    and self._rect.height() >= _MIN_SIDE):
                self.accept()
                return
            self._origin = None
            self._rect = QtCore.QRect()
            self.update()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    # ── result ────────────────────────────────────────────────────
    def region(self):
        """The chosen ``(x, y, w, h)`` in global coords, or ``None``.

        The rectangle is clamped to the monitor under its top-left corner.
        """
        if self._rect.isNull() or self._rect.width() < _MIN_SIDE:
            return None
        top_left = self.geometry().topLeft() + self._rect.topLeft()
        rect = QtCore.QRect(top_left, self._rect.size())
        screen = (QtWidgets.QApplication.screenAt(top_left)
                  or QtWidgets.QApplication.primaryScreen())
        if screen is not None:
            rect = rect.intersected(screen.geometry())
        if rect.width() < _MIN_SIDE or rect.height() < _MIN_SIDE:
            return None
        return (rect.x(), rect.y(), rect.width(), rect.height())

    # ── painting ──────────────────────────────────────────────────
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 120))
        if not self._rect.isNull():
            painter.setCompositionMode(
                QtGui.QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(self._rect, QtCore.Qt.GlobalColor.transparent)
            painter.setCompositionMode(
                QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QtGui.QPen(QtGui.QColor(60, 170, 255), 2))
            painter.drawRect(self._rect.adjusted(1, 1, -1, -1))
        painter.setPen(QtGui.QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(max(11, font.pointSize()))
        painter.setFont(font)
        painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter,
                         tr("screen_region_hint"))
