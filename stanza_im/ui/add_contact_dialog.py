"""Contact addition dialog, including XMPP gateway translation."""
from __future__ import annotations

import asyncio

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr


class AddContactDialog(QtWidgets.QDialog):
    """Collect contact data and optionally translate a gateway address."""

    def __init__(self, groups: list[str], client, parent=None, jid: str = ""):
        super().__init__(parent)
        self._client = client
        self.setWindowTitle(tr("add_contact_title"))
        self.setMinimumWidth(500)
        layout = QtWidgets.QVBoxLayout(self)

        service_form = QtWidgets.QFormLayout()
        self._service = QtWidgets.QComboBox()
        self._service.setEditable(False)
        self._service.addItem("XMPP", "")
        service_form.addRow(tr("add_contact_service"), self._service)
        layout.addLayout(service_form)

        self._gateway_box = QtWidgets.QGroupBox(tr("add_contact_gateway"))
        gateway_form = QtWidgets.QFormLayout(self._gateway_box)
        self._gateway_desc = QtWidgets.QLabel(tr("add_contact_gateway_default"))
        self._gateway_desc.setWordWrap(True)
        self._gateway_prompt = QtWidgets.QLineEdit()
        self._gateway_prompt.setPlaceholderText(tr("add_contact_gateway_placeholder"))
        self._gateway_button = QtWidgets.QPushButton(tr("add_contact_gateway_get"))
        self._gateway_button.clicked.connect(self._translate)
        gateway_form.addRow(self._gateway_desc)
        gateway_form.addRow(self._gateway_prompt, self._gateway_button)
        layout.addWidget(self._gateway_box)
        self._gateway_box.setEnabled(False)

        layout.addWidget(self._separator())
        form = QtWidgets.QFormLayout()
        self._jid = QtWidgets.QLineEdit()
        self._name = QtWidgets.QLineEdit()
        self._group = QtWidgets.QComboBox()
        self._group.setEditable(True)
        self._group.addItem("")
        self._group.addItems(groups)
        self._subscribe = QtWidgets.QCheckBox(tr("add_contact_subscribe"))
        self._subscribe.setChecked(True)
        self._message = QtWidgets.QPlainTextEdit()
        self._message.setMaximumHeight(80)
        form.addRow(tr("add_contact_jid"), self._jid)
        form.addRow(tr("add_contact_nick"), self._name)
        form.addRow(tr("add_contact_group"), self._group)
        form.addRow(self._subscribe)
        form.addRow(tr("add_contact_message"), self._message)
        layout.addLayout(form)
        self._jid.setText(jid)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(tr("dialog_ok"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(tr("dialog_cancel"))
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._service.currentIndexChanged.connect(self._service_changed)

    @staticmethod
    def _separator():
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        return line

    def _service_changed(self, index: int):
        service = self._service.itemData(index) or ""
        self._gateway_box.setEnabled(False)
        if service:
            self._start(self._load_gateway(service))

    def _start(self, coroutine):
        asyncio.get_event_loop().create_task(coroutine)

    async def _load_gateway(self, service: str):
        try:
            info = await self._client.gateway_info(service)
        except Exception as exc:
            self._gateway_desc.setText(tr("add_contact_gateway_error", error=str(exc)))
            return
        self._gateway_desc.setText(info.get("desc") or tr("add_contact_gateway_default"))
        self._gateway_prompt.setPlaceholderText(info.get("prompt") or tr("add_contact_gateway_placeholder"))
        self._gateway_box.setEnabled(True)

    def _translate(self):
        service = self._service.currentData() or ""
        prompt = self._gateway_prompt.text().strip()
        if not service or not prompt:
            return
        self._gateway_button.setEnabled(False)
        self._start(self._translate_async(service, prompt))

    async def _translate_async(self, service: str, prompt: str):
        try:
            self._jid.setText(await self._client.gateway_translate(service, prompt))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("add_contact_title"),
                                          tr("add_contact_gateway_error", error=str(exc)))
        finally:
            self._gateway_button.setEnabled(True)

    def _validate(self):
        if not self._jid.text().strip():
            QtWidgets.QMessageBox.warning(self, tr("add_contact_title"),
                                          tr("add_contact_jid_required"))
            return
        self.accept()

    def collect(self) -> dict:
        return {"jid": self._jid.text().strip(), "name": self._name.text().strip(),
                "group": self._group.currentText().strip(),
                "subscribe": self._subscribe.isChecked(),
                "message": self._message.toPlainText().strip()}
