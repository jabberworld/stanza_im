"""Minimal SVG ``transform`` (matrix) parsing and composition.

Pure Python (no Qt), so the XMPP layer can compose a group's transform into its
children (the whiteboard's ungroup operation) without importing the UI.  Only
``matrix(a b c d e f)`` is handled — the form the whiteboard itself emits.
"""
from __future__ import annotations

import re

_MATRIX_RE = re.compile(
    r"matrix\(\s*([-\d.eE+]+)[\s,]+([-\d.eE+]+)[\s,]+([-\d.eE+]+)[\s,]+"
    r"([-\d.eE+]+)[\s,]+([-\d.eE+]+)[\s,]+([-\d.eE+]+)\s*\)")


def parse_matrix(value) -> tuple[float, float, float, float, float, float] | None:
    """Parse an SVG ``matrix(...)`` attribute into ``(a, b, c, d, e, f)``."""
    if not value:
        return None
    match = _MATRIX_RE.search(str(value))
    if not match:
        return None
    try:
        return tuple(float(g) for g in match.groups())
    except (TypeError, ValueError):
        return None


def compose(outer, inner):
    """The matrix of applying *inner* then *outer* (the SVG attribute order)."""
    a1, b1, c1, d1, e1, f1 = outer
    a2, b2, c2, d2, e2, f2 = inner
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def is_identity(matrix) -> bool:
    if matrix is None:
        return True
    a, b, c, d, e, f = matrix
    return (abs(a - 1) < 1e-9 and abs(b) < 1e-9 and abs(c) < 1e-9
            and abs(d - 1) < 1e-9 and abs(e) < 1e-9 and abs(f) < 1e-9)


def to_str(matrix) -> str:
    """Serialise a matrix tuple as an SVG ``matrix(...)`` ("" when identity)."""
    if is_identity(matrix):
        return ""
    return "matrix(%g %g %g %g %g %g)" % tuple(matrix)
