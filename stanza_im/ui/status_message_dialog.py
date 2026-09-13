"""Multiline editor for the presence status message.

Opened from the roster bottom bar; the previously stored message is preloaded
and the edited text is returned by :meth:`text`.
"""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.i18n import tr


class StatusMessageDialog(QtWidgets.QDialog):
    """Edit the user's presence status text."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("status_message_title"))
        self.setMinimumSize(440, 220)

        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(tr("status_message_hint"), self)
        label.setWordWrap(True)
        layout.addWidget(label)

        self._edit = QtWidgets.QPlainTextEdit(self)
        self._edit.setPlainText(text or "")
        self._edit.setPlaceholderText(tr("status_message_placeholder"))
        layout.addWidget(self._edit, stretch=1)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(tr("dialog_ok"))
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
                tr("dialog_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def text(self) -> str:
        return self._edit.toPlainText().strip()
