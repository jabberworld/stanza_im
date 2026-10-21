"""Shared rich-text tooltip popup.

A small frameless, click-through window used wherever a tooltip needs rich
content or an avatar image (the built-in Qt tooltips are plain-text only).
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

_SHOW_DELAY_MS = 350
_OFFSET = QtCore.QPoint(16, 14)
_MARGIN = 8

# Avatar size in logical px (configurable via ``set_avatar_size``).
_AVATAR_SIZE = [64]

# Popup text font (configurable via ``set_font``; ""/0 = the system default).
_FONT = [("", 0)]


def set_avatar_size(size: int) -> None:
    """Set the avatar size (px) used by the shared tooltip popup."""
    value = int(size or 0)
    _AVATAR_SIZE[0] = value if value >= 16 else 64


def set_font(family: str, size: int) -> None:
    """Set the popup's font family/point size ("" / 0 = the system default)."""
    _FONT[0] = (str(family or ""), int(size or 0))


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
        family, size = _FONT[0]
        font = QtGui.QFont()
        if family:
            font.setFamily(family)
        if size:
            font.setPointSize(int(size))
        self._label.setFont(font)
        self._avatar.setFont(font)

    def set_content(self, html: str, avatar_path: str | None,
                    wrap: bool = False, max_width: int = 0) -> None:
        self._apply_style()
        # Undo a width clamp left by a previous, very wide tooltip.
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)
        self._label.setWordWrap(bool(wrap))
        if wrap and max_width > 0:
            self._label.setMaximumWidth(int(max_width))
        else:
            self._label.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
        self._label.setText(html)
        if avatar_path:
            pix = QtGui.QPixmap(avatar_path)
            size = _AVATAR_SIZE[0]
            avatar = pix if pix.isNull() else pix.scaled(
                size, size, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
            self._avatar.setPixmap(avatar)
            self._avatar.show()
        else:
            self._avatar.clear()
            self._avatar.hide()


_WINDOW: _ToolTipWindow | None = None
_TIMER: QtCore.QTimer | None = None
# global_pos, html, avatar_path, wrap, max_width
_PENDING: list = [QtCore.QPoint(), "", None, False, 0]


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
        # Never let a wide (unwrapped) tooltip fall off the screen sideways.
        limit_w = max(120, area.width() - 2 * _MARGIN)
        limit_h = max(60, area.height() - 2 * _MARGIN)
        if size.width() > limit_w:
            # Pin the width (the label clips or wraps): a plain resize is
            # ignored because the label's minimum hint is the huge text width.
            win.setFixedWidth(limit_w)
            win.adjustSize()
            size = win.size()
        if size.height() > limit_h:
            win.resize(size.width(), limit_h)
            size = win.size()
        target = QtCore.QPoint(
            min(max(area.left() + _MARGIN, target.x()),
                area.right() - size.width() - _MARGIN),
            min(max(area.top() + _MARGIN, target.y()),
                area.bottom() - size.height() - _MARGIN))
    return target


def _show_now(global_pos: QtCore.QPoint, html: str,
              avatar_path: str | None, wrap: bool = False,
              max_width: int = 0) -> None:
    win = _window()
    win.set_content(html, avatar_path, wrap=wrap, max_width=max_width)
    win.move(_place(global_pos))
    win.show()
    win.raise_()


def show(global_pos: QtCore.QPoint, html: str,
         avatar_path: str | None = None, wrap: bool = False,
         max_width: int = 0) -> None:
    """Schedule a popup near *global_pos* (restarting the delay timer).

    *wrap* breaks long lines at *max_width* px (0 = leave the label's own
    maximum), which keeps a long conference subject readable instead of
    producing a tooltip wider than the screen.
    """
    global _TIMER
    if _TIMER is None:
        _TIMER = QtCore.QTimer()
        _TIMER.setSingleShot(True)
        _TIMER.timeout.connect(
            lambda: _show_now(*_PENDING))
    _PENDING[:] = [global_pos, html, avatar_path, bool(wrap), int(max_width)]
    _TIMER.start(_SHOW_DELAY_MS)


def hide() -> None:
    """Cancel any pending popup and hide the current one."""
    if _TIMER is not None:
        _TIMER.stop()
    if _WINDOW is not None:
        _WINDOW.hide()