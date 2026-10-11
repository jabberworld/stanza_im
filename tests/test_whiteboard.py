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
canvas.resize(600, 400)   # 1:1 with the 600x400 viewBox
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
      "<svg" in svg and 'viewBox="0 0 600 400"' in svg)
check("the SVG contains rect/ellipse/path",
      "<rect" in svg and "<ellipse" in svg and "<path" in svg)
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

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All whiteboard tests passed.")
