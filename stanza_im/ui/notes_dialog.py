"""Note create/edit dialog (Notes plugin).

Three fields: a one-line title, a one-line comma-separated tag list and a
multi-line body.  The caller owns persistence — the dialog only collects the
values.
"""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.i18n import tr


class NoteDialog(QtWidgets.QDialog):
    """Create or edit a single note."""

    def __init__(self, note: dict | None = None, parent=None):
        super().__init__(parent)
        self._note = dict(note or {})
        editing = bool(self._note)
        self.setWindowTitle(tr("notes_dialog_edit_title") if editing
                            else tr("notes_dialog_new_title"))
        self.setMinimumSize(420, 320)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._title = QtWidgets.QLineEdit(str(self._note.get("title") or ""))
        self._tags = QtWidgets.QLineEdit(str(self._note.get("tags") or ""))
        self._text = QtWidgets.QPlainTextEdit(str(self._note.get("text") or ""))

        form.addRow(tr("notes_field_title"), self._title)
        form.addRow(tr("notes_field_tags"), self._tags)
        layout.addLayout(form)
        layout.addWidget(QtWidgets.QLabel(tr("notes_field_text")))
        layout.addWidget(self._text, 1)

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

    def collect(self) -> dict:
        return {
            "title": self._title.text().strip(),
            "tags": self._tags.text().strip(),
            "text": self._text.toPlainText(),
        }
