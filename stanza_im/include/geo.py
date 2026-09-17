"""geo: URI support (RFC 5870), Spherical-Mercator math and location tracks.

Pure logic (no Qt): the OSM tile-cache indexing and the projection/track/speed
helpers here are unit-tested headless, while the widgets in
``stanza_im/ui/map_widget.py`` handle rendering and network fetching.

A geo: URI looks like ``geo:lat,lon;u=accuracy`` (latitude and longitude in
decimal degrees, optional ``;u=`` accuracy radius in meters).  Coordinates in
message bodies are linkified by :func:`extract_geo_uris`
(see ``include/utils.py:tokenize_urls``); a click on the link opens the
in-app OpenStreetMap window, and geo coordinates that arrive via XEP-0308
message corrections extend the window's track in place.
"""
from __future__ import annotations

import json
import math
import os
import re
import time

from stanza_im.include.constants import CACHE_DIR

__all__ = [
    "MAX_LATITUDE", "TILE_SIZE", "parse_geo_uri", "extract_geo_uris",
    "lat_lon_to_world", "world_to_lat_lon", "tile_for_world",
    "meters_per_pixel", "haversine_m", "TileCache", "Track", "Fix",
]

MAX_LATITUDE = 85.05112878   # Web-Mercator cutoff; beyond this projection breaks
TILE_SIZE = 256
_MIN_ZOOM = 2
_MAX_ZOOM = 18

# A full RFC 5870 'geo:' URI with one coordinate pair plus optional parameters
# (e.g. ';u=10', ';crs=gcrs;u=5').  Coordinates may be negative/decimals.
_GEO_URI_RE = re.compile(
    r"geo:(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?),"
    r"(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"(?:;(?:u=(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|[^;]+))*$",
    re.IGNORECASE,
)
# Substring scanner used inside message bodies (URL-like boundaries).
_GEO_IN_TEXT_RE = re.compile(
    r"geo:-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?(?:;[^\s<>\"']+)?",
    re.IGNORECASE,
)


class Fix:
    """A single location fix: coordinates, timestamp and accuracy radius."""

    __slots__ = ("lat", "lon", "ts", "accuracy")

    def __init__(self, lat: float, lon: float, ts: float,
                 accuracy: float = 0.0):
        self.lat = float(lat)
        self.lon = float(lon)
        self.ts = float(ts)
        self.accuracy = max(0.0, float(accuracy))


def parse_geo_uri(uri: str):
    """Parse a ``geo:lat,lon;u=accuracy`` URI (RFC 5870 subset).

    Returns ``{"lat": float, "lon": float, "accuracy": float}`` or ``None``
    when the string is not a valid geo: URI.  ``accuracy`` defaults to ``0``
    when the optional ``;u=`` parameter is absent; other parameters
    (``;crs=``, ``;unc=``, ...) are tolerated and ignored.
    """
    if not isinstance(uri, str):
        return None
    match = _GEO_URI_RE.match(uri.strip())
    if not match:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    if abs(lat) > 90.0 or abs(lon) > 180.0:
        return None
    accuracy = float(match.group(3)) if match.group(3) else 0.0
    if accuracy < 0:
        return None
    return {"lat": lat, "lon": lon, "accuracy": accuracy}


def extract_geo_uris(body: str) -> list[str]:
    """Return every geo: URI substring found in *body* (in order)."""
    if not isinstance(body, str):
        return []
    return [match.group(0) for match in _GEO_IN_TEXT_RE.finditer(body)]


def escape_body_with_geo(body: str) -> str:
    """HTML-escape *body* and wrap its geo: and xmpp: URIs in clickable links.

    Used by the QTextBrowser chat fallback (which does no skin rendering):
    HTTP(S)/ftp URLs stay plain text, only ``geo:`` coordinates and XEP-0147
    ``xmpp:`` URIs become ``<a href="...">`` anchors that the view forwards to
    the map window / the XMPP-URI handler.
    """
    import html as _html
    if not body:
        return ""
    escaped = _html.escape(str(body)).replace("\r\n", "\n").replace("\r", "\n")
    escaped = escaped.replace("\n", "<br>")

    def _repl(match):
        uri = match.group(0)
        return f'<a href="{uri}">{uri}</a>'

    escaped = _GEO_IN_TEXT_RE.sub(_repl, escaped)

    from stanza_im.include.xmpp_uri import _XMPP_URI_RE
    from stanza_im.include.utils import _URL_TRAILING_PUNCT

    def _uri_repl(match):
        uri = _URL_TRAILING_PUNCT.sub("", match.group(0))
        if not uri:
            return match.group(0)
        return f'<a href="{uri}">{uri}</a>' + match.group(0)[len(uri):]

    return _XMPP_URI_RE.sub(_uri_repl, escaped)


def clamp_zoom(zoom: float) -> float:
    """Clamp *zoom* into the supported tile range."""
    return max(_MIN_ZOOM, min(_MAX_ZOOM, float(zoom)))


# ── Web-Mercator helpers ────────────────────────────────────────────────

def lat_lon_to_world(lat: float, lon: float, zoom: float
                     ) -> tuple[float, float]:
    """Map (lat, lon) to Slip-map tile coordinates at *zoom*.

    Returns fractional tile units in ``0..2**zoom`` on both axes (a whole tile
    is ``1.0``); multiply by :data:`TILE_SIZE` to get pixel coordinates.  These
    are the standard OpenStreetMap indices, so ``int(x), int(y)`` address a
    real ``{z}/{x}/{y}.png`` tile.
    """
    lat = max(-MAX_LATITUDE, min(MAX_LATITUDE, float(lat)))
    n = 2.0 ** clamp_zoom(zoom)
    x = (float(lon) + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def world_to_lat_lon(x: float, y: float, zoom: float
                     ) -> tuple[float, float]:
    """Inverse of :func:`lat_lon_to_world` (fractional tile units)."""
    n = 2.0 ** clamp_zoom(zoom)
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lat, lon


def tile_for_world(x: float, y: float) -> tuple[int, int]:
    """Tile indices covering the world pixel *x*, *y*."""
    return int(math.floor(x)), int(math.floor(y))


def meters_per_pixel(lat: float, zoom: float) -> float:
    """Ground resolution in meters per pixel at *lat* and *zoom* (256 px)."""
    return (156543.03392 * math.cos(math.radians(float(lat)))
            / 2.0 ** clamp_zoom(zoom))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two coordinates in meters."""
    r_lat1 = math.radians(float(lat1))
    r_lat2 = math.radians(float(lat2))
    d_lat = r_lat2 - r_lat1
    d_lon = math.radians(float(lon2)) - math.radians(float(lon1))
    a = (math.sin(d_lat / 2.0) ** 2
         + math.cos(r_lat1) * math.cos(r_lat2) * math.sin(d_lon / 2.0) ** 2)
    return 2.0 * 6371000.0 * math.asin(min(1.0, math.sqrt(a)))


def osm_external_url(lat: float, lon: float, zoom: int = 16) -> str:
    """An openstreetmap.org deep link for opening the point in a browser."""
    return "https://www.openstreetmap.org/?mlat=%.6f&mlon=%.6f#map=%d/%.6f/%.6f" % (
        lat, lon, int(zoom), lat, lon)


# ── Track (live location via message corrections) ───────────────────────

_MIN_FIX_DISTANCE_M = 2.0   # ignore fixes closer than 2 m to the previous one
_MIN_FIX_DT_S = 1.0         # ... and earlier than 1 s after the previous one
_MAX_TRACK_FIXES = 2000     # keep a bounded live track (drop oldest fixes)


class Track:
    """An ordered series of location fixes plus derived movement stats.

    The current speed is the great-circle distance between the last two fixes
    divided by their time delta (empty/zero delta yields zero).  The track is
    capped at *max_fixes* (oldest fixes dropped) so a long live session cannot
    grow without bound; the start marker then reflects the oldest retained fix.
    """

    def __init__(self, max_fixes: int = _MAX_TRACK_FIXES) -> None:
        self._fixes: list[Fix] = []
        try:
            self._max_fixes = max(1, int(max_fixes))
        except (TypeError, ValueError):
            self._max_fixes = _MAX_TRACK_FIXES

    def add_fix(self, lat: float, lon: float, accuracy: float = 0.0,
                ts: float | None = None) -> bool:
        """Append *fix* unless it is a near-duplicate of the last one."""
        ts = float(ts) if ts is not None else time.time()
        fix = Fix(lat, lon, ts, accuracy)
        last = self._fixes[-1] if self._fixes else None
        if last is not None:
            distance = haversine_m(last.lat, last.lon, fix.lat, fix.lon)
            if distance < _MIN_FIX_DISTANCE_M and fix.ts - last.ts < _MIN_FIX_DT_S:
                return False
        self._fixes.append(fix)
        if len(self._fixes) > self._max_fixes:
            del self._fixes[:len(self._fixes) - self._max_fixes]
        return True

    @property
    def empty(self) -> bool:
        return not self._fixes

    @property
    def points(self) -> list[Fix]:
        return list(self._fixes)

    @property
    def count(self) -> int:
        return len(self._fixes)

    @property
    def start(self) -> Fix | None:
        return self._fixes[0] if self._fixes else None

    @property
    def current(self) -> Fix | None:
        return self._fixes[-1] if self._fixes else None

    @property
    def total_distance_m(self) -> float:
        total = 0.0
        for prev, fix in zip(self._fixes, self._fixes[1:]):
            total += haversine_m(prev.lat, prev.lon, fix.lat, fix.lon)
        return total

    @property
    def speed_kmh(self) -> float:
        if len(self._fixes) < 2:
            return 0.0
        prev, fix = self._fixes[-2], self._fixes[-1]
        dt = fix.ts - prev.ts
        if dt <= 0:
            return 0.0
        distance = haversine_m(prev.lat, prev.lon, fix.lat, fix.lon)
        return distance / dt * 3.6


# ── Tile cache (on-disk LRU) ────────────────────────────────────────────

TILES_DIR = os.path.join(CACHE_DIR, "tiles")


class TileCache:
    """Disk cache for OSM tile PNGs under ``$XDG_CACHE_HOME/stanza-im/tiles``.

    Layout mirrors ``MediaCache``: tiles live as ``{z}/{x}/{y}.png`` and an
    ``index.json`` tracks last access for LRU eviction (``prune`` enforces a
    total-size cap and a TTL).
    """

    def __init__(self, directory: str = TILES_DIR, max_bytes: int = 64 << 20,
                 ttl_days: float = 14.0):
        self._dir = directory
        self._index_file = os.path.join(directory, "index.json")
        self._max_bytes = max(0, int(max_bytes))
        self._ttl = max(0.0, float(ttl_days)) * 86400.0
        self._index: dict[str, dict] = {}
        self._dirty = False
        self._load()

    def _key(self, z: int, x: int, y: int) -> str:
        return "%d/%d/%d" % (z, x, y)

    def _path(self, z: int, x: int, y: int) -> str:
        return os.path.join(self._dir, "%d" % z, "%d" % x, "%d.png" % y)

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
        except OSError:
            pass

    def get(self, z: int, x: int, y: int) -> str | None:
        key = self._key(z, x, y)
        if key not in self._index:
            return None
        path = self._path(z, x, y)
        if not os.path.isfile(path):
            self._index.pop(key, None)
            return None
        self._index[key]["last_access"] = time.time()
        self._dirty = True
        return path

    def put(self, z: int, x: int, y: int, data: bytes) -> str | None:
        try:
            os.makedirs(os.path.dirname(self._path(z, x, y)), exist_ok=True)
            path = self._path(z, x, y)
            with open(path, "wb") as fh:
                fh.write(data)
        except OSError:
            return None
        self._index[self._key(z, x, y)] = {
            "last_access": time.time(), "size": len(data)}
        self._dirty = True
        self._save_index()
        return path

    def total_bytes(self) -> int:
        return sum(int(entry.get("size") or 0)
                   for entry in self._index.values())

    def prune(self) -> int:
        """Drop tiles not used within the TTL and enforce the size cap."""
        removed = 0
        if self._ttl > 0:
            now = time.time()
            for key, entry in list(self._index.items()):
                try:
                    last = float(entry.get("last_access") or 0)
                except (TypeError, ValueError):
                    last = 0.0
                if now - last > self._ttl:
                    self._delete(key)
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
            total -= int(entry.get("size") or 0)
            self._delete(key)
            removed += 1
        return removed

    def _delete(self, key: str) -> None:
        z, x, y = key.split("/")
        try:
            os.remove(self._path(int(z), int(x), int(y)))
        except OSError:
            pass
        self._index.pop(key, None)