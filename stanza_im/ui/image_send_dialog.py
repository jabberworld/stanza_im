"""Single-image sender for a Ctrl+V clipboard image.

The ordinary transfer window is a multi-file progress list; a pasted
screenshot benefits from a large preview, one caption and an automatic close
after the image reaches the server.
"""
from __future__ import annotations

import os

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.ui import theme
from stanza_im.ui.upload_dialog import format_size


class ImageSendDialog(QtWidgets.QDialog):
    """Preview one image, let the user caption it and send it."""

    send_requested = QtCore.pyqtSignal(str)  # caption

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = str(path or "")
        self._sending = False
        self.succeeded = False
        self.setWindowTitle(tr("image_send_title"))
        self.setMinimumWidth(500)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)

        self._preview = QtWidgets.QLabel(self)
        self._preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(440, 280)
        self._preview.setMaximumHeight(360)
        self._preview.setStyleSheet(
            "QLabel { background: palette(alternate-base); "
            "border: 1px solid palette(mid); border-radius: 4px; }")
        pixmap = QtGui.QPixmap(self._path)
        if not pixmap.isNull():
            self._preview.setPixmap(pixmap.scaled(
                520, 330,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(self._preview)

        name = os.path.basename(self._path) or tr("image_send_title")
        try:
            size = format_size(os.path.getsize(self._path))
        except OSError:
            size = ""
        info = QtWidgets.QLabel(
            name + ((" \u00b7 " + size) if size else ""), self)
        info.setStyleSheet("color: palette(mid);")
        info.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(info)

        caption_label = QtWidgets.QLabel(tr("image_send_caption_label"), self)
        layout.addWidget(caption_label)
        self._caption = QtWidgets.QLineEdit(self)
        self._caption.setPlaceholderText(tr("image_send_caption_placeholder"))
        self._caption.returnPressed.connect(self._on_send)
        layout.addWidget(self._caption)

        self._progress = QtWidgets.QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = QtWidgets.QLabel("", self)
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        layout.addWidget(self._status)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._cancel_btn = QtWidgets.QPushButton(tr("dialog_cancel"), self)
        self._send_btn = QtWidgets.QPushButton(tr("image_send_send"), self)
        self._send_btn.setDefault(True)
        buttons.addWidget(self._cancel_btn)
        buttons.addWidget(self._send_btn)
        layout.addLayout(buttons)

        self._cancel_btn.clicked.connect(self.reject)
        self._send_btn.clicked.connect(self._on_send)
        self._caption.setFocus()

    def caption(self) -> str:
        return self._caption.text().strip()

    def set_sending(self) -> None:
        if self._sending:
            return
        self._sending = True
        self._send_btn.setEnabled(False)
        self._caption.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._send_btn.setText(tr("image_send_sending"))
        self._progress.setVisible(True)
        self._status.setStyleSheet("")
        self._status.setText(tr("image_send_sending"))
        self._status.setVisible(True)

    def set_progress(self, percent: int) -> None:
        self._progress.setVisible(True)
        self._progress.setValue(max(0, min(100, int(percent or 0))))

    def set_error(self, message: str) -> None:
        self._sending = False
        self._send_btn.setEnabled(True)
        self._caption.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._send_btn.setText(tr("image_send_send"))
        self._status.setText(tr("image_send_failed", error=message))
        self._status.setStyleSheet(
            f"color: {theme.error_color().name()};")
        self._status.setVisible(True)

    def mark_success(self) -> None:
        self.succeeded = True
        self._progress.setVisible(True)
        self._progress.setValue(100)
        self.accept()

    def _on_send(self) -> None:
        if self._sending or self.succeeded:
            return
        self.set_sending()
        self.send_requested.emit(self.caption())

    def closeEvent(self, event):  # noqa: N802 - Qt API
        # The upload cannot be cancelled after it starts; keeping the dialog
        # alive prevents the temporary file from being removed under the
        # upload thread.
        if self._sending and not self.succeeded:
            event.ignore()
            return
        super().closeEvent(event)
