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

# 3. toolbar buttons + history move -------------------------------------------
check("clear button", getattr(cw, "_history_btn") is not None)
cw2 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
check("send file button menu", cw2._send_file_btn.menu() is not None)
actions = [a.text() for a in cw2._send_file_btn.menu().actions()]
check("send file options", "P2P" in actions and "HTTP Upload" in actions)

# 4. drop file requests upload ------------------------------------------------
up = []
cw3 = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw3.file_upload_requested.connect(lambda *a: up.append(a))
mime = QtCore.QMimeData()
mime.setUrls([QtCore.QUrl.fromLocalFile("/tmp/example.txt")])
drop = QtGui.QDropEvent(
    QtCore.QPointF(10, 10), QtCore.Qt.DropAction.CopyAction, mime,
    QtCore.Qt.MouseButton.LeftButton,
    QtCore.Qt.KeyboardModifier.NoModifier)
cw3.dropEvent(drop)
check("drop requests http upload",
      bool(up) and up[0] == ("bob@example.com", "/tmp/example.txt", "http"))

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
win.file_upload_requested.connect(lambda *a: fwd.append(("f", *a)))
widget = win.open_chat("carol@example.com", "Carol")
widget.vcard_requested.emit("carol@example.com")
widget.file_upload_requested.emit("carol@example.com", "/tmp/a.bin", "http")
check("chat window forwards vcard + upload",
      ("v", "carol@example.com") in fwd
      and ("f", "carol@example.com", "/tmp/a.bin", "http") in fwd)

# 6. roster send-file menu present --------------------------------------------
_mw_src = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "stanza_im", "ui", "main_window.py"), encoding="utf-8").read()
check("roster send file menu", "ctx_send_file" in _mw_src
      and "upload_http(jid, path)" in _mw_src
      and "send_file(jid, path)" in _mw_src)

# 7. config default input_height ----------------------------------------------
from stanza_im.core.storage import Config
check("config input height default", Config().chat.input_height == 60)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)