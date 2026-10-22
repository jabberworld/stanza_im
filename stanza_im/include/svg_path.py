"""Minimal SVG path-data parser and builder (QPainterPath).

The whiteboard serialises every shape as a ``<path d="…"/>`` element, so a
remote edit can be rendered by parsing its ``d``.  The parser supports the SVG
path grammar used by the whiteboard (moveto, lineto, horizontal/vertical
lineto, cubic/quadratic curves, elliptical arcs and closepath, absolute and
relative).
"""
from __future__ import annotations

import math
import re

from PyQt6 import QtCore, QtGui

_NUM = r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
_TOKEN_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|(" + _NUM + r")")


def _tokens(data: str) -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for match in _TOKEN_RE.finditer(data or ""):
        if match.group(1):
            out.append(("cmd", match.group(1)))
        else:
            out.append(("num", float(match.group(2))))
    return out


def parse_path(data: str) -> QtGui.QPainterPath:
    """Parse an SVG path-data string into a :class:`QPainterPath`."""
    path = QtGui.QPainterPath()
    tokens = _tokens(data)
    index = 0
    command = ""
    current = QtCore.QPointF(0.0, 0.0)
    sub_start = QtCore.QPointF(0.0, 0.0)
    prev_cubic_ctrl = None
    prev_quad_ctrl = None

    def number() -> float | None:
        nonlocal index
        if index < len(tokens) and tokens[index][0] == "num":
            value = float(tokens[index][1])
            index += 1
            return value
        return None

    def flag() -> float | None:
        # Arc flags may be written without separators ("0 0 1" or "001").
        nonlocal index
        if index >= len(tokens):
            return None
        kind, value = tokens[index]
        if kind == "num":
            index += 1
            return float(value)
        return None

    while index < len(tokens):
        kind, value = tokens[index]
        if kind == "cmd":
            command = str(value)
            index += 1
            if command in "Zz":
                path.closeSubpath()
                current = QtCore.QPointF(sub_start)
                continue
        elif not command:
            index += 1
            continue

        relative = command.islower()
        cmd = command.upper()

        if cmd == "M":
            x = number()
            y = number()
            if x is None or y is None:
                break
            if relative:
                x += current.x()
                y += current.y()
            current = QtCore.QPointF(x, y)
            sub_start = QtCore.QPointF(current)
            path.moveTo(current)
            command = "l" if relative else "L"
        elif cmd == "L":
            x = number()
            y = number()
            if x is None or y is None:
                break
            if relative:
                x += current.x()
                y += current.y()
            current = QtCore.QPointF(x, y)
            path.lineTo(current)
        elif cmd == "H":
            x = number()
            if x is None:
                break
            if relative:
                x += current.x()
            current = QtCore.QPointF(x, current.y())
            path.lineTo(current)
        elif cmd == "V":
            y = number()
            if y is None:
                break
            if relative:
                y += current.y()
            current = QtCore.QPointF(current.x(), y)
            path.lineTo(current)
        elif cmd in ("C", "S"):
            if cmd == "C":
                x1 = number()
                y1 = number()
            else:
                x1 = y1 = None
            x2 = number()
            y2 = number()
            x = number()
            y = number()
            if None in (x2, y2, x):
                break
            if relative:
                x2 += current.x()
                y2 += current.y()
                x += current.x()
                y += current.y()
            if x1 is None:
                if prev_cubic_ctrl is not None:
                    x1 = 2 * current.x() - prev_cubic_ctrl.x()
                    y1 = 2 * current.y() - prev_cubic_ctrl.y()
                else:
                    x1, y1 = current.x(), current.y()
            elif relative:
                x1 += current.x()
                y1 += current.y()
            ctrl2 = QtCore.QPointF(x2, y2)
            path.cubicTo(QtCore.QPointF(x1, y1), ctrl2, QtCore.QPointF(x, y))
            prev_cubic_ctrl = ctrl2
            prev_quad_ctrl = None
            current = QtCore.QPointF(x, y)
        elif cmd in ("Q", "T"):
            if cmd == "Q":
                x1 = number()
                y1 = number()
            else:
                x1 = y1 = None
            x = number()
            y = number()
            if x is None or y is None:
                break
            if relative:
                x += current.x()
                y += current.y()
            if x1 is None:
                if prev_quad_ctrl is not None:
                    x1 = 2 * current.x() - prev_quad_ctrl.x()
                    y1 = 2 * current.y() - prev_quad_ctrl.y()
                else:
                    x1, y1 = current.x(), current.y()
            elif relative:
                x1 += current.x()
                y1 += current.y()
            ctrl = QtCore.QPointF(x1, y1)
            path.quadTo(ctrl, QtCore.QPointF(x, y))
            prev_quad_ctrl = ctrl
            prev_cubic_ctrl = None
            current = QtCore.QPointF(x, y)
        elif cmd == "A":
            rx = number()
            ry = number()
            rotation = number()
            large = flag()
            sweep = flag()
            x = number()
            y = number()
            if None in (rx, ry, rotation, large, sweep, x, y):
                break
            if relative:
                x += current.x()
                y += current.y()
            _arc_to(path, current, rx, ry, rotation, bool(large),
                    bool(sweep), QtCore.QPointF(x, y))
            current = QtCore.QPointF(x, y)
            prev_cubic_ctrl = None
            prev_quad_ctrl = None
        else:
            index += 1
    return path


def _arc_to(path: QtGui.QPainterPath, start: QtCore.QPointF, rx: float,
            ry: float, rotation: float, large: bool, sweep: bool,
            end: QtCore.QPointF) -> None:
    """Append an SVG elliptical arc (endpoint parametrisation) to *path*."""
    if rx == 0 or ry == 0 or start == end:
        path.lineTo(end)
        return
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rotation % 360.0)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx = (start.x() - end.x()) / 2.0
    dy = (start.y() - end.y()) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale
    sign = -1 if large == sweep else 1
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = sign * math.sqrt(max(0.0, num / den)) if den else 0.0
    cxp = coef * (rx * y1p / ry)
    cyp = coef * (-ry * x1p / rx)
    cx = cos_phi * cxp - sin_phi * cyp + (start.x() + end.x()) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (start.y() + end.y()) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        norm = math.hypot(ux, uy) * math.hypot(vx, vy)
        if norm == 0:
            return 0.0
        value = max(-1.0, min(1.0, dot / norm))
        result = math.acos(value)
        if ux * vy - uy * vx < 0:
            result = -result
        return result

    theta1 = angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                  (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    segments = max(1, int(math.ceil(abs(delta) / (math.pi / 2))))
    step = delta / segments
    t = 4.0 / 3.0 * math.tan(step / 4.0)
    for _ in range(segments):
        cos1, sin1 = math.cos(theta1), math.sin(theta1)
        cos2, sin2 = math.cos(theta1 + step), math.sin(theta1 + step)
        p1x = cx + rx * cos1 * cos_phi - ry * sin1 * sin_phi
        p1y = cy + rx * cos1 * sin_phi + ry * sin1 * cos_phi
        p2x = cx + rx * cos2 * cos_phi - ry * sin2 * sin_phi
        p2y = cy + rx * cos2 * sin_phi + ry * sin2 * cos_phi
        d1x = -rx * sin1 * cos_phi - ry * cos1 * sin_phi
        d1y = -rx * sin1 * sin_phi + ry * cos1 * cos_phi
        d2x = -rx * sin2 * cos_phi - ry * cos2 * sin_phi
        d2y = -rx * sin2 * sin_phi + ry * cos2 * cos_phi
        c1 = QtCore.QPointF(p1x + t * d1x, p1y + t * d1y)
        c2 = QtCore.QPointF(p2x - t * d2x, p2y - t * d2y)
        path.cubicTo(c1, c2, QtCore.QPointF(p2x, p2y))
        theta1 += step


# The basic-shape builders live in a Qt-free module (the XMPP layer needs
# them too) and are re-exported here for the canvas and the tests.
from stanza_im.include.svg_shapes import (  # noqa: F401
    ellipse_d, points_pairs, polyline_d, rect_d)


def path_to_d(path: QtGui.QPainterPath) -> str:
    """Serialise a :class:`QPainterPath` to SVG path data.

    Used to turn text glyph outlines (``QPainterPath.addText``) into a plain
    ``<path d="…"/>``; every contour is closed with ``Z`` (glyph outlines are
    filled, matching Qt's implicit closing when filling).
    """
    move = QtGui.QPainterPath.ElementType.MoveToElement
    line = QtGui.QPainterPath.ElementType.LineToElement
    curve = QtGui.QPainterPath.ElementType.CurveToElement
    parts: list[str] = []
    i = 0
    count = path.elementCount()
    while i < count:
        el = path.elementAt(i)
        if el.type == move:
            if parts and parts[-1] != "Z":
                parts.append("Z")
            parts.append("M %g %g" % (el.x, el.y))
            i += 1
        elif el.type == line:
            parts.append("L %g %g" % (el.x, el.y))
            i += 1
        elif el.type == curve and i + 2 < count:
            c2 = path.elementAt(i + 1)
            end = path.elementAt(i + 2)
            parts.append("C %g %g %g %g %g %g"
                         % (el.x, el.y, c2.x, c2.y, end.x, end.y))
            i += 3
        else:
            i += 1
    if parts and parts[-1] != "Z":
        parts.append("Z")
    return " ".join(parts)
