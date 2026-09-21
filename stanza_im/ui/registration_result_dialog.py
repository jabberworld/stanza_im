"""Result dialog shown after a successful account registration (XEP-0077).

Shows the credentials of the created account, the connection settings used
and the data that was submitted to the server, so the user can copy and keep
them before the values are written to the configuration.
"""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.i18n import tr


class RegistrationResultDialog(QtWidgets.QDialog):
    """Present the created account and let the user apply the settings."""

    def __init__(self, jid: str, password: str,
                 details: list[tuple[str, str]] | None = None,
                 submitted: list[tuple[str, str]] | None = None,
                 parent=None):
        super().__init__(parent)
        self._summary = self._build_summary(jid, password, details or [],
                                            submitted or [])
        self.setWindowTitle(tr("registration_result_title"))
        self.setMinimumWidth(420)
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(tr("registration_result_intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self._text = QtWidgets.QPlainTextEdit(self._summary)
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(
            QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._text, 1)
        buttons = QtWidgets.QHBoxLayout()
        self._copy_btn = QtWidgets.QPushButton(tr("registration_result_copy"))
        self._copy_btn.clicked.connect(self._copy)
        buttons.addWidget(self._copy_btn)
        buttons.addStretch(1)
        self._apply_btn = QtWidgets.QPushButton(tr("dialog_apply"))
        self._apply_btn.setDefault(True)
        self._apply_btn.clicked.connect(self.accept)
        buttons.addWidget(self._apply_btn)
        self._close_btn = QtWidgets.QPushButton(tr("dialog_close"))
        self._close_btn.clicked.connect(self.reject)
        buttons.addWidget(self._close_btn)
        layout.addLayout(buttons)

    def summary(self) -> str:
        """The full text shown in the dialog and copied to the clipboard."""
        return self._summary

    def _copy(self) -> None:
        QtWidgets.QApplication.clipboard().setText(self._summary)

    @staticmethod
    def _build_summary(jid: str, password: str,
                       details: list[tuple[str, str]],
                       submitted: list[tuple[str, str]]) -> str:
        lines = [
            f'{tr("registration_result_jid")}: {jid}',
            f'{tr("registration_result_password")}: {password}',
        ]
        for label, value in details:
            if value:
                lines.append(f"{label}: {value}")
        if submitted:
            lines.append("")
            lines.append(tr("registration_result_submitted"))
            for label, value in submitted:
                lines.append(f"{label}: {value}")
        return "\n".join(lines)
