"""Persistent vCard metadata cache with a one-hour freshness window."""
from __future__ import annotations

import json
import os
import tempfile
import time

from jabbim.include.constants import CACHE_DIR

_PATH = os.path.join(CACHE_DIR, "vcard-cache.json")
MAX_AGE = 60 * 60


class VCardCache:
    """Small JSON cache for vCard fields and avatar paths.

    Binary photos are intentionally not stored here.  ``avatars.save_avatar``
    keeps those in the XDG cache and the JSON stores only the path.
    """

    def __init__(self, path: str = _PATH):
        self.path = path
        self._items: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._items = data
        except (OSError, ValueError):
            self._items = {}

    def get(self, jid: str, max_age: float = MAX_AGE) -> dict | None:
        bare = str(jid).split("/", 1)[0]
        item = self._items.get(bare)
        if not isinstance(item, dict):
            return None
        fetched_at = float(item.get("fetched_at", 0))
        if time.time() - fetched_at > max_age:
            return None
        card = item.get("card")
        return dict(card) if isinstance(card, dict) else None

    def put(self, jid: str, card: dict) -> None:
        bare = str(jid).split("/", 1)[0]
        safe = {key: value for key, value in card.items()
                if key != "photo" and isinstance(value, (str, int, float, bool, type(None)))}
        self._items[bare] = {"fetched_at": time.time(), "card": safe}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="vcard-", dir=os.path.dirname(self.path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._items, fh, ensure_ascii=True, indent=2)
                fh.write("\n")
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
