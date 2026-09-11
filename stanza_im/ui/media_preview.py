"""Media preview service: markup generation and async thumbnail fetching.

The service decides, for a given URL and the configured *mode*, whether to
replace its plain link with an embedded preview (image) or player (audio /
video).  Image originals are downloaded in a worker thread, resized to the
configured preview size and cached on disk; the resulting PNG is handed to the
chat page as a data-URI (no local-file access needed).
"""
from __future__ import annotations

import asyncio
import base64
import html
import logging
from urllib.parse import quote

from PyQt6 import QtCore, QtGui

from stanza_im.i18n import tr
from stanza_im.include import media as media_mod

logger = logging.getLogger(__name__)

MODES = ("none", "images", "images_audio", "all")

__all__ = ["MODES", "mode_allows", "MediaPreviewService"]


def mode_allows(mode: str, kind: str) -> bool:
    """Return True when *kind* should be previewed under *mode*."""
    if mode == "all":
        return kind in ("image", "audio", "video")
    if mode == "images_audio":
        return kind in ("image", "audio")
    if mode == "images":
        return kind == "image"
    return False


class MediaPreviewService(QtCore.QObject):
    """Owns the preview policy, the download/thumbnail workers and the cache."""

    thumbnail_ready = QtCore.pyqtSignal(str, str)  # url, png data-URI
    failed = QtCore.pyqtSignal(str)                # url

    MAX_DOWNLOAD = 64 * 1024 * 1024
    _UA = "StanzaIM/1.0 (media preview)"

    def __init__(self, cache: media_mod.MediaCache, parent=None):
        super().__init__(parent)
        self._cache = cache
        self._mode = "images"
        self._size = 200
        self._pending: set[str] = set()
        self._thumb_uris: dict[str, str] = {}

    # ── Policy ────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        self._mode = mode if mode in MODES else "images"

    def set_size(self, size) -> None:
        try:
            size = int(size or 200)
        except (TypeError, ValueError):
            size = 200
        self._size = max(32, min(1024, size))
        self._thumb_uris.clear()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def size(self) -> int:
        return self._size

    @property
    def cache(self) -> media_mod.MediaCache:
        return self._cache

    def previewable(self, url: str) -> str | None:
        kind = media_mod.media_kind(url)
        if kind and mode_allows(self._mode, kind):
            return kind
        return None

    # ── Markup ────────────────────────────────────────────────────

    def cached_thumb_uri(self, url: str) -> str | None:
        uri = self._thumb_uris.get(url)
        if uri is not None:
            return uri
        path = self._cache.thumb_path(url)
        if not path:
            return None
        uri = self._file_data_uri(path)
        if uri:
            self._thumb_uris[url] = uri
        return uri

    def markup(self, url: str) -> str | None:
        """Return embed HTML for *url*, or ``None`` to keep the plain link."""
        kind = self.previewable(url)
        if not kind:
            return None
        data = html.escape(url, quote=True)
        enc = quote(url, safe="")
        if kind == "image":
            uri = self.cached_thumb_uri(url)
            if uri:
                return (
                    f'<a class="stanza-media stanza-media-image" '
                    f'href="stanza:view:image/{enc}" data-media-url="{data}">'
                    f'<img class="stanza-media-thumb" data-media-url="{data}" '
                    f'src="{uri}" width="{self._size}" alt=""></a>')
            self.request(url)
            return (
                f'<a class="stanza-media stanza-media-image stanza-media-loading" '
                f'href="stanza:view:image/{enc}" data-media-url="{data}">'
                f'<img class="stanza-media-thumb" data-media-url="{data}" '
                f'width="{self._size}" alt=""></a>')
        if kind == "audio":
            return (
                f'<span class="stanza-media stanza-media-audio">'
                f'<audio controls preload="metadata" src="{data}" '
                f'data-media-url="{data}"></audio></span>')
        width = min(max(self._size, 160), 480)
        return (
            f'<span class="stanza-media stanza-media-video">'
            f'<video controls preload="metadata" src="{data}" '
            f'data-media-url="{data}" width="{width}"></video>'
            f'<a class="stanza-media-open" href="stanza:view:video/{enc}">'
            f'{html.escape(tr("media_open_viewer"))}</a></span>')

    # ── Download / thumbnail ──────────────────────────────────────

    def request(self, url: str) -> None:
        """Queue a thumbnail download for an image URL (idempotent)."""
        if url in self._pending or self._cache.has_thumb(url):
            return
        self._pending.add(url)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(self._fetch(url))
        else:
            import threading
            threading.Thread(target=self._fetch_thread, args=(url,),
                             daemon=True).start()

    async def _fetch(self, url: str) -> None:
        try:
            raw = await asyncio.to_thread(self._download, url)
            thumb = await asyncio.to_thread(self._make_thumb, raw)
            self._cache.store(url, original_bytes=raw, thumb_bytes=thumb,
                              kind="image")
            uri = self._data_uri(thumb)
            self._thumb_uris[url] = uri
            self.thumbnail_ready.emit(url, uri)
        except Exception as exc:  # noqa: BLE001 - reported via signal
            logger.debug("media preview failed for %s: %s", url, exc)
            self.failed.emit(url)
        finally:
            self._pending.discard(url)

    def _fetch_thread(self, url: str) -> None:
        try:
            raw = self._download(url)
            thumb = self._make_thumb(raw)
            self._cache.store(url, original_bytes=raw, thumb_bytes=thumb,
                              kind="image")
            uri = self._data_uri(thumb)
            self._thumb_uris[url] = uri
            QtCore.QTimer.singleShot(
                0, lambda: self.thumbnail_ready.emit(url, uri))
        except Exception as exc:  # noqa: BLE001
            logger.debug("media preview failed for %s: %s", url, exc)
            QtCore.QTimer.singleShot(0, lambda: self.failed.emit(url))
        finally:
            self._pending.discard(url)

    def _download(self, url: str) -> bytes:
        import urllib.request
        request = urllib.request.Request(url, headers={"User-Agent": self._UA})
        with urllib.request.urlopen(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            if length:
                try:
                    if int(length) > self.MAX_DOWNLOAD:
                        raise RuntimeError("file too large")
                except ValueError:
                    pass
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.MAX_DOWNLOAD:
                    raise RuntimeError("file too large")
                chunks.append(chunk)
            return b"".join(chunks)

    def _make_thumb(self, raw: bytes) -> bytes:
        image = QtGui.QImage()
        if not image.loadFromData(raw):
            raise RuntimeError("unsupported image data")
        size = self._size
        if image.width() > size or image.height() > size:
            image = image.scaled(
                size, size,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
        buf = QtCore.QBuffer()
        buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buf, "PNG"):
            raise RuntimeError("could not encode thumbnail")
        return bytes(buf.data())

    # ── Originals (viewer / "Save as...") ─────────────────────────

    async def ensure_original(self, url: str) -> str | None:
        path = self._cache.original_path(url)
        if path:
            return path
        raw = await asyncio.to_thread(self._download, url)
        return self._cache.store(url, original_bytes=raw)

    def ensure_original_async(self, url: str, on_ready, on_error=None) -> None:
        """Resolve the cached original without blocking the UI thread."""
        path = self._cache.original_path(url)
        if path:
            on_ready(path)
            return

        def _work():
            try:
                raw = self._download(url)
                resolved = self._cache.store(url, original_bytes=raw)
                QtCore.QTimer.singleShot(0, lambda: on_ready(resolved))
            except Exception as exc:  # noqa: BLE001
                if on_error is not None:
                    QtCore.QTimer.singleShot(0, lambda: on_error(exc))

        import threading
        threading.Thread(target=_work, daemon=True).start()

    @staticmethod
    def _data_uri(raw: bytes) -> str:
        return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")

    @staticmethod
    def _file_data_uri(path: str) -> str | None:
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            return None
        return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
