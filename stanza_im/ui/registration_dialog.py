"""XEP-0077 in-band registration dialog."""
from __future__ import annotations

import asyncio

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.ui.data_form_widget import (
    DataFormWidget, LegacyFormWidget, fit_dialog_to_content)


class RegistrationDialog(QtWidgets.QDialog):
    """Show a service registration form and submit or remove it."""

    def __init__(self, client, jid: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._jid = jid
        self._form = None
        self._form_widget: DataFormWidget | None = None
        self._legacy_widget: LegacyFormWidget | None = None
        self._registered = False
        self.setWindowTitle(tr("register_title"))
        self.resize(420, 0)
        layout = QtWidgets.QVBoxLayout(self)
        self._status = QtWidgets.QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._body = QtWidgets.QVBoxLayout()
        layout.addLayout(self._body)
        buttons = QtWidgets.QHBoxLayout()
        self._btn_submit = QtWidgets.QPushButton(tr("register_apply"))
        self._btn_submit.clicked.connect(self._on_submit)
        buttons.addWidget(self._btn_submit)
        self._btn_remove = QtWidgets.QPushButton(tr("register_remove"))
        self._btn_remove.clicked.connect(self._on_remove)
        buttons.addWidget(self._btn_remove)
        buttons.addStretch()
        close = QtWidgets.QPushButton(tr("dialog_close"))
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._btn_submit.setEnabled(False)
        self._btn_remove.setEnabled(False)
        asyncio.get_event_loop().create_task(self._load())

    async def _load(self) -> None:
        try:
            info = await self._client.get_registration_form(self._jid)
        except Exception as exc:
            self._status.setText(tr("register_error", error=str(exc)))
            return
        self._registered = info.get("registered", False)
        form = info.get("form")
        fields = info.get("fields")
        instructions = info.get("instructions") or ""
        if instructions:
            note = QtWidgets.QLabel(str(instructions))
            note.setWordWrap(True)
            self._body.addWidget(note)
        oob = info.get("oob") or ""
        if oob:
            link = QtWidgets.QLabel(
                f'<a href="{oob}">{tr("captcha_open_oob")}</a>')
            link.setOpenExternalLinks(True)
            self._body.addWidget(link)
        if form is not None:
            self._form = form
            self._form_widget = DataFormWidget(form)
            self._form_widget.media_open_requested.connect(
                lambda url, _kind: QtGui.QDesktopServices.openUrl(
                    QtCore.QUrl(url)))
            self._form_widget.media_ready.connect(
                lambda: fit_dialog_to_content(self))
            scroll = QtWidgets.QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll.setWidget(self._form_widget)
            self._body.addWidget(scroll)
        elif fields:
            self._legacy_widget = LegacyFormWidget(fields)
            self._body.addWidget(self._legacy_widget)
        else:
            if self._registered:
                self._status.setText(tr("register_current"))
            else:
                self._status.setText(tr("register_none"))
        self._btn_submit.setEnabled(form is not None or fields is not None)
        self._btn_remove.setEnabled(self._registered)

    def _on_submit(self) -> None:
        asyncio.get_event_loop().create_task(self._submit())

    async def _submit(self) -> None:
        if self._form is not None:
            assert self._form_widget is not None
            error = self._form_widget.validate()
            if error:
                self._status.setText(error)
                return
            self._form_widget.apply_to_form()
            values = {}
        elif self._legacy_widget is not None:
            values = self._legacy_widget.values()
        else:
            return
        self._btn_submit.setEnabled(False)
        try:
            await self._client.submit_registration(self._jid, values,
                                                   form=self._form)
            self._status.setText(tr("register_success"))
            self._btn_remove.setEnabled(True)
        except Exception as exc:
            self._status.setText(tr("register_error", error=str(exc)))
        finally:
            self._btn_submit.setEnabled(True)

    def _on_remove(self) -> None:
        asyncio.get_event_loop().create_task(self._remove())

    async def _remove(self) -> None:
        self._btn_remove.setEnabled(False)
        try:
            await self._client.unregister(self._jid)
            self._status.setText(tr("register_removed"))
        except Exception as exc:
            self._status.setText(tr("register_error", error=str(exc)))
        finally:
            self._btn_remove.setEnabled(True)