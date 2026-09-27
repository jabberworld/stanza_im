"""System tray icon with context menu and notification blinking."""
from __future__ import annotations

import math
import os

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import (
    APP_ICON_16, APP_ICON_22, APP_ICON_32, APP_ICON_48,
    APP_ICON_SVG, APP_NAME, find_icon,
)

_STATUS_KEYS = ("online", "chat", "away", "xa", "dnd", "offline")

# Tray popup ("balloon") modes.
POPUPS_OFF = "off"
POPUPS_SYSTEM = "system"
POPUPS_SYSTEM_MESSAGES = "system_messages"


def normalize_popups_mode(value) -> str:
    """Coerce a stored ``notifications.popups`` value to a mode string.

    Legacy configs stored a bool (``True`` = message popups shown); a missing
    or unknown value falls back to the "system only" default.
    """
    if value in (POPUPS_OFF, POPUPS_SYSTEM, POPUPS_SYSTEM_MESSAGES):
        return value
    if isinstance(value, bool):
        return POPUPS_SYSTEM_MESSAGES if value else POPUPS_OFF
    return POPUPS_SYSTEM


def _menu_icon(filename: str) -> QtGui.QIcon:
    """Load an action/category/status icon for menus from resources."""
    path = find_icon(filename)
    if path:
        pix = QtGui.QPixmap(path)
        if not pix.isNull():
            return QtGui.QIcon(pix)
    return QtGui.QIcon()


def build_app_icon() -> QtGui.QIcon:
    """Build a multi-resolution app icon from every available size.

    Modern trays (especially HiDPI) render poorly with a single 16×16
    pixmap — they need larger fallbacks.  We collect PNGs at 16/22/32/48
    plus the SVG and let Qt pick the best one.
    """
    icon = QtGui.QIcon()
    candidates = [
        ("16x16", APP_ICON_16),
        ("22x22", APP_ICON_22),
        ("32x32", APP_ICON_32),
        ("48x48", APP_ICON_48),
    ]
    for size, base_dir in candidates:
        path = os.path.join(base_dir, "stanza-im.png")
        if os.path.isfile(path):
            w = int(size.split("x")[0])
            icon.addFile(path, QtCore.QSize(w, w))
    if os.path.isfile(APP_ICON_SVG):
        icon.addFile(APP_ICON_SVG)
    return icon


class TrayIcon(QtCore.QObject):
    """System tray icon with context menu and event-driven blinking."""

    show_requested = QtCore.pyqtSignal()
    quit_requested = QtCore.pyqtSignal()
    connect_requested = QtCore.pyqtSignal()
    disconnect_requested = QtCore.pyqtSignal()
    settings_requested = QtCore.pyqtSignal()
    status_requested = QtCore.pyqtSignal(str)
    cycle_unread_requested = QtCore.pyqtSignal()

    def __init__(self, parent=None, icons=None):
        super().__init__(parent)
        self._icons = icons
        self._current_status = "offline"
        self._status_actions: dict[str, QtGui.QAction] = {}
        self._normal_icon = build_app_icon()
        self._popups_mode = POPUPS_SYSTEM
        self._tray = QtWidgets.QSystemTrayIcon(self._normal_icon)
        self._tray.setToolTip(APP_NAME)
        self._tray.activated.connect(self._on_activated)

        # Smooth blink: fade the icon out and back in over one period using a
        # sine curve, redrawing at ~25 fps.
        self._blink_timer = QtCore.QTimer(self)
        self._blink_timer.timeout.connect(self._blink_step)
        self._blink_active = False
        self._blink_elapsed = 0.0
        self._blink_period_ms = 1000   # full fade-out + fade-in
        self._blink_interval_ms = 40
        self._blink_pixmap = QtGui.QPixmap()

        self._menu = QtWidgets.QMenu()
        self._menu.aboutToShow.connect(self._sync_status_checks)
        self._build_menu()

    def show(self):
        self._tray.show()

    def hide(self):
        self._tray.hide()

    def set_icon(self, icon: QtGui.QIcon):
        self._normal_icon = icon
        self._blink_pixmap = QtGui.QPixmap()
        if not self._blink_active:
            self._tray.setIcon(icon)

    def set_popups_mode(self, mode) -> None:
        """Set the tray popup mode (off / system / system_messages)."""
        self._popups_mode = normalize_popups_mode(mode)

    def popups_mode(self) -> str:
        return self._popups_mode

    def show_message(self, title: str, message: str,
                     icon: QtWidgets.QSystemTrayIcon.MessageIcon =
                     QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                     duration: int = 4000, kind: str = "system"):
        """Show a tray balloon, honouring the popups mode.

        ``kind="message"`` is the incoming-message preview; it is shown only in
        the ``system_messages`` mode.  System balloons are hidden only when the
        mode is ``off``.
        """
        if self._popups_mode == POPUPS_OFF:
            return
        if kind == "message" and self._popups_mode != POPUPS_SYSTEM_MESSAGES:
            return
        self._tray.showMessage(title, message, icon, duration)

    def start_blinking(self):
        if not self._blink_active:
            self._blink_active = True
            self._blink_elapsed = 0.0
            self._blink_pixmap = self._source_pixmap()
            self._blink_timer.start(self._blink_interval_ms)

    def stop_blinking(self):
        self._blink_active = False
        self._blink_timer.stop()
        self._tray.setIcon(self._normal_icon)

    def _source_pixmap(self) -> QtGui.QPixmap:
        """The opaque icon pixmap at a sensible tray size."""
        size = self._tray.geometry().size()
        side = size.width() if size.width() > 0 else 22
        return self._normal_icon.pixmap(side, side)

    def _blink_step(self):
        """Advance the fade by one frame and repaint the tray icon."""
        self._blink_elapsed = (self._blink_elapsed
                               + self._blink_interval_ms) % self._blink_period_ms
        if self._blink_pixmap.isNull():
            self._blink_pixmap = self._source_pixmap()
        # alpha: 1.0 -> 0.0 -> 1.0 over one period (cosine, starts opaque).
        phase = self._blink_elapsed / float(self._blink_period_ms)
        alpha = 0.5 * (1.0 + math.cos(2.0 * math.pi * phase))
        if self._blink_pixmap.isNull():
            return
        faded = QtGui.QPixmap(self._blink_pixmap.size())
        faded.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(faded)
        painter.setOpacity(max(0.0, min(1.0, alpha)))
        painter.drawPixmap(0, 0, self._blink_pixmap)
        painter.end()
        self._tray.setIcon(QtGui.QIcon(faded))

    def _build_menu(self):
        self._menu.addAction(QtGui.QIcon(), tr("tray_show"), self._on_show)
        self._menu.addAction(_menu_icon("gtk-preferences.png"),
                             tr("menu_preferences"), self.settings_requested.emit)
        self._menu.addSeparator()
        for key in _STATUS_KEYS:
            icon = QtGui.QIcon()
            if self._icons is not None:
                icon = QtGui.QIcon(self._icons.get_status_icon(key))
            action = self._menu.addAction(icon, tr(f"status_{key}"))
            action.setCheckable(True)
            action.triggered.connect(lambda _=False, k=key:
                                     self.status_requested.emit(k))
            self._status_actions[key] = action
        self._menu.addSeparator()
        self._menu.addAction(QtGui.QIcon(), tr("tray_quit"),
                             self.quit_requested.emit)
        self._tray.setContextMenu(self._menu)

    def set_current_status(self, show: str):
        """Remember the active presence show for the menu checkmark."""
        self._current_status = show if show in _STATUS_KEYS else "offline"

    def _sync_status_checks(self):
        for key, action in self._status_actions.items():
            action.setChecked(key == self._current_status)

    def _on_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            self.show_requested.emit()
        elif reason == QtWidgets.QSystemTrayIcon.ActivationReason.MiddleClick:
            self.cycle_unread_requested.emit()

    def _on_show(self):
        self.show_requested.emit()
