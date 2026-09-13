"""Offscreen smoke tests for persistence: chat input height, text scale
(Ctrl+wheel zoom) and chat-window geometry.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_persist.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_persist_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui import chat_themes
from stanza_im.ui.chat_widget import ChatWidget
from stanza_im.ui.chat_window import ChatWindow
from stanza_im.core.storage import Config

i18n_load("en")

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. config defaults for the new persistence keys -----------------------------
cfg = Config()
check("text_scale default 1.0", cfg.chat.text_scale == 1.0)
check("chat_window defaults",
      cfg.chat_window.width == 640 and cfg.chat_window.height == 480
      and cfg.chat_window.x == 0 and cfg.chat_window.y == 0
      and cfg.chat_window.maximized is False)

# 2. config save/load roundtrip for text_scale + chat_window ------------------
cfg.chat.text_scale = 1.7
cfg.chat_window.width = 820
cfg.chat_window.height = 620
cfg.chat_window.x = 45
cfg.chat_window.y = 35
cfg.save()
cfg2 = Config()
check("text_scale persisted", abs(cfg2.chat.text_scale - 1.7) < 1e-6)
check("chat_window persisted",
      cfg2.chat_window.width == 820 and cfg2.chat_window.height == 620
      and cfg2.chat_window.x == 45 and cfg2.chat_window.y == 35)

# 3. input-height clamp ---------------------------------------------------------
cw = ChatWidget("bob@example.com", "Bob", chat_themes.ChatThemeFactory())
cw._set_input_height(500)
check("input clamped to max", cw._input_height == 240
      and cw._input.height() == 240)
cw._set_input_height(10)
check("input clamped to min", cw._input_height == 40
      and cw._input.height() == 40)

# 4. set_chat_options applies text_scale and input_height ----------------------
cw.set_chat_options({"text_scale": 1.5, "input_height": 130})
check("text_scale applied to view", abs(cw._view._zoom - 1.5) < 1e-6)
check("input_height applied", cw._input_height == 130)

theme = chat_themes.ChatThemeFactory()
win = ChatWindow(theme, theme)

# 5. input_height shrinks are seen by NEW tabs (regression: stale snapshot) ----
c1 = win.open_chat("bob@example.com", "Bob")
c1._set_input_height(80)
check("snapshot synced on input change", win._chat_options["input_height"] == 80)
c2 = win.open_chat("carol@example.com", "Carol")
check("new tab uses fresh input height", c2._input_height == 80)

# 6. text_scale changes are seen by NEW tabs -----------------------------------
scales = []
win.text_scale_changed.connect(lambda jid, f: scales.append((jid, f)))
win._on_widget_text_scale_changed("bob@example.com", 1.9)
check("text_scale snapshot synced",
      abs(win._chat_options["text_scale"] - 1.9) < 1e-6)
check("text_scale signal forwarded",
      len(scales) == 1 and scales[0][0] == "bob@example.com"
      and abs(scales[0][1] - 1.9) < 1e-6)
c3 = win.open_chat("dave@example.com", "Dave")
check("new tab applies text_scale",
      abs(c3._view._zoom - 1.9) < 1e-6)

# 7. chat-window geometry roundtrip ---------------------------------------------
geo = {"width": 640, "height": 480, "x": 0, "y": 0, "maximized": False}
win2 = ChatWindow(theme, theme)
win2.resize(720, 560)
win2.move(120, 70)
win2.save_geometry(geo)
check("geometry saved",
      geo["width"] == 720 and geo["height"] == 560
      and geo["x"] == 120 and geo["y"] == 70)
win3 = ChatWindow(theme, theme)
win3.restore_geometry(geo)
g = win3.geometry()
check("geometry restored",
      g.width() == 720 and g.height() == 560
      and g.x() == 120 and g.y() == 70)

# 8. window_closed signal fires -------------------------------------------------
closes = []
win.window_closed.connect(lambda: closes.append(True))
win.close()
check("window_closed emitted", len(closes) == 1)

# 9. text-scale clamp stays within 0.5..3.0 -------------------------------------
cw._view.set_chat_zoom(9.0)
check("zoom clamped to max", abs(cw._view._zoom - 3.0) < 1e-6)
cw._view.set_chat_zoom(0.01)
check("zoom clamped to min", abs(cw._view._zoom - 0.5) < 1e-6)

# 10. REOPENED tabs re-apply the zoom (the reported reset-to-100% bug) ----------
win4 = ChatWindow(theme, theme)
cc = win4.open_chat("bob@example.com", "Bob")
win4._chat_options["text_scale"] = 2.2
cc2 = win4.open_chat("bob@example.com", "Bob", focus=False)
check("reopen 1:1 re-applies text_scale", cc2 is cc
      and abs(cc._view._zoom - 2.2) < 1e-6)
cm = win4.open_groupchat("room@conference.example.com", "alice", "Room")
win4._chat_options["text_scale"] = 0.7
cm2 = win4.open_groupchat("room@conference.example.com", "alice", "Room")
check("reopen MUC re-applies text_scale", cm2 is cm
      and abs(cm._view._zoom - 0.7) < 1e-6)

# 11. chat font override lands in the generated page CSS ------------------------
tf = chat_themes.ChatThemeFactory()
plain = tf.generate_empty_page()
check("no font override by default", "14pt" not in plain)
tf.set_chat_font("DejaVu Sans", 14)
page = tf.generate_empty_page()
check("family overridden in css", "DejaVu Sans" in page)
check("size overridden in css", "14pt" in page and "font-size: 14pt" in page)
options = tf.chat_font()
check("font getter roundtrip", options == ("DejaVu Sans", 14))
page_full = tf.generate_page([{
    "sender": "Bob", "body": "hi", "time": "12:00",
    "direction": "incoming", "is_next": False}])
check("page override carries into messages", "14pt" in page_full)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)