"""Contact addition dialog, including XMPP gateway translation."""
from __future__ import annotations

import asyncio

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.include.constants import find_icon


class AddContactDialog(QtWidgets.QDialog):
    """Collect contact data and optionally translate a gateway address."""

    vcard_requested = QtCore.pyqtSignal(str)  # jid

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
        gateway_layout = QtWidgets.QVBoxLayout(self._gateway_box)
        gateway_layout.setContentsMargins(9, 6, 9, 6)
        gateway_layout.setSpacing(4)
        self._gateway_desc = QtWidgets.QLabel(tr("add_contact_gateway_default"))
        self._gateway_desc.setWordWrap(True)
        gateway_layout.addWidget(self._gateway_desc)
        self._gateway_prompt = QtWidgets.QLineEdit()
        self._gateway_prompt.setPlaceholderText(tr("add_contact_gateway_placeholder"))
        self._gateway_button = QtWidgets.QPushButton(tr("add_contact_gateway_get"))
        self._gateway_button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed)
        self._gateway_button.clicked.connect(self._translate)
        gateway_row = QtWidgets.QHBoxLayout()
        gateway_row.setContentsMargins(0, 0, 0, 0)
        gateway_row.addWidget(self._gateway_prompt, 1)
        gateway_row.addWidget(self._gateway_button, 0)
        gateway_layout.addLayout(gateway_row)
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
        self._vcard_btn = self._icon_button("v-card.png", tr("chat_vcard"))
        self._vcard_btn.clicked.connect(self._show_entered_vcard)
        self._nick_btn = self._icon_button(
            "nick-fill.svg", tr("add_contact_fill_nick"))
        self._nick_btn.clicked.connect(self._fill_nick)
        form.addRow(tr("add_contact_jid"),
                    self._field_row(self._jid, self._vcard_btn))
        form.addRow(tr("add_contact_nick"),
                    self._field_row(self._name, self._nick_btn))
        form.addRow(tr("add_contact_group"), self._group)
        form.addRow(self._subscribe)
        form.addRow(tr("add_contact_message"), self._message)
        layout.addLayout(form)
        self._jid.setText(jid if isinstance(jid, str) else "")

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

    @staticmethod
    def _icon_button(icon_name: str, tooltip: str) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setIcon(QtGui.QIcon(find_icon(icon_name)))
        button.setIconSize(QtCore.QSize(16, 16))
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        return button

    @staticmethod
    def _field_row(field: QtWidgets.QWidget,
                   button: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """A line edit plus a trailing icon button (the edit grows)."""
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(field, 1)
        layout.addWidget(button, 0)
        return row

    def _entered_jid(self) -> str:
        return self._jid.text().strip()

    def _show_entered_vcard(self):
        """Open the vCard of the JID typed in the field (if any)."""
        jid = self._entered_jid()
        if jid:
            self.vcard_requested.emit(jid)

    def _fill_nick(self):
        """Fill the nickname from the entered JID's vCard (async)."""
        jid = self._entered_jid()
        if not jid or self._client is None:
            return
        self._start(self._fill_nick_async(jid))

    async def _fill_nick_async(self, jid: str):
        from stanza_im.include.vcard import parse_vcard
        card = {}
        try:
            iq = await self._client.xmpp.plugin["xep_0054"].get_vcard(jid)
            card = parse_vcard(iq) or {}
        except Exception:
            card = {}
        # nickname, else fn, else the JID localpart.
        name = (str(card.get("nickname") or "").strip()
                or str(card.get("fn") or "").strip()
                or jid.split("@", 1)[0])
        if name:
            self._name.setText(name)

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
