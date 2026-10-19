"""Full-screen overlay to pick a screen-capture rectangle.

The overlay spans the whole virtual desktop and paints a **snapshot** of the
screen as its background (dimmed outside the selection, bright inside), so it
stays visible with or without a compositing manager — a translucent frameless
window on a non-composited desktop can end up invisible while its modal loop
still blocks the UI.  The user drags a rectangle (``Esc`` or a right click
cancels); :meth:`region` returns the ``(x, y, w, h)`` rectangle in global
screen coordinates, clamped to the monitor that holds its top-left corner (a
region grab is relative to one screen).
"""
from __future__ import annotations

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr

logger = logging.getLogger(__name__)

_MIN_SIDE = 8


class ScreenRegionDialog(QtWidgets.QDialog):
    """Drag a screen rectangle; ``Accepted`` carries it via :meth:`region`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.setWindowTitle(tr("screen_region_title"))
        self._origin = None
        self._rect = QtCore.QRect()
        self._backdrop = None
        geometry = QtCore.QRect()
        for screen in QtWidgets.QApplication.screens():
            geometry = geometry.united(screen.geometry())
        if not geometry.isNull():
            self.setGeometry(geometry)

    # ── backdrop ──────────────────────────────────────────────────
    def _grab_backdrop(self) -> QtGui.QPixmap:
        """Compose a snapshot of the whole virtual desktop."""
        from stanza_im.include import screen as screen_mod
        geometry = self.geometry()
        backdrop = QtGui.QPixmap(geometry.size())
        backdrop.fill(QtGui.QColor(20, 20, 20))
        painter = QtGui.QPainter(backdrop)
        for screen in QtWidgets.QApplication.screens():
            shot = screen_mod.grab_screen(screen)
            if shot is None or shot.isNull():
                continue
            geo = screen.geometry()
            target = QtCore.QRect(geo.topLeft() - geometry.topLeft(),
                                  geo.size())
            painter.drawPixmap(target, shot)
        painter.end()
        return backdrop

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._backdrop is None:
            self._backdrop = self._grab_backdrop()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        logger.debug("SCREEN region picker: geom=%s visible=%s backdrop=%s",
                     self.geometry(), self.isVisible(),
                     "none" if self._backdrop is None
                     else "%dx%d" % (self._backdrop.width(),
                                     self._backdrop.height()))

    # ── interaction ───────────────────────────────────────────────
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self.reject()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._rect = QtCore.QRect(self._origin, QtCore.QSize())
            self.update()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._origin is not None:
            self._rect = QtCore.QRect(
                self._origin, event.position().toPoint()).normalized()
            self.update()
            return
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
            return
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
        backdrop = self._backdrop
        if backdrop is not None and not backdrop.isNull():
            painter.drawPixmap(0, 0, backdrop)
            painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 120))
            if not self._rect.isNull():
                # Show the selection undimmed (the snapshot, bright).
                painter.drawPixmap(self._rect, backdrop, self._rect)
        else:
            painter.fillRect(self.rect(), QtGui.QColor(20, 20, 20, 230))
        if not self._rect.isNull():
            painter.setPen(QtGui.QPen(QtGui.QColor(60, 170, 255), 2))
            painter.drawRect(self._rect.adjusted(1, 1, -1, -1))
        painter.setPen(QtGui.QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(max(11, font.pointSize()))
        painter.setFont(font)
        painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter,
                         tr("screen_region_hint"))
        painter.end()
