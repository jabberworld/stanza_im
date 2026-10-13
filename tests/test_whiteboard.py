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
          "select", "move", "rotate", "scale", "pencil", "line", "arrow",
          "rect", "ellipse", "polygon", "fill", "eraser", "text"})
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

# 10. fill toggle + bucket ---------------------------------------------------
fc = WhiteboardCanvas()
fc.resize(1280, 720)   # 1:1 -> world == widget
fc.set_fill_enabled(False)
fc.set_tool("rect")
drag(fc, 100, 100, 200, 160)
check("fill disabled -> a new closed shape is unfilled",
      not WhiteboardCanvas._filled(fc.shapes()[0]))
check("an unfilled closed shape serialises fill=none",
      WhiteboardCanvas.shape_attrs(fc.shapes()[0])["fill"] == "none")

fc.set_fill_enabled(True)
fc.set_tool("rect")
drag(fc, 300, 100, 400, 160)
check("fill enabled -> a new closed shape is filled",
      WhiteboardCanvas._filled(fc.shapes()[1]))

fc.set_tool("fill")
fc.bucket_fill(QtCore.QPointF(350, 130))   # inside the filled rect
check("bucket unfills a filled closed shape",
      not WhiteboardCanvas._filled(fc.shapes()[1]))
fc.bucket_fill(QtCore.QPointF(350, 130))   # again
check("bucket fills an unfilled closed shape",
      WhiteboardCanvas._filled(fc.shapes()[1]))
check("bucket ignores the empty background",
      fc.bucket_fill(QtCore.QPointF(600, 400)) is False)
check("the dialog has a fill toggle button",
      hasattr(WhiteboardDialog("bob@example.com"), "_fill_on_btn"))
check("the dialog has a bucket tool",
      "fill" in WhiteboardDialog("bob@example.com")._tool_buttons)

# 11. selection handles + body drag (select tool) ----------------------------
hc = WhiteboardCanvas()
hc.resize(1280, 720)   # 1:1 -> widget == world
hc.set_tool("rect")
drag(hc, 100, 100, 200, 160)
sid = hc.selected_id()
check("drawing selects the new shape", bool(sid))
hc.set_tool("select")
handles = hc._selection_handles()
check("the selected shape has rotate and resize handles",
      set(handles) == {"rotate", "resize"})
check("the resize handle is hit-testable",
      hc._handle_at(handles["resize"].center()) == "resize")
check("the rotate handle is hit-testable",
      hc._handle_at(handles["rotate"].center()) == "rotate")

updates = []
hc.shape_updated.connect(updates.append)
drag(hc, 150, 130, 190, 150, steps=2)
check("dragging the body moves the shape",
      hc._shape_by_id(sid)["transform"].dx() > 10)
check("a body move emits shape_updated", len(updates) == 1)

before_scale = hc._shape_by_id(sid)["transform"].m11()
resize_pt = hc._selection_handles()["resize"].center()
drag(hc, resize_pt.x(), resize_pt.y(),
     resize_pt.x() + 40, resize_pt.y() + 20, steps=3)
check("dragging the resize handle scales the shape",
      hc._shape_by_id(sid)["transform"].m11() != before_scale)

before_rot = hc._shape_by_id(sid)["transform"].m12()
rotate_pt = hc._selection_handles()["rotate"].center()
drag(hc, rotate_pt.x(), rotate_pt.y(),
     rotate_pt.x() + 30, rotate_pt.y() + 10, steps=3)
check("dragging the rotate handle rotates the shape",
      abs(hc._shape_by_id(sid)["transform"].m12() - before_rot) > 1e-3)

# 12. arrow tool -------------------------------------------------------------
ac = WhiteboardCanvas()
ac.resize(1280, 720)
ac.set_tool("arrow")
drag(ac, 100, 100, 300, 200, steps=3)
ash = ac.shapes()[0]
check("the arrow tool draws an arrow", ash["kind"] == "arrow")
arrow_d = WhiteboardCanvas.shape_attrs(ash)["d"]
check("the arrow path has a shaft and a head", arrow_d.count("M") == 2)
check("an arrow is not filled", WhiteboardCanvas._filled(ash) is False)
check("an arrow renders locally",
      ac._world_path(ash).boundingRect().width() > 0)
rc = WhiteboardCanvas()
rc.load_shapes([{"rid": "a1", "id": "a1", "d": arrow_d, "stroke": "#000000",
                 "stroke-width": "2", "fill": "none"}])
check("a remote arrow renders",
      rc._world_path(rc.shapes()[0]).boundingRect().width() > 0)

# 13. width menu checkmark ---------------------------------------------------
wdlg = WhiteboardDialog("bob@example.com")
wdlg._set_width(5)
check("the width menu checks the active width",
      wdlg._width_actions[5].isChecked()
      and not wdlg._width_actions[2].isChecked())

# 14. toolbar layout: delete with the tools, separators between the groups ---
_tb = wdlg.layout().itemAt(0).layout()
check("delete sits with the tools (before the width/colour options)",
      _tb.indexOf(wdlg._delete_btn) < _tb.indexOf(wdlg._width_btn))
check("the toolbar uses separators",
      any(isinstance(_tb.itemAt(i).widget(), QtWidgets.QFrame)
          for i in range(_tb.count())))

# 15. PNG export + deselect + finish -----------------------------------------
img = ac.render_image()
check("render_image is the board size",
      img.width() == 1280 and img.height() == 720)
png_path = os.path.join(_SCRATCH, "whiteboard.png")
check("save_png writes a non-empty file",
      ac.save_png(png_path) and os.path.getsize(png_path) > 0)

hc._selected = sid
hc.deselect()
check("deselect clears the selection", hc.selected_id() == "")


class _WbMgr:
    def __init__(self):
        self.ended = []

    def end_session(self, sid):
        self.ended.append(sid)


class _WbClient:
    def __init__(self):
        self.whiteboard = _WbMgr()


fd = WhiteboardDialog("bob@example.com", client=_WbClient())
fd._sid = "s1"
fd._canvas._shapes.append({
    "id": "x", "rid": "", "kind": "rect", "rect": (0, 0, 10, 10),
    "stroke": "#000000", "stroke_width": 2, "fill": "",
    "transform": QtGui.QTransform()})
fd._end_board()
check("finish ends the session", fd._client.whiteboard.ended == ["s1"])
check("finish clears the board", fd._canvas.shapes() == [])
check("finish detaches the session", fd.session_id() == "")

# 16. eraser (click + drag) --------------------------------------------------
ec = WhiteboardCanvas()
ec.resize(1280, 720)
ec.set_tool("rect")
drag(ec, 100, 100, 200, 160)
ec.set_tool("rect")
drag(ec, 300, 100, 400, 160)
ec.set_tool("eraser")
removed = []
ec.shape_removed.connect(removed.append)
QtWidgets.QApplication.sendEvent(ec, _event(
    QtCore.QEvent.Type.MouseButtonPress, 150, 130))
check("the eraser removes the shape under the cursor",
      len(ec.shapes()) == 1 and len(removed) == 1)
drag(ec, 320, 120, 380, 150, steps=3)
check("dragging the eraser removes more shapes", ec.shapes() == [])
check("the eraser emits shape_removed per shape", len(removed) == 2)

# 17. snapshot share + toolbar placement -------------------------------------
sp = WhiteboardDialog("bob@example.com", client=object())
sp._canvas._shapes.append({
    "id": "s", "rid": "", "kind": "rect", "rect": (0, 0, 10, 10),
    "stroke": "#000000", "stroke_width": 2, "fill": "",
    "transform": QtGui.QTransform()})
paths = []
sp.share_png_requested.connect(paths.append)
sp._on_share_png()
check("share snapshot writes a temp PNG and emits the path",
      len(paths) == 1 and paths[0].endswith(".png")
      and os.path.getsize(paths[0]) > 0)
os.remove(paths[0])

sp_tb = sp.layout().itemAt(0).layout()
check("delete is before the drawing tools",
      sp_tb.indexOf(sp._delete_btn)
      < sp_tb.indexOf(sp._tool_buttons["pencil"]))
check("the snapshot-share button exists after the tools",
      sp_tb.indexOf(sp._share_png_btn)
      > sp_tb.indexOf(sp._tool_buttons["pencil"]))
check("the end-session button follows the share-board button",
      sp_tb.indexOf(sp._finish_btn) > sp_tb.indexOf(sp._share_btn))

# 17b. text tool -------------------------------------------------------------
tc = WhiteboardCanvas()
tc.resize(1280, 720)
sh = tc.add_text(QtCore.QPointF(100, 100), "Hello\nWorld")
check("add_text creates a text shape", sh is not None and sh["kind"] == "text")
check("a text shape has path data",
      bool(WhiteboardCanvas.shape_attrs(sh)["d"]))
check("a text shape is filled", WhiteboardCanvas._filled(sh) is True)
check("a text shape renders", tc._world_path(sh).boundingRect().width() > 0)
rt = WhiteboardCanvas()
rt.load_shapes([{"rid": "t1", "id": "t1",
                 "d": WhiteboardCanvas.shape_attrs(sh)["d"],
                 "stroke": "#000000", "stroke-width": "1",
                 "fill": "#000000"}])
check("a remote text shape renders",
      rt._world_path(rt.shapes()[0]).boundingRect().width() > 0)

# 18. middle-button pan (any tool) + fill-toggle icon ------------------------
mc = WhiteboardCanvas()
mc.resize(1280, 720)
mc.set_tool("pencil")
QtWidgets.QApplication.sendEvent(mc, _event(
    QtCore.QEvent.Type.MouseButtonPress, 300, 200,
    buttons=QtCore.Qt.MouseButton.MiddleButton,
    button=QtCore.Qt.MouseButton.MiddleButton))
QtWidgets.QApplication.sendEvent(mc, _event(
    QtCore.QEvent.Type.MouseMove, 360, 240,
    buttons=QtCore.Qt.MouseButton.MiddleButton,
    button=QtCore.Qt.MouseButton.NoButton))
QtWidgets.QApplication.sendEvent(mc, _event(
    QtCore.QEvent.Type.MouseButtonRelease, 360, 240,
    buttons=QtCore.Qt.MouseButton.NoButton,
    button=QtCore.Qt.MouseButton.MiddleButton))
check("middle-button drag pans the view in a drawing tool",
      mc._view_pan.x() > 50 and mc._view_pan.y() > 30)
check("middle-button pan starts no shape", mc.shapes() == [])

from stanza_im.include.constants import find_icon  # noqa: E402
check("the fill-toggle icon exists", bool(find_icon("wb-fill-toggle.svg")))
check("the fill toggle carries an icon",
      not wdlg._fill_on_btn.icon().isNull())

# 19. media metadata lookup for a shared URL ---------------------------------
cw = ChatWidget("bob@example.com", "Bob", ChatThemeFactory())
cw.add_message(sender="Bob", body="http://x/img.png", timestamp="12:00",
               direction="incoming",
               media={"url": "http://x/img.png", "name": "img.png",
                      "size": 123, "media_type": "image/png"})
m = cw.media_for_url("http://x/img.png")
check("ChatWidget.media_for_url returns the stored media dict",
      bool(m) and m.get("size") == 123 and m.get("media_type") == "image/png")
check("media_for_url misses an unknown url",
      cw.media_for_url("http://x/other.png") is None)
cw.deleteLater()

from stanza_im.ui.main_window import MainWindow  # noqa: E402


class _CWStub:
    def __init__(self, media):
        self._media = media

    def media_for_url(self, url):
        return self._media


class _MCStub:
    def info(self, url):
        return {"mime": "image/png", "size": 999}


mw = MainWindow.__new__(MainWindow)
mw._chat_window = _CWStub(None)
mw._media_cache = _MCStub()
res = mw._resolve_share_media("http://x/a.png")
check("share media falls back to the media cache",
      bool(res) and res.get("media_type") == "image/png"
      and res.get("size") == 999)
mw._chat_window = _CWStub({"url": "http://x/a.png", "size": 42,
                           "media_type": "image/png"})
res2 = mw._resolve_share_media("http://x/a.png")
check("share media prefers the stored message metadata",
      bool(res2) and res2.get("size") == 42)
check("share media ignores a non-media URL",
      mw._resolve_share_media("hello world") is None)
mw._chat_window = _CWStub(None)
mw._media_cache = _MCStub()
res3 = mw._resolve_share_media(
    "Переслано:\n> [2026-10-13 00:32:15] jabbim-test: https://h/a.png")
check("share media extracts the URL from a composed forward",
      bool(res3) and res3.get("url") == "https://h/a.png")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All whiteboard tests passed.")
