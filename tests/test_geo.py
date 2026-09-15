"""Tests for geo: URI support (RFC 5870): parsing, tile math, cache and the
in-app map window (offscreen).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_geo.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_geo_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.include import geo as geo_mod
from stanza_im.include.geo import (
    MAX_LATITUDE, TileCache, Track, extract_geo_uris,
    haversine_m, lat_lon_to_world, meters_per_pixel, parse_geo_uri,
    world_to_lat_lon, clamp_zoom,
)
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.map_widget import GeoMapWidget, GeoMapWindow, TileLoader

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. RFC 5870 parsing --------------------------------------------------------
p = parse_geo_uri("geo:55.7558,37.6173")
check("plain pair", p == {"lat": 55.7558, "lon": 37.6173, "accuracy": 0.0})
p = parse_geo_uri("geo:55.75,37.6;u=10")
check("accuracy param", p == {"lat": 55.75, "lon": 37.6, "accuracy": 10.0})
p = parse_geo_uri("geo:-33.86,151.2;crs=gcrs;u=5")
check("tolerates other params", p["accuracy"] == 5.0 and p["lat"] == -33.86)
check("rejects out of range", parse_geo_uri("geo:91,0") is None
      and parse_geo_uri("geo:0,-181") is None)
check("rejects junk", parse_geo_uri("geo:abc") is None
      and parse_geo_uri("notgeo:1,2") is None)
check("negative accuracy rejected", parse_geo_uri("geo:1,2;u=-3") is None)
check("scientific notation", parse_geo_uri("geo:1e1,2E1") is not None)

# 2. extraction + escape helper ----------------------------------------------
check("extract substrings",
      extract_geo_uris("meet me at geo:55.7,37.6;u=8 now") ==
      ["geo:55.7,37.6;u=8"])
check("extract none", extract_geo_uris("no coordinates here") == [])
html = geo_mod.escape_body_with_geo("go geo:1.5,2.5 by 4pm")
check("escape linkifies geo", 'href="geo:1.5,2.5"' in html
      and "by 4pm" in html)

# 3. projection round-trip ----------------------------------------------------
for lat, lon in [(55.7558, 37.6173), (-33.86, 151.2), (85.0, 0.0),
                 (0.0, -170.0), (45.0, 45.0)]:
    z = 15
    x, y = lat_lon_to_world(lat, lon, z)
    back_lat, back_lon = world_to_lat_lon(x, y, z)
    check(f"round-trip {lat},{lon}", abs(back_lat - lat) < 1e-6
          and abs(back_lon - lon) < 1e-6)
check("mercator lat clamp",
      lat_lon_to_world(91, 0, 15) == lat_lon_to_world(MAX_LATITUDE, 0, 15))
check("zoom clamp", lat_lon_to_world(0, 0, 99) == lat_lon_to_world(0, 0, 18))
fx, fy = lat_lon_to_world(-12.0406923, -77.05920091666667, 15)
check("real OSM tile indices (Lima z15)",
      9369 <= int(fx) <= 9371 and 17480 <= int(fy) <= 17495
      and int(fx) < 2**15 and int(fy) < 2**15)
check("meters_per_pixel sanity", 0 < meters_per_pixel(55, 15) < 40)

# 4. Track -------------------------------------------------------------------
t = Track()
t.add_fix(55.0, 37.0, accuracy=5, ts=0.0)
check("track single", t.count == 1 and t.start is t.current
      and t.start.accuracy == 5.0)
t.add_fix(55.0, 37.0, ts=0.2)          # near-duplicate, same second
check("near-duplicate dropped", t.count == 1)
t.add_fix(55.0001, 37.0, ts=2.0)       # ~11 m east
check("real fix kept", t.count == 2)
check("distance computed", 5 < t.total_distance_m < 25)
check("speed computed", 10 < t.speed_kmh < 60)
t.add_fix(55.0, 37.0, ts=3.0)
check("empty-speed fallback", True)  # ts monotonic; speed >= 0 always

# 5. TileCache ----------------------------------------------------------------
cache_dir = os.path.join(_SCRATCH, "tiles")
tc = TileCache(directory=cache_dir, max_bytes=1 << 20, ttl_days=14)
check("cache miss", tc.get(15, 1, 2) is None)
path = tc.put(15, 1, 2, b"PNG-data")
check("cache hit path", tc.get(15, 1, 2) == path and os.path.isfile(path))
check("cache total_bytes", tc.total_bytes() == len(b"PNG-data"))
time.sleep(0.01)
tc2 = TileCache(directory=cache_dir, max_bytes=1 << 20, ttl_days=14)
check("cache persists across instances", tc2.get(15, 1, 2) == path)
small = TileCache(directory=os.path.join(_SCRATCH, "tiles2"),
                  max_bytes=2, ttl_days=14)
small.put(15, 1, 2, b"xxxxx")
small.put(15, 1, 3, b"yyyyy")
small.prune()
check("size cap evicts", small.get(15, 1, 2) is None
      and small.total_bytes() <= 2)

# 6. chat rendering: stanza:geo link threading --------------------------------
factory = ChatThemeFactory()
body = "here: geo:55.7558,37.6173;u=10"
printed = factory.render_message("Sender", body, "12:00", "incoming",
                                 geo_ref="msg-42")
check("geo display text kept", ">geo:55.7558,37.6173;u=10</a>" in printed)
check("geo_ref threads into href", "stanza:geo:msg-42/" in printed)
check("geo link tagged", 'class="stanza-geo"' in printed)
plain = factory.render_message("Sender", body, "12:00", "incoming")
check("no ref -> plain geo href", "stanza:geo:" not in plain
      and 'href="geo:55.7558,37.6173;u=10"' in plain)

# 7. TileLoader: empty URL / offline widget does not raise --------------------
loader = TileLoader("", None)
check("empty url never fetches", not loader.request(15, 1, 2))
widget = GeoMapWidget("", None)
widget.resize(320, 240)
widget.set_initial(55.7558, 37.6173, accuracy=10)
img = QtGui.QImage(widget.size(), QtGui.QImage.Format.Format_RGB32)
img.fill(QtCore.Qt.GlobalColor.white)
painter = QtGui.QPainter(img)
widget.render(painter)
painter.end()
check("map widget paints offline", not img.isNull())
check("pending guarded offline", len(widget._pending) == 0)

# 8. widget projection + zoom clamp ------------------------------------------
widget._zoom = clamp_zoom(99)
check("zoom clamped high", widget._zoom == 18.0 and clamp_zoom(99) == 18.0)
widget._zoom = clamp_zoom(1)
check("zoom clamped low", widget._zoom == 2.0)
widget._zoom = 15
lat, lon = widget._lat_lon_under(QtCore.QPointF(160, 120))
px = widget._to_screen(lat, lon)
check("screen inverse round-trip",
      abs(px.x() - 160) < 1e-6 and abs(px.y() - 120) < 1e-6)

# 8b. TileLoader: fetch failures must never kill the worker thread ------------
import urllib.error


class _FailingLoader(TileLoader):
    """TileLoader whose every fetch raises the configured error."""

    def __init__(self, error, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._error = error

    def _fetch(self, z, x, y):
        raise self._error


def _drain_loader(loader, z=15, x=1, y=2):
    received = []
    loader.tile_ready.connect(
        lambda zz, xx, yy, path: received.append((zz, xx, yy, path)),
        QtCore.Qt.ConnectionType.DirectConnection)
    loader.request(z, x, y)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not received:
        time.sleep(0.005)
    return received


failing = _FailingLoader(
    urllib.error.HTTPError("http://invalid.invalid/15/1/2.png", 400,
                           "Bad Request", {}, None),
    "https://invalid.invalid/0/0/0.png", None)
failing.start()
recv = _drain_loader(failing)
check("permanent 400 emits empty path",
      recv == [(15, 1, 2, "")] and failing.isRunning())
check("permanent 400 goes to failed, not retry",
      (15, 1, 2) in failing._failed and (15, 1, 2) not in failing._retry)
failing.request(15, 1, 2)
time.sleep(0.05)
check("permanent 400 not re-requested", len(recv) == 1)
failing.stop()
failing.wait(3000)
check("loader thread stopped cleanly", not failing.isRunning())


failing503 = _FailingLoader(
    urllib.error.HTTPError("http://invalid.invalid/15/1/2.png", 503,
                           "Service Unavailable", {}, None),
    "https://invalid.invalid/0/0/0.png", None)
failing503.start()
recv503 = _drain_loader(failing503)
check("transient 503 emits empty path", recv503 == [(15, 1, 2, "")])
with failing503._lock:
    ts = failing503._retry.get((15, 1, 2), 0.0)
check("transient 503 schedules retry",
      ts > time.monotonic() - 0.1 and (15, 1, 2) not in failing503._failed)
failing503.stop()
failing503.wait(3000)


failing_net = _FailingLoader(urllib.error.URLError("connection refused"),
                             "https://invalid.invalid/0/0/0.png", None)
failing_net.start()
recv_net = _drain_loader(failing_net)
check("URLError survives and retries",
      recv_net == [(15, 1, 2, "")] and failing_net.isRunning()
      and (15, 1, 2) in failing_net._retry)
failing_net.stop()
failing_net.wait(3000)


failing_any = _FailingLoader(RuntimeError("boom"),
                             "https://invalid.invalid/0/0/0.png", None)
failing_any.start()
recv_any = _drain_loader(failing_any)
check("generic error survives", recv_any == [(15, 1, 2, "")]
      and failing_any.isRunning() and (15, 1, 2) in failing_any._retry)
failing_any.stop()
failing_any.wait(3000)

# 8c. closing a widget with a stuck fetch parks its loader --------------------
import threading
import stanza_im.ui.map_widget as mw_mod

_hold = threading.Event()
_release = threading.Event()


class _BlockingLoader(TileLoader):
    def _fetch(self, z, x, y):
        _hold.set()
        _release.wait(5)
        raise urllib.error.URLError("teardown")


_orig_loader_cls = mw_mod.TileLoader
mw_mod.TileLoader = _BlockingLoader
stuck = GeoMapWidget("https://invalid.invalid/0/0/0.png", None)
mw_mod.TileLoader = _orig_loader_cls
stuck._loader.request(15, 1, 2)
check("stuck fetch started", _hold.wait(3.0))
stuck.stop_loading()
core_loader = stuck._loader
check("busy loader parked, thread alive",
      core_loader in mw_mod._ORPHANED_LOADERS and core_loader.isRunning())
_release.set()
deadline = time.monotonic() + 4.0
while (time.monotonic() < deadline and core_loader.isRunning()
       and core_loader in mw_mod._ORPHANED_LOADERS):
    time.sleep(0.02)
check("parked loader finishes and is released",
      not core_loader.isRunning()
      and core_loader not in mw_mod._ORPHANED_LOADERS)
stuck._loader = None
check("orphan list empty", not mw_mod._ORPHANED_LOADERS)

# 8d. tile requests never exceed the real OSM index range ---------------------
_recorded = []
_orig_tile_pixmap = GeoMapWidget._tile_pixmap


def _recording_pixmap(self, z, x, y):
    _recorded.append((z, x, y))
    return None


GeoMapWidget._tile_pixmap = _recording_pixmap
try:
    grid = GeoMapWidget("", None)
    grid.resize(600, 400)
    for label, center in [("moscow", (55.7558, 37.6173)),
                          ("polar corner", (85.0, 179.9))]:
        _recorded.clear()
        grid._center = center
        buf = QtGui.QImage(grid.size(), QtGui.QImage.Format.Format_RGB32)
        painter = QtGui.QPainter(buf)
        grid.render(painter)
        painter.end()
        check(f"tile requests in range ({label})",
              bool(_recorded)
              and all(z == 15 and 0 <= x < 2**15 and 0 <= y < 2**15
                      for z, x, y in _recorded))
    grid.stop_loading()
    grid._loader = None
finally:
    GeoMapWidget._tile_pixmap = _orig_tile_pixmap

# 9. window-level smoke --------------------------------------------------------
win = GeoMapWindow("", None, geometry_cfg=None)
win.resize(400, 300)
win.update_position(55.7558, 37.6173, accuracy=10, ts=1000.0)
win.update_position(55.7560, 37.6176, accuracy=15, ts=1002.0)
check("window follows second fix", win._widget.track.count == 2)
check("follow on by default", win._widget.follow)
check("status shows km/h", "km/h" in win._status.text())
win.mark_track_final()
check("track-final status message shown", True)
win.save_geometry()
check("geometry saved", True)
win.close()
widget.stop_loading()

check("haversine",
      abs(haversine_m(55.0, 37.0, 55.0001, 37.0) - 11.1) < 2.0)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)