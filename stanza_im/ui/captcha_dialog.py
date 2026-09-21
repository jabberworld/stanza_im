"""XEP-0158 CAPTCHA challenge dialog (responder side)."""
from __future__ import annotations

import asyncio

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.ui.data_form_widget import (
    DataFormWidget, _link_label, fit_dialog_to_content)


class CaptchaDialog(QtWidgets.QDialog):
    """Prompt the user to solve a XEP-0158 CAPTCHA challenge."""

    def __init__(self, client, challenger: str, form, oob: str = "",
                 body: str = "", media_service=None, parent=None):
        super().__init__(parent)
        self._client = client
        self._challenger = challenger
        self._form = form
        self._viewer = None
        self.setWindowTitle(tr("captcha_title"))
        self.setMinimumWidth(380)
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel((body or "").strip() or tr("captcha_body_hint"))
        label.setWordWrap(True)
        layout.addWidget(label)
        if oob:
            layout.addWidget(_link_label(oob, tr("captcha_open_oob")))
        self._widget = DataFormWidget(form, self, media_service=media_service)
        self._widget.media_open_requested.connect(self._open_media)
        self._widget.media_ready.connect(
            lambda: fit_dialog_to_content(self))
        self._form_scroll = QtWidgets.QScrollArea(self)
        self._form_scroll.setWidgetResizable(True)
        self._form_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._form_scroll.setWidget(self._widget)
        layout.addWidget(self._form_scroll, 1)
        self._status = QtWidgets.QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self._ok = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(tr("dialog_ok"))
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
                tr("dialog_cancel"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        QtCore.QTimer.singleShot(0, lambda: fit_dialog_to_content(self))

    def _open_media(self, url: str, kind: str) -> None:
        service = getattr(self._widget, "_media_service", None)
        if service is not None:
            from stanza_im.ui.media_viewer import MediaViewer
            self._viewer = MediaViewer(url, kind, service, parent=self)
            self._viewer.show()
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def _on_accept(self) -> None:
        error = self._widget.validate()
        if error:
            self._status.setText(error)
            return
        self._widget.apply_to_form()
        self._ok.setEnabled(False)
        asyncio.get_event_loop().create_task(self._submit())

    async def _submit(self) -> None:
        try:
            await self._client.answer_captcha(self._challenger, self._form)
        except Exception as exc:
            self._status.setText(tr("captcha_error", error=str(exc)))
            self._ok.setEnabled(True)
            return
        self.accept()
