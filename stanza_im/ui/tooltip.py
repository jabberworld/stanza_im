"""Shared rich-text tooltip popup.

A small frameless, click-through window used wherever a tooltip needs rich
content or an avatar image (the built-in Qt tooltips are plain-text only).
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

_SHOW_DELAY_MS = 350
_OFFSET = QtCore.QPoint(16, 14)
_MARGIN = 8


class _ToolTipWindow(QtWidgets.QWidget):
    """Frameless rich-text popup with an optional avatar image."""

    def __init__(self):
        super().__init__(None,
                         QtCore.Qt.WindowType.ToolTip
                         | QtCore.Qt.WindowType.FramelessWindowHint
                         | QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)
        self._avatar = QtWidgets.QLabel(self)
        self._avatar.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self._avatar.hide()
        row.addWidget(self._avatar)
        self._label = QtWidgets.QLabel(self)
        self._label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._label.setWordWrap(False)
        row.addWidget(self._label, 1)

    def _apply_style(self) -> None:
        pal = QtGui.QPalette()
        base = pal.color(QtGui.QPalette.ColorRole.ToolTipBase)
        text = pal.color(QtGui.QPalette.ColorRole.ToolTipText)
        self.setStyleSheet(
            f"QWidget {{ background-color: {base.name()}; "
            f"color: {text.name()}; border: none; }}")

    def set_content(self, html: str, avatar_path: str | None) -> None:
        self._apply_style()
        self._label.setText(html)
        if avatar_path:
            pix = QtGui.QPixmap(avatar_path)
            avatar = pix if pix.isNull() else pix.scaled(
                32, 32, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
            self._avatar.setPixmap(avatar)
            self._avatar.show()
        else:
            self._avatar.clear()
            self._avatar.hide()


_WINDOW: _ToolTipWindow | None = None
_TIMER: QtCore.QTimer | None = None
_PENDING: list = [QtCore.QPoint(), "", None]  # global_pos, html, avatar_path


def _window() -> _ToolTipWindow:
    global _WINDOW
    if _WINDOW is None:
        _WINDOW = _ToolTipWindow()
    return _WINDOW


def _place(pos: QtCore.QPoint) -> QtCore.QPoint:
    """Shift *pos* so the popup stays inside the visible screen area."""
    win = _window()
    win.adjustSize()
    size = win.size()
    target = pos + _OFFSET
    screen = QtWidgets.QApplication.screenAt(pos) \
        or QtWidgets.QApplication.primaryScreen()
    if screen is not None:
        area = screen.availableGeometry()
        target = QtCore.QPoint(
            min(max(area.left() + _MARGIN, target.x()),
                area.right() - size.width() - _MARGIN),
            min(max(area.top() + _MARGIN, target.y()),
                area.bottom() - size.height() - _MARGIN))
    return target


def _show_now(global_pos: QtCore.QPoint, html: str,
              avatar_path: str | None) -> None:
    win = _window()
    win.set_content(html, avatar_path)
    win.move(_place(global_pos))
    win.show()
    win.raise_()


def show(global_pos: QtCore.QPoint, html: str,
         avatar_path: str | None = None) -> None:
    """Schedule a popup near *global_pos* (restarting the delay timer)."""
    global _TIMER
    if _TIMER is None:
        _TIMER = QtCore.QTimer()
        _TIMER.setSingleShot(True)
        _TIMER.timeout.connect(
            lambda: _show_now(_PENDING[0], _PENDING[1], _PENDING[2]))
    _PENDING[:] = [global_pos, html, avatar_path]
    _TIMER.start(_SHOW_DELAY_MS)


def hide() -> None:
    """Cancel any pending popup and hide the current one."""
    if _TIMER is not None:
        _TIMER.stop()
    if _WINDOW is not None:
        _WINDOW.hide()