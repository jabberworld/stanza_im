"""System tray icon with context menu and notification blinking."""
from __future__ import annotations

import os

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import (
    ACTIONS_DIR_16, APP_ICON_16, APP_ICON_22, APP_ICON_32, APP_ICON_48,
    APP_ICON_SVG, APP_NAME, CATEGORIES_DIR_16, PLACES_DIR_22, STATUS_DIR_32,
)

_STATUS_KEYS = ("online", "chat", "away", "xa", "dnd", "offline")


def _menu_icon(filename: str) -> QtGui.QIcon:
    """Load an action/category/status icon for menus from resources."""
    for directory in (ACTIONS_DIR_16, CATEGORIES_DIR_16, STATUS_DIR_32,
                      PLACES_DIR_22):
        pix = QtGui.QPixmap(os.path.join(directory, filename))
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

    def __init__(self, parent=None, icons=None):
        super().__init__(parent)
        self._icons = icons
        self._current_status = "offline"
        self._status_actions: dict[str, QtGui.QAction] = {}
        self._normal_icon = build_app_icon()
        self._tray = QtWidgets.QSystemTrayIcon(self._normal_icon)
        self._tray.setToolTip(APP_NAME)
        self._tray.activated.connect(self._on_activated)

        self._blink_timer = QtCore.QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_visible = True
        self._blink_active = False

        self._menu = QtWidgets.QMenu()
        self._menu.aboutToShow.connect(self._sync_status_checks)
        self._build_menu()

    def show(self):
        self._tray.show()

    def hide(self):
        self._tray.hide()

    def set_icon(self, icon: QtGui.QIcon):
        self._normal_icon = icon
        if not self._blink_active:
            self._tray.setIcon(icon)

    def show_message(self, title: str, message: str,
                     icon: QtWidgets.QSystemTrayIcon.MessageIcon =
                     QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                     duration: int = 4000):
        self._tray.showMessage(title, message, icon, duration)

    def start_blinking(self):
        if not self._blink_active:
            self._blink_active = True
            self._blink_timer.start(500)

    def stop_blinking(self):
        self._blink_active = False
        self._blink_timer.stop()
        self._tray.setIcon(self._normal_icon)

    def _toggle_blink(self):
        self._blink_visible = not self._blink_visible
        if self._blink_visible:
            self._tray.setIcon(self._normal_icon)
        else:
            self._tray.setIcon(QtGui.QIcon())

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

    def _on_show(self):
        self.show_requested.emit()
