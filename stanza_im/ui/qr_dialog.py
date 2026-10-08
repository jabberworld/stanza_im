"""QR code dialog for an OMEMO fingerprint."""
from __future__ import annotations

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr

logger = logging.getLogger("stanza_im.omemo")


def render_qr_pixmap(text: str, module_size: int = 4, border: int = 4,
                     fg: str = "#000000", bg: str = "#ffffff"):
    """Return a ``QPixmap`` with *text* encoded as a QR code (or ``None``)."""
    try:
        from stanza_im.xmpp.omemo.qr import encode
        matrix = encode(text)
    except Exception:  # noqa: BLE001
        logger.debug("QR encoding failed", exc_info=True)
        return None
    n = len(matrix)
    size = (n + 2 * border) * module_size
    image = QtGui.QImage(size, size, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtGui.QColor(bg))
    painter = QtGui.QPainter(image)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QColor(fg))
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                painter.drawRect((c + border) * module_size,
                                 (r + border) * module_size,
                                 module_size, module_size)
    painter.end()
    return QtGui.QPixmap.fromImage(image)


class QrDialog(QtWidgets.QDialog):
    """Show a QR code for the given text."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("prefs_omemo_qr"))
        layout = QtWidgets.QVBoxLayout(self)
        pixmap = render_qr_pixmap(text)
        if pixmap is None or pixmap.isNull():
            layout.addWidget(QtWidgets.QLabel(tr("qr_unavailable")))
        else:
            label = QtWidgets.QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        caption = QtWidgets.QLabel(text)
        caption.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        caption.setWordWrap(True)
        caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(caption)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Close).setText(
            tr("dialog_close"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def show_fingerprint_qr(parent, text: str) -> None:
    """Open the QR dialog for *text* (no-op for empty text)."""
    if not text:
        return
    QrDialog(text, parent).exec()
