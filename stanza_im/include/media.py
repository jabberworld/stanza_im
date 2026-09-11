"""Media preview helpers: URL kind detection and an on-disk preview cache.

Originals and generated thumbnails live in ``$XDG_CACHE_HOME/stanza-im/media/``
(``<sha1>.orig`` / ``<sha1>.thumb.png``) together with an ``index.json`` that
tracks the last access time and file sizes.  Unused previews are evicted by a
TTL and a total-size (LRU) cap.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from urllib.parse import unquote, urlsplit

from stanza_im.include.constants import CACHE_DIR

logger = logging.getLogger(__name__)

MEDIA_DIR = os.path.join(CACHE_DIR, "media")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
              ".svgz", ".tif", ".tiff", ".ico", ".avif", ".heic"}
AUDIO_EXTS = {".mp3", ".ogg", ".oga", ".opus", ".wav", ".m4a", ".aac",
              ".flac", ".weba", ".mka"}
VIDEO_EXTS = {".mp4", ".webm", ".ogv", ".mkv", ".mov", ".avi", ".m4v",
              ".mpeg", ".mpg", ".ts", ".3gp"}


def url_path(url: str) -> str:
    """Return the URL path component (query/fragment stripped)."""
    try:
        return urlsplit(url).path or ""
    except ValueError:
        return url or ""


def url_extension(url: str) -> str:
    """Lower-cased file extension of *url*'s path ('' when unknown)."""
    return os.path.splitext(unquote(url_path(url)))[1].lower()


def media_kind(url: str) -> str | None:
    """Classify *url* as ``"image"``, ``"audio"``, ``"video"`` or ``None``."""
    ext = url_extension(url)
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def url_key(url: str) -> str:
    """Stable cache key (SHA-1) for *url*."""
    return hashlib.sha1(str(url).encode("utf-8", "replace")).hexdigest()


def filename_from_url(url: str, default: str = "file") -> str:
    """Best-effort original filename for a URL (used by "Save as...")."""
    name = os.path.basename(unquote(url_path(url)))
    return name or default


class MediaCache:
    """Disk-backed cache for media originals and thumbnails."""

    def __init__(self, directory: str = MEDIA_DIR, ttl_days: float = 30.0,
                 max_bytes: int = 128 * 1024 * 1024):
        self._dir = directory
        self._index_file = os.path.join(directory, "index.json")
        self._ttl = max(0.0, float(ttl_days)) * 86400.0
        self._max_bytes = max(0, int(max_bytes))
        self._index: dict[str, dict] = {}
        self._dirty = False
        self._load()

    # ── Configuration ─────────────────────────────────────────────

    def set_limits(self, ttl_days: float, max_bytes: int) -> None:
        self._ttl = max(0.0, float(ttl_days)) * 86400.0
        self._max_bytes = max(0, int(max_bytes))

    @property
    def directory(self) -> str:
        return self._dir

    # ── Internal paths / index ────────────────────────────────────

    def _original_path(self, key: str) -> str:
        return os.path.join(self._dir, key + ".orig")

    def _thumb_path(self, key: str) -> str:
        return os.path.join(self._dir, key + ".thumb.png")

    def _load(self) -> None:
        try:
            with open(self._index_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self._index = {k: v for k, v in data.items()
                           if isinstance(v, dict)}

    def _save_index(self) -> None:
        if not self._dirty:
            return
        try:
            os.makedirs(self._dir, exist_ok=True)
            tmp = self._index_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._index, fh)
            os.replace(tmp, self._index_file)
            self._dirty = False
        except OSError as exc:
            logger.warning("Could not write media index: %s", exc)

    def _entry_size(self, key: str) -> int:
        total = 0
        for path in (self._original_path(key), self._thumb_path(key)):
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        return total

    def _delete_entry(self, key: str) -> None:
        for path in (self._original_path(key), self._thumb_path(key)):
            try:
                os.remove(path)
            except OSError:
                pass
        self._index.pop(key, None)

    # ── Lookups ───────────────────────────────────────────────────

    def has_thumb(self, url: str) -> bool:
        return self.thumb_path(url) is not None

    def thumb_path(self, url: str) -> str | None:
        key = url_key(url)
        entry = self._index.get(key)
        if not entry or not entry.get("thumb"):
            return None
        path = self._thumb_path(key)
        if not os.path.isfile(path):
            return None
        self._touch(key)
        return path

    def original_path(self, url: str) -> str | None:
        key = url_key(url)
        entry = self._index.get(key)
        if not entry or not entry.get("original"):
            return None
        path = self._original_path(key)
        if not os.path.isfile(path):
            return None
        self._touch(key)
        return path

    def _touch(self, key: str) -> None:
        entry = self._index.get(key)
        if entry is not None:
            entry["last_access"] = time.time()
            self._dirty = True

    def touch(self, url: str) -> None:
        self._touch(url_key(url))

    # ── Store ─────────────────────────────────────────────────────

    def store(self, url: str, original_bytes: bytes | None = None,
              thumb_bytes: bytes | None = None, mime: str = "",
              kind: str = "") -> str | None:
        """Persist originals/thumbnails for *url*; returns the written path."""
        try:
            os.makedirs(self._dir, exist_ok=True)
        except OSError as exc:
            logger.warning("Could not create media cache dir: %s", exc)
            return None
        key = url_key(url)
        entry = self._index.get(key) or {}
        entry["url"] = url
        if kind:
            entry["kind"] = kind
        if mime:
            entry["mime"] = mime
        written = None
        if original_bytes is not None:
            path = self._original_path(key)
            with open(path, "wb") as fh:
                fh.write(original_bytes)
            entry["original"] = True
            entry["size"] = len(original_bytes)
            written = path
        if thumb_bytes is not None:
            path = self._thumb_path(key)
            with open(path, "wb") as fh:
                fh.write(thumb_bytes)
            entry["thumb"] = True
            written = path
        entry["last_access"] = time.time()
        self._index[key] = entry
        self._dirty = True
        self._enforce_size()
        self._save_index()
        return written

    # ── Eviction ──────────────────────────────────────────────────

    def total_bytes(self) -> int:
        return sum(self._entry_size(key) for key in self._index)

    def prune(self) -> int:
        """Drop entries unused longer than the TTL and enforce the size cap."""
        removed = 0
        if self._ttl > 0:
            now = time.time()
            for key, entry in list(self._index.items()):
                try:
                    last = float(entry.get("last_access") or 0)
                except (TypeError, ValueError):
                    last = 0.0
                if now - last > self._ttl:
                    self._delete_entry(key)
                    removed += 1
        removed += self._enforce_size()
        self._dirty = True
        self._save_index()
        return removed

    def _enforce_size(self) -> int:
        if self._max_bytes <= 0:
            return 0
        total = self.total_bytes()
        if total <= self._max_bytes:
            return 0
        removed = 0
        for key, entry in sorted(
                self._index.items(),
                key=lambda kv: float(kv[1].get("last_access") or 0)):
            if total <= self._max_bytes:
                break
            total -= self._entry_size(key)
            self._delete_entry(key)
            removed += 1
        if removed:
            self._dirty = True
        return removed
