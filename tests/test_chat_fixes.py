"""Offscreen tests for the chat avatar, media preview, upload receipt and the
whiteboard invitation shortcut.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_chat_fixes.py
"""
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_fix_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402

from stanza_im.core import client as client_mod  # noqa: E402
from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.include import avatars  # noqa: E402
from stanza_im.include.avatars import (default_avatar_uri,  # noqa: E402
                                       save_avatar)

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["stanza"])

FAILURES = []
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. our own avatar on outgoing messages -------------------------------------
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.chat_widget import ChatWidget  # noqa: E402

_image = QtGui.QImage(8, 8, QtGui.QImage.Format.Format_RGB32)
_image.fill(QtGui.QColor("#3366cc"))
_buf = QtCore.QBuffer()
_buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
_image.save(_buf, "PNG")
save_avatar("me@example.com", bytes(_buf.data()))

_cw = ChatWidget("bob@example.com", "Bob", ChatThemeFactory())
check("outgoing without an own JID uses the placeholder",
      _cw._user_icon("outgoing") == default_avatar_uri())
_cw.set_own_jid("me@example.com/desk")
check("outgoing uses our own avatar once the JID is known",
      _cw._user_icon("outgoing") == avatars.avatar_data_uri("me@example.com")
      and _cw._user_icon("outgoing") != default_avatar_uri())
_cw.detach()

# 2. the media preview shrinks a portrait image and pins the bottom ----------
_view_src = open(os.path.join(_ROOT, "stanza_im/ui/chat_view.py"),
                 encoding="utf-8").read()
check("a loaded thumbnail drops the forced width",
      "img.removeAttribute('width')" in _view_src)
check("the view scrolls back to the end after the thumbnail",
      "window.scrollTo(0, document.body.scrollHeight)" in _view_src
      and "stick" in _view_src)

# 3. the HTTP upload result feeds the local echo ------------------------------
class _UploadState:
    def __init__(self):
        self._upload_results = {}


_state = _UploadState()
_state._upload_results[("bob@example.com", "/tmp/x.png")] = (
    "mid-1", {"url": "https://u/x.png"})
check("take_upload_result returns the stashed result",
      client_mod.JabberClient.take_upload_result(
          _state, "bob@example.com", "/tmp/x.png")
      == ("mid-1", {"url": "https://u/x.png"}))
check("take_upload_result consumes the entry",
      client_mod.JabberClient.take_upload_result(
          _state, "bob@example.com", "/tmp/x.png") == ("", None))

# 4. the main-window wiring --------------------------------------------------
_mw_src = open(os.path.join(_ROOT, "stanza_im/ui/main_window.py"),
               encoding="utf-8").read()
_ready = _mw_src.split("def _on_whiteboard_ready", 1)[1].split(
    "def _on_whiteboard_state", 1)[0]
check("a ready whiteboard session is shown",
      "dialog.show()" in _ready and "dialog.raise_()" in _ready)
check("the upload done handler reuses the sent id",
      "take_upload_result(" in _mw_src)
check("the local echo stores the media metadata", "media=media" in _mw_src)
check("the client caches our own avatar under the bare JID",
      'save_avatar(\n                    self.jid_str.split("/", 1)[0]'
      in _mw_src or 'self.jid_str.split("/", 1)[0], card["photo"]'
      in open(os.path.join(_ROOT, "stanza_im/core/client.py"),
              encoding="utf-8").read())

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All chat-fix tests passed.")
