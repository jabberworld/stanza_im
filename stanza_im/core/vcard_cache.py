"""Persistent vCard metadata cache with a one-hour freshness window."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time

from stanza_im.include.constants import CACHE_DIR

_PATH = os.path.join(CACHE_DIR, "vcard-cache.json")
MAX_AGE = 3 * 24 * 60 * 60
# Roster refresh is deliberately slow: XEP-0153 photo hashes and explicit
# vCard refresh keep avatars current without refetching every login.
_FLUSH_DELAY = 1.0
_CARD_VERSION = 3


class VCardCache:
    """Small JSON cache for vCard fields and avatar paths.

    Binary photos are intentionally not stored here.  ``avatars.save_avatar``
    keeps those in the XDG cache and the JSON stores only the path.
    """

    def __init__(self, path: str = _PATH):
        self.path = path
        self._items: dict[str, dict] = {}
        self._dirty = False
        self._timer: threading.Timer | None = None
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._items = data
        except (OSError, ValueError):
            self._items = {}

    def clear(self) -> None:
        """Forget every cached card and remove the backing file."""
        with self._lock:
            self._items = {}
            self._dirty = False
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()
        try:
            os.remove(self.path)
        except OSError:
            pass

    @staticmethod
    def _key(jid: str) -> str:
        value = str(jid)
        bare, separator, resource = value.partition("/")
        # MUC virtual JIDs identify a specific occupant and must retain nick.
        return value if separator and "@" in bare else bare

    def get(self, jid: str, max_age: float = MAX_AGE) -> dict | None:
        item = self._items.get(self._key(jid))
        if not isinstance(item, dict):
            return None
        fetched_at = float(item.get("fetched_at", 0))
        if time.time() - fetched_at > max_age:
            return None
        card = item.get("card")
        if not isinstance(card, dict):
            return None
        if int(item.get("version", 0)) < _CARD_VERSION:
            return None
        result = dict(card)
        result.setdefault("fetched_at", fetched_at)
        return result

    def put(self, jid: str, card: dict, defer: bool = False) -> None:
        """Store a card; *defer* batches the JSON rewrite.

        The client receives hundreds of cards during a roster refresh.  Writing
        the whole growing JSON file after each one is quadratic and blocks the
        GUI thread, so the network path defers and a single background flush
        persists the batch.  Tests and explicit callers keep the immediate file
        write (``defer=False``).
        """
        bare = self._key(jid)
        safe = {key: value for key, value in card.items()
                if key != "photo" and isinstance(value, (str, int, float, bool, type(None)))}
        with self._lock:
            self._items[bare] = {"version": _CARD_VERSION,
                                 "fetched_at": time.time(), "card": safe}
            self._dirty = True
            if not defer:
                timer, self._timer = self._timer, None
                if timer is not None:
                    timer.cancel()
                self._write_locked()
                return
            if self._timer is None:
                timer = threading.Timer(_FLUSH_DELAY, self.flush)
                timer.daemon = True
                self._timer = timer
                timer.start()

    def _write_locked(self) -> None:
        if not self._dirty:
            return
        snapshot = self._items
        self._dirty = False
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="vcard-", dir=os.path.dirname(self.path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, ensure_ascii=True, indent=2)
                fh.write("\n")
            os.replace(tmp, self.path)
        except OSError:
            self._dirty = True
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def flush(self) -> None:
        """Persist a deferred batch now (also used on logout/shutdown)."""
        with self._lock:
            timer, self._timer = self._timer, None
            if timer is not None:
                timer.cancel()
            self._write_locked()
