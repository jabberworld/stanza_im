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
check("fill is off by default", canvas._fill_enabled is False)
canvas.set_fill_enabled(True)
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
check("the selected shape has rotate/resize/move handles",
      set(handles) == {"rotate", "resize", "move"})
check("the resize handle is hit-testable",
      hc._handle_at(handles["resize"].center()) == "resize")
check("the rotate handle is hit-testable",
      hc._handle_at(handles["rotate"].center()) == "rotate")
check("the move handle is hit-testable",
      hc._handle_at(handles["move"].center()) == "move")

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

before_move = hc._shape_by_id(sid)["transform"].dx()
move_pt = hc._selection_handles()["move"].center()
drag(hc, move_pt.x(), move_pt.y(), move_pt.x() + 30, move_pt.y(), steps=3)
check("dragging the move handle moves the shape",
      hc._shape_by_id(sid)["transform"].dx() > before_move)

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

# 17c. undo / redo buttons ---------------------------------------------------
class _WbStub:
    def __init__(self):
        self.calls = []

    def undo(self, sid):
        self.calls.append(("undo", sid))

    def redo(self, sid):
        self.calls.append(("redo", sid))

    def can_undo(self, sid):
        return True

    def can_redo(self, sid):
        return True


class _ClientStub:
    def __init__(self):
        self.whiteboard = _WbStub()


ud = WhiteboardDialog("bob@example.com", client=_ClientStub())
ud._sid = "s1"
check("the dialog has undo/redo buttons",
      hasattr(ud, "_undo_btn") and hasattr(ud, "_redo_btn"))
ud._on_undo()
ud._on_redo()
check("undo/redo call the manager",
      ud._client.whiteboard.calls == [("undo", "s1"), ("redo", "s1")])
ud.close()

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
check("the insert-image icon exists", bool(find_icon("wb-image.svg")))
check("the insert-image button carries an icon",
      not wdlg._image_btn.icon().isNull())

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

# 20. board session start/end status line ------------------------------------
from types import SimpleNamespace  # noqa: E402


class _ChatStub:
    def __init__(self):
        self.lines = []

    def add_status(self, text, ts):
        self.lines.append(text)


class _CWStub2:
    def __init__(self):
        self.chats = {}

    def get_chat(self, jid):
        return self.chats.get(jid)


bw = MainWindow.__new__(MainWindow)
bw._config = SimpleNamespace(
    chat=SimpleNamespace(whiteboard_show_status=True))
_bchat = _ChatStub()
_bcw = _CWStub2()
_bcw.chats["bob@example.com"] = _bchat
bw._chat_window = _bcw
bw._on_whiteboard_activity("bob@example.com", True)
check("a board start shows a chat status line", len(_bchat.lines) == 1)
bw._on_whiteboard_activity("bob@example.com", False)
check("a board end shows a chat status line", len(_bchat.lines) == 2)
bw._config.chat.whiteboard_show_status = False
bw._on_whiteboard_activity("bob@example.com", True)
check("the board status line is gated by the setting",
      len(_bchat.lines) == 2)
mw._chat_window = _CWStub(None)
mw._media_cache = _MCStub()
res3 = mw._resolve_share_media(
    "Переслано:\n> [2026-10-13 00:32:15] jabbim-test: https://h/a.png")
check("share media extracts the URL from a composed forward",
      bool(res3) and res3.get("url") == "https://h/a.png")

# 21. the canvas viewBox is configurable (the host's is authoritative) --------
vb = WhiteboardCanvas()
vb.resize(600, 400)   # 1:1 with a 600x400 viewBox
check("the default viewBox is our canvas size", vb.view_box() == (1280, 720))
vb.set_view_box(600, 400)
check("set_view_box is reported", vb.view_box() == (600, 400))
check("the fit scale follows the viewBox", abs(vb._scale() - 1.0) < 1e-9)
check("the SVG export uses the viewBox", 'viewBox="0 0 600 400"' in vb.to_svg())
check("render_image follows the viewBox",
      (vb.render_image().width(), vb.render_image().height()) == (600, 400))

# 22. embedded (data:) images ------------------------------------------------
from stanza_im.ui.whiteboard_canvas import IMAGE_MAX_BYTES, image_data_uri  # noqa: E402

_img_path = os.path.join(_SCRATCH, "pic.png")
_pm = QtGui.QPixmap(2, 3)
_pm.fill(QtGui.QColor("#3366cc"))
check("a test PNG is written", _pm.save(_img_path, "PNG"))
_uri = image_data_uri(_img_path)
check("image_data_uri builds a data: URI",
      _uri.startswith("data:image/png;base64,"))

_bad = os.path.join(_SCRATCH, "pic.tiff")
with open(_bad, "wb") as _fh:
    _fh.write(b"x")
try:
    image_data_uri(_bad)
    check("an unsupported image format is rejected", False)
except ValueError:
    check("an unsupported image format is rejected", True)

_big = os.path.join(_SCRATCH, "big.png")
with open(_big, "wb") as _fh:
    _fh.write(b"\x00" * (IMAGE_MAX_BYTES + 10))
try:
    image_data_uri(_big)
    check("an oversized image is rejected", False)
except ValueError:
    check("an oversized image is rejected", True)

ic = WhiteboardCanvas()
ic.resize(1280, 720)
ish = ic.add_image(QtCore.QPointF(100, 100), _uri)
check("add_image creates an image shape",
      ish is not None and ish["kind"] == "image")
check("an image keeps its natural size",
      ish["image"][2] == 2 and ish["image"][3] == 3)
check("an image renders from its data: URI",
      not ic._pixmap_for(_uri).isNull())
check("an image is hit-testable by its interior",
      ic._shape_at(QtCore.QPointF(100.5, 100.5)) is ish)
check("shape_attrs marks an image",
      WhiteboardCanvas.shape_attrs(ish)["tag"] == "image")
check("an image exports as <image xlink:href>",
      "<image" in ic.to_svg() and "xlink:href" in ic.to_svg())

rc2 = WhiteboardCanvas()
rc2.load_shapes([{"rid": "i1", "id": "i1", "tag": "image",
                  "x": "10", "y": "20", "width": "2", "height": "3",
                  "href": _uri, "transform": ""}])
check("a remote image loads",
      len(rc2.shapes()) == 1 and rc2.shapes()[0]["kind"] == "image")
check("a remote image renders",
      rc2._world_path(rc2.shapes()[0]).boundingRect().width() == 2)
# Drawing an image must not raise (the drawPixmap overload regression).
check("render_image draws an image without error",
      ic.render_image().width() == 1280)
check("painting a canvas with an image does not raise",
      not ic.grab().isNull())

# 23. stacking order (local) + selection preservation ------------------------
oc = WhiteboardCanvas()
oc.resize(1280, 720)
oc.set_tool("rect")
drag(oc, 10, 10, 40, 40)
oc.set_tool("rect")
drag(oc, 60, 10, 90, 40)
_oc_ids = [s["id"] for s in oc.shapes()]
check("two rects are drawn", len(_oc_ids) == 2)
oc.reorder_local(_oc_ids[0], "front")
check("reorder_local brings a shape to the front",
      oc.shapes()[-1]["id"] == _oc_ids[0])
oc.reorder_local(_oc_ids[0], "back")
check("reorder_local sends a shape to the back",
      oc.shapes()[0]["id"] == _oc_ids[0])
oc.reorder_local(_oc_ids[0], "forward")
check("reorder_local moves a shape forward",
      oc.shapes()[1]["id"] == _oc_ids[0])
oc._selected = _oc_ids[0]
oc.load_shapes([{"rid": "r1", "id": _oc_ids[0], "d": "M 0 0 L 5 5"}])
check("load_shapes keeps a surviving selection",
      oc.selected_id() == _oc_ids[0])

# 24. the dialog exposes the order + canvas-size controls --------------------
od = WhiteboardDialog("bob@example.com")
check("the dialog has an order button", hasattr(od, "_order_btn"))
check("the order menu has four entries", len(od._order_menu.actions()) == 4)
check("the order icon exists", bool(find_icon("wb-order.svg")))
check("the dialog has a canvas-size button", hasattr(od, "_size_btn"))
check("the resize icon exists", bool(find_icon("wb-resize.svg")))
od.close()


class _WbOrder:
    def __init__(self):
        self.calls = []

    def reorder(self, sid, rid, op):
        self.calls.append((sid, rid, op))


class _ClientOrder:
    def __init__(self):
        self.whiteboard = _WbOrder()


od2 = WhiteboardDialog("bob@example.com", client=_ClientOrder())
od2._sid = "s1"
od2._canvas.load_shapes([{"rid": "R1", "id": "I1", "d": "M 0 0 L 5 5"}])
od2._canvas._selected = "I1"
check("selected_rid reports the document record",
      od2._canvas.selected_rid() == "R1")
od2._reorder("front")
check("a shared reorder calls the manager",
      od2._client.whiteboard.calls == [("s1", "R1", "front")])
od2.close()

# 25. canvas grouping + multi-select -----------------------------------------
def _ctrl_click(widget, x, y):
    QtWidgets.QApplication.sendEvent(widget, QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonPress, QtCore.QPointF(x, y),
        QtCore.QPointF(x, y), QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.ControlModifier))


gc = WhiteboardCanvas()
gc.resize(1280, 720)
gc.set_tool("rect")
drag(gc, 10, 10, 40, 40)
gc.set_tool("rect")
drag(gc, 60, 10, 90, 40)
gc.set_tool("select")
QtWidgets.QApplication.sendEvent(gc, _event(
    QtCore.QEvent.Type.MouseButtonPress, 75, 25))
check("a plain click selects one shape", len(gc.selection()) == 1)
_ctrl_click(gc, 25, 25)
check("Ctrl+click adds to the selection", len(gc.selection()) == 2)
_grp = gc.group_local()
check("group_local groups the selection", bool(_grp))
check("the members carry the group",
      all(s.get("group") == _grp for s in gc.shapes()))
check("selected_group reports the common group", gc.selected_group() == _grp)

_before = gc._group_transforms[_grp].dx()
gc.set_tool("move")
drag(gc, 25, 25, 45, 25, steps=2)
check("dragging a grouped shape moves the group transform",
      gc._group_transforms[_grp].dx() != _before)
check("ungroup_local dissolves the group",
      gc.ungroup_local(_grp)
      and all(not s.get("group") for s in gc.shapes()))

# 25b. the dialog groups a local (unshared) selection ------------------------
lg = WhiteboardDialog("bob@example.com")
lg._canvas.resize(1280, 720)
lg._canvas.set_tool("rect")
drag(lg._canvas, 10, 10, 40, 40)
lg._canvas.set_tool("rect")
drag(lg._canvas, 60, 10, 90, 40)
lg._canvas.set_tool("select")
QtWidgets.QApplication.sendEvent(lg._canvas, _event(
    QtCore.QEvent.Type.MouseButtonPress, 75, 25))
_ctrl_click(lg._canvas, 25, 25)
lg._group_selection()
check("the dialog groups a local selection",
      len(lg._canvas.selection()) == 2
      and all(s.get("group") for s in lg._canvas.shapes()))
check("the group is reported on the local board",
      bool(lg._canvas.selected_group()))
check("the group has a bounding box for its outline",
      not lg._canvas._group_world_bbox(
          lg._canvas.selected_group()).isNull())
lg._ungroup_selection()
check("the dialog ungroups a local selection",
      all(not s.get("group") for s in lg._canvas.shapes()))
lg.close()


class _WbGroup:
    def __init__(self):
        self.calls = []

    def group_shapes(self, sid, rids):
        self.calls.append((sid, tuple(rids)))
        return "G1"


class _ClientGroup:
    def __init__(self):
        self.whiteboard = _WbGroup()


sg = WhiteboardDialog("bob@example.com", client=_ClientGroup())
sg._sid = "s1"
sg._canvas.load_shapes([{"rid": "R1", "id": "I1", "d": "M 0 0 L 1 1"},
                        {"rid": "R2", "id": "I2", "d": "M 0 0 L 2 2"}])
sg._canvas._selection = ["I1", "I2"]
sg._group_selection()
check("a shared selection is grouped through the manager",
      sg._client.whiteboard.calls == [("s1", ("R1", "R2"))])
sg.close()

# 26. the dialog exposes the group controls ----------------------------------
gd = WhiteboardDialog("bob@example.com")
check("the dialog has group/ungroup buttons",
      hasattr(gd, "_group_btn") and hasattr(gd, "_ungroup_btn"))
check("the group actions start disabled",
      not gd._group_btn.isEnabled() and not gd._ungroup_btn.isEnabled())
check("the group icons exist",
      bool(find_icon("wb-group.svg")) and bool(find_icon("wb-ungroup.svg")))
gd.close()

# 27. HTTP-uploaded images: fetch + cache ------------------------------------
class _StubFetcher:
    def __init__(self):
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)


fc2 = WhiteboardCanvas()
fc2._image_fetcher = _StubFetcher()
fc2.resize(1280, 720)
_url = "https://upload.example/pic.png"
check("an http image source triggers a fetch",
      fc2._pixmap_for(_url).isNull() and fc2._image_fetcher.urls == [_url])
_img = QtGui.QPixmap(4, 5)
_img.fill(QtGui.QColor("#123456"))
_buf = QtCore.QBuffer()
_buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
_img.save(_buf, "PNG")
fc2._on_image_loaded(_url, bytes(_buf.data()))
check("a fetched image is cached and rendered",
      not fc2._pixmap_for(_url).isNull()
      and fc2._pixmap_for(_url).width() == 4)
fc2.cache_image("https://upload.example/x.png", bytes(_buf.data()))
check("cache_image seeds the cache",
      not fc2._pixmap_for("https://upload.example/x.png").isNull())


class _UploadClient:
    def __init__(self, feature):
        self._feature = feature

    def supports_feature(self, bare, feature):
        return feature == self._feature


uc = WhiteboardDialog("bob@example.com",
                      client=_UploadClient("urn:xmpp:http:upload:0"))
uc._sid = "s1"
check("the peer's upload support is detected", uc._peer_supports_upload())
uc.close()
uc2 = WhiteboardDialog("bob@example.com", client=_UploadClient("other"))
uc2._sid = "s1"
check("a peer without upload falls back to data:",
      not uc2._peer_supports_upload())
uc2.close()
vd = WhiteboardDialog("bob@example.com")
check("a valid image is embedded",
      vd._add_embedded_image(_img_path, QtCore.QPointF(50, 50))
      and len(vd._canvas.shapes()) == 1)
vd.close()

# 28. canvas-size presets ----------------------------------------------------
from stanza_im.ui.whiteboard_dialog import _canvas_size_items  # noqa: E402

_labels, _idx = _canvas_size_items(1280, 720)
check("the canvas-size presets start with the profile default",
      _labels[0] == "600×400")
check("the current size is preselected", _labels[_idx] == "1280×720")
_custom_labels, _custom_idx = _canvas_size_items(1111, 777)
check("a custom size is appended and preselected",
      _custom_labels[-1] == "1111×777" and _custom_idx == len(_custom_labels) - 1)
check("the presets are in increasing order",
      _labels == sorted(_labels,
                        key=lambda s: (int(s.split("×")[0]),
                                       int(s.split("×")[1]))))

# 29. local (unshared) undo / redo -------------------------------------------
uc3 = WhiteboardCanvas()
uc3.resize(1280, 720)
uc3.set_tool("rect")
drag(uc3, 10, 10, 40, 40)
check("a local board records an edit", uc3.can_undo())
uc3.undo_local()
check("undo_local removes the drawn shape", uc3.shapes() == [])
check("undo_local enables redo", uc3.can_redo())
uc3.redo_local()
check("redo_local restores the shape", len(uc3.shapes()) == 1)

uc3.set_tool("select")
QtWidgets.QApplication.sendEvent(uc3, _event(
    QtCore.QEvent.Type.MouseButtonPress, 25, 25))
uc3.set_tool("move")
_before_dx = uc3.shapes()[0]["transform"].dx()
drag(uc3, 25, 25, 55, 25, steps=2)
check("a local move changes the shape",
      uc3.shapes()[0]["transform"].dx() != _before_dx)
uc3.undo_local()
check("undo_local reverts a move",
      uc3.shapes()[0]["transform"].dx() == _before_dx)

ud3 = WhiteboardDialog("bob@example.com")
ud3._canvas.set_tool("rect")
drag(ud3._canvas, 10, 10, 40, 40)
ud3._on_undo()
check("the dialog's local undo button reverts the board",
      ud3._canvas.shapes() == [])
ud3._on_redo()
check("the dialog's local redo button restores it",
      len(ud3._canvas.shapes()) == 1)
ud3.close()

# 30. the whiteboard image-upload mode ---------------------------------------
def _wb_mode_dialog(mode):
    cfg = SimpleNamespace(chat=SimpleNamespace(whiteboard_image_upload=mode))
    return WhiteboardDialog("bob@example.com", config=cfg)


check("the auto image mode is reported",
      _wb_mode_dialog("auto")._image_upload_mode() == "auto")
check("the embed image mode is reported",
      _wb_mode_dialog("embed")._image_upload_mode() == "embed")
check("a missing image mode falls back to auto",
      WhiteboardDialog("bob@example.com")._image_upload_mode() == "auto")

# 31. the roster contact menu offers "Open whiteboard" ------------------------
from stanza_im.i18n import tr  # noqa: E402

check("ctx_open_whiteboard is translated",
      tr("ctx_open_whiteboard") != "ctx_open_whiteboard")

_mw_src = open(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "stanza_im/ui/main_window.py"), encoding="utf-8").read()
check("the contact menu offers Open Whiteboard after the call submenu",
      'tr("ctx_open_whiteboard")' in _mw_src
      and "self._on_whiteboard_requested(jid)" in _mw_src)

# 32. fill-opacity: a Psi+ outline is not a filled shape ---------------------
_fc = WhiteboardCanvas()
_fc.load_shapes([
    {"rid": "r1", "fill": "#000000", "fill-opacity": "0",
     "d": "M 0 0 L 10 10"},
    {"rid": "r2", "fill": "#000000", "d": "M 0 0 L 10 10"},
    {"rid": "r3", "fill": "#ff0000", "fill-opacity": "0.5",
     "d": "M 0 0 L 10 10"},
])
_s1, _s2, _s3 = _fc.shapes()
check("a Psi+ outline (fill-opacity=0) is not filled",
      WhiteboardCanvas._filled(_s1) is False)
check("a plain filled shape is still filled",
      WhiteboardCanvas._filled(_s2) is True)
check("fill-opacity is parsed",
      _s1["fill_opacity"] == 0.0 and _s2["fill_opacity"] == 1.0)
check("a partially transparent fill stays filled",
      WhiteboardCanvas._filled(_s3) is True
      and _s3["fill_opacity"] == 0.5)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All whiteboard tests passed.")
