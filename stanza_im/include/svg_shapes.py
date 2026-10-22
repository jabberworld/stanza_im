"""Pure SVG basic-shape builders (path data), shared by the whiteboard.

The whiteboard document is SVG, so a peer may describe a drawable as a
``<rect/>``, ``<ellipse/>``, ``<circle/>``, ``<line/>``, ``<polyline/>`` or
``<polygon/>`` instead of a ``<path/>`` (Psi does exactly that).  Our canvas
renders remote objects from path data, so these helpers turn the basic shapes
into a ``d`` attribute.  No Qt import: the XMPP layer uses them too.
"""
from __future__ import annotations

import re

_NUMBER_SPLIT = re.compile(r"[\s,]+")


def polyline_d(points: list[tuple[float, float]], close: bool = False) -> str:
    """Build a ``d`` string for a polyline (optionally closed)."""
    if not points:
        return ""
    parts = ["M %g %g" % (points[0][0], points[0][1])]
    for x, y in points[1:]:
        parts.append("L %g %g" % (x, y))
    if close:
        parts.append("Z")
    return " ".join(parts)


def rect_d(x: float, y: float, w: float, h: float,
           rx: float = 0.0, ry: float = 0.0) -> str:
    """Path data for a rectangle, optionally with rounded corners."""
    w = abs(w)
    h = abs(h)
    radius_x = max(0.0, min(abs(rx), w / 2.0))
    radius_y = max(0.0, min(abs(ry or rx), h / 2.0))
    if radius_x <= 0.0 or radius_y <= 0.0:
        return "M %g %g L %g %g L %g %g L %g %g Z" % (
            x, y, x + w, y, x + w, y + h, x, y + h)
    return (
        "M %g %g L %g %g A %g %g 0 0 1 %g %g "
        "L %g %g A %g %g 0 0 1 %g %g "
        "L %g %g A %g %g 0 0 1 %g %g "
        "L %g %g A %g %g 0 0 1 %g %g Z"
        % (x + radius_x, y, x + w - radius_x, y,
           radius_x, radius_y, x + w, y + radius_y,
           x + w, y + h - radius_y,
           radius_x, radius_y, x + w - radius_x, y + h,
           x + radius_x, y + h,
           radius_x, radius_y, x, y + h - radius_y,
           x, y + radius_y,
           radius_x, radius_y, x + radius_x, y))


def diamond_d(x: float, y: float, w: float, h: float) -> str:
    """Path data for a rhombus inscribed in the (x, y, w, h) rectangle.

    The vertices sit at the middle of each side, so the drag rectangle defines
    the diamond's corners exactly like it defines an ellipse's extents.
    """
    w = abs(w)
    h = abs(h)
    cx = x + w / 2.0
    cy = y + h / 2.0
    return "M %g %g L %g %g L %g %g L %g %g Z" % (
        cx, y, x + w, cy, cx, y + h, x, cy)


def ellipse_d(cx: float, cy: float, rx: float, ry: float) -> str:
    rx = abs(rx)
    ry = abs(ry)
    return ("M %g %g A %g %g 0 1 0 %g %g A %g %g 0 1 0 %g %g Z"
            % (cx - rx, cy, rx, ry, cx + rx, cy, rx, ry, cx - rx, cy))


def points_pairs(text) -> list[tuple[float, float]]:
    """Parse an SVG ``points`` attribute into ``(x, y)`` pairs.

    Commas and whitespace are both accepted (Psi writes "x,y x,y"); an odd
    trailing number and unparsable tokens are dropped.
    """
    tokens = [token for token in _NUMBER_SPLIT.split(str(text or "").strip())
              if token]
    values: list[float] = []
    for token in tokens:
        try:
            values.append(float(token))
        except ValueError:
            continue
    return [(values[i], values[i + 1])
            for i in range(0, len(values) - 1, 2)]


def _number(attrs, key: str, default: float = 0.0) -> float:
    try:
        return float(attrs.get(key, default))
    except (TypeError, ValueError):
        return default


def element_d(name: str, attrs) -> str:
    """Path data for a basic SVG element named *name* ("" when unsupported)."""
    if name == "rect":
        width = abs(_number(attrs, "width"))
        height = abs(_number(attrs, "height"))
        if width <= 0 or height <= 0:
            return ""
        return rect_d(_number(attrs, "x"), _number(attrs, "y"),
                      width, height,
                      _number(attrs, "rx"), _number(attrs, "ry"))
    if name == "ellipse":
        rx = abs(_number(attrs, "rx"))
        ry = abs(_number(attrs, "ry"))
        if rx <= 0 or ry <= 0:
            return ""
        return ellipse_d(_number(attrs, "cx"), _number(attrs, "cy"), rx, ry)
    if name == "circle":
        radius = abs(_number(attrs, "r"))
        if radius <= 0:
            return ""
        return ellipse_d(_number(attrs, "cx"), _number(attrs, "cy"),
                         radius, radius)
    if name == "line":
        return polyline_d([(_number(attrs, "x1"), _number(attrs, "y1")),
                           (_number(attrs, "x2"), _number(attrs, "y2"))])
    if name in ("polyline", "polygon"):
        points = points_pairs(attrs.get("points", ""))
        if len(points) < 2:
            return ""
        return polyline_d(points, close=(name == "polygon"))
    return ""
