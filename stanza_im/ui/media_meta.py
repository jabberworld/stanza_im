"""Background media metadata for the history media calendar.

Extracts duration (audio/video) and a first-frame thumbnail (video) without
blocking the UI.  PyAV is optional (installed by the ``calls`` extra); without
it the calendar still works, cards simply keep their generic placeholder and
no duration.  ``aesgcm://`` files are downloaded/decrypted first through the
shared preview service and cached as originals.
"""
from __future__ import annotations

import base64
import logging
import queue
import threading

from PyQt6 import QtCore, QtGui

from stanza_im.include import media as media_mod

logger = logging.getLogger(__name__)


class MediaMetadataService(QtCore.QObject):
    """Serial background worker for video thumbnails and media duration."""

    meta_ready = QtCore.pyqtSignal(str, float, str)  # url, seconds, png data-URI
    failed = QtCore.pyqtSignal(str)

    def __init__(self, cache: media_mod.MediaCache, downloader=None,
                 parent=None):
        super().__init__(parent)
        self._cache = cache
        self._downloader = downloader
        self._queue: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._pending: set[str] = set()
        self._thread: threading.Thread | None = None
        self._available: bool | None = None

    def request(self, url: str, kind: str) -> None:
        """Queue metadata extraction for *url* (idempotent)."""
        if not url or kind not in ("audio", "video") or url in self._pending:
            return
        info = self._cache.info(url)
        thumb = self._cache.thumb_path(url) if kind == "video" else None
        duration = float(info.get("duration") or 0.0)
        if duration and (kind != "video" or thumb):
            uri = self._thumb_uri(thumb) if thumb else ""
            QtCore.QTimer.singleShot(
                0, lambda: self.meta_ready.emit(url, duration, uri))
            return
        self._pending.add(url)
        self._ensure_thread()
        self._queue.put((url, kind))

    def shutdown(self) -> None:
        self._queue.put(None)

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            url, kind = item
            try:
                duration, thumb = self._probe(url, kind)
                if duration or thumb:
                    self._cache.store(
                        url, original_bytes=None, thumb_bytes=thumb or None,
                        kind=kind, duration=duration)
                uri = self._thumb_uri(self._cache.thumb_path(url))
                self.meta_ready.emit(url, float(duration or 0.0), uri)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Media metadata failed for %s: %s", url, exc)
                self.failed.emit(url)
            finally:
                self._pending.discard(url)

    def _local_source(self, url: str) -> str:
        path = self._cache.original_path(url)
        if path:
            return path
        if url.startswith("aesgcm://") and self._downloader is not None:
            raw = self._downloader._download(url)
            path = self._cache.store(url, original_bytes=raw, kind="file")
            if path:
                return path
        return url

    def _probe(self, url: str, kind: str) -> tuple[float, bytes]:
        try:
            import av
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.info("Video metadata unavailable (PyAV missing): %s", exc)
            return 0.0, b""
        source = self._local_source(url)
        container = av.open(source)
        try:
            duration = 0.0
            if container.duration:
                duration = float(container.duration) / float(av.time_base)
            if not duration:
                for stream in container.streams:
                    if stream.duration and stream.time_base:
                        duration = float(stream.duration * stream.time_base)
                        break
            thumb = b""
            if kind == "video":
                stream = next((s for s in container.streams
                               if s.type == "video"), None)
                if stream is not None:
                    frame = next(container.decode(stream), None)
                    if frame is not None:
                        thumb = self._frame_png(frame)
            return max(0.0, duration), thumb
        finally:
            container.close()

    @staticmethod
    def _frame_png(frame) -> bytes:
        rgb = frame.to_rgb()
        plane = rgb.planes[0]
        image = QtGui.QImage(
            bytes(plane), rgb.width, rgb.height, plane.line_size,
            QtGui.QImage.Format.Format_RGB888).copy()
        if image.width() > 320 or image.height() > 240:
            image = image.scaled(
                320, 240, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            return b""
        return bytes(buffer.data())

    @staticmethod
    def _thumb_uri(path: str | None) -> str:
        if not path:
            return ""
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError:
            return ""
        return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
