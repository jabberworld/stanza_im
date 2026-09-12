"""Background discovery of file-transfer proxies and STUN/TURN servers.

File-transfer proxies are found with XEP-0065 service discovery
(``category='proxy' type='bytestreams'``); STUN/TURN servers are found via
SRV records (``_stun``/``_stuns``/``_turn``/``_turns`` over TCP/UDP) for the
account domain.  Both results are cached in a JSON file under the XDG cache
directory for a day so reconnecting does not repeat the lookups.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time

from stanza_im.include.constants import CACHE_DIR

try:  # optional dependency: SRV discovery degrades gracefully without it
    import aiodns  # type: ignore
    HAS_AIODNS = True
except Exception:  # pragma: no cover - import guard
    aiodns = None  # type: ignore
    HAS_AIODNS = False

logger = logging.getLogger(__name__)

CACHE_PATH = os.path.join(CACHE_DIR, "discovery.json")
MAX_AGE = 24 * 60 * 60
# Negative (nothing found) results are cached only briefly so a transient
# failure or an offline start is retried on the next connection.
NEGATIVE_MAX_AGE = 10 * 60

# Query order: encrypted variants first, and TURN before STUN within each
# encryption class (TURN can relay traffic, STUN only discovers addresses).
SRV_SERVICES = (
    "_turns._tcp",
    "_stuns._tcp",
    "_turn._tcp",
    "_turn._udp",
    "_stun._tcp",
    "_stun._udp",
)


class DiscoveryCache:
    """Small JSON cache with per-section freshness."""

    def __init__(self, path: str = CACHE_PATH):
        self.path = path
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._data = data
        except (OSError, ValueError):
            self._data = {}

    def get(self, key: str, max_age: float = MAX_AGE,
            negative_max_age: float = NEGATIVE_MAX_AGE):
        """Return ``(True, value)`` for a fresh entry, else ``(False, None)``.

        Positive results live for *max_age*; a cached negative result (empty)
        expires after the shorter *negative_max_age* so it is retried sooner.
        """
        entry = self._data.get(key)
        if not isinstance(entry, dict):
            return False, None
        limit = max_age if entry.get("ok", True) else negative_max_age
        if time.time() - float(entry.get("fetched_at", 0)) > limit:
            return False, None
        return True, entry.get("value")

    def put(self, key: str, value) -> None:
        self._data[key] = {"fetched_at": time.time(), "value": value,
                           "ok": bool(value)}
        self._save()

    def _save(self) -> None:
        directory = os.path.dirname(self.path)
        try:
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix="discovery-", dir=directory)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=True, indent=2)
            os.replace(tmp, self.path)
        except OSError as exc:
            logger.warning("Could not save discovery cache: %s", exc)


def effective_endpoint(mode: str, manual: str, auto) -> str | None:
    """Return the endpoint to use, or ``None`` for a direct connection.

    The four combinations:
      1. auto + found           -> the discovered endpoint
      2. auto + not found       -> None (direct)
      3. manual + field filled  -> the manual value (auto is ignored)
      4. manual + field empty   -> None (direct)
    """
    if mode == "manual":
        value = (manual or "").strip()
        return value or None
    if not auto:
        return None
    if isinstance(auto, dict):
        host = auto.get("host")
        port = auto.get("port")
        return f"{host}:{port}" if host and port else None
    return str(auto)


async def discover_file_proxy(xmpp) -> dict | None:
    """Return ``{"jid", "host", "port"}`` for an announced XEP-0065 proxy.

    Only proxies that explicitly advertise the
    ``category='proxy' type='bytestreams'`` identity are used.
    """
    try:
        plugin = xmpp["xep_0065"]
        proxies = await plugin.discover_proxies()
        if not proxies:
            logger.info("No XEP-0065 bytestream proxy announced by the server")
            return None
        # slixmpp keys the mapping by JID, which is not orderable; sort by
        # string to pick a stable entry.
        jid = sorted(proxies, key=str)[0]
        host, port = proxies[jid]
        logger.info("File-transfer proxy: %s (%s:%s)", jid, host, port)
        return {"jid": str(jid), "host": str(host), "port": int(port)}
    except Exception as exc:
        logger.warning("File-transfer proxy discovery failed: %s", exc)
        return None


def _srv_to_dict(service: str, answer) -> list[dict]:
    entries: list[dict] = []
    for record in answer:
        host = getattr(record, "host", None)
        port = getattr(record, "port", None)
        if not host or not port:
            continue
        entries.append({
            "service": service,
            "host": str(host).rstrip("."),
            "port": int(port),
            "priority": int(getattr(record, "priority", 0) or 0),
            "weight": int(getattr(record, "weight", 0) or 0),
            "tls": service.startswith("_turns") or service.startswith("_stuns"),
        })
    return entries


async def discover_stun_turn(domain: str,
                             loop: asyncio.AbstractEventLoop | None = None
                             ) -> list[dict]:
    """Discover STUN/TURN servers for *domain* via SRV records.

    Returns a flat list ordered by :data:`SRV_SERVICES` (encrypted first,
    TURN before STUN), each item a dict with host/port/priority/weight/tls.
    """
    if not domain:
        return []
    if not HAS_AIODNS:
        logger.warning("aiodns is not available; skipping STUN/TURN discovery")
        return []
    try:
        resolver = aiodns.DNSResolver(loop=loop)
    except Exception as exc:
        logger.warning("Could not create the DNS resolver: %s", exc)
        return []
    found: list[dict] = []
    for service in SRV_SERVICES:
        try:
            answer = await resolver.query(f"{service}.{domain}", "SRV")
        except Exception as exc:
            logger.debug("No %s SRV record for %s: %s", service, domain, exc)
            continue
        entries = _srv_to_dict(service, answer)
        entries.sort(key=lambda e: (e["priority"], -e["weight"]))
        found.extend(entries)
    logger.info("STUN/TURN discovery for %s: %d entr%s", domain, len(found),
                "y" if len(found) == 1 else "ies")
    return found


async def refresh(xmpp, domain: str, cache: DiscoveryCache,
                  max_age: float = MAX_AGE,
                  negative_max_age: float = NEGATIVE_MAX_AGE,
                  force: bool = False) -> dict:
    """Run the discoveries whose cache is stale and return the results.

    Each section is isolated so a failure in one never hides the other.
    Successful results (including a genuine "nothing found") are cached;
    an exception is *not* cached, so it is retried on the next connection.
    With *force* the cache is bypassed entirely.
    """
    result: dict = {}

    async def _section(key: str, discover) -> object:
        if not force:
            fresh, value = cache.get(key, max_age, negative_max_age)
            if fresh:
                return value
        try:
            value = await discover()
            cache.put(key, value)
            return value
        except Exception as exc:
            logger.warning("Discovery of %s failed: %s", key, exc)
            # Keep the last known result (even stale) to avoid flapping.
            _, stale = cache.get(key, max_age=float("inf"),
                                 negative_max_age=float("inf"))
            return stale

    result["file_proxy"] = await _section(
        "file_proxy", lambda: discover_file_proxy(xmpp))

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    result["stun_turn"] = await _section(
        "stun_turn", lambda: discover_stun_turn(domain, loop=loop))

    return result
