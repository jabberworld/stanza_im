"""Tests for the SVG path-data parser/builder (whiteboard serialisation).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_svg_path.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_svg_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets

from stanza_im.include import svg_path

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


# 1. basic line path ---------------------------------------------------------
path = svg_path.parse_path("M 0 0 L 10 20 L 30 20")
rect = path.boundingRect()
check("a line path has the right bounds",
      approx(rect.left(), 0) and approx(rect.top(), 0)
      and approx(rect.right(), 30) and approx(rect.bottom(), 20))

# 2. relative commands -------------------------------------------------------
path = svg_path.parse_path("m 5 5 l 10 0 l 0 10")
rect = path.boundingRect()
check("relative commands accumulate",
      approx(rect.right(), 15) and approx(rect.bottom(), 15))

# 3. close path --------------------------------------------------------------
path = svg_path.parse_path("M 0 0 L 10 0 L 10 10 Z")
check("closepath adds an element", path.elementCount() > 0)

# 4. rect / ellipse builders round-trip through the parser -------------------
rect_path = svg_path.parse_path(svg_path.rect_d(10, 20, 30, 40))
check("rect_d bounds", approx(rect_path.boundingRect().width(), 30)
      and approx(rect_path.boundingRect().height(), 40))
ellipse_path = svg_path.parse_path(svg_path.ellipse_d(50, 50, 20, 10))
bounds = ellipse_path.boundingRect()
check("ellipse_d bounds", approx(bounds.width(), 40, 1e-3)
      and approx(bounds.height(), 20, 1e-3))

# 4b. basic SVG shapes from a peer (Psi sends rect/ellipse/polygon) ----------
from stanza_im.include import svg_shapes  # noqa: E402

check("points pairs accept commas and spaces",
      svg_shapes.points_pairs("530.4,516.8 582.4,588")
      == [(530.4, 516.8), (582.4, 588.0)])
check("points pairs drop junk and a lone trailing number",
      svg_shapes.points_pairs("0,0 bad 10 10 5")
      == [(0.0, 0.0), (10.0, 10.0)])
rect = svg_path.parse_path(svg_shapes.element_d(
    "rect", {"x": "10", "y": "20", "width": "30", "height": "40"}))
check("element_d rect bounds",
      approx(rect.boundingRect().width(), 30)
      and approx(rect.boundingRect().height(), 40))
circle = svg_path.parse_path(svg_shapes.element_d(
    "circle", {"cx": "50", "cy": "50", "r": "10"}))
check("element_d circle is an ellipse",
      approx(circle.boundingRect().width(), 20, 1e-3)
      and approx(circle.boundingRect().height(), 20, 1e-3))
line = svg_path.parse_path(svg_shapes.element_d(
    "line", {"x1": "0", "y1": "0", "x2": "10", "y2": "0"}))
check("element_d line has the right length", approx(line.length(), 10, 1e-3))
polygon_d = svg_shapes.element_d("polygon", {"points": "0,0 10,0 10,10"})
check("element_d polygon is closed", polygon_d.count("L") == 2
      and polygon_d.endswith("Z"))
check("element_d polyline stays open",
      not svg_shapes.element_d("polyline", {"points": "0,0 10,0"}).endswith("Z"))
check("rounded rect keeps its size",
      approx(svg_path.parse_path(svg_shapes.element_d(
          "rect", {"width": "40", "height": "20", "rx": "5"})
      ).boundingRect().width(), 40, 1e-3))
diamond = svg_path.parse_path(svg_shapes.diamond_d(10, 20, 40, 60))
check("diamond_d bounds",
      approx(diamond.boundingRect().width(), 40, 1e-3)
      and approx(diamond.boundingRect().height(), 60, 1e-3))
check("diamond_d is closed and re-exported",
      diamond.elementCount() >= 5
      and svg_path.diamond_d(0, 0, 10, 10).endswith("Z"))
check("an unsupported element has no path data",
      svg_shapes.element_d("text", {"x": "1"}) == "")
check("a zero-size rect has no path data",
      svg_shapes.element_d("rect", {"width": "0", "height": "5"}) == "")

# 5. curve commands ----------------------------------------------------------
path = svg_path.parse_path("M 0 0 C 10 0 10 10 20 10")
check("cubic curve produces elements", path.elementCount() >= 4)
path = svg_path.parse_path("M 0 0 Q 10 0 20 10 T 40 10")
check("smooth quad is accepted", path.elementCount() >= 3)

# 6. arc command -------------------------------------------------------------
path = svg_path.parse_path("M 0 0 A 10 10 0 1 0 20 0")
check("arc is converted to curves", path.elementCount() >= 4)

# 7. empty input -------------------------------------------------------------
check("empty path is empty", svg_path.parse_path("").elementCount() == 0)
check("polyline_d of nothing is empty", svg_path.polyline_d([]) == "")

# 8. path_to_d (QPainterPath -> SVG path data) ------------------------------
from PyQt6 import QtGui as _QtGui  # noqa: E402

p = _QtGui.QPainterPath()
p.moveTo(0, 0)
p.lineTo(10, 0)
p.lineTo(10, 10)
p.closeSubpath()
d = svg_path.path_to_d(p)
check("path_to_d emits move/line/close",
      d.startswith("M") and "L" in d and d.endswith("Z"))
rt = svg_path.parse_path(d)
check("path_to_d round-trips through parse_path",
      abs(rt.boundingRect().width() - 10) < 1e-6
      and abs(rt.boundingRect().height() - 10) < 1e-6)

ellipse = _QtGui.QPainterPath()
ellipse.addEllipse(0, 0, 10, 10)
check("path_to_d emits curves for an ellipse",
      "C" in svg_path.path_to_d(ellipse))

font = _QtGui.QFont()
font.setPointSizeF(24.0)
glyphs = _QtGui.QPainterPath()
glyphs.addText(0, 0, font, "Ag")
glyph_d = svg_path.path_to_d(glyphs)
check("text glyphs produce non-empty path data", bool(glyph_d))
check("glyph path data parses", svg_path.parse_path(glyph_d).elementCount() > 0)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All svg_path tests passed.")
