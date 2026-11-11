"""QR code dialog for an OMEMO fingerprint."""
from __future__ import annotations

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.ui.dialogs import show_modeless

logger = logging.getLogger("stanza_im.omemo")


def _encode_matrix(text: str):
    try:
        from stanza_im.xmpp.omemo.qr import encode
        return encode(text)
    except Exception:  # noqa: BLE001
        logger.debug("QR encoding failed", exc_info=True)
        return None


def render_qr_pixmap(text: str, module_size: int = 4, border: int = 4,
                     fg: str = "#000000", bg: str = "#ffffff"):
    """Return a ``QPixmap`` with *text* encoded as a QR code (or ``None``)."""
    matrix = _encode_matrix(text)
    if matrix is None:
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


class QrCodeView(QtWidgets.QWidget):
    """Draw a cached QR matrix at the current widget size.

    The matrix is encoded once; resizing only repaints its modules, so the
    code stays sharp without running the QR encoder again.
    """

    BORDER = 4
    SIZE_HINT = 280
    MINIMUM_SIZE = 140

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._matrix = _encode_matrix(text)
        self._fg = QtGui.QColor("#000000")
        self._bg = QtGui.QColor("#ffffff")
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMinimumSize(self.MINIMUM_SIZE, self.MINIMUM_SIZE)

    def has_qr(self) -> bool:
        return self._matrix is not None

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self.SIZE_HINT, self.SIZE_HINT)

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self.MINIMUM_SIZE, self.MINIMUM_SIZE)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._matrix is None:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        total = len(self._matrix) + 2 * self.BORDER
        available = min(self.width(), self.height())
        module = max(1, available // total)
        size = total * module
        left = (self.width() - size) // 2
        top = (self.height() - size) // 2
        painter.fillRect(QtCore.QRect(left, top, size, size), self._bg)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(self._fg)
        for r, row in enumerate(self._matrix):
            for c, dark in enumerate(row):
                if dark:
                    painter.drawRect(
                        left + (c + self.BORDER) * module,
                        top + (r + self.BORDER) * module,
                        module, module)
        painter.end()


class QrDialog(QtWidgets.QDialog):
    """Show a QR code for the given text."""

    def __init__(self, text: str, parent=None, title: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title or tr("prefs_omemo_qr"))
        layout = QtWidgets.QVBoxLayout(self)
        qr_view = QrCodeView(text, self)
        if not qr_view.has_qr():
            layout.addWidget(QtWidgets.QLabel(tr("qr_unavailable")))
        else:
            self._qr_view = qr_view
            layout.addWidget(qr_view, 1)
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
    show_modeless(QrDialog(text, parent))
