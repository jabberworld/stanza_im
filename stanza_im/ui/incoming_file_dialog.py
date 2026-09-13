"""Incoming Jingle file-transfer confirmation dialog (XEP-0234).

Shown when a peer offers a file and "automatically accept files" is off.  On
accept the user picks a destination with a save dialog; the chosen path is
reported through :attr:`decision`.
"""
from __future__ import annotations

import os

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.utils import default_download_dir, safe_filename
from stanza_im.ui.upload_dialog import format_size


class IncomingFileDialog(QtWidgets.QDialog):
    """Ask the user whether to receive an offered file."""

    decision = QtCore.pyqtSignal(bool, str)   # accepted, save path

    def __init__(self, sender: str, meta: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ft_recv_offer_title"))
        self._meta = dict(meta or {})
        self._sender = sender
        self._name = safe_filename(self._meta.get("name") or "file")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        text = tr("ft_recv_offer_text",
                  sender=sender or "",
                  file=self._name,
                  size=format_size(int(self._meta.get("size") or 0)))
        label = QtWidgets.QLabel(text, self)
        label.setWordWrap(True)
        layout.addWidget(label)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._accept_btn = QtWidgets.QPushButton(tr("ft_recv_accept"), self)
        self._reject_btn = QtWidgets.QPushButton(tr("ft_recv_reject"), self)
        self._accept_btn.setDefault(True)
        buttons.addWidget(self._accept_btn)
        buttons.addWidget(self._reject_btn)
        layout.addLayout(buttons)

        self._accept_btn.clicked.connect(self._on_accept)
        self._reject_btn.clicked.connect(self._on_reject)

    def _on_accept(self):
        name = self._name
        suggested = os.path.join(default_download_dir(), name)
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("ft_recv_save_title"), suggested)
        if not path:
            return
        self.decision.emit(True, path)
        self.accept()

    def _on_reject(self):
        self.decision.emit(False, "")
        self.reject()
