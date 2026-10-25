"""Prompt shown when the server's TLS certificate fails verification.

The dialog never ignores the error by default: the user must explicitly choose
a one-off or a persistent (profile-level) exception.
"""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr


class CertificateErrorDialog(QtWidgets.QDialog):
    """Explain a certificate failure and let the user decide what to do."""

    def __init__(self, host: str, reason: str, parent=None):
        super().__init__(parent)
        self.host = str(host or "")
        self.reason = str(reason or "")
        self.choice = "cancel"
        self.setWindowTitle(tr("cert_error_title", host=self.host))
        self.setMinimumSize(520, 320)
        layout = QtWidgets.QVBoxLayout(self)

        self._message = QtWidgets.QLabel(
            tr("cert_error_text", reason=self.reason))
        self._message.setWordWrap(True)
        self._message.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._message)

        self._warning = QtWidgets.QLabel(tr("cert_error_warning"))
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet("color: #b00020;")
        layout.addWidget(self._warning)

        self._details = QtWidgets.QPlainTextEdit(self)
        self._details.setReadOnly(True)
        self._details.setPlainText(self.reason)
        self._details.setLineWrapMode(
            QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self._details, 1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        cancel = QtWidgets.QPushButton(tr("dialog_cancel"), self)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        once = QtWidgets.QPushButton(tr("cert_error_once"), self)
        once.clicked.connect(lambda: self._choose("once"))
        buttons.addWidget(once)
        always = QtWidgets.QPushButton(tr("cert_error_always"), self)
        always.clicked.connect(lambda: self._choose("always"))
        buttons.addWidget(always)
        layout.addLayout(buttons)

    def _choose(self, choice: str) -> None:
        self.choice = choice
        self.accept()
