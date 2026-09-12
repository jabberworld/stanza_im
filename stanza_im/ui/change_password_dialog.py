"""Dialog for entering and confirming a new account password."""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.i18n import tr


class ChangePasswordDialog(QtWidgets.QDialog):
    """Collect a new password with a confirmation field."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("change_password_title"))
        self.resize(380, 0)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._new = QtWidgets.QLineEdit()
        self._new.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._confirm = QtWidgets.QLineEdit()
        self._confirm.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        form.addRow(tr("change_password_new"), self._new)
        form.addRow(tr("change_password_confirm"), self._confirm)
        layout.addLayout(form)

        self._status = QtWidgets.QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(
            tr("change_password_apply"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
            tr("dialog_cancel"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._new.returnPressed.connect(self._on_accept)
        self._confirm.returnPressed.connect(self._on_accept)
        self._new.setFocus()

    def _validate(self) -> str:
        """Return an error message key (or "") when the input is valid."""
        if not self._new.text() or not self._confirm.text():
            return tr("change_password_empty")
        if self._new.text() != self._confirm.text():
            return tr("change_password_mismatch")
        return ""

    def _on_accept(self):
        error = self._validate()
        if error:
            self._status.setText(error)
            self._status.setStyleSheet("color: red;")
            return
        self.accept()

    def password(self) -> str:
        return self._new.text()
