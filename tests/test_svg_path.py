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

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All svg_path tests passed.")
