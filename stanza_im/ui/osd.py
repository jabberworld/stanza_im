"""On-screen display (OSD) notifications — translucent frameless windows.

Notifications are docked to a saved base position and stack vertically from
it, either downward (top-down mode) or upward.  A draggable preview lets the
user move that base position from the preferences OSD page.
"""
from __future__ import annotations

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr

logger = logging.getLogger(__name__)

_OSD_WIDTH = 280
_OSD_GAP = 8
_MIN_HEIGHT = 14


def stack_position(index: int, base_y: int, heights,
                   topdown: bool = True, gap: int = _OSD_GAP) -> int:
    """Absolute Y for the OSD at *index* docked to *base_y*.

    Index 0 is the base itself.  In top-down mode the rest appear below it,
    otherwise (newest above) they appear above the base.
    """
    heights = list(heights or [])
    if index <= 0:
        return base_y
    offset = 0
    for i in range(index):
        offset += (heights[i] if i < len(heights) else 0) + gap
    return base_y + offset if topdown else base_y - offset


class _OsdWindow(QtWidgets.QWidget):
    """A single OSD bubble (optionally draggable for the preview)."""

    def _stylesheet(self) -> str:
        alpha = int(round(max(0, min(100, self._opacity)) * 255 / 100))
        bg = QtGui.QColor(self._bg_color) if self._bg_color else \
            QtGui.QColor(40, 40, 40)
        if not bg.isValid():
            bg = QtGui.QColor(40, 40, 40)
        fg = QtGui.QColor(self._font_color) if self._font_color else \
            QtGui.QColor(255, 255, 255)
        if not fg.isValid():
            fg = QtGui.QColor(255, 255, 255)
        css = (
            "#osd-frame { background: rgba(%d, %d, %d, %d); border: 1px solid "
            "rgba(255, 255, 255, 90); border-radius: 8px; }"
            "#osd-frame QLabel { color: %s; background: transparent; }"
            "#osd-title { font-weight: bold; font-size: 13px; }"
            "#osd-body { font-size: 12px; color: %s; }"
            "#osd-close { color: %s; background: transparent; border: 0; "
            "border-radius: 9px; font-size: 12px; font-weight: bold; }"
            "#osd-close:hover { background: rgba(255, 255, 255, 45); }"
            % (bg.red(), bg.green(), bg.blue(), alpha,
               fg.name(), fg.name(), fg.name()))
        if self._family or self._size:
            fam = (self._family or "sans-serif").replace("'", "\\'").replace("\\", "\\\\")
            title_size = self._size or 13
            body_size = self._size or 12
            css += ("\n#osd-title {{ font-family: '{0}'; font-size: {1}pt; }}"
                    "\n#osd-body {{ font-family: '{0}'; font-size: {2}pt; }}"
                    .format(fam, title_size, body_size))
        return css

    def __init__(self, icon, title: str, body: str, draggable: bool = False,
                 family: str = "", size: int = 0, bg_color: str = "",
                 font_color: str = "", opacity: int = 92, parent=None):
        super().__init__(None)
        self._family = family or ""
        self._size = int(size or 0)
        self._bg_color = bg_color or ""
        self._font_color = font_color or ""
        self._opacity = int(opacity)
        self.setWindowFlags(
            QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.X11BypassWindowManagerHint
            | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFixedWidth(_OSD_WIDTH)

        self._drag_offset: QtCore.QPoint | None = None
        self._press_global: QtCore.QPoint | None = None
        self._system_dragging = False
        self._draggable = draggable
        self._on_clicked = None
        self._on_moved = None
        self._on_close = None
        app = QtWidgets.QApplication.instance()
        platform = (app.platformName() if app else "").lower()
        # startSystemMove() (_NET_WM_MOVERESIZE) is unreliable on some X11
        # window managers (e.g. Trinity) that acknowledge it but never move the
        # window; use it only on Wayland and move manually on X11.
        self._use_system_move = platform.startswith("wayland")

        frame = QtWidgets.QFrame(self)
        frame.setObjectName("osd-frame")
        frame.setStyleSheet(self._stylesheet())
        self._frame = frame

        row = QtWidgets.QHBoxLayout(frame)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(8)
        if icon is not None and not icon.isNull():
            icon_label = QtWidgets.QLabel(frame)
            icon_label.setPixmap(icon.pixmap(32, 32))
            row.addWidget(icon_label, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        text_col = QtWidgets.QVBoxLayout()
        text_col.setSpacing(2)
        title_label = QtWidgets.QLabel(title or "", frame)
        title_label.setObjectName("osd-title")
        title_label.setWordWrap(True)
        body_label = QtWidgets.QLabel(body or "", frame)
        body_label.setObjectName("osd-body")
        body_label.setWordWrap(True)
        text_col.addWidget(title_label)
        text_col.addWidget(body_label)
        row.addLayout(text_col, 1)

        close_btn = QtWidgets.QToolButton(frame)
        close_btn.setObjectName("osd-close")
        close_btn.setText("\u00d7")
        close_btn.setAutoRaise(True)
        close_btn.setFixedSize(18, 18)
        close_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip(tr("osd_close"))
        close_btn.clicked.connect(self._close)
        row.addWidget(close_btn, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self._close_btn = close_btn

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        # Let every mouse event reach the window itself: clicks and (for the
        # preview) drags must not be swallowed by the frame/label children.
        frame.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        for child in frame.findChildren(QtWidgets.QWidget):
            child.setAttribute(
                QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # …except the close button, which stays clickable.
        close_btn.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self.setCursor(
            QtCore.Qt.CursorShape.OpenHandCursor if draggable
            else QtCore.Qt.CursorShape.PointingHandCursor)

    # ── Input ────────────────────────────────────────────────────

    def apply_font(self, family: str = "", size: int = 0) -> None:
        """Re-apply the configured font to a live OSD window."""
        self.apply_style(family=family, size=size)

    def apply_style(self, family=None, size=None, bg_color=None,
                    font_color=None, opacity=None) -> None:
        """Update any of the font/color/opacity settings and restyle."""
        if family is not None:
            self._family = family or ""
        if size is not None:
            self._size = int(size or 0)
        if bg_color is not None:
            self._bg_color = bg_color or ""
        if font_color is not None:
            self._font_color = font_color or ""
        if opacity is not None:
            self._opacity = int(opacity)
        frame = getattr(self, "_frame", None)
        if frame is not None:
            frame.setStyleSheet(self._stylesheet())

    def _click(self) -> None:
        cb = self._on_clicked
        if cb:
            cb()

    def _close(self) -> None:
        cb = self._on_close
        if cb:
            cb()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._draggable:
                self._drag_offset = (
                    event.globalPosition().toPoint() - self.pos())
                self._press_global = event.globalPosition().toPoint()
                self._system_dragging = False
                self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                if not self._use_system_move:
                    self.grabMouse()
                event.accept()
            else:
                self._click()
                event.accept()

    def mouseMoveEvent(self, event):
        if not self._draggable or self._press_global is None:
            return
        if self._system_dragging:
            return
        if (event.globalPosition().toPoint()
                - self._press_global).manhattanLength() < 6:
            return
        if self._use_system_move:
            try:
                handle = self.windowHandle()
                if handle is not None and handle.startSystemMove():
                    self._system_dragging = True
                    self.move(self._press_global - self._drag_offset)
                    return
            except (AttributeError, RuntimeError, TypeError):
                pass
        # Manual move: reliable on X11 (the window is override-redirect) and
        # a safe fallback for any other platform.
        self.move(event.globalPosition().toPoint() - self._drag_offset)
        if self._on_moved:
            self._on_moved(self.x(), self.y())

    def moveEvent(self, event):
        super().moveEvent(event)
        if (self._system_dragging and self._on_moved
                and self.x() > -16000 and self.y() > -16000):
            self._on_moved(self.x(), self.y())

    def mouseReleaseEvent(self, event):
        if self._press_global is not None or self._system_dragging:
            if self._on_moved and self.x() > -16000 and self.y() > -16000:
                self._on_moved(self.x(), self.y())
            if self.underMouse():
                self.releaseMouse()
            self._press_global = None
            self._drag_offset = None
            self._system_dragging = False
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)


class OsdManager:
    """Owns and stacks on-screen notifications for the main window."""

    def __init__(self, config, icons=None):
        self._config = config
        self._icons = icons
        self._windows: list[dict] = []
        self._preview: dict | None = None

    @property
    def _cfg(self):
        return self._config.notifications

    # ── Public API ────────────────────────────────────────────────

    def show(self, icon, title: str, body: str, on_click=None):
        """Display a transient OSD notification (subject to the enabled flag)."""
        if not getattr(self._cfg, "osd_enabled", False):
            return
        max_visible = max(1, int(getattr(self._cfg, "osd_max", 3) or 3))
        non_preview = [r for r in self._windows if not r["preview"]]
        while len(non_preview) >= max_visible:
            self._dismiss(non_preview[0])
            non_preview = [r for r in self._windows if not r["preview"]]
        duration = float(getattr(self._cfg, "osd_duration", 5) or 5)
        rec = self._spawn(icon, title, body, draggable=False,
                          preview=False, duration=duration)
        rec["on_click"] = on_click
        rec["window"]._on_clicked = lambda: self._clicked(rec)

    def show_preview(self):
        """Show (or re-dock) the draggable OSD used in the preferences page."""
        if self._preview is not None and self._preview["window"].isVisible():
            self._restack()
            return
        rec = self._spawn(None, tr("osd_preview_title"),
                          tr("osd_preview_body"), draggable=True,
                          preview=True, duration=0)
        rec["window"]._on_moved = self._preview_moved
        self._preview = rec

    def hide_preview(self):
        if self._preview is not None:
            self._dismiss(self._preview)
            self._preview = None

    def apply_font(self, family: str = "", size: int = 0) -> None:
        """Re-apply the configured font to all live OSD windows/preview."""
        for rec in list(self._windows):
            rec["window"].apply_font(family, size)

    def apply_colors(self, bg_color: str = "", font_color: str = "",
                     opacity: int = 92) -> None:
        """Re-apply the configured background/text color and opacity."""
        for rec in list(self._windows):
            rec["window"].apply_style(bg_color=bg_color,
                                      font_color=font_color, opacity=opacity)

    @property
    def _osd_font(self) -> tuple[str, int]:
        appearance = getattr(self._config, "appearance", None)
        if appearance is None:
            return "", 0
        return (getattr(appearance, "osd_font", "") or "",
                int(getattr(appearance, "osd_font_size", 0) or 0))

    @property
    def _osd_colors(self) -> tuple[str, str, int]:
        appearance = getattr(self._config, "appearance", None)
        if appearance is None:
            return "", "", 92
        return (getattr(appearance, "osd_bg_color", "") or "",
                getattr(appearance, "osd_font_color", "") or "",
                int(getattr(appearance, "osd_opacity", 92) or 0))

    def dismiss_all(self):
        for rec in list(self._windows):
            self._dismiss(rec)
        self._preview = None

    # ── Internals ─────────────────────────────────────────────────

    def _preview_moved(self, x: int, y: int) -> None:
        self._cfg.osd_x = int(x)
        self._cfg.osd_y = int(y)

    def _clicked(self, rec: dict) -> None:
        cb = rec.get("on_click")
        if cb:
            cb()
        self._dismiss(rec)

    def _spawn(self, icon, title: str, body: str, draggable: bool,
               preview: bool, duration: float) -> dict:
        family, size = self._osd_font
        bg_color, font_color, opacity = self._osd_colors
        win = _OsdWindow(icon, title, body, draggable=draggable,
                         family=family, size=size, bg_color=bg_color,
                         font_color=font_color, opacity=opacity)
        rec = {"window": win, "timer": None, "preview": preview,
               "on_click": None}
        win._on_close = lambda: self._dismiss(rec)
        self._windows.append(rec)
        win.show()
        win.adjustSize()
        win.raise_()
        if duration and duration > 0:
            timer = QtCore.QTimer(win)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._dismiss(rec))
            timer.start(int(duration * 1000))
            rec["timer"] = timer
        self._restack()
        return rec

    def _dismiss(self, rec: dict) -> None:
        if rec not in self._windows:
            return
        self._windows.remove(rec)
        timer = rec.get("timer")
        if timer is not None:
            timer.stop()
        if self._preview is rec:
            self._preview = None
        win = rec["window"]
        win.hide()
        win.deleteLater()
        self._restack()

    def _base_point(self) -> QtCore.QPoint:
        cfg = self._cfg
        return QtCore.QPoint(
            int(getattr(cfg, "osd_x", 0) or 0),
            int(getattr(cfg, "osd_y", 0) or 0))

    def _screen_for(self, point: QtCore.QPoint):
        app = QtWidgets.QApplication.instance()
        if app is None:
            return None
        return app.screenAt(point) or app.primaryScreen()

    def _externalize(self, point: QtCore.QPoint) -> QtCore.QPoint:
        screen = self._screen_for(point)
        if screen is None:
            return point
        rect = screen.availableGeometry()
        x = max(rect.left(), min(point.x(), rect.right() - _OSD_WIDTH - 6))
        y = max(rect.top(), min(point.y(), rect.bottom() - _MIN_HEIGHT - 6))
        return QtCore.QPoint(x, y)

    def _restack(self) -> None:
        cfg = self._cfg
        topdown = bool(getattr(cfg, "osd_topdown", True))
        base = self._externalize(self._base_point())
        active = [r for r in self._windows if r["window"].isVisible()]
        heights = [max(_MIN_HEIGHT, r["window"].height()) for r in active]
        for index, rec in enumerate(active):
            y = stack_position(index, base.y(), heights, topdown, _OSD_GAP)
            win = rec["window"]
            win.move(base.x(), y)
            win.raise_()