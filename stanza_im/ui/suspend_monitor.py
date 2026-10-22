"""System suspend/resume notifications for the presence status.

The client goes offline right before the computer sleeps and restores the
status on wake (``connection.offline_on_suspend``).  The events come from
``systemd-logind`` (``PrepareForSleep``) with a ``UPower`` (``Sleeping``)
fallback for systems without logind; without a system D-Bus the monitor is a
silent no-op.
"""
from __future__ import annotations

import logging

from PyQt6 import QtCore

try:  # Qt may be built without QtDBus
    from PyQt6 import QtDBus
except ImportError:  # pragma: no cover - depends on the Qt build
    QtDBus = None

logger = logging.getLogger(__name__)

LOGIND_SERVICE = "org.freedesktop.login1"
LOGIND_PATH = "/org/freedesktop/login1"
LOGIND_INTERFACE = "org.freedesktop.login1.Manager"
LOGIND_SIGNAL = "PrepareForSleep"

UPOWER_SERVICE = "org.freedesktop.UPower"
UPOWER_PATH = "/org/freedesktop/UPower"
UPOWER_INTERFACE = "org.freedesktop.UPower"
UPOWER_SIGNAL = "Sleeping"


class SuspendMonitor(QtCore.QObject):
    """Emit ``suspending`` right before sleep and ``resumed`` on wake.

    Both logind and UPower may report the same transition; the state flag
    collapses them into one signal per edge.
    """

    suspending = QtCore.pyqtSignal()
    resumed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sleeping = False
        self._available = False
        self._connect()

    def _connect(self) -> None:
        if QtDBus is None:
            logger.debug("Suspend monitor unavailable: QtDBus is missing")
            return
        try:
            bus = QtDBus.QDBusConnection.systemBus()
        except Exception:  # noqa: BLE001 - no D-Bus is not an error
            bus = None
        if bus is None or not bus.isConnected():
            logger.debug("Suspend monitor unavailable: no system D-Bus")
            return
        self._available = self._subscribe(
            bus, LOGIND_SERVICE, LOGIND_PATH, LOGIND_INTERFACE,
            LOGIND_SIGNAL, self._on_logind)
        if not self._available:
            # Older/non-systemd systems may only expose UPower.
            self._available = self._subscribe(
                bus, UPOWER_SERVICE, UPOWER_PATH, UPOWER_INTERFACE,
                UPOWER_SIGNAL, self._on_upower)

    @staticmethod
    def _subscribe(bus, service: str, path: str, interface: str,
                   signal: str, slot) -> bool:
        try:
            ok = bus.connect(service, path, interface, signal, slot)
        except Exception:  # noqa: BLE001
            logger.debug("Could not subscribe to %s.%s", interface, signal,
                         exc_info=True)
            return False
        if ok:
            logger.debug("Suspend monitor: listening to %s.%s", interface,
                         signal)
        return bool(ok)

    def available(self) -> bool:
        """Whether a sleep notification source was found."""
        return self._available

    @QtCore.pyqtSlot(bool)
    def _on_logind(self, before_sleep: bool) -> None:
        self._set_sleeping(bool(before_sleep))

    @QtCore.pyqtSlot(bool)
    def _on_upower(self, sleeping: bool) -> None:
        self._set_sleeping(bool(sleeping))

    def _set_sleeping(self, sleeping: bool) -> None:
        if sleeping == self._sleeping:
            return
        self._sleeping = sleeping
        if sleeping:
            self.suspending.emit()
        else:
            self.resumed.emit()
