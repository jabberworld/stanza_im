"""Per-profile key/value storage for the OMEMO library.

``python-omemo`` persists all of its state through a ``Storage`` implementation
(JSON-compatible values keyed by string).  We back it with a single JSON file in
the active profile's data directory (``<DATA_DIR>/<jid>/omemo.json``, 0600), so
each account keeps its own identity, sessions and trust decisions.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading

from omemo.storage import Just, Maybe, Nothing, Storage
from omemo.types import JSONType

logger = logging.getLogger("stanza_im.omemo")

_FILE = "omemo.json"


def storage_path(data_dir: str) -> str:
    """Path of the OMEMO store inside a profile data directory."""
    return os.path.join(data_dir, _FILE)


class OmemoStorage(Storage):
    """JSON-file backed :class:`omemo.storage.Storage`."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path
        self._lock = threading.RLock()
        self._data: dict[str, JSONType] = self._read()

    # ── file helpers ────────────────────────────────────────────

    def _read(self) -> dict[str, JSONType]:
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read OMEMO store %s: %s", self._path, exc)
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False)
            os.replace(tmp, self._path)
            os.chmod(self._path, 0o600)
        except OSError as exc:
            logger.warning("Could not write OMEMO store %s: %s", self._path, exc)

    # ── Storage API ─────────────────────────────────────────────

    async def _load(self, key: str) -> Maybe[JSONType]:
        def _do() -> Maybe[JSONType]:
            with self._lock:
                if key in self._data:
                    return Just(self._data[key])
                return Nothing()

        return await asyncio.to_thread(_do)

    async def _store(self, key: str, value: JSONType) -> None:
        def _do() -> None:
            with self._lock:
                self._data[key] = value
                self._write()

        await asyncio.to_thread(_do)

    async def _delete(self, key: str) -> None:
        def _do() -> None:
            with self._lock:
                self._data.pop(key, None)
                self._write()

        await asyncio.to_thread(_do)

    # ── app-level helpers (non-OMEMO keys) ──────────────────────

    def get_app(self, key: str, default=None):
        """Read an application key (stored next to the OMEMO state)."""
        with self._lock:
            return self._data.get("stanza_im:" + key, default)

    def set_app(self, key: str, value) -> None:
        """Write an application key (e.g. per-chat encryption mode)."""
        with self._lock:
            self._data["stanza_im:" + key] = value
            self._write()
