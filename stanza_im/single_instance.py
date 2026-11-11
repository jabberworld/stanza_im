"""One running Stanza IM instance per user, with local URI forwarding.

The second process forwards ``xmpp:`` URIs (and a "raise" request) to the
already running process through a QLocalServer/QLocalSocket pair.  Tokens are
never written to logs; the payload is intentionally small and validated.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile

from PyQt6 import QtCore, QtNetwork

from stanza_im.include.constants import PROJECT_ROOT

logger = logging.getLogger(__name__)

MAX_PAYLOAD = 64 * 1024


def socket_name() -> str:
    """Return the per-user local-socket name (creating its directory)."""
    uid = getattr(os, "getuid", lambda: 0)()
    digest = hashlib.sha1(
        os.path.abspath(PROJECT_ROOT).encode("utf-8")).hexdigest()[:10]
    if sys.platform.startswith("win"):
        return f"stanza-im-{uid}-{digest}"
    runtime = QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.StandardLocation.RuntimeLocation)
    if runtime:
        directory = os.path.join(runtime, "stanza-im")
    else:
        directory = os.path.join(
            tempfile.gettempdir(), f"stanza-im-{uid}")
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
    except OSError:
        directory = os.path.join(
            tempfile.gettempdir(), f"stanza-im-{uid}")
        try:
            os.makedirs(directory, mode=0o700, exist_ok=True)
        except OSError:
            pass
    return os.path.join(directory, f"socket-{uid}.sock")


def encode_payload(uris, raise_window: bool = True) -> bytes:
    """Serialise a validated forwarding request (newline-terminated)."""
    clean = [str(uri) for uri in (uris or ())
             if isinstance(uri, str) and uri.lower().startswith("xmpp:")]
    data = json.dumps({"uris": clean, "raise": bool(raise_window)},
                      ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_PAYLOAD:
        raise ValueError("forwarding payload is too large")
    return data + b"\n"


def decode_payload(data: bytes) -> tuple[list[str], bool] | None:
    """Validate a forwarding payload; return ``(uris, raise_window)``."""
    try:
        if not data or len(data) > MAX_PAYLOAD:
            return None
        payload = json.loads(data.decode("utf-8").strip())
        if not isinstance(payload, dict):
            return None
        uris = [str(uri) for uri in (payload.get("uris") or ())
                if isinstance(uri, str) and uri.lower().startswith("xmpp:")]
        return uris, bool(payload.get("raise", True))
    except (UnicodeDecodeError, ValueError, TypeError):
        return None


class SingleInstance(QtCore.QObject):
    """Own the local socket in the first instance and forward from later ones."""

    uris_received = QtCore.pyqtSignal(list, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server: QtNetwork.QLocalServer | None = None
        self._clients: set[QtNetwork.QLocalSocket] = set()
        self._buffers: dict[QtNetwork.QLocalSocket, bytes] = {}

    def forward(self, uris, raise_window: bool = True,
                timeout_ms: int = 1200) -> bool:
        """Send a request to the running instance; False when none is running."""
        try:
            payload = encode_payload(uris, raise_window)
        except ValueError:
            return False
        sock = QtNetwork.QLocalSocket(self)
        sock.connectToServer(socket_name())
        if not sock.waitForConnected(timeout_ms):
            return False
        try:
            sock.write(payload)
            sock.flush()
            sock.waitForBytesWritten(timeout_ms)
            sock.disconnectFromServer()
        except Exception:  # noqa: BLE001 - forwarding is best effort
            logger.debug("Could not forward to the running instance",
                         exc_info=True)
        sock.deleteLater()
        return True

    def listen(self) -> bool:
        """Become the primary instance; False when the socket is unavailable."""
        if self._server is not None:
            return True
        name = socket_name()
        server = QtNetwork.QLocalServer(self)
        if not server.listen(name):
            # Only remove a socket that nobody answers on; blindly unlinking
            # an active first instance would start a second process.
            probe = QtNetwork.QLocalSocket()
            probe.connectToServer(name)
            if probe.waitForConnected(150):
                probe.abort()
                server.deleteLater()
                return False
            probe.abort()
            if not sys.platform.startswith("win"):
                try:
                    QtNetwork.QLocalServer.removeServer(name)
                except Exception:  # noqa: BLE001 - stale socket is best effort
                    pass
            if not server.listen(name):
                logger.debug("Single-instance listen failed: %s",
                             server.errorString())
                server.deleteLater()
                return False
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        return True

    def close(self) -> None:
        for sock in list(self._clients):
            try:
                sock.abort()
            except Exception:  # noqa: BLE001
                pass
        self._clients.clear()
        self._buffers.clear()
        if self._server is not None:
            name = self._server.fullServerName()
            self._server.close()
            self._server.deleteLater()
            self._server = None
            if name and not sys.platform.startswith("win"):
                try:
                    QtNetwork.QLocalServer.removeServer(name)
                except Exception:  # noqa: BLE001
                    pass

    def _on_new_connection(self) -> None:
        while (self._server is not None
               and self._server.hasPendingConnections()):
            sock = self._server.nextPendingConnection()
            if sock is None:
                continue
            self._clients.add(sock)
            self._buffers[sock] = b""
            sock.readyRead.connect(
                lambda s=sock: self._read_socket(s))
            sock.disconnected.connect(
                lambda s=sock: self._drop_socket(s))
            if sock.bytesAvailable():
                self._read_socket(sock)

    def _read_socket(self, sock: QtNetwork.QLocalSocket) -> None:
        if sock not in self._clients:
            return
        try:
            data = bytes(sock.readAll().data())
        except Exception:  # noqa: BLE001
            data = b""
        buffer = self._buffers.get(sock, b"") + data
        if len(buffer) > MAX_PAYLOAD:
            logger.debug("Oversized forwarding request ignored")
            self._drop_socket(sock, abort=True)
            return
        self._buffers[sock] = buffer
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            self._buffers[sock] = buffer
            parsed = decode_payload(line)
            if parsed is not None:
                uris, raise_window = parsed
                self.uris_received.emit(uris, raise_window)
        if not buffer:
            try:
                sock.disconnectFromServer()
            except Exception:  # noqa: BLE001
                pass

    def _drop_socket(self, sock: QtNetwork.QLocalSocket,
                     abort: bool = False) -> None:
        self._buffers.pop(sock, None)
        self._clients.discard(sock)
        try:
            if abort:
                sock.abort()
            else:
                sock.deleteLater()
        except Exception:  # noqa: BLE001
            pass
