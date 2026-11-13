"""Ctrl+V image dialog: preview, caption, progress and success close.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_image_send.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_image_send_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtGui, QtWidgets

from stanza_im.i18n import load as i18n_load
from stanza_im.ui.image_send_dialog import ImageSendDialog
from stanza_im.ui.main_window import MainWindow

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


path = os.path.join(_SCRATCH, "pasted.png")
image = QtGui.QImage(96, 64, QtGui.QImage.Format.Format_ARGB32)
image.fill(QtGui.QColor("#3366cc"))
check("test image saved", image.save(path, "PNG"))

dlg = ImageSendDialog(path)
check("large preview is shown", not dlg._preview.pixmap().isNull())
check("caption starts empty", dlg.caption() == "")
sent = []
dlg.send_requested.connect(sent.append)
dlg._caption.setText("  hello  ")
dlg._on_send()
check("send carries the trimmed caption", sent == ["hello"])
check("send disables the controls", not dlg._send_btn.isEnabled()
      and not dlg._caption.isEnabled())
dlg.set_progress(42)
check("progress is applied", dlg._progress.value() == 42)
dlg.mark_success()
check("success closes the dialog", dlg.result() == QtWidgets.QDialog.DialogCode.Accepted
      and dlg.succeeded)

dlg2 = ImageSendDialog(path)
dlg2.set_sending()
dlg2.set_error("network down")
check("failure keeps the dialog usable",
      "network down" in dlg2._status.text()
      and dlg2._send_btn.isEnabled()
      and dlg2._caption.isEnabled())
dlg2.close()

# The preview re-scales with the dialog instead of leaving empty bands.
dlg3 = ImageSendDialog(path)
dlg3.show()
app.processEvents()
small = dlg3._preview.pixmap().size()
dlg3.resize(900, 700)
app.processEvents()
large = dlg3._preview.pixmap().size()
check("preview grows with the dialog", large.width() > small.width()
      and large.height() > small.height())
check("preview fits the available label area",
      large.width() <= dlg3._preview.contentsRect().width()
      and large.height() <= dlg3._preview.contentsRect().height())
source = QtGui.QPixmap(path)
check("preview keeps the source aspect ratio",
      abs(large.width() / max(1, large.height())
          - source.width() / max(1, source.height())) < 0.02)
dlg3.resize(900, 900)
app.processEvents()
tall = dlg3._preview.pixmap().size()
check("extra dialog height goes to the preview",
      tall.height() > large.height())
dlg3.close()

# MainWindow routes a clipboard image to the dedicated dialog, not the batch.
mw = MainWindow.__new__(MainWindow)
mw._client = object()
opened = []
mw._open_pasted_image = lambda jid, path, parent: opened.append(
    (jid, path, parent))
MainWindow._on_chat_files_upload(
    mw, "bob@example.com", ["/tmp/pasted.png"], "pasted-image", None)
check("MainWindow opens the image dialog for pasted-image",
      opened == [("bob@example.com", "/tmp/pasted.png", mw)])

print()
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All tests passed")
