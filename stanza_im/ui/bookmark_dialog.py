"""Conference bookmark create/edit dialog.

Collects the XEP-0402 bookmark fields — name, nickname, room (the localpart),
server, password and the ``autojoin`` flag — and splits/joins the room JID.
"""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.i18n import tr


class BookmarkDialog(QtWidgets.QDialog):
    """Create or edit a conference bookmark."""

    def __init__(self, servers: list[str] | None = None,
                 bookmark: dict | None = None, default_nick: str = "",
                 parent=None):
        super().__init__(parent)
        self._bookmark = dict(bookmark or {})
        editing = bool(self._bookmark)
        self.setWindowTitle(tr("bookmark_edit_title") if editing
                            else tr("bookmark_new_title"))
        self.setMinimumWidth(420)
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        jid = str(self._bookmark.get("jid") or "")
        room, _, server = jid.partition("@")

        self._name = QtWidgets.QLineEdit(str(self._bookmark.get("name") or ""))
        self._nick = QtWidgets.QLineEdit(
            str(self._bookmark.get("nick") or "") or default_nick)
        self._room = QtWidgets.QLineEdit(room)
        self._server = QtWidgets.QComboBox()
        self._server.setEditable(True)
        values = list(dict.fromkeys(servers or []))
        if server and server not in values:
            values.insert(0, server)
        self._server.addItems(values)
        if server:
            self._server.setCurrentText(server)
        self._password = QtWidgets.QLineEdit(
            str(self._bookmark.get("password") or ""))
        self._password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

        form.addRow(tr("bookmark_field_name"), self._name)
        form.addRow(tr("bookmark_field_nick"), self._nick)
        form.addRow(tr("bookmark_field_room"), self._room)
        form.addRow(tr("bookmark_field_server"), self._server)
        form.addRow(tr("bookmark_field_password"), self._password)
        layout.addLayout(form)

        self._autojoin = QtWidgets.QCheckBox(tr("bookmark_autojoin"))
        self._autojoin.setChecked(bool(self._bookmark.get("autojoin")))
        layout.addWidget(self._autojoin)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(tr("dialog_ok"))
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
                tr("dialog_cancel"))
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate(self) -> None:
        if not self._room.text().strip() or not self._server.currentText().strip():
            QtWidgets.QMessageBox.warning(
                self, self.windowTitle(), tr("bookmark_room_required"))
            return
        self.accept()

    def collect(self) -> dict:
        room = self._room.text().strip()
        server = self._server.currentText().strip()
        return {
            "jid": f"{room}@{server}" if server else room,
            "name": self._name.text().strip(),
            "nick": self._nick.text().strip(),
            "password": self._password.text(),
            "autojoin": self._autojoin.isChecked(),
        }
