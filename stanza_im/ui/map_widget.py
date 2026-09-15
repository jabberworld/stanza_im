"""In-app OpenStreetMap window (custom QPainter rendering, no WebEngine).

A ``GeoMapWindow`` presents a ``GeoMapWidget`` that downloads OSM raster
tiles into a disk ``TileCache`` (``include/geo.py``) and paints them with a
hand-rolled Web-Mercator projection.  On top of the tiles it draws:

* the **accuracy zone** — a circle whose radius in meters (``;u=``) is mapped
  to pixels via ``meters_per_pixel``;
* the **track** polyline over the series of location fixes;
* the **start marker** (green) and the **current position** marker (red).

The window is updated live: geo: coordinates that arrive through XEP-0308
message corrections are pushed via :meth:`GeoMapWindow.update_position`,
extending the track, recomputing the current speed and optionally re-centering
(follow mode).  When a corrected message no longer carries coordinates the
window stops at the last fix (:meth:`GeoMapWindow.mark_track_final`).
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import urllib.error
import urllib.request

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.geo import (
    MAX_LATITUDE, TILE_SIZE, Track, clamp_zoom,
    lat_lon_to_world, meters_per_pixel, osm_external_url,
    world_to_lat_lon,
)

logger = logging.getLogger(__name__)

_USER_AGENT = ("StanzaIM/0.1 (XMPP desktop client / OpenStreetMap tiles, "
               "https://www.openstreetmap.org/copyright)")
_REQUEST_PACING_S = 0.5        # OSM tile policy: stay far below 2 req/s
_RETRY_PACING_S = 10.0         # re-request a failed tile after this delay
_MEM_PIXMAP_MAX = 512          # in-memory QPixmap LRU cap
# HTTP codes worth a retry (429 rate-limit, 5xx, temporary server states).
_TRANSIENT_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}


class TileLoader(QtCore.QThread):
    """Background OSM tile downloader with a pacing queue (worker thread)."""

    tile_ready = QtCore.pyqtSignal(int, int, int, str)  # z, x, y, path (''=fail)

    def __init__(self, tile_url: str, cache, parent=None):
        super().__init__(parent)
        self._tile_url = (tile_url or "").rstrip("/")
        self._cache = cache
        self._queue: queue.Queue = queue.Queue()
        self._inflight: set[tuple[int, int, int]] = set()
        self._failed: set[tuple[int, int, int]] = set()  # permanent errors
        self._lock = threading.Lock()
        self._stopped = False
        self._retry: dict[tuple[int, int, int], float] = {}

    def request(self, z: int, x: int, y: int) -> None:
        if not self._tile_url:
            return
        key = (z, x, y)
        with self._lock:
            if key in self._inflight or key in self._failed or self._stopped:
                return
            now = time.monotonic()
            if self._retry.get(key, 0.0) > now:
                return
            self._inflight.add(key)
            self._queue.put(key)

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
        self._queue.put(None)

    def run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            z, x, y = item
            path, permanent = "", False
            try:
                path = self._fetch(z, x, y)
            except urllib.error.HTTPError as exc:
                permanent = exc.code not in _TRANSIENT_HTTP_CODES
                logger.debug("tile %d/%d/%d HTTP %d", z, x, y, exc.code)
            except Exception as exc:
                logger.debug("tile %d/%d/%d fetch failed: %s", z, x, y, exc)
            with self._lock:
                if permanent:
                    self._failed.add((z, x, y))
                elif not path:
                    self._retry[(z, x, y)] = time.monotonic() + _RETRY_PACING_S
                self._inflight.discard((z, x, y))
            self.tile_ready.emit(z, x, y, path or "")
            time.sleep(_REQUEST_PACING_S)

    def _fetch(self, z: int, x: int, y: int) -> str:
        cached = self._cache.get(z, x, y) if self._cache else None
        if cached:
            return cached
        url = "%s/%d/%d/%d.png" % (self._tile_url, z, x, y)
        req = urllib.request.Request(
            url, headers={"User-Agent": _USER_AGENT, "Accept": "image/png"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if not data:
            return ""
        if self._cache:
            return self._cache.put(z, x, y, data) or ""
        return ""


class GeoMapWidget(QtWidgets.QWidget):
    """Custom-painted OpenStreetMap widget (tiles + accuracy + track)."""

    def __init__(self, tile_url: str, cache, tile_url_provider=None,
                 default_zoom: int = 15, parent=None):
        super().__init__(parent)
        self._tile_url = tile_url or ""
        self._tile_url_provider = tile_url_provider
        self._cache = cache
        self._zoom = clamp_zoom(int(default_zoom or 15))
        self._center = (55.7558, 37.6173)   # fallback: Moscow
        self._track = Track()
        self._follow = True
        self._pixmaps: dict[tuple[int, int, int], QtGui.QPixmap] = {}
        self._pending: set[tuple[int, int, int]] = set()
        self._drag: QtCore.QPointF | None = None
        self._loader = TileLoader(self._tile_url, cache, self)
        self._loader.tile_ready.connect(self._on_tile_ready)
        self._loader.start()
        self.setMouseTracking(True)
        self.setMinimumSize(200, 160)

    # ── Public API ─────────────────────────────────────────────────

    @property
    def track(self) -> Track:
        return self._track

    @property
    def follow(self) -> bool:
        return self._follow

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_follow(self, follow: bool) -> None:
        self._follow = bool(follow)

    def set_initial(self, lat: float, lon: float, accuracy: float = 0.0,
                    zoom: float | None = None, ts: float | None = None) -> None:
        self._center = (float(lat), float(lon))
        if zoom:
            self._zoom = clamp_zoom(zoom)
        self._track.add_fix(float(lat), float(lon), float(accuracy), ts)
        self._follow = True
        self.update()

    def add_fix(self, lat: float, lon: float, accuracy: float = 0.0,
                ts: float | None = None, recenter: bool | None = None) -> bool:
        added = self._track.add_fix(float(lat), float(lon),
                                    float(accuracy), ts)
        if added and (self._follow if recenter is None else recenter):
            self._center = (float(lat), float(lon))
        self.update()
        return added

    def clear_retries(self) -> None:
        if hasattr(self._loader, "_retry"):
            self._loader._retry.clear()
        if hasattr(self._loader, "_failed"):
            self._loader._failed.clear()

    def stop_loading(self) -> None:
        self._loader.stop()
        self._loader.wait(2000)

    # ── Projection helpers ─────────────────────────────────────────

    def _world_px(self, lat: float, lon: float) -> tuple[float, float]:
        x, y = lat_lon_to_world(lat, lon, self._zoom)
        return x * TILE_SIZE, y * TILE_SIZE

    def _to_screen(self, lat: float, lon: float) -> QtCore.QPointF:
        cx, cy = self._world_px(*self._center)
        return QtCore.QPointF(self.width() / 2.0 + (self._world_px(lat, lon)[0] - cx),
                              self.height() / 2.0 + (self._world_px(lat, lon)[1] - cy))

    def _lat_lon_under(self, pos: QtCore.QPointF):
        """Convert a widget pixel position to (lat, lon)."""
        cx, cy = self._world_px(*self._center)
        wx = cx + (pos.x() - self.width() / 2.0)
        wy = cy + (pos.y() - self.height() / 2.0)
        return world_to_lat_lon(wx / TILE_SIZE, wy / TILE_SIZE, self._zoom)

    # ── Tiles ──────────────────────────────────────────────────────

    def _tile_pixmap(self, z: int, x: int, y: int) -> QtGui.QPixmap | None:
        key = (z, x, y)
        pm = self._pixmaps.get(key)
        if pm is not None and not pm.isNull():
            self._pixmaps.pop(key)
            self._pixmaps[key] = pm     # LRU refresh
            return pm
        path = self._cache.get(z, x, y) if self._cache else None
        if path:
            pm = QtGui.QPixmap(path)
            self._pixmaps[key] = pm
            if len(self._pixmaps) > _MEM_PIXMAP_MAX:
                for stale in list(self._pixmaps)[: -_MEM_PIXMAP_MAX]:
                    self._pixmaps.pop(stale, None)
            return pm
        if key not in self._pending and self._tile_url:
            self._pending.add(key)
            self._loader.request(z, x, y)
        return None

    def _on_tile_ready(self, z: int, x: int, y: int, path: str) -> None:
        self._pending.discard((z, x, y))
        if path:
            pm = QtGui.QPixmap(path)
            if not pm.isNull():
                self._pixmaps[(z, x, y)] = pm
        self.update()

    # ── Painting ───────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QtGui.QPainter(self)
        try:
            self._paint_tiles(painter)
            self._paint_track(painter)
            self._paint_markers(painter)
            self._paint_attribution(painter)
        finally:
            painter.end()

    def _paint_tiles(self, painter: QtGui.QPainter) -> None:
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor("#e8e8e8"))
        cx, cy = self._world_px(*self._center)
        left = cx - rect.width() / 2.0
        top = cy - rect.height() / 2.0
        x0 = int(left // TILE_SIZE)
        y0 = int(top // TILE_SIZE)
        x1 = int((left + rect.width()) // TILE_SIZE)
        y1 = int((top + rect.height()) // TILE_SIZE)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                if ty < 0:
                    continue
                pm = self._tile_pixmap(int(self._zoom), tx, ty)
                painter.drawPixmap(
                    QtCore.QPoint(int(tx * TILE_SIZE - left),
                                  int(ty * TILE_SIZE - top)),
                    pm if pm is not None else QtGui.QPixmap())
                if pm is None:
                    painter.fillRect(
                        QtCore.QRect(int(tx * TILE_SIZE - left),
                                     int(ty * TILE_SIZE - top),
                                     TILE_SIZE, TILE_SIZE),
                        QtGui.QColor("#c8c8c8"))

    def _paint_track(self, painter: QtGui.QPainter) -> None:
        fixes = self._track.points
        if len(fixes) < 2:
            return
        path = QtGui.QPainterPath()
        first = True
        for fix in fixes:
            pt = self._to_screen(fix.lat, fix.lon)
            if first:
                path.moveTo(pt)
                first = False
            else:
                path.lineTo(pt)
        pen = QtGui.QPen(QtGui.QColor("#1565c0"), 2.0)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _paint_markers(self, painter: QtGui.QPainter) -> None:
        start = self._track.start
        current = self._track.current
        if start is not None:
            pos = self._to_screen(start.lat, start.lon)
            painter.setPen(QtGui.QPen(QtGui.QColor("#1b5e20"), 1.5))
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#2e7d32")))
            painter.drawEllipse(pos, 6.0, 6.0)
        if current is None:
            return
        pos = self._to_screen(current.lat, current.lon)
        if current.accuracy > 0:
            radius = current.accuracy / meters_per_pixel(current.lat, self._zoom)
            fill = QtGui.QColor(255, 82, 82, 46)
            outline = QtGui.QColor(255, 82, 82, 160)
            painter.setPen(QtGui.QPen(outline, 1.0))
            painter.setBrush(fill)
            painter.drawEllipse(pos, radius, radius)
        painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2.0))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#d32f2f")))
        painter.drawEllipse(pos, 6.0, 6.0)

    def _paint_attribution(self, painter: QtGui.QPainter) -> None:
        rect = self.rect()
        painter.setPen(QtGui.QColor(0, 0, 0, 140))
        font = painter.font()
        font.setPointSizeF(max(6.0, font.pointSizeF() - 1.0))
        painter.setFont(font)
        text = tr("map_attribution")
        metrics = painter.fontMetrics()
        painter.drawText(
            QtCore.QPointF(rect.right() - metrics.horizontalAdvance(text) - 6.0,
                           rect.bottom() - 5.0),
            text)

    # ── Interaction ────────────────────────────────────────────────

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if not delta:
            return
        steps = delta / 120.0
        pos = event.position()
        anchor = self._lat_lon_under(pos)
        self._zoom = clamp_zoom(round(self._zoom + steps))
        # Keep the point under the cursor fixed on screen while zooming.
        wx, wy = self._world_px(*anchor)
        self._center = world_to_lat_lon(
            (wx - (pos.x() - self.width() / 2.0)) / TILE_SIZE,
            (wy - (pos.y() - self.height() / 2.0)) / TILE_SIZE,
            self._zoom)
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() in (QtCore.Qt.MouseButton.LeftButton,
                              QtCore.Qt.MouseButton.MiddleButton):
            self._drag = event.position()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            delta = event.position() - self._drag
            self._drag = event.position()
            cx, cy = self._world_px(*self._center)
            cx -= delta.x()
            cy -= delta.y()
            lat, lon = world_to_lat_lon(cx / TILE_SIZE, cy / TILE_SIZE,
                                        self._zoom)
            lat = max(-MAX_LATITUDE, min(MAX_LATITUDE, lat))
            self._center = (lat, lon)
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag = None
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        pos = event.position()
        anchor = self._lat_lon_under(pos)
        self._zoom = clamp_zoom(self._zoom + 1)
        self._center = anchor
        self.update()
        event.accept()

    def closeEvent(self, event):
        self.stop_loading()
        super().closeEvent(event)


class GeoMapWindow(QtWidgets.QMainWindow):
    """Top-level map window for a geo: message (accuracy zone + live track)."""

    closed = QtCore.pyqtSignal()
    copy_requested = QtCore.pyqtSignal(str)  # "lat,lon" plain text

    def __init__(self, tile_url: str, cache, geometry_cfg=None, parent=None,
                 default_zoom: int = 15, follow: bool = True):
        super().__init__(parent)
        self._geometry_cfg = geometry_cfg
        self._default_zoom = int(default_zoom or 15)
        self._start_ts: float | None = None
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle(tr("map_window_title"))
        self.restore_geometry()

        self._widget = GeoMapWidget(tile_url, cache, default_zoom=self._default_zoom)
        self._widget.set_follow(follow)
        self.setCentralWidget(self._widget)

        self._build_toolbar()
        self._status = QtWidgets.QLabel("")
        self.statusBar().addPermanentWidget(self._status)
        self._refresh_status()

    # ── Construction ───────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        bar = QtWidgets.QToolBar(tr("map_window_title"), self)
        bar.setMovable(False)
        self.addToolBar(bar)

        self._follow_action = bar.addAction(tr("map_follow"), self._toggle_follow)
        self._follow_action.setCheckable(True)
        self._follow_action.setChecked(self._widget.follow)

        bar.addSeparator()
        bar.addAction(tr("map_zoom_in"), lambda: self._zoom_by(1))
        bar.addAction(tr("map_zoom_out"), lambda: self._zoom_by(-1))
        bar.addSeparator()
        bar.addAction(tr("map_open_browser"), self._open_in_browser)
        copy = bar.addAction(tr("map_copy_coords"), self._copy_coords)
        copy.setEnabled(False)
        self._copy_action = copy

    # ── Public API ─────────────────────────────────────────────────

    def update_position(self, lat: float, lon: float, accuracy: float = 0.0,
                        ts: float | None = None) -> None:
        """Push a new fix (from a XEP-0308 correction) onto the track."""
        if self._start_ts is None:
            self._start_ts = ts if ts is not None else time.time()
        self._widget.add_fix(lat, lon, accuracy, ts)
        self._widget.update()
        self._refresh_status()

    def mark_track_final(self) -> None:
        """The corrected message no longer carries coordinates — stop here."""
        self.statusBar().showMessage(tr("map_track_final"), 8000)

    def center_on(self, lat: float, lon: float, zoom: float | None = None) -> None:
        self._widget.set_initial(lat, lon, zoom=zoom or self._default_zoom)
        self._refresh_status()

    # ── Actions ────────────────────────────────────────────────────

    def _toggle_follow(self) -> None:
        self._widget.set_follow(self._follow_action.isChecked())

    def _zoom_by(self, steps: float) -> None:
        self._widget._zoom = clamp_zoom(self._widget._zoom + steps)
        self._widget.update()

    def _open_in_browser(self) -> None:
        current = self._widget.track.current
        if current is None:
            return
        import webbrowser
        webbrowser.open(osm_external_url(current.lat, current.lon,
                                         int(self._widget._zoom)))

    def _copy_coords(self) -> None:
        current = self._widget.track.current
        if current is None:
            return
        text = "%.6f, %.6f" % (current.lat, current.lon)
        QtWidgets.QApplication.clipboard().setText(text)
        self.statusBar().showMessage(tr("map_coords_copied"), 3000)

    # ── Status ─────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        track = self._widget.track
        current = track.current
        if current is None:
            self._status.setText("")
            self._copy_action.setEnabled(False)
            return
        self._copy_action.setEnabled(True)
        parts = [tr("map_coords", lat=current.lat, lon=current.lon)]
        if current.accuracy > 0:
            parts.append(tr("map_accuracy", m=current.accuracy))
        if track.count > 1:
            parts.append(tr("map_speed", speed=track.speed_kmh))
            parts.append(tr("map_distance", m=track.total_distance_m / 1000.0))
        self._status.setText(" · ".join(parts))

    # ── Geometry persistence (mirrors MediaViewer) ─────────────────

    def restore_geometry(self) -> None:
        cfg = self._geometry_cfg
        width, height, x, y, maximized = 700, 520, 0, 0, False
        if cfg:
            try:
                width = int(cfg.get("width", width) or width)
                height = int(cfg.get("height", height) or height)
                x = int(cfg.get("x", 0) or 0)
                y = int(cfg.get("y", 0) or 0)
            except (TypeError, ValueError):
                width, height, x, y = 700, 520, 0, 0
            maximized = bool(cfg.get("maximized"))
        self.resize(max(320, width), max(240, height))
        if x or y:
            self.move(x, y)
        if maximized:
            self.setWindowState(
                self.windowState() | QtCore.Qt.WindowState.WindowMaximized)

    def save_geometry(self) -> None:
        cfg = self._geometry_cfg
        if not cfg:
            return
        geo = (self.normalGeometry()
               if self.isFullScreen() or self.isMaximized()
               else self.geometry())
        cfg["x"] = geo.x()
        cfg["y"] = geo.y()
        cfg["width"] = geo.width()
        cfg["height"] = geo.height()
        cfg["maximized"] = self.isMaximized()

    def closeEvent(self, event):
        self.save_geometry()
        self._widget.stop_loading()
        self.closed.emit()
        super().closeEvent(event)