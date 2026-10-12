"""Whiteboard drawing canvas.

A :class:`WhiteboardCanvas` holds an ordered list of SVG-like shape records and
renders them with a custom ``QPainter`` pass (no WebEngine).  It implements the
interactive tools (draw, select, move, rotate, scale) and can serialise the
document to SVG.
"""
from __future__ import annotations

import math
import uuid

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.include import svg_path
from stanza_im.include.constants import (WHITEBOARD_HEIGHT, WHITEBOARD_WIDTH)

#: Logical canvas size (the SVG ``viewBox``).
VIEW_W = WHITEBOARD_WIDTH
VIEW_H = WHITEBOARD_HEIGHT

#: Tools that draw a new shape (as opposed to editing an existing one).
DRAW_TOOLS = ("pencil", "line", "rect", "ellipse", "polygon")
#: Shapes whose closed area is filled with the fill colour.
CLOSED_KINDS = ("rect", "ellipse", "polygon")

#: View (zoom) limits.
MIN_VIEW_ZOOM = 0.25
MAX_VIEW_ZOOM = 8.0

_MATRIX_RE = __import__("re").compile(
    r"matrix\(\s*([-\d.eE+]+)[\s,]+([-\d.eE+]+)[\s,]+([-\d.eE+]+)[\s,]+"
    r"([-\d.eE+]+)[\s,]+([-\d.eE+]+)[\s,]+([-\d.eE+]+)\s*\)")


def _parse_transform(value) -> QtGui.QTransform:
    """Parse an SVG ``transform`` attribute (``matrix(...)``) into a transform."""
    if not value:
        return QtGui.QTransform()
    match = _MATRIX_RE.search(str(value))
    if not match:
        return QtGui.QTransform()
    try:
        a, b, c, d, e, f = (float(g) for g in match.groups())
    except (TypeError, ValueError):
        return QtGui.QTransform()
    return QtGui.QTransform(a, b, c, d, e, f)


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shapes: list[dict] = []
        self._selected: str = ""
        self._tool = "pencil"
        self._stroke = "#1a1a1a"
        self._fill = "#e53935"
        self._width = 2
        self._active: dict | None = None
        self._start: QtCore.QPointF | None = None
        self._last: QtCore.QPointF | None = None
        self._transformed = False
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
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor
                       if tool in DRAW_TOOLS
                       else QtCore.Qt.CursorShape.ArrowCursor)

    def tool(self) -> str:
        return self._tool

    def set_stroke(self, color: str) -> None:
        self._stroke = color

    def set_fill(self, color: str) -> None:
        self._fill = color

    def set_width(self, width: int) -> None:
        self._width = max(1, int(width))

    def shapes(self) -> list[dict]:
        return self._shapes

    def selected_id(self) -> str:
        return self._selected

    # ── Actions ───────────────────────────────────────────────────

    def clear(self) -> None:
        for shape in self._shapes:
            self.shape_removed.emit(shape)
        self._shapes = []
        self._selected = ""
        self._active = None
        self.update()
        self.changed.emit()

    def delete_selected(self) -> None:
        if not self._selected:
            return
        shape = self._shape_by_id(self._selected)
        self._shapes = [s for s in self._shapes if s["id"] != self._selected]
        self._selected = ""
        self.update()
        self.changed.emit()
        if shape is not None:
            self.shape_removed.emit(shape)

    def set_rid(self, shape_id: str, rid: str) -> None:
        """Record the SXE record id the collaborative session assigned."""
        shape = self._shape_by_id(shape_id)
        if shape is not None:
            shape["rid"] = str(rid or "")

    @staticmethod
    def shape_attrs(shape: dict) -> dict:
        """The SVG attributes of *shape* (for a collaborative edit)."""
        return {
            "id": shape["id"],
            "d": WhiteboardCanvas.shape_d(shape),
            "stroke": shape["stroke"],
            "stroke-width": str(shape["stroke_width"]),
            "fill": (shape["fill"] if WhiteboardCanvas._filled(shape)
                     else "none"),
            "transform": transform_str(shape["transform"]),
        }

    def finish_drawing(self) -> None:
        """Commit the in-progress shape (e.g. close a polygon) and stop."""
        if self._active is not None:
            self._commit_active()
        self.set_tool("select")
        self.update()

    # ── Geometry helpers ──────────────────────────────────────────

    def _fit_scale(self) -> float:
        """The board-to-widget scale at zoom 1 (fits the whole board)."""
        if self.width() <= 0 or self.height() <= 0:
            return 1.0
        return min(self.width() / VIEW_W, self.height() / VIEW_H)

    def _scale(self) -> float:
        """The current view scale (fit scale times the view zoom)."""
        return self._fit_scale() * self._view_zoom

    def _offset(self) -> tuple[float, float]:
        s = self._scale()
        return ((self.width() - VIEW_W * s) / 2.0 + self._view_pan.x(),
                (self.height() - VIEW_H * s) / 2.0 + self._view_pan.y())

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
            cx = (self.width() - VIEW_W * s) / 2.0
            cy = (self.height() - VIEW_H * s) / 2.0
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
        if shape.get("kind") == "remote":
            return svg_path.parse_path(shape.get("d") or "")
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

    @staticmethod
    def _world_path(shape: dict) -> QtGui.QPainterPath:
        return shape["transform"].map(WhiteboardCanvas._local_path(shape))

    @staticmethod
    def _filled(shape: dict) -> bool:
        # ``fill="none"`` (sent for open shapes: line, pencil) means "no fill"
        # — a bare ``bool("none")`` is True and would fill a remote line.
        value = str(shape.get("fill") or "")
        if not value or value.lower() == "none":
            return False
        if shape.get("kind") == "remote":
            return True
        return shape["kind"] in CLOSED_KINDS

    @staticmethod
    def shape_d(shape: dict) -> str:
        """The SVG ``d`` attribute for *shape*."""
        if shape.get("kind") == "remote":
            return shape.get("d") or ""
        kind = shape["kind"]
        if kind in ("pencil", "line", "polygon"):
            return svg_path.polyline_d(shape.get("points") or [],
                                       close=(kind == "polygon"))
        if kind == "rect":
            return svg_path.rect_d(*shape["rect"])
        if kind == "ellipse":
            return svg_path.ellipse_d(*shape["ellipse"])
        return ""

    def load_shapes(self, shapes: list[dict]) -> None:
        """Rebuild the board from a list of shape descriptors (remote state).

        Each descriptor carries ``rid``, ``d`` and the presentation attributes.
        """
        loaded: list[dict] = []
        for item in shapes:
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
            loaded.append(shape)
        self._shapes = loaded
        self._selected = ""
        self._active = None
        self.update()
        self.changed.emit()

    def _shape_by_id(self, shape_id: str) -> dict | None:
        return next((s for s in self._shapes if s["id"] == shape_id), None)

    def _new_shape(self, kind: str, **extra) -> dict:
        shape = {"id": uuid.uuid4().hex, "rid": "", "kind": kind,
                 "stroke": self._stroke, "stroke_width": self._width,
                 "fill": self._fill, "transform": QtGui.QTransform()}
        shape.update(extra)
        return shape

    def _shape_at(self, world: QtCore.QPointF) -> dict | None:
        """The topmost shape under *world* (hit-test), or ``None``."""
        for shape in reversed(self._shapes):
            path = self._world_path(shape)
            stroker = QtGui.QPainterPathStroker()
            stroker.setWidth(max(8.0, shape["stroke_width"] + 4.0))
            if stroker.createStroke(path).contains(world):
                return shape
            if self._filled(shape) and path.contains(world):
                return shape
        return None

    def _select_at(self, world: QtCore.QPointF) -> None:
        shape = self._shape_at(world)
        self._selected = shape["id"] if shape is not None else ""

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
        for gx in range(0, VIEW_W + 1, 100):
            painter.drawLine(gx, 0, gx, VIEW_H)
        for gy in range(0, VIEW_H + 1, 100):
            painter.drawLine(0, gy, VIEW_W, gy)
        for shape in self._shapes:
            self._draw_shape(painter, shape)
        if self._active is not None:
            self._draw_shape(painter, self._active)
        if self._selected:
            shape = self._shape_by_id(self._selected)
            if shape is not None:
                rect = self._world_path(shape).boundingRect()
                pen = QtGui.QPen(QtGui.QColor("#1a73e8"),
                                 max(1.0, 1.0 / max(s, 1e-6)))
                pen.setStyle(QtCore.Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
        painter.restore()

    def _draw_shape(self, painter: QtGui.QPainter, shape: dict) -> None:
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
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        world = self._to_world(event.position())
        tool = self._tool
        if tool == "select":
            self._select_at(world)
            if not self._selected:
                # Dragging empty space pans the view.
                self._pan_origin = event.position()
                self._pan_start = QtCore.QPointF(self._view_pan)
                self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            self.update()
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
            elif tool == "line":
                self._active = self._new_shape(
                    "line", points=[(world.x(), world.y()),
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
        if self._active is not None:
            kind = self._active["kind"]
            if kind in ("pencil", "polygon"):
                self._active["points"].append((world.x(), world.y()))
            elif kind == "line":
                self._active["points"][1] = (world.x(), world.y())
            elif kind == "rect":
                self._active["rect"] = self._rect_from(self._start, world)
            elif kind == "ellipse":
                self._active["ellipse"] = self._ellipse_from(self._start, world)
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
        over = self._shape_at(self._to_world(pos)) is not None
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor if over
                       else QtCore.Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._pan_origin is not None:
            self._pan_origin = None
            self._update_select_cursor(event.position())
            return
        if self._active is not None:
            self._commit_active()
        elif self._transformed and self._selected:
            shape = self._shape_by_id(self._selected)
            if shape is not None:
                self.shape_updated.emit(shape)
        self._transformed = False
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
    def _transform(shape: dict, tool: str, last, world) -> None:
        if tool == "move":
            op = QtGui.QTransform()
            op.translate(world.x() - last.x(), world.y() - last.y())
        else:
            center = WhiteboardCanvas._world_path(shape).boundingRect().center()
            if tool == "rotate":
                a0 = math.atan2(last.y() - center.y(), last.x() - center.x())
                a1 = math.atan2(world.y() - center.y(), world.x() - center.x())
                degrees = math.degrees(a1 - a0)
                op = QtGui.QTransform()
                op.translate(center.x(), center.y())
                op.rotate(degrees)
                op.translate(-center.x(), -center.y())
            else:  # scale
                d0 = math.hypot(last.x() - center.x(), last.y() - center.y())
                d1 = math.hypot(world.x() - center.x(), world.y() - center.y())
                if d0 < 1.0:
                    return
                factor = max(0.05, d1 / d0)
                op = QtGui.QTransform()
                op.translate(center.x(), center.y())
                op.scale(factor, factor)
                op.translate(-center.x(), -center.y())
        shape["transform"] = shape["transform"] * op

    # ── SVG export ────────────────────────────────────────────────

    def to_svg(self) -> str:
        """Serialise the document to an SVG string."""
        parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" version="1.2" '
            'baseProfile="tiny" viewBox="0 0 %d %d">' % (VIEW_W, VIEW_H)]
        for shape in self._shapes:
            parts.append(self._shape_svg(shape))
        parts.append("</svg>")
        return "\n".join(parts)

    def save_svg(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_svg())

    @staticmethod
    def _shape_svg(shape: dict) -> str:
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
