"""System tray icon with context menu and notification blinking."""
from __future__ import annotations

import os

from PyQt6 import QtCore, QtGui, QtWidgets

from jabbim.i18n import tr
from jabbim.include.constants import (
    APP_ICON_16, APP_ICON_22, APP_ICON_32, APP_ICON_48, APP_ICON_SVG,
)


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
        path = os.path.join(base_dir, "jabbim.png")
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._normal_icon = build_app_icon()
        self._tray = QtWidgets.QSystemTrayIcon(self._normal_icon)
        self._tray.setToolTip("Jabbim-next")
        self._tray.activated.connect(self._on_activated)

        self._blink_timer = QtCore.QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_visible = True
        self._blink_active = False

        self._menu = QtWidgets.QMenu()
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
        self._menu.addSeparator()
        self._menu.addAction(QtGui.QIcon(), tr("tray_quit"), self.quit_requested.emit)
        self._tray.setContextMenu(self._menu)

    def _on_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            self.show_requested.emit()

    def _on_show(self):
        self.show_requested.emit()
