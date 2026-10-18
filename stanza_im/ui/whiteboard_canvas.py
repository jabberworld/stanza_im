"""Whiteboard drawing canvas.

A :class:`WhiteboardCanvas` holds an ordered list of SVG-like shape records and
renders them with a custom ``QPainter`` pass (no WebEngine).  It implements the
interactive tools (draw, select, move, rotate, scale) and can serialise the
document to SVG.
"""
from __future__ import annotations

import base64
import math
import os
import threading
import uuid

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.include import svg_path, svg_transform
from stanza_im.include.constants import (WHITEBOARD_HEIGHT, WHITEBOARD_WIDTH,
                                         find_icon)
from stanza_im.include.utils import escape_html
from stanza_im.i18n import tr

#: Default logical canvas size (the SVG ``viewBox``).  A collaborative session
#: may override it with the host's ``viewBox`` (see :meth:`set_view_box`).
VIEW_W = WHITEBOARD_WIDTH
VIEW_H = WHITEBOARD_HEIGHT

#: Tools that draw a new shape (as opposed to editing an existing one).
DRAW_TOOLS = ("pencil", "line", "arrow", "rect", "ellipse", "polygon")
#: Shapes whose closed area is filled with the fill colour.
CLOSED_KINDS = ("rect", "ellipse", "polygon")

#: View (zoom) limits.
MIN_VIEW_ZOOM = 0.25
MAX_VIEW_ZOOM = 8.0

#: Embedded (``data:``) image limits — the profile's Security Considerations ask
#: implementations to enforce size and format limits.
IMAGE_MAX_BYTES = 2 * 1024 * 1024
IMAGE_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
}
#: The XLink namespace (the profile embeds the image source in ``xlink:href``).
XLINK_NS = "http://www.w3.org/1999/xlink"


def image_data_uri(path: str) -> str:
    """Read an image file and return a ``data:`` URI.

    Raises :class:`ValueError` (with a user-facing message) for an unsupported
    format or a file over :data:`IMAGE_MAX_BYTES`.
    """
    mime = IMAGE_MIME.get(os.path.splitext(path)[1].lower())
    if not mime:
        raise ValueError(tr("whiteboard_image_unsupported"))
    limit_text = "%d MB" % (IMAGE_MAX_BYTES // (1024 * 1024))
    try:
        if os.path.getsize(path) > IMAGE_MAX_BYTES:
            raise ValueError(tr("whiteboard_image_too_large", size=limit_text))
        with open(path, "rb") as fh:
            raw = fh.read(IMAGE_MAX_BYTES + 1)
    except OSError as exc:
        raise ValueError(tr("whiteboard_image_failed")) from exc
    if len(raw) > IMAGE_MAX_BYTES:
        raise ValueError(tr("whiteboard_image_too_large", size=limit_text))
    return "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))


class _ImageFetcher(QtCore.QObject):
    """Download an ``http(s)`` image off the UI thread.

    The extended profile may reference an image uploaded via HTTP File Upload
    (XEP-0363); its bytes are fetched (size-limited) and delivered on the UI
    thread so the canvas can cache and render them.
    """

    ready = QtCore.pyqtSignal(str, bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy: set[str] = set()

    def fetch(self, url: str) -> None:
        if url in self._busy:
            return
        self._busy.add(url)
        threading.Thread(target=self._run, args=(url,), daemon=True).start()

    def _run(self, url: str) -> None:
        data = b""
        try:
            import urllib.request
            request = urllib.request.Request(url, headers={"User-Agent": "StanzaIM"})
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read(IMAGE_MAX_BYTES + 1)
        except Exception:  # noqa: BLE001 - an unreachable image stays unrendered
            data = b""
        self.ready.emit(url, data)

def _parse_transform(value) -> QtGui.QTransform:
    """Parse an SVG ``transform`` attribute (``matrix(...)``) into a transform."""
    matrix = svg_transform.parse_matrix(value)
    if matrix is None:
        return QtGui.QTransform()
    return QtGui.QTransform(*matrix)


def transform_str(transform: QtGui.QTransform) -> str:
    """Serialise a transform as an SVG ``matrix(...)`` attribute ("" if identity)."""
    if transform.isIdentity():
        return ""
    return "matrix(%g %g %g %g %g %g)" % (
        transform.m11(), transform.m12(), transform.m21(), transform.m22(),
        transform.dx(), transform.dy())


class WhiteboardCanvas(QtWidgets.QWidget):
    """Interactive drawing surface backed by a list of shape records."""

    changed = QtCore.pyqtSignal()
    #: Local edit notifications (for the collaborative session).
    shape_added = QtCore.pyqtSignal(dict)
    shape_updated = QtCore.pyqtSignal(dict)
    shape_removed = QtCore.pyqtSignal(dict)
    #: A group's transform changed (the group record id).
    group_updated = QtCore.pyqtSignal(str)
    #: The selection changed (so the toolbar can gate the group actions).
    selection_changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shapes: list[dict] = []
        # Decoded image pixmaps, keyed by their source URI (bounded).
        self._image_cache: dict[str, QtGui.QPixmap] = {}
        self._image_fetcher = _ImageFetcher(self)
        self._image_fetcher.ready.connect(self._on_image_loaded)
        # The current selection (the last entry is the primary shape).
        self._selection: list[str] = []
        # Group record id -> transform (a ``<g>`` transform applies to its
        # children; see the profile §8.5).
        self._group_transforms: dict[str, QtGui.QTransform] = {}
        # Logical canvas size (the SVG ``viewBox``); the host's may override it.
        self._view_w = VIEW_W
        self._view_h = VIEW_H
        self._tool = "pencil"
        self._stroke = "#1a1a1a"
        self._fill = "#e53935"
        self._fill_enabled = False
        self._width = 2
        self._active: dict | None = None
        self._start: QtCore.QPointF | None = None
        self._last: QtCore.QPointF | None = None
        self._transformed = False
        # Object manipulation in the select tool ("move"/"rotate"/"scale").
        self._manip = ""
        self._manip_id = ""
        # View transform (zoom/pan) — local, never part of the document.
        self._view_zoom = 1.0
        self._view_pan = QtCore.QPointF(0.0, 0.0)
        self._pan_origin: QtCore.QPointF | None = None
        self._pan_start = QtCore.QPointF(0.0, 0.0)
        self.setMinimumSize(480, 320)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    # ── Options ───────────────────────────────────────────────────

    def set_tool(self, tool: str) -> None:
        self._tool = tool
        self._apply_tool_cursor()

    def _apply_tool_cursor(self) -> None:
        if self._tool in DRAW_TOOLS or self._tool in ("fill", "eraser", "text"):
            self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def tool(self) -> str:
        return self._tool

    def set_stroke(self, color: str) -> None:
        self._stroke = color

    def set_fill(self, color: str) -> None:
        self._fill = color

    def set_fill_enabled(self, enabled: bool) -> None:
        """Whether newly drawn closed shapes get the fill colour."""
        self._fill_enabled = bool(enabled)

    def set_width(self, width: int) -> None:
        self._width = max(1, int(width))

    def shapes(self) -> list[dict]:
        return self._shapes

    @property
    def _selected(self) -> str:
        """The primary selected shape id (the last clicked); "" when none."""
        return self._selection[-1] if self._selection else ""

    @_selected.setter
    def _selected(self, value: str) -> None:
        self._selection = [value] if value else []

    def selection(self) -> list[str]:
        """The selected shape ids (the last one is the primary)."""
        return list(self._selection)

    def view_box(self) -> tuple[int, int]:
        """The logical canvas size (the SVG ``viewBox``)."""
        return self._view_w, self._view_h

    def set_view_box(self, width: int, height: int) -> None:
        """Adopt the shared document's ``viewBox`` (the host's is authoritative)."""
        self._view_w = max(1, int(width))
        self._view_h = max(1, int(height))
        self.update()

    def selected_id(self) -> str:
        return self._selected

    def selected_rid(self) -> str:
        """The document record id of the selected shape ("" when unshared)."""
        shape = self._shape_by_id(self._selected)
        return str(shape.get("rid") or "") if shape is not None else ""

    def selected_rids(self) -> list[str]:
        """The document record ids of the whole selection."""
        return [str((self._shape_by_id(i) or {}).get("rid") or "")
                for i in self._selection]

    def group_transform_str(self, group_rid: str) -> str:
        """The serialised transform of *group_rid* ("" when identity)."""
        return transform_str(
            self._group_transforms.get(group_rid, QtGui.QTransform()))

    def reorder_local(self, shape_id: str, op: str) -> bool:
        """Reorder a local (unshared) board's paint order."""
        ids = [s["id"] for s in self._shapes]
        if shape_id not in ids or len(ids) < 2:
            return False
        index = ids.index(shape_id)
        if op == "front":
            self._shapes.append(self._shapes.pop(index))
        elif op == "back":
            self._shapes.insert(0, self._shapes.pop(index))
        elif op == "forward" and index < len(self._shapes) - 1:
            self._shapes[index], self._shapes[index + 1] = (
                self._shapes[index + 1], self._shapes[index])
        elif op == "backward" and index > 0:
            self._shapes[index], self._shapes[index - 1] = (
                self._shapes[index - 1], self._shapes[index])
        else:
            return False
        self.update()
        self.changed.emit()
        return True

    # ── Selection & grouping ──────────────────────────────────────

    def _group_members(self, group: str) -> list[str]:
        return [s["id"] for s in self._shapes
                if (s.get("group") or "") == group]

    def select_shape(self, shape_id: str, additive: bool = False) -> None:
        """Select *shape_id* (expanding to its group); Ctrl toggles membership."""
        shape = self._shape_by_id(shape_id)
        if shape is None:
            if not additive:
                self._selection = []
                self.selection_changed.emit()
            return
        group = shape.get("group") or ""
        ids = self._group_members(group) if group else [shape_id]
        if additive:
            present = all(i in self._selection for i in ids)
            for member in ids:
                if present and member in self._selection:
                    self._selection.remove(member)
                elif not present and member not in self._selection:
                    self._selection.append(member)
        else:
            self._selection = list(ids)
        if shape_id in self._selection:  # the clicked shape is the primary
            self._selection.remove(shape_id)
            self._selection.append(shape_id)
        self.update()
        self.selection_changed.emit()

    def selected_group(self) -> str:
        """The common group rid of the selection ("" when mixed or ungrouped)."""
        groups = {(self._shape_by_id(i) or {}).get("group") or ""
                  for i in self._selection}
        return groups.pop() if len(groups) == 1 else ""

    def _shape_matrix(self, shape: dict) -> QtGui.QTransform:
        """The shape's world matrix: the group transform times its own."""
        group = shape.get("group") or ""
        if group:
            return (self._group_transforms.get(group, QtGui.QTransform())
                    * shape["transform"])
        return shape["transform"]

    def group_local(self, group_rid: str = "") -> str:
        """Group the current selection on a local board; returns the group rid."""
        ids = [i for i in self._selection
               if not (self._shape_by_id(i) or {}).get("group")]
        if len(ids) < 2:
            return ""
        group_rid = group_rid or uuid.uuid4().hex
        for shape in self._shapes:
            if shape["id"] in ids:
                shape["group"] = group_rid
        self._group_transforms.setdefault(group_rid, QtGui.QTransform())
        self.update()
        self.changed.emit()
        self.selection_changed.emit()
        return group_rid

    def ungroup_local(self, group_rid: str) -> bool:
        """Ungroup on a local board (compose the group transform into members)."""
        if not group_rid:
            return False
        group_tf = self._group_transforms.get(group_rid, QtGui.QTransform())
        members = [s for s in self._shapes
                   if (s.get("group") or "") == group_rid]
        if not members:
            return False
        for shape in members:
            shape["transform"] = group_tf * shape["transform"]
            shape["group"] = ""
        self._group_transforms.pop(group_rid, None)
        self.update()
        self.changed.emit()
        self.selection_changed.emit()
        return True

    # ── Actions ───────────────────────────────────────────────────

    def clear(self) -> None:
        for shape in self._shapes:
            self.shape_removed.emit(shape)
        self._shapes = []
        self._selection = []
        self._group_transforms.clear()
        self._active = None
        self.update()
        self.changed.emit()
        self.selection_changed.emit()

    def delete_selected(self) -> None:
        if not self._selected:
            return
        shape = self._shape_by_id(self._selected)
        if shape is not None:
            self.delete_shape(shape)

    def delete_shape(self, shape: dict) -> None:
        """Remove *shape* and notify (used by delete/eraser)."""
        self._shapes = [s for s in self._shapes if s["id"] != shape["id"]]
        self._selection = [i for i in self._selection if i != shape["id"]]
        self.update()
        self.changed.emit()
        self.selection_changed.emit()
        self.shape_removed.emit(shape)

    def erase_at(self, world: QtCore.QPointF) -> bool:
        """Erase the shape under *world*; returns True when one was removed."""
        shape = self._shape_at(world)
        if shape is None:
            return False
        self.delete_shape(shape)
        return True

    def deselect(self) -> None:
        if self._selection:
            self._selection = []
            self.update()
            self.selection_changed.emit()

    def set_rid(self, shape_id: str, rid: str) -> None:
        """Record the SXE record id the collaborative session assigned."""
        shape = self._shape_by_id(shape_id)
        if shape is not None:
            shape["rid"] = str(rid or "")

    @staticmethod
    def shape_attrs(shape: dict) -> dict:
        """The SVG attributes of *shape* (for a collaborative edit)."""
        if shape.get("kind") == "image":
            x, y, w, h = shape["image"]
            return {
                "tag": "image",
                "id": shape["id"],
                "x": "%g" % x, "y": "%g" % y,
                "width": "%g" % w, "height": "%g" % h,
                "href": shape.get("href", ""),
                "transform": transform_str(shape["transform"]),
            }
        return {
            "tag": "path",
            "id": shape["id"],
            "d": WhiteboardCanvas.shape_d(shape),
            "stroke": shape["stroke"],
            "stroke-width": str(shape["stroke_width"]),
            "fill": (shape["fill"] if WhiteboardCanvas._filled(shape)
                     else "none"),
            "transform": transform_str(shape["transform"]),
        }

    # ── Geometry helpers ──────────────────────────────────────────

    def _fit_scale(self) -> float:
        """The board-to-widget scale at zoom 1 (fits the whole board)."""
        if self.width() <= 0 or self.height() <= 0:
            return 1.0
        return min(self.width() / self._view_w, self.height() / self._view_h)

    def _scale(self) -> float:
        """The current view scale (fit scale times the view zoom)."""
        return self._fit_scale() * self._view_zoom

    def _offset(self) -> tuple[float, float]:
        s = self._scale()
        return ((self.width() - self._view_w * s) / 2.0 + self._view_pan.x(),
                (self.height() - self._view_h * s) / 2.0 + self._view_pan.y())

    def _to_world(self, pos: QtCore.QPointF) -> QtCore.QPointF:
        s = self._scale()
        ox, oy = self._offset()
        return QtCore.QPointF((pos.x() - ox) / s, (pos.y() - oy) / s)

    def _to_screen(self, world: QtCore.QPointF) -> QtCore.QPointF:
        s = self._scale()
        ox, oy = self._offset()
        return QtCore.QPointF(ox + world.x() * s, oy + world.y() * s)

    # ── View zoom / pan ───────────────────────────────────────────

    def view_zoom(self) -> float:
        return self._view_zoom

    def set_view_zoom(self, zoom: float,
                      anchor: QtCore.QPointF | None = None) -> None:
        """Set the view zoom, keeping the point under *anchor* (widget px)."""
        zoom = max(MIN_VIEW_ZOOM, min(MAX_VIEW_ZOOM, float(zoom)))
        if abs(zoom - self._view_zoom) < 1e-9:
            return
        world = self._to_world(anchor) if anchor is not None else None
        self._view_zoom = zoom
        if world is not None:
            s = self._scale()
            cx = (self.width() - self._view_w * s) / 2.0
            cy = (self.height() - self._view_h * s) / 2.0
            self._view_pan = QtCore.QPointF(
                anchor.x() - cx - world.x() * s,
                anchor.y() - cy - world.y() * s)
        self.update()

    def zoom_by(self, factor: float,
                anchor: QtCore.QPointF | None = None) -> None:
        self.set_view_zoom(self._view_zoom * factor, anchor)

    def reset_view(self) -> None:
        if self._view_zoom == 1.0 and self._view_pan.isNull():
            return
        self._view_zoom = 1.0
        self._view_pan = QtCore.QPointF(0.0, 0.0)
        self.update()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (QtCore.Qt.Key.Key_Delete,
                           QtCore.Qt.Key.Key_Backspace):
            self.delete_selected()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):  # noqa: N802
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom_by(1.1 if delta > 0 else 1.0 / 1.1,
                             event.position())
                event.accept()
                return
        super().wheelEvent(event)

    @staticmethod
    def _local_path(shape: dict) -> QtGui.QPainterPath:
        if shape.get("kind") in ("remote", "text"):
            return svg_path.parse_path(shape.get("d") or "")
        if shape.get("kind") == "image":
            path = QtGui.QPainterPath()
            path.addRect(QtCore.QRectF(*shape["image"]))
            return path
        if shape.get("kind") == "arrow":
            return svg_path.parse_path(WhiteboardCanvas._arrow_d(shape))
        path = QtGui.QPainterPath()
        kind = shape["kind"]
        if kind in ("pencil", "line", "polygon"):
            points = shape.get("points") or []
            if points:
                path.moveTo(points[0][0], points[0][1])
                for x, y in points[1:]:
                    path.lineTo(x, y)
                if kind == "polygon" and len(points) >= 3:
                    path.closeSubpath()
        elif kind == "rect":
            x, y, w, h = shape["rect"]
            path.addRect(x, y, w, h)
        elif kind == "ellipse":
            cx, cy, rx, ry = shape["ellipse"]
            path.addEllipse(QtCore.QPointF(cx, cy), rx, ry)
        return path

    def _world_path(self, shape: dict) -> QtGui.QPainterPath:
        return self._shape_matrix(shape).map(self._local_path(shape))

    @staticmethod
    def _filled(shape: dict) -> bool:
        # ``fill="none"`` (sent for open shapes: line, pencil) means "no fill"
        # — a bare ``bool("none")`` is True and would fill a remote line.
        value = str(shape.get("fill") or "")
        if not value or value.lower() == "none":
            return False
        if shape.get("kind") in ("remote", "text"):
            return True
        return shape["kind"] in CLOSED_KINDS

    @staticmethod
    def shape_d(shape: dict) -> str:
        """The SVG ``d`` attribute for *shape*."""
        if shape.get("kind") in ("remote", "text"):
            return shape.get("d") or ""
        kind = shape["kind"]
        if kind == "arrow":
            return WhiteboardCanvas._arrow_d(shape)
        if kind in ("pencil", "line", "polygon"):
            return svg_path.polyline_d(shape.get("points") or [],
                                       close=(kind == "polygon"))
        if kind == "rect":
            return svg_path.rect_d(*shape["rect"])
        if kind == "ellipse":
            return svg_path.ellipse_d(*shape["ellipse"])
        return ""

    @staticmethod
    def _arrow_d(shape: dict) -> str:
        """The path data of an arrow: a shaft plus an open (V) head."""
        points = shape.get("points") or []
        if len(points) < 2:
            return svg_path.polyline_d(points)
        ax, ay = points[0]
        bx, by = points[1]
        size = 12.0 + float(shape.get("stroke_width", 2)) * 2.0
        angle = math.atan2(by - ay, bx - ax)
        spread = math.radians(25.0)
        h1x = bx - size * math.cos(angle - spread)
        h1y = by - size * math.sin(angle - spread)
        h2x = bx - size * math.cos(angle + spread)
        h2y = by - size * math.sin(angle + spread)
        return ("M %g %g L %g %g M %g %g L %g %g L %g %g"
                % (ax, ay, bx, by, h1x, h1y, bx, by, h2x, h2y))

    def load_shapes(self, shapes: list[dict]) -> None:
        """Rebuild the board from a list of shape descriptors (remote state).

        Each descriptor carries ``rid``, ``d`` and the presentation attributes.
        """
        loaded: list[dict] = []
        groups: dict[str, QtGui.QTransform] = {}
        for item in shapes:
            group = str(item.get("group") or "")
            if group and group not in groups:
                groups[group] = _parse_transform(item.get("group-transform"))
            if str(item.get("tag") or "path") == "image":
                shape = self._image_shape(item)
            else:
                fill = str(item.get("fill") or "")
                if fill.lower() == "none":
                    fill = ""
                shape = {
                    "id": str(item.get("id") or uuid.uuid4().hex),
                    "rid": str(item.get("rid") or ""),
                    "kind": "remote",
                    "d": str(item.get("d") or ""),
                    "stroke": str(item.get("stroke") or "#1a1a1a"),
                    "stroke_width": int(item.get("stroke-width") or 2),
                    "fill": fill,
                    "transform": _parse_transform(item.get("transform")),
                }
            shape["group"] = group
            loaded.append(shape)
        self._shapes = loaded
        self._group_transforms = groups
        # Keep the current selection when it survived the rebuild (a reorder or
        # a remote edit keeps the ``id``), so a re-order does not drop it.
        loaded_ids = {s["id"] for s in loaded}
        self._selection = [i for i in self._selection if i in loaded_ids]
        self._active = None
        self.update()
        self.changed.emit()
        self.selection_changed.emit()

    @staticmethod
    def _image_shape(item: dict) -> dict:
        def _num(key: str, default: float = 0.0) -> float:
            try:
                return float(item.get(key))
            except (TypeError, ValueError):
                return default

        return {
            "id": str(item.get("id") or uuid.uuid4().hex),
            "rid": str(item.get("rid") or ""),
            "kind": "image",
            "image": (_num("x"), _num("y"),
                      _num("width", 120.0), _num("height", 120.0)),
            "href": str(item.get("href") or ""),
            "stroke": "#1a1a1a",
            "stroke_width": 2,
            "fill": "",
            "transform": _parse_transform(item.get("transform")),
        }

    def _shape_by_id(self, shape_id: str) -> dict | None:
        return next((s for s in self._shapes if s["id"] == shape_id), None)

    def _new_shape(self, kind: str, **extra) -> dict:
        shape = {"id": uuid.uuid4().hex, "rid": "", "kind": kind,
                 "group": "",
                 "stroke": self._stroke, "stroke_width": self._width,
                 "fill": (self._fill if self._fill_enabled else ""),
                 "transform": QtGui.QTransform()}
        shape.update(extra)
        return shape

    # ── Bucket fill ───────────────────────────────────────────────

    @staticmethod
    def _is_closed(shape: dict) -> bool:
        """True when the shape encloses an area (fillable by the bucket)."""
        if shape.get("kind") == "remote":
            return "z" in (shape.get("d") or "").lower()
        return shape.get("kind") in CLOSED_KINDS

    def _closed_shape_at(self, world: QtCore.QPointF) -> dict | None:
        for shape in reversed(self._shapes):
            if not self._is_closed(shape):
                continue
            if self._world_path(shape).contains(world):
                return shape
        return None

    def bucket_fill(self, world: QtCore.QPointF) -> bool:
        """Fill (or, if already filled, unfill) the closed shape at *world*.

        Only a closed region can be filled, so clicking the empty background
        never floods the whole board.  Returns ``True`` when something changed.
        """
        shape = self._closed_shape_at(world)
        if shape is None:
            return False
        shape["fill"] = "" if self._filled(shape) else self._fill
        self.update()
        self.changed.emit()
        self.shape_updated.emit(shape)
        return True

    # ── Text ──────────────────────────────────────────────────────

    def _request_text(self, world: QtCore.QPointF) -> None:
        """Ask for text (multiline) and place it as a vector object."""
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, tr("whiteboard_text_title"), tr("whiteboard_text_prompt"), "")
        if ok and (text or "").strip():
            self.add_text(world, text)

    def add_text(self, world: QtCore.QPointF, text: str,
                 font_size: float = 24.0) -> dict | None:
        """Place *text* at *world* as a filled glyph-outline path.

        The text is converted to a vector path (``QPainterPath.addText`` ->
        ``svg_path.path_to_d``) so it serialises as a plain ``<path d="…"/>``
        and syncs/renders like any other shape.
        """
        text = (text or "").strip("\n")
        if not text:
            return None
        font = QtGui.QFont()
        font.setPointSizeF(float(font_size))
        metrics = QtGui.QFontMetricsF(font)
        path = QtGui.QPainterPath()
        y = 0.0
        for line in text.split("\n"):
            path.addText(0.0, y + metrics.ascent(), font, line)
            y += metrics.lineSpacing()
        path.translate(world.x(), world.y())
        shape = self._new_shape("text")
        shape["d"] = svg_path.path_to_d(path)
        shape["points"] = [(world.x(), world.y())]
        shape["fill"] = self._stroke  # the text colour is the line colour
        self._shapes.append(shape)
        self._selected = shape["id"]
        self.update()
        self.changed.emit()
        self.shape_added.emit(shape)
        return shape

    # ── Images ────────────────────────────────────────────────────

    def view_center_world(self) -> QtCore.QPointF:
        """The world point at the centre of the visible area (drop position)."""
        return self._to_world(QtCore.QPointF(self.width() / 2.0,
                                             self.height() / 2.0))

    def _pixmap_for(self, href: str) -> QtGui.QPixmap:
        """Decode (and cache) the pixmap of an image source.

        A ``data:`` URI is decoded inline; an ``http(s)`` URL (an image uploaded
        via HTTP File Upload, the profile §12.2) is fetched off the UI thread and
        the board is repainted once it arrives.  The empty pixmap returned in the
        meantime keeps the shape selectable.
        """
        cached = self._image_cache.get(href)
        if cached is not None:
            return cached
        pixmap = QtGui.QPixmap()
        if href.startswith("data:"):
            try:
                _header, _sep, payload = href.partition(",")
                raw = base64.b64decode(payload, validate=False)
                if len(raw) <= IMAGE_MAX_BYTES:
                    pixmap.loadFromData(raw)
            except (ValueError, TypeError):
                pixmap = QtGui.QPixmap()
        elif href.startswith(("http://", "https://")):
            self._image_fetcher.fetch(href)
        if len(self._image_cache) >= 32:
            self._image_cache.clear()
        self._image_cache[href] = pixmap
        return pixmap

    def cache_image(self, href: str, data: bytes) -> None:
        """Seed the image cache (e.g. with the bytes we just uploaded)."""
        self._on_image_loaded(href, data)

    def _on_image_loaded(self, href: str, data: bytes) -> None:
        """An ``http(s)`` image arrived: decode, cache and repaint."""
        pixmap = QtGui.QPixmap()
        if data and len(data) <= IMAGE_MAX_BYTES:
            pixmap.loadFromData(data)
        self._image_cache[href] = pixmap
        self.update()

    def add_image(self, world: QtCore.QPointF, href: str,
                  width: float | None = None,
                  height: float | None = None) -> dict | None:
        """Place an embedded (``data:``) image with its top-left at *world*."""
        if not href:
            return None
        if width is None or height is None:
            pixmap = self._pixmap_for(href)
            if not pixmap.isNull() and pixmap.width() and pixmap.height():
                width, height = float(pixmap.width()), float(pixmap.height())
            else:
                width = height = 120.0
        # Clamp so a large photo still fits on the canvas.
        w = min(float(width), float(self._view_w))
        h = min(float(height), float(self._view_h))
        shape = self._new_shape("image")
        shape["image"] = (world.x(), world.y(), w, h)
        shape["href"] = href
        self._shapes.append(shape)
        self._selected = shape["id"]
        self.update()
        self.changed.emit()
        self.shape_added.emit(shape)
        return shape

    def _shape_at(self, world: QtCore.QPointF) -> dict | None:
        """The topmost shape under *world* (hit-test), or ``None``."""
        for shape in reversed(self._shapes):
            path = self._world_path(shape)
            stroker = QtGui.QPainterPathStroker()
            stroker.setWidth(max(8.0, shape["stroke_width"] + 4.0))
            if stroker.createStroke(path).contains(world):
                return shape
            # A closed shape (or an image) is selectable by its interior even
            # when unfilled.
            if (self._filled(shape) or self._is_closed(shape)
                    or shape.get("kind") == "image") and path.contains(world):
                return shape
        return None

    # ── Selection handles (select tool) ───────────────────────────

    _HANDLE_SIZE = 18.0

    def _widget_bbox(self, shape: dict) -> QtCore.QRectF:
        rect = self._world_path(shape).boundingRect()
        tl = self._to_screen(rect.topLeft())
        br = self._to_screen(rect.bottomRight())
        return QtCore.QRectF(tl, br).normalized()

    def _selection_widget_bbox(self) -> QtCore.QRectF:
        """The union of the selected shapes' bounding boxes (widget coords)."""
        rects = [self._widget_bbox(s) for s in self._shapes
                 if s["id"] in self._selection]
        rects = [r for r in rects if not r.isNull()]
        if not rects:
            return QtCore.QRectF()
        out = rects[0]
        for rect in rects[1:]:
            out = out.united(rect)
        return out

    def _selection_handles(self) -> dict[str, QtCore.QRectF]:
        """The rotate/resize handles of the selection (widget coords)."""
        if not self._selection:
            return {}
        r = self._selection_widget_bbox()
        if r.isNull():
            return {}
        size = self._HANDLE_SIZE
        return {
            "rotate": QtCore.QRectF(r.center().x() - size / 2,
                                    r.top() - size - 8, size, size),
            "resize": QtCore.QRectF(r.right() - size / 2,
                                    r.bottom() - size / 2, size, size),
        }

    def _handle_at(self, pos: QtCore.QPointF) -> str:
        for name, rect in self._selection_handles().items():
            if rect.contains(pos):
                return name
        return ""

    # ── Painting ──────────────────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor("#ffffff"))
        s = self._scale()
        ox, oy = self._offset()
        painter.save()
        painter.translate(ox, oy)
        painter.scale(s, s)
        # A light grid helps the empty canvas.
        grid = QtGui.QPen(QtGui.QColor("#eef1f4"), 1.0)
        painter.setPen(grid)
        for gx in range(0, self._view_w + 1, 100):
            painter.drawLine(gx, 0, gx, self._view_h)
        for gy in range(0, self._view_h + 1, 100):
            painter.drawLine(0, gy, self._view_w, gy)
        for shape in self._shapes:
            self._draw_shape(painter, shape)
        if self._active is not None:
            self._draw_shape(painter, self._active)
        for selected in self._selection:
            shape = self._shape_by_id(selected)
            if shape is None:
                continue
            rect = self._world_path(shape).boundingRect()
            pen = QtGui.QPen(QtGui.QColor("#1a73e8"),
                             max(1.0, 1.0 / max(s, 1e-6)))
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
        group = self.selected_group()
        if group:
            # A distinct outline marks the selection as one group.
            group_rect = self._group_world_bbox(group)
            if not group_rect.isNull():
                pen = QtGui.QPen(QtGui.QColor("#2e7d32"),
                                 max(1.5, 1.5 / max(s, 1e-6)))
                painter.setPen(pen)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRect(group_rect.adjusted(-3, -3, 3, 3))
        painter.restore()
        if self._selection and self._tool == "select":
            self._draw_handles(painter)

    def _draw_handles(self, painter: QtGui.QPainter) -> None:
        """Rotate/resize handles of the selected shape (constant screen size)."""
        handles = self._selection_handles()
        if not handles:
            return
        painter.save()
        for name, rect in handles.items():
            painter.setPen(QtGui.QPen(QtGui.QColor("#1a73e8"), 1.5))
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#ffffff")))
            painter.drawEllipse(rect)
            icon_name = ("wb-rotate.svg" if name == "rotate"
                         else "wb-scale.svg")
            path = find_icon(icon_name)
            if path:
                QtGui.QIcon(path).paint(
                    painter, rect.adjusted(3, 3, -3, -3).toRect())
        painter.restore()

    def _draw_shape(self, painter: QtGui.QPainter, shape: dict) -> None:
        if shape.get("kind") == "image":
            pixmap = self._pixmap_for(shape.get("href") or "")
            if not pixmap.isNull():
                painter.save()
                painter.setTransform(self._shape_matrix(shape), True)
                painter.drawPixmap(QtCore.QRectF(*shape["image"]), pixmap,
                                   QtCore.QRectF(pixmap.rect()))
                painter.restore()
            return
        path = self._world_path(shape)
        pen = QtGui.QPen(QtGui.QColor(shape["stroke"]),
                         float(shape["stroke_width"]))
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        if self._filled(shape):
            painter.setBrush(QtGui.QColor(shape["fill"]))
        else:
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    # ── Mouse ─────────────────────────────────────────────────────

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            # Middle-button drag pans the view in any tool.
            self._pan_origin = event.position()
            self._pan_start = QtCore.QPointF(self._view_pan)
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        world = self._to_world(event.position())
        tool = self._tool
        if tool == "select":
            additive = bool(event.modifiers()
                            & QtCore.Qt.KeyboardModifier.ControlModifier)
            handle = self._handle_at(event.position())
            if handle:
                self._manip = handle
                self._manip_id = self._selected
                self._last = world
                return
            shape = self._shape_at(world)
            if shape is not None:
                self.select_shape(shape["id"], additive)
                self._manip = "move"
                self._manip_id = shape["id"]
                self._last = world
                self.update()
                return
            # Empty space: deselect (unless additive) and pan the view.
            if not additive:
                self._selection = []
            self._pan_origin = event.position()
            self._pan_start = QtCore.QPointF(self._view_pan)
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            self.update()
            return
        if tool == "fill":
            self.bucket_fill(world)
            return
        if tool == "eraser":
            self.erase_at(world)
            return
        if tool == "text":
            self._request_text(world)
            return
        if tool in ("move", "rotate", "scale"):
            if self._selected and self._shape_by_id(self._selected):
                self._last = world
            return
        if tool in DRAW_TOOLS:
            if tool == "rect":
                self._active = self._new_shape(
                    "rect", rect=(world.x(), world.y(), 0.0, 0.0))
            elif tool == "ellipse":
                self._active = self._new_shape(
                    "ellipse", ellipse=(world.x(), world.y(), 0.0, 0.0))
            elif tool in ("line", "arrow"):
                self._active = self._new_shape(
                    tool, points=[(world.x(), world.y()),
                                  (world.x(), world.y())])
            else:  # pencil / polygon
                self._active = self._new_shape(
                    tool, points=[(world.x(), world.y())])
            self._start = world
            self.update()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._pan_origin is not None:
            self._view_pan = self._pan_start + (event.position()
                                                - self._pan_origin)
            self.update()
            return
        world = self._to_world(event.position())
        if self._tool == "eraser" \
                and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self.erase_at(world)
            return
        if self._active is not None:
            kind = self._active["kind"]
            if kind in ("pencil", "polygon"):
                self._active["points"].append((world.x(), world.y()))
            elif kind in ("line", "arrow"):
                self._active["points"][1] = (world.x(), world.y())
            elif kind == "rect":
                self._active["rect"] = self._rect_from(self._start, world)
            elif kind == "ellipse":
                self._active["ellipse"] = self._ellipse_from(self._start, world)
            self.update()
            return
        if self._manip:
            shape = self._shape_by_id(self._manip_id)
            if shape is not None and self._last is not None:
                self._transform(shape, self._manip, self._last, world)
                self._transformed = True
                self._last = world
                self.update()
            return
        tool = self._tool
        if tool in ("move", "rotate", "scale") and self._selected \
                and self._last is not None:
            shape = self._shape_by_id(self._selected)
            if shape is not None:
                self._transform(shape, tool, self._last, world)
                self._transformed = True
                self._last = world
                self.update()
        elif tool == "select":
            self._update_select_cursor(event.position())

    def _update_select_cursor(self, pos: QtCore.QPointF) -> None:
        if self._tool != "select":
            return
        if self._handle_at(pos):
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            return
        over = self._shape_at(self._to_world(pos)) is not None
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor if over
                       else QtCore.Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._pan_origin is not None:
            self._pan_origin = None
            self._apply_tool_cursor()
            return
        if self._active is not None:
            self._commit_active()
        elif self._transformed:
            sid = self._manip_id or self._selected
            shape = self._shape_by_id(sid) if sid else None
            if shape is not None:
                group = shape.get("group") or ""
                if group:
                    self.group_updated.emit(group)
                else:
                    self.shape_updated.emit(shape)
        self._transformed = False
        self._manip = ""
        self._manip_id = ""
        self._start = None
        self._last = None
        self.update()

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if self._tool == "select" \
                and event.button() == QtCore.Qt.MouseButton.LeftButton:
            world = self._to_world(event.position())
            if self._shape_at(world) is None:
                self.reset_view()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def _commit_active(self) -> None:
        shape = self._active
        self._active = None
        if shape is None:
            return
        if shape["kind"] in ("pencil", "polygon") \
                and len(shape.get("points") or []) < 2:
            return
        self._shapes.append(shape)
        self._selected = shape["id"]
        self.changed.emit()
        self.shape_added.emit(shape)

    @staticmethod
    def _rect_from(start, end) -> tuple[float, float, float, float]:
        return (min(start.x(), end.x()), min(start.y(), end.y()),
                abs(end.x() - start.x()), abs(end.y() - start.y()))

    @staticmethod
    def _ellipse_from(start, end) -> tuple[float, float, float, float]:
        cx = (start.x() + end.x()) / 2.0
        cy = (start.y() + end.y()) / 2.0
        return (cx, cy, abs(end.x() - start.x()) / 2.0,
                abs(end.y() - start.y()) / 2.0)

    @staticmethod
    def _op_matrix(tool: str, last, world,
                   center: QtCore.QPointF) -> QtGui.QTransform | None:
        """The move/rotate/scale matrix about *center* (``None`` = no change)."""
        if tool == "move":
            op = QtGui.QTransform()
            op.translate(world.x() - last.x(), world.y() - last.y())
            return op
        if tool == "rotate":
            a0 = math.atan2(last.y() - center.y(), last.x() - center.x())
            a1 = math.atan2(world.y() - center.y(), world.x() - center.x())
            op = QtGui.QTransform()
            op.translate(center.x(), center.y())
            op.rotate(math.degrees(a1 - a0))
            op.translate(-center.x(), -center.y())
            return op
        # scale
        d0 = math.hypot(last.x() - center.x(), last.y() - center.y())
        d1 = math.hypot(world.x() - center.x(), world.y() - center.y())
        if d0 < 1.0:
            return None
        factor = max(0.05, d1 / d0)
        op = QtGui.QTransform()
        op.translate(center.x(), center.y())
        op.scale(factor, factor)
        op.translate(-center.x(), -center.y())
        return op

    def _group_world_bbox(self, group: str) -> QtCore.QRectF:
        """The union bounding box of a group's members (world coords)."""
        rects = [self._world_path(s).boundingRect() for s in self._shapes
                 if (s.get("group") or "") == group]
        if not rects:
            return QtCore.QRectF()
        out = rects[0]
        for rect in rects[1:]:
            out = out.united(rect)
        return out

    def _group_world_center(self, group: str) -> QtCore.QPointF:
        return self._group_world_bbox(group).center()

    def _transform(self, shape: dict, tool: str, last, world) -> None:
        group = shape.get("group") or ""
        if group:
            # A grouped shape transforms the whole group about the group's box.
            current = self._group_transforms.get(group, QtGui.QTransform())
            center = self._group_world_center(group)
            inverted, ok = current.inverted()
            if ok:
                center = inverted.map(center)
            op = self._op_matrix(tool, last, world, center)
            if op is None:
                return
            self._group_transforms[group] = current * op
            return
        center = self._world_path(shape).boundingRect().center()
        op = self._op_matrix(tool, last, world, center)
        if op is None:
            return
        shape["transform"] = shape["transform"] * op

    # ── SVG export ────────────────────────────────────────────────

    def to_svg(self) -> str:
        """Serialise the document to an SVG string."""
        parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" version="1.2" '
            'baseProfile="tiny" viewBox="0 0 %d %d">'
            % (self._view_w, self._view_h)]
        for shape in self._shapes:
            parts.append(self._shape_svg(shape))
        parts.append("</svg>")
        return "\n".join(parts)

    def save_svg(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_svg())

    def render_image(self) -> QtGui.QImage:
        """Render the board (shapes only, white background) to a 1x image."""
        image = QtGui.QImage(self._view_w, self._view_h,
                             QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor("#ffffff"))
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        for shape in self._shapes:
            self._draw_shape(painter, shape)
        painter.end()
        return image

    def save_png(self, path: str) -> bool:
        """Write the board to *path* as a PNG; returns success."""
        return bool(self.render_image().save(path, "PNG"))

    @staticmethod
    def _shape_svg(shape: dict) -> str:
        if shape.get("kind") == "image":
            x, y, w, h = shape["image"]
            attrs = [f'id="{shape["id"]}"', f'x="{x:g}"', f'y="{y:g}"',
                     f'width="{w:g}"', f'height="{h:g}"',
                     'xlink:href="%s"' % escape_html(shape.get("href") or "")]
            transform = transform_str(shape["transform"])
            if transform:
                attrs.append(f'transform="{transform}"')
            return ('  <image xmlns:xlink="%s" %s/>'
                    % (XLINK_NS, " ".join(attrs)))
        d = WhiteboardCanvas.shape_d(shape)
        if not d:
            return ""
        attrs = [f'id="{shape["id"]}"',
                 f'd="{d}"',
                 f'stroke="{shape["stroke"]}"',
                 f'stroke-width="{shape["stroke_width"]}"',
                 f'fill="{shape["fill"]}"'
                 if WhiteboardCanvas._filled(shape) else 'fill="none"']
        transform = transform_str(shape["transform"])
        if transform:
            attrs.append(f'transform="{transform}"')
        return "  <path %s/>" % " ".join(attrs)
