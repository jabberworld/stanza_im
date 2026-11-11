"""XEP-0401 invitation creation dialog.

Creates a user invitation (``urn:xmpp:invite#invite``) or an account-creation
invitation (``urn:xmpp:invite#create-account``) and presents the returned
XMPP URI / landing URL.  When the server has no invite command the user
invitation falls back to a client-generated XEP-0379 PARS token.
"""
from __future__ import annotations

import asyncio

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.core import pars_tokens
from stanza_im.i18n import tr
from stanza_im.include.utils import format_local_datetime
from stanza_im.include.xmpp_uri import make_xmpp_uri
from stanza_im.ui.qr_dialog import QrDialog


class InviteDialog(QtWidgets.QDialog):
    """Create and show a user or account invitation."""

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self._result: dict | None = None
        self.setWindowTitle(tr("invite_title"))
        self.setMinimumWidth(560)
        self._build_ui()
        asyncio.get_event_loop().create_task(self._detect_commands())

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        mode_box = QtWidgets.QGroupBox(tr("invite_kind"), self)
        mode_layout = QtWidgets.QVBoxLayout(mode_box)
        self._user_radio = QtWidgets.QRadioButton(
            tr("invite_user"), mode_box)
        self._user_radio.setChecked(True)
        self._user_radio.setToolTip(tr("invite_user_tip"))
        mode_layout.addWidget(self._user_radio)
        self._account_radio = QtWidgets.QRadioButton(
            tr("invite_account"), mode_box)
        self._account_radio.setToolTip(tr("invite_account_tip"))
        self._account_radio.setEnabled(False)
        mode_layout.addWidget(self._account_radio)
        layout.addWidget(mode_box)

        form = QtWidgets.QFormLayout()
        self._username = QtWidgets.QLineEdit(self)
        self._username.setPlaceholderText(tr("invite_username_placeholder"))
        self._roster = QtWidgets.QCheckBox(tr("invite_roster_subscription"),
                                           self)
        self._roster.setChecked(True)
        form.addRow(tr("invite_username"), self._username)
        form.addRow(self._roster)
        layout.addLayout(form)
        self._account_controls = (self._username, self._roster)

        self._create_btn = QtWidgets.QPushButton(tr("invite_create"), self)
        self._create_btn.clicked.connect(self._on_create)
        layout.addWidget(self._create_btn)

        self._status = QtWidgets.QLabel("", self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._result_box = QtWidgets.QGroupBox(tr("invite_result"), self)
        result_layout = QtWidgets.QFormLayout(self._result_box)
        self._uri = QtWidgets.QLineEdit(self)
        self._uri.setReadOnly(True)
        self._landing = QtWidgets.QLineEdit(self)
        self._landing.setReadOnly(True)
        self._expiry = QtWidgets.QLabel(self)
        self._expiry.setWordWrap(True)
        result_layout.addRow(tr("invite_uri"), self._uri)
        result_layout.addRow(tr("invite_landing"), self._landing)
        result_layout.addRow(tr("invite_expires"), self._expiry)
        buttons = QtWidgets.QHBoxLayout()
        copy = QtWidgets.QPushButton(tr("invite_copy"), self)
        copy.clicked.connect(self._copy)
        open_btn = QtWidgets.QPushButton(tr("invite_open"), self)
        open_btn.clicked.connect(self._open_landing)
        qr_btn = QtWidgets.QPushButton(tr("invite_qr"), self)
        qr_btn.clicked.connect(self._show_qr)
        buttons.addWidget(copy)
        buttons.addWidget(open_btn)
        buttons.addWidget(qr_btn)
        buttons.addStretch(1)
        result_layout.addRow(buttons)
        self._result_box.setVisible(False)
        layout.addWidget(self._result_box)

        close = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close)
        close.button(QtWidgets.QDialogButtonBox.StandardButton.Close).setText(
            tr("dialog_close"))
        close.rejected.connect(self.reject)
        layout.addWidget(close)

        self._user_radio.toggled.connect(self._update_mode)
        self._account_radio.toggled.connect(self._update_mode)
        self._update_mode()

    def _update_mode(self) -> None:
        account = self._account_radio.isChecked()
        self._username.setEnabled(account)
        self._roster.setEnabled(account)

    def _set_status(self, text: str, color: str = "gray") -> None:
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color};")

    async def _detect_commands(self) -> None:
        try:
            commands = await self._client.invite_commands()
        except Exception:
            commands = set()
        self._account_radio.setEnabled(
            "urn:xmpp:invite#create-account" in commands)
        if "urn:xmpp:invite#invite" not in commands:
            self._user_radio.setToolTip(tr("invite_user_fallback_tip"))

    def _on_create(self) -> None:
        self._create_btn.setEnabled(False)
        self._result_box.setVisible(False)
        self._set_status(tr("invite_creating"))
        asyncio.get_event_loop().create_task(self._create())

    async def _create(self) -> None:
        try:
            if self._account_radio.isChecked():
                result = await self._client.create_account_invitation(
                    self._username.text().strip(), self._roster.isChecked())
                fallback = False
            else:
                try:
                    result = await self._client.create_user_invitation()
                    fallback = False
                except Exception:
                    result = self._fallback_invitation()
                    fallback = True
        except Exception as exc:  # noqa: BLE001 - shown in the dialog
            self._set_status(tr("invite_error", error=str(exc)), "red")
            self._create_btn.setEnabled(True)
            return
        self._show_result(result, fallback)
        self._create_btn.setEnabled(True)

    def _fallback_invitation(self) -> dict:
        bare = self._client.jid_str.split("/", 1)[0]
        name = ""
        try:
            contact = self._client.get_contact(bare)
            name = str(getattr(contact, "name", "") or "")
        except Exception:  # noqa: BLE001 - name is optional
            pass
        token = pars_tokens.issue(name=name)
        uri = make_xmpp_uri(bare, "roster", preauth=token, name=name)
        return {"uri": uri, "landing_url": "", "expire": "",
                "fallback": True}

    def _show_result(self, result: dict, fallback: bool) -> None:
        self._result = result
        self._uri.setText(str(result.get("uri") or ""))
        self._landing.setText(str(result.get("landing_url") or ""))
        expire = str(result.get("expire") or "")
        self._expiry.setText(format_local_datetime(expire) if expire else "")
        self._result_box.setVisible(True)
        self._set_status(
            tr("invite_fallback_done") if fallback else tr("invite_done"),
            "green" if not fallback else "gray")

    def _copy(self) -> None:
        if self._result:
            QtWidgets.QApplication.clipboard().setText(
                str(self._result.get("uri") or ""))
            self._set_status(tr("invite_copied"), "gray")

    def _open_landing(self) -> None:
        if self._result:
            url = str(self._result.get("landing_url") or "")
            if url:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def _show_qr(self) -> None:
        if self._result:
            dlg = QrDialog(str(self._result.get("uri") or ""), self,
                           title=tr("invite_qr"))
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
