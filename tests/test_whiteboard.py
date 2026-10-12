"""Tests for the whiteboard canvas, dialog and chat toolbar button.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_whiteboard.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_wb_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.whiteboard_canvas import WhiteboardCanvas
from stanza_im.ui.whiteboard_dialog import WhiteboardDialog

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _event(kind, x, y, buttons=QtCore.Qt.MouseButton.LeftButton,
           button=QtCore.Qt.MouseButton.LeftButton):
    return QtGui.QMouseEvent(kind, QtCore.QPointF(x, y), QtCore.QPointF(x, y),
                             button, buttons,
                             QtCore.Qt.KeyboardModifier.NoModifier)


def drag(widget, x1, y1, x2, y2, steps=3):
    QtWidgets.QApplication.sendEvent(
        widget, _event(QtCore.QEvent.Type.MouseButtonPress, x1, y1))
    for i in range(1, steps + 1):
        QtWidgets.QApplication.sendEvent(widget, _event(
            QtCore.QEvent.Type.MouseMove,
            x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps))
    QtWidgets.QApplication.sendEvent(widget, _event(
        QtCore.QEvent.Type.MouseButtonRelease, x2, y2,
        buttons=QtCore.Qt.MouseButton.NoButton))


# 1. drawing every shape type ------------------------------------------------
canvas = WhiteboardCanvas()
canvas.resize(1280, 720)   # 1:1 with the 1280x720 viewBox
canvas.set_tool("rect")
drag(canvas, 100, 100, 200, 150)
canvas.set_tool("ellipse")
drag(canvas, 250, 100, 350, 180)
canvas.set_tool("line")
drag(canvas, 100, 200, 200, 250)
canvas.set_tool("pencil")
drag(canvas, 300, 250, 340, 280, steps=6)
canvas.set_tool("polygon")
drag(canvas, 400, 100, 470, 110, steps=6)
check("all shape kinds are drawn",
      [s["kind"] for s in canvas.shapes()]
      == ["rect", "ellipse", "line", "pencil", "polygon"])
check("a rect stores its geometry",
      canvas.shapes()[0]["rect"][2] == 100
      and canvas.shapes()[0]["rect"][3] == 50)
check("a pencil stores its points",
      len(canvas.shapes()[3]["points"]) >= 2)

# 2. SVG export --------------------------------------------------------------
svg = canvas.to_svg()
check("the SVG has the root and viewBox",
      "<svg" in svg and 'viewBox="0 0 1280 720"' in svg)
check("the SVG serialises every shape as a path",
      svg.count("<path") == 5)
check("the rect geometry is written as path data",
      "M 100 100 L 200 100 L 200 150 L 100 150 Z" in svg)
check("a polygon is closed in the path data", " Z" in svg)
check("a filled shape carries a fill colour", 'fill="#e53935"' in svg)

# 3. select / move / rotate / scale ------------------------------------------
canvas.set_tool("select")
QtWidgets.QApplication.sendEvent(canvas, _event(
    QtCore.QEvent.Type.MouseButtonPress, 150, 120))
selected = canvas.selected_id()
check("clicking a shape selects it", bool(selected))
canvas.set_tool("move")
drag(canvas, 150, 120, 180, 140, steps=3)
moved = canvas._shape_by_id(selected)["transform"]
check("moving updates the transform", moved.dx() > 10)
before = canvas._shape_by_id(selected)["transform"].m11()
canvas.set_tool("scale")
drag(canvas, 200, 150, 260, 200, steps=3)
after = canvas._shape_by_id(selected)["transform"].m11()
check("scaling changes the transform", after != before)

# 4. delete and clear --------------------------------------------------------
canvas.set_tool("select")
QtWidgets.QApplication.sendEvent(canvas, _event(
    QtCore.QEvent.Type.MouseButtonPress, 190, 150))
canvas.delete_selected()
check("delete removes the selected shape", len(canvas.shapes()) == 4)
canvas.clear()
check("clear empties the board", canvas.shapes() == [])

# 5. the dialog builds its tools and actions ---------------------------------
dialog = WhiteboardDialog("bob@example.com")
check("the dialog has every tool button",
      set(dialog._tool_buttons) == {
          "select", "move", "rotate", "scale", "pencil", "line",
          "rect", "ellipse", "polygon"})
check("the pencil tool is active by default",
      dialog._tool_buttons["pencil"].isChecked())
check("the dialog embeds the canvas",
      isinstance(dialog._canvas, WhiteboardCanvas))
dialog.close()

# 6. the chat toolbar exposes the whiteboard button --------------------------
widget = ChatWidget("bob@example.com", "Bob", ChatThemeFactory())
check("the chat has a whiteboard button", hasattr(widget, "_whiteboard_btn"))
check("the whiteboard button carries an icon",
      not widget._whiteboard_btn.icon().isNull())
seen = []
widget.whiteboard_requested.connect(seen.append)
widget._whiteboard_btn.click()
check("the button emits the conversation JID", seen == ["bob@example.com"])
widget.deleteLater()

# 7. the collaborative canvas model ------------------------------------------
canvas2 = WhiteboardCanvas()
canvas2.resize(1280, 720)
canvas2.load_shapes([{"rid": "r1", "id": "s1", "d": "M 0 0 L 50 50",
                      "stroke": "#123456", "stroke-width": "3",
                      "fill": "none"}])
shapes = canvas2.shapes()
check("load_shapes builds a remote shape",
      len(shapes) == 1 and shapes[0]["rid"] == "r1")
check("a remote shape renders from its path data",
      canvas2._world_path(shapes[0]).boundingRect().width() > 0)
check("shape_attrs round-trips the path data",
      WhiteboardCanvas.shape_attrs(shapes[0])["d"] == "M 0 0 L 50 50")

# 7b. fill="none" means an unfilled remote shape (line/pencil stay lines) -----
line_canvas = WhiteboardCanvas()
line_canvas.load_shapes([
    {"rid": "l1", "id": "l1", "d": "M 0 0 L 100 0",
     "stroke": "#000000", "stroke-width": "2", "fill": "none"},
    {"rid": "p1", "id": "p1", "d": "M 0 0 L 10 10",
     "stroke": "#000000", "stroke-width": "2", "fill": "none"},
    {"rid": "r1", "id": "r1", "d": "M 0 0 L 10 0 L 10 10 L 0 10 Z",
     "stroke": "#000000", "stroke-width": "2", "fill": "#e53935"},
])
remote = line_canvas.shapes()
check("a remote line with fill=none is not filled",
      WhiteboardCanvas._filled(remote[0]) is False)
check("a remote pencil with fill=none is not filled",
      WhiteboardCanvas._filled(remote[1]) is False)
check("a remote closed shape keeps its fill",
      WhiteboardCanvas._filled(remote[2]) is True)
check("load_shapes normalises fill=none to empty",
      remote[0]["fill"] == "")
check("shape_attrs keeps fill=none for an unfilled shape",
      WhiteboardCanvas.shape_attrs(remote[0])["fill"] == "none")

added = []
canvas2.shape_added.connect(added.append)
canvas2.set_tool("rect")
drag(canvas2, 10, 10, 40, 40)
check("drawing a shape emits shape_added",
      len(added) == 1 and added[0]["kind"] == "rect")
removed = []
canvas2.shape_removed.connect(removed.append)
canvas2.set_tool("select")
QtWidgets.QApplication.sendEvent(canvas2, _event(
    QtCore.QEvent.Type.MouseButtonPress, 25, 25))
canvas2.delete_selected()
check("deleting a shape emits shape_removed", len(removed) == 1)

# 8. the dialog exposes the share controls -----------------------------------
dialog2 = WhiteboardDialog("bob@example.com", client=object())
check("the dialog has a share button", hasattr(dialog2, "_share_btn"))
check("the dialog reports no session by default", dialog2.session_id() == "")
shared = []
dialog2.share_requested.connect(lambda j, m: shared.append((j, m)))
dialog2._on_share(True)
check("the share button requests a session",
      shared == [("bob@example.com", False)])
dialog2.close()

# 9. view zoom / pan ---------------------------------------------------------
vc = WhiteboardCanvas()
vc.resize(1280, 720)   # 1:1 with the viewBox -> fit scale 1.0
anchor = QtCore.QPointF(300, 200)
world_before = vc._to_world(anchor)
vc.zoom_by(1.5, anchor)
world_after = vc._to_world(anchor)
check("zooming keeps the point under the cursor fixed",
      abs(world_before.x() - world_after.x()) < 1e-6
      and abs(world_before.y() - world_after.y()) < 1e-6)
check("zooming changes the view scale", abs(vc._scale() - 1.5) < 1e-9)
check("zoom is clamped to the maximum",
      (vc.set_view_zoom(99.0), vc.view_zoom())[1] == 8.0)

wheel = QtGui.QWheelEvent(
    QtCore.QPointF(300, 200), QtCore.QPointF(300, 200),
    QtCore.QPoint(0, 0), QtCore.QPoint(0, 120),
    QtCore.Qt.MouseButton.NoButton,
    QtCore.Qt.KeyboardModifier.ControlModifier,
    QtCore.Qt.ScrollPhase.NoScrollPhase, False)
vc.reset_view()
before = vc.view_zoom()
vc.wheelEvent(wheel)
check("Ctrl+wheel zooms in", vc.view_zoom() > before)

vc.reset_view()
check("reset restores zoom/pan",
      vc.view_zoom() == 1.0 and vc._view_pan.isNull())

# Panning: drag on empty space in select mode.
vc.set_tool("select")
drag(vc, 400, 300, 460, 330, steps=2)
check("dragging empty space pans the view",
      vc._view_pan.x() > 50 and vc._view_pan.y() > 20)
vc.zoom_by(2.0)
vc.mouseDoubleClickEvent(_event(
    QtCore.QEvent.Type.MouseButtonDblClick, 10, 10))
check("a double click on empty space resets the view", vc.view_zoom() == 1.0)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All whiteboard tests passed.")
