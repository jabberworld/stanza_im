"""Offscreen smoke tests for XEP-0363 HTTP File Upload and input toolbar.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_upload.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_upload_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from PyQt6 import QtCore, QtGui, QtWidgets

import slixmpp

from stanza_im.core.client import JabberClient, NS_UPLOAD
from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. upload slot request iq + response parsing -------------------------------
c = JabberClient("me@example.com/res", "pw")
iq = c._http_upload_request_iq("upload.example.com", "photo.png", 1234,
                               "image/png")
req = next(iq.xml.iter(f"{{{NS_UPLOAD}}}request"))
check("slot request fields",
      iq.xml.get("to") == "upload.example.com"
      and req.get("filename") == "photo.png"
      and req.get("size") == "1234"
      and req.get("content-type") == "image/png")

slot_iq = slixmpp.Iq()
root = slot_iq.xml
put = ET.SubElement(root, f"{{{NS_UPLOAD}}}put")
put.set("url", "https://upload.example.com/put/abc")
header = ET.SubElement(put, f"{{{NS_UPLOAD}}}header")
header.set("name", "Authorization")
header.text = "token123"
get = ET.SubElement(root, f"{{{NS_UPLOAD}}}get")
get.set("url", "https://upload.example.com/get/abc")
parsed = c._parse_upload_slot(slot_iq)
check("slot response parsed",
      parsed == ("https://upload.example.com/put/abc",
                 "https://upload.example.com/get/abc",
                 {"Authorization": "token123"}))

# 2. resizable input ----------------------------------------------------------
cw = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
check("input default height", cw._input.height() == 60)
cw._set_input_height(140)
check("input resized", cw._input.height() == 140
      and cw._input_height == 140)

# 3. toolbar buttons + flat style ---------------------------------------------
check("clear button", getattr(cw, "_clear_btn") is not None)
check("history menu button removed",
      not hasattr(cw, "_history_btn")
      and not hasattr(cw, "_history_menu"))
check("send button height follows the input",
      cw._send_btn.height() == cw._input_height == 140)
cw2 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
check("send file button menu", cw2._send_file_btn.menu() is not None)
actions = [a.text() for a in cw2._send_file_btn.menu().actions()]
check("send file options", "P2P" in actions and "HTTP Upload" in actions)
check("toolbar buttons are flat",
      cw._send_file_btn.autoRaise() and cw._call_btn.autoRaise()
      and cw._clear_btn.autoRaise())
cmuc = ChatWidget("room@conf.example", "Room",
                  chat_themes.ChatThemeFactory(), is_muc=True)
check("muc send file has no method menu",
      cmuc._send_file_btn.menu() is None)
check("muc send file is flat", cmuc._send_file_btn.autoRaise())

# 4. drop requests upload -----------------------------------------------------
up = []
cw3 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw3.files_upload_requested.connect(lambda *a: up.append(a))
mime = QtCore.QMimeData()
mime.setUrls([QtCore.QUrl.fromLocalFile("/tmp/example.txt"),
              QtCore.QUrl.fromLocalFile("/tmp/photo.png")])
drop = QtGui.QDropEvent(
    QtCore.QPointF(10, 10), QtCore.Qt.DropAction.CopyAction, mime,
    QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.KeyboardModifier.NoModifier)
cw3.dropEvent(drop)
check("drop requests http upload",
      bool(up) and up[0] == ("bob@example.com",
                             ["/tmp/example.txt", "/tmp/photo.png"], "http"))
check("drop propagation enabled",
      not cw3._view.acceptDrops() and not cw3._input.acceptDrops()
      and cw3.acceptDrops())

# 5. input height signal + chat_window forwarding -----------------------------
heights = []
cw4 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw4.input_height_changed.connect(lambda jid, h: heights.append((jid, h)))
cw4._set_input_height(180)
check("input height signal", heights == [("bob@example.com", 180)])

from stanza_im.ui.chat_window import ChatWindow
win = ChatWindow(chat_themes.ChatThemeFactory(),
                 chat_themes.ChatThemeFactory())
fwd = []
win.vcard_requested.connect(lambda j: fwd.append(("v", j)))
win.files_upload_requested.connect(lambda *a: fwd.append(("f", *a)))
widget = win.open_chat("carol@example.com", "Carol")
widget.vcard_requested.emit("carol@example.com")
widget.files_upload_requested.emit("carol@example.com",
                                   ["/tmp/a.bin", "/tmp/b.txt"], "http")
check("chat window forwards vcard + upload",
      ("v", "carol@example.com") in fwd
      and ("f", "carol@example.com", ["/tmp/a.bin", "/tmp/b.txt"], "http")
      in fwd)

# 6. roster send-file menu present --------------------------------------------
_mw_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "ui", "main_window.py"), encoding="utf-8").read()
check("roster send file menu", "ctx_send_file" in _mw_src
      and "upload_http(jid, path)" in _mw_src
      and "send_file(jid" in _mw_src)
check("upload dialog parented to source window",
      "_on_chat_files_upload(jid, paths, method" in _mw_src
      and "_place_dialog_over(dlg, parent)" in _mw_src
      and "self._chat_window))" in _mw_src)
check("upload done renders outgoing message",
      "_display_local_outgoing" in _mw_src
      and "uuid.uuid4().hex" in _mw_src
      and "groupchats.get(target)" in _mw_src)

# 7. config default input_height ----------------------------------------------
from stanza_im.core.storage import Config
check("config input height default", Config().chat.input_height == 60)

# 8. FileTransferDialog --------------------------------------------------------
from stanza_im.ui.upload_dialog import FileTransferDialog, format_size, \
    format_speed, format_eta, _FileRow, _preview_pixmap
img_path = os.path.join(_SCRATCH, "photo.png")
canvas = QtGui.QPixmap(96, 72)
canvas.fill(QtCore.Qt.GlobalColor.red)
check("test image saved", canvas.save(img_path, "PNG"))
doc_path = os.path.join(_SCRATCH, "notes.txt")
with open(doc_path, "w", encoding="utf-8") as fh:
    fh.write("hello")
dlg = FileTransferDialog([img_path, doc_path])
check("dialog rows", dlg.row_count() == 2)
img_row, doc_row = dlg._rows[0], dlg._rows[1]
check("dialog image thumbnail", not img_row._icon.pixmap().isNull())
check("dialog generic icon", not doc_row._icon.pixmap().isNull())
check("size format", format_size(0) == "0 B" and format_size(1536) == "1.5 KB")
dlg._caption.setText("  Check this out  ")
check("dialog caption", dlg.caption() == "Check this out")
dlg.set_progress(1, 42)
check("dialog per-file progress", doc_row._bar.value() == 42)
dlg.set_progress(1, 999)
check("dialog progress clamped", doc_row._bar.value() == 100)
dlg.set_row_done(0)
check("dialog row done", img_row._bar.value() == 100)
dlg.set_row_failed(1, "boom")
check("dialog row failed", "boom" in doc_row._bar.text())
started = []
dlg.upload_started.connect(started.append)
dlg._on_ok()
check("dialog ok emits caption",
      started == ["Check this out"] and not dlg._ok_btn.isEnabled())
check("dialog preview helper", _preview_pixmap(doc_path, dlg).isNull() is False)

# 8a. transfer speed + ETA -----------------------------------------------------
check("speed format", format_speed(1536) == "1.5 KB/s"
      and format_speed(0) == "" and format_speed(-5) == "")
check("eta format", format_eta(12) == "12s" and format_eta(125) == "2:05"
      and format_eta(0) == "" and format_eta(3725) == "1:02:05")
speed_path = os.path.join(_SCRATCH, "speed.bin")
with open(speed_path, "wb") as fh:
    fh.write(b"x" * 4096)
speed_row = _FileRow(speed_path)
speed_row.set_progress(25, now=0.0)
check("stats show transferred volume", "/" in speed_row._stats_label.text())
speed_row.set_progress(75, now=1.0)      # +2048 B in 1 s
stats = speed_row._stats_label.text()
check("stats show speed", "/s" in stats and speed_row._speed > 0)
check("stats show eta", "ETA" in stats)
speed_row.finish(now=2.0)
check("finish shows average speed", "/s" in speed_row._stats_label.text())
speed_row.fail("boom")
check("fail clears stats", speed_row._stats_label.text() == "")

# 9. resizable handle ----------------------------------------------------------
handle = cw3._input_handle
check("handle height getter", handle._get_height() == cw3._input_height)
_cw_src = open(os.path.join(_ROOT, "stanza_im", "ui", "chat_widget.py"),
               encoding="utf-8").read()
check("handle sits above the input (before input_row in layout)",
      _cw_src.index("chat_col.addWidget(self._input_handle)")
      < _cw_src.index("chat_col.addLayout(input_row)"))
handle._press_h = 100
check("top-handle drag shrinks down",
      handle._resized_height(30) == 70)
check("top-handle drag grows up",
      handle._resized_height(-20) == 120)

# 10. file-URL messages render as clickable links -----------------------------
theme = chat_themes.ChatThemeFactory()
url_html = theme.render_message("Me", "https://upload.example.com/get/abc123",
                                "12:00:00", "outgoing")
check("file url renders as link",
      '<a href="https://upload.example.com/get/abc123"' in url_html)

# 11. Ctrl+V pastes a clipboard image as an upload ----------------------------
cb = QtGui.QGuiApplication.clipboard()
canvas = QtGui.QPixmap(64, 48)
canvas.fill(QtCore.Qt.GlobalColor.green)
cb.setImage(canvas.toImage())
paste_rows = []
cw5 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw5.files_upload_requested.connect(lambda *a: paste_rows.append(a))
paste_ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                           QtCore.Qt.Key.Key_V,
                           QtCore.Qt.KeyboardModifier.ControlModifier)
cw5.eventFilter(cw5._input, paste_ev)
pasted_path = paste_rows[0][1][0] if paste_rows else ""
check("ctrl+v offers clipboard image",
      bool(paste_rows) and paste_rows[0][0] == "bob@example.com"
      and paste_rows[0][2] == "http" and os.path.exists(pasted_path))
if pasted_path:
    with open(pasted_path, "rb") as fh:
        check("pasted image is a png", fh.read(4) == b"\x89PNG")
cb.clear()
paste_rows.clear()
cw5.eventFilter(cw5._input, paste_ev)
check("ctrl+v with no image falls through", not paste_rows)
check("null image -> no temp file",
      ChatWidget._clipboard_image_to_tempfile(QtGui.QImage()) is None)

# 12. 1:1 chat header removed (name/status labels never shown) ----------------
cw6 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
check("1:1 name label hidden", not cw6._name_label.isVisible())
check("1:1 status label hidden", not cw6._status_label.isVisible())

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
