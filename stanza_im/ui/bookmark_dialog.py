"""Conference bookmark create/edit dialog.

Collects the XEP-0402 bookmark fields — name, nickname, room (the localpart),
server, password and the ``autojoin`` flag — and splits/joins the room JID.
"""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.include.xmpp_uri import split_jid
from stanza_im.i18n import tr
from stanza_im.ui.jid_edit import RoomJidEdit


class BookmarkDialog(QtWidgets.QDialog):
    """Create or edit a conference bookmark."""

    def __init__(self, servers: list[str] | None = None,
                 bookmark: dict | None = None, default_nick: str = "",
                 parent=None):
        super().__init__(parent)
        _ = servers  # kept for caller compatibility; the field is free text
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
        self._room = RoomJidEdit(room)
        self._room.split.connect(
            lambda _room, host: self._server.setText(host))
        self._server = QtWidgets.QLineEdit(server)
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

    def _room_parts(self) -> tuple[str, str]:
        """``(room, server)``: a full JID in the room field wins."""
        room, server = split_jid(self._room.text())
        return room, server or self._server.text().strip()

    def _validate(self) -> None:
        room, server = self._room_parts()
        if not room or not server:
            QtWidgets.QMessageBox.warning(
                self, self.windowTitle(), tr("bookmark_room_required"))
            return
        self.accept()

    def collect(self) -> dict:
        room, server = self._room_parts()
        return {
            "jid": f"{room}@{server}" if server else room,
            "name": self._name.text().strip(),
            "nick": self._nick.text().strip(),
            "password": self._password.text(),
            "autojoin": self._autojoin.isChecked(),
        }
