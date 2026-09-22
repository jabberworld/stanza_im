"""XEP-0377 report dialog: pick a reason and an optional comment."""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.i18n import tr


class ReportDialog(QtWidgets.QDialog):
    """Ask for the spam/abuse reason and an optional comment."""

    def __init__(self, jid: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("report_title", jid=jid))
        self.setMinimumWidth(420)
        layout = QtWidgets.QFormLayout(self)
        layout.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._reason = QtWidgets.QComboBox(self)
        self._reason.addItem(tr("report_spam"), "spam")
        self._reason.addItem(tr("report_abuse"), "abuse")
        layout.addRow(tr("report_reason"), self._reason)

        self._text = QtWidgets.QPlainTextEdit(self)
        self._text.setPlaceholderText(tr("report_text_hint"))
        self._text.setFixedHeight(80)
        layout.addRow(tr("report_text"), self._text)

        note = QtWidgets.QLabel(tr("report_note"), self)
        note.setWordWrap(True)
        layout.addRow(note)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(
            tr("report_send"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
            tr("dialog_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def reason(self) -> str:
        return str(self._reason.currentData() or "spam")

    def text(self) -> str:
        return self._text.toPlainText().strip()
