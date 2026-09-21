"""Standalone account-registration dialog (XEP-0077 in-band registration).

Collects the target server and the connection settings, connects without
authenticating, shows the server's registration data form and, on success,
stores the new account and connection settings in the application config.
"""
from __future__ import annotations

import asyncio
import logging
import os

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.core.client import JabberClient
from stanza_im.core.storage import Config
from stanza_im.include.constants import ACTIONS_DIR_16, SERVERS_FILE
from stanza_im.ui.data_form_widget import (
    DataFormWidget, LegacyFormWidget, _link_label, fit_dialog_to_content)
from stanza_im.ui.registration_result_dialog import RegistrationResultDialog

logger = logging.getLogger(__name__)


def load_servers() -> list[str]:
    """Return the suggested servers from ``resources/servers.txt``.

    One domain per line; blank lines and ``#`` comments are ignored.  A
    missing file simply yields an empty list (manual entry still works).
    """
    servers: list[str] = []
    try:
        with open(SERVERS_FILE, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                servers.append(line)
    except OSError:
        return []
    return servers


class AccountRegistrationDialog(QtWidgets.QDialog):
    """Two-step dialog: server + connection settings, then the data form."""

    registered = QtCore.pyqtSignal(str, str)  # jid, password

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._config = config
        self._client: JabberClient | None = None
        self._form = None
        self._form_widget: DataFormWidget | None = None
        self._legacy_widget: LegacyFormWidget | None = None
        self._server = ""
        self.setWindowTitle(tr("register_account_title"))
        self.resize(470, 0)
        self._build_ui()

    # ── UI construction ─────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self._stack = QtWidgets.QStackedWidget(self)
        self._stack.addWidget(self._build_settings_page())
        self._stack.addWidget(self._build_form_page())
        layout.addWidget(self._stack)

        self._status = QtWidgets.QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._next_btn = QtWidgets.QPushButton(tr("register_next"))
        self._next_btn.setDefault(True)
        self._next_btn.clicked.connect(self._on_next)
        buttons.addWidget(self._next_btn)
        self._cancel_btn = QtWidgets.QPushButton(tr("dialog_cancel"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        buttons.addWidget(self._cancel_btn)
        layout.addLayout(buttons)

    def _build_settings_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(page)

        server_row = QtWidgets.QHBoxLayout()
        server_row.addWidget(QtWidgets.QLabel(tr("register_server"), page))
        self._server_combo = QtWidgets.QComboBox(page)
        self._server_combo.setEditable(True)
        self._server_combo.addItem("")
        for server in load_servers():
            self._server_combo.addItem(server)
        self._server_combo.setCurrentIndex(0)
        server_row.addWidget(self._server_combo, 1)
        server_row.addWidget(self._info_icon(tr("register_server_info"), page))
        layout.addLayout(server_row)

        group = QtWidgets.QGroupBox(tr("register_section_connection"), page)
        form = QtWidgets.QFormLayout(group)
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._override = QtWidgets.QCheckBox(tr("prefs_override_host"), group)
        form.addRow(self._override)
        self._host = QtWidgets.QLineEdit(group)
        self._port = QtWidgets.QSpinBox(group)
        self._port.setRange(1, 65535)
        self._port.setValue(5222)
        self._host.setEnabled(False)
        self._port.setEnabled(False)
        self._override.toggled.connect(self._host.setEnabled)
        self._override.toggled.connect(self._port.setEnabled)
        form.addRow(tr("prefs_host"), self._host)
        form.addRow(tr("prefs_port"), self._port)

        self._tls = QtWidgets.QComboBox(group)
        for key, value in (("conn_mode_direct", "direct"),
                           ("conn_mode_prefer", "prefer"),
                           ("conn_mode_normal", "normal")):
            self._tls.addItem(tr(key), value)
        self._tls.setCurrentIndex(1)  # "Prefer TLS"
        self._enc = QtWidgets.QComboBox(group)
        for key, value in (("enc_always", "always"),
                           ("enc_opportunistic", "opportunistic"),
                           ("enc_never", "never")):
            self._enc.addItem(tr(key), value)
        self._enc.setCurrentIndex(0)  # "Always"

        def _sync_encryption():
            self._enc.setEnabled(self._tls.currentData() != "direct")

        self._tls.currentIndexChanged.connect(_sync_encryption)
        _sync_encryption()
        form.addRow(tr("prefs_connection_mode"), self._tls)
        form.addRow(tr("prefs_encryption"), self._enc)

        self._proxy_mode = QtWidgets.QComboBox(group)
        for key, value in (("prefs_proxy_none", "none"),
                           ("prefs_proxy_socks5", "socks5")):
            self._proxy_mode.addItem(tr(key), value)
        self._proxy_host = QtWidgets.QLineEdit(group)
        self._proxy_port = QtWidgets.QSpinBox(group)
        self._proxy_port.setRange(0, 65535)
        self._proxy_host.setEnabled(False)
        self._proxy_port.setEnabled(False)

        def _sync_proxy():
            enabled = self._proxy_mode.currentData() == "socks5"
            self._proxy_host.setEnabled(enabled)
            self._proxy_port.setEnabled(enabled)

        self._proxy_mode.currentIndexChanged.connect(_sync_proxy)
        _sync_proxy()
        form.addRow(tr("prefs_proxy_type"), self._proxy_mode)
        form.addRow(tr("prefs_host"), self._proxy_host)
        form.addRow(tr("prefs_port"), self._proxy_port)

        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_form_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(page)
        inner = QtWidgets.QWidget(page)
        self._form_container = QtWidgets.QVBoxLayout(inner)
        scroll = QtWidgets.QScrollArea(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        self._form_scroll = scroll
        return page

    @staticmethod
    def _info_icon(tooltip: str, parent=None) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(parent)
        icon = QtGui.QIcon(os.path.join(ACTIONS_DIR_16, "info.svg"))
        if not icon.isNull():
            label.setPixmap(icon.pixmap(16, 16))
        label.setToolTip(tooltip)
        return label

    # ── actions ─────────────────────────────────────────────────

    def _on_next(self) -> None:
        if self._stack.currentIndex() == 0:
            asyncio.get_event_loop().create_task(self._load_form())
        else:
            asyncio.get_event_loop().create_task(self._submit())

    def _on_cancel(self) -> None:
        self.reject()

    def _make_client(self, server: str) -> JabberClient:
        override = self._override.isChecked()
        return JabberClient(
            jid=server, password="", resource="stanza-im-reg",
            host=self._host.text().strip() if override else "",
            port=self._port.value() if override else 0,
            proxy_mode=self._proxy_mode.currentData(),
            proxy_host=self._proxy_host.text().strip(),
            proxy_port=self._proxy_port.value(),
            tls_mode=self._tls.currentData(),
            starttls_mode=self._enc.currentData(),
        )

    async def _load_form(self) -> None:
        server = self._server_combo.currentText().strip()
        if not server:
            self._set_status(tr("register_server_required"), "red")
            return
        self._server = server
        self._next_btn.setEnabled(False)
        self._set_status(tr("login_connecting"), "gray")
        self._client = self._make_client(server)
        try:
            await self._client.connect_for_registration()
        except Exception as exc:
            logger.debug("Registration connection to %s failed", server,
                         exc_info=True)
            self._set_status(tr("register_connect_failed", error=str(exc)),
                             "red")
            await self._close_client()
            self._next_btn.setEnabled(True)
            return
        try:
            info = await self._client.get_registration_form(server)
        except Exception as exc:
            logger.debug("Registration form request to %s failed", server,
                         exc_info=True)
            self._set_status(tr("register_none"), "red")
            await self._close_client()
            self._next_btn.setEnabled(True)
            return
        self._populate_form(info)
        self._next_btn.setText(tr("register_submit"))
        self._next_btn.setEnabled(True)
        self._stack.setCurrentIndex(1)

    def _populate_form(self, info: dict) -> None:
        instructions = info.get("instructions") or ""
        if instructions:
            note = QtWidgets.QLabel(str(instructions))
            note.setWordWrap(True)
            self._form_container.addWidget(note)
        oob = info.get("oob") or ""
        if oob:
            self._form_container.addWidget(
                _link_label(oob, tr("captcha_open_oob")))
        form = info.get("form")
        fields = info.get("fields")
        if form is not None:
            self._form = form
            self._form_widget = DataFormWidget(form)
            self._form_widget.media_open_requested.connect(
                lambda url, _kind: QtGui.QDesktopServices.openUrl(
                    QtCore.QUrl(url)))
            self._form_widget.media_ready.connect(
                lambda: fit_dialog_to_content(self))
            self._form_container.addWidget(self._form_widget)
        elif fields:
            self._legacy_widget = LegacyFormWidget(fields)
            self._form_container.addWidget(self._legacy_widget)
        else:
            self._set_status(tr("register_none"), "red")
            self._next_btn.setEnabled(False)
        self._form_container.addStretch(1)
        QtCore.QTimer.singleShot(0, lambda: fit_dialog_to_content(self))

    async def _submit(self) -> None:
        if self._form_widget is not None:
            error = self._form_widget.validate()
            if error:
                self._set_status(error, "red")
                return
            self._form_widget.apply_to_form()
            values = {}
        elif self._legacy_widget is not None:
            values = self._legacy_widget.values()
        else:
            return
        self._next_btn.setEnabled(False)
        self._set_status(tr("login_connecting"), "gray")
        try:
            await self._client.submit_registration(self._server, values,
                                                   form=self._form)
        except Exception as exc:
            logger.debug("Account registration at %s failed", self._server,
                         exc_info=True)
            self._set_status(tr("register_error", error=str(exc)), "red")
            self._next_btn.setEnabled(True)
            return
        jid, password = self._credentials(values)
        await self._close_client()
        result = RegistrationResultDialog(
            jid, password, self._connection_details(),
            self._submitted_data(values), parent=self)
        if result.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            self.reject()
            return
        self._save_config(jid, password)
        self.registered.emit(jid, password)
        self.accept()

    def _credentials(self, values: dict) -> tuple[str, str]:
        username = str(values.get("username") or "").strip()
        password = str(values.get("password") or "")
        if self._form is not None:
            for field in self._form["fields"]:
                var = str(field.get("var") or "")
                value = field.get("value")
                if var == "username" and value:
                    username = str(value).strip()
                elif var == "password" and value:
                    password = str(value)
        jid = username if "@" in username else f"{username}@{self._server}"
        return jid, password

    def _connection_details(self) -> list[tuple[str, str]]:
        """Localized ``(label, value)`` rows for the connection settings."""
        encryption = self._tls.currentText()
        if self._enc.isEnabled():
            encryption = f"{encryption} / {self._enc.currentText()}"
        details = [(tr("registration_result_encryption"), encryption)]
        if self._proxy_mode.currentData() == "socks5":
            host = self._proxy_host.text().strip()
            port = self._proxy_port.value()
            details.append((tr("registration_result_proxy"),
                            f"{host}:{port}" if host else ""))
        if self._override.isChecked():
            host = self._host.text().strip()
            details.append((tr("prefs_host"),
                            f"{host}:{self._port.value()}" if host else ""))
        return details

    def _submitted_data(self, values: dict) -> list[tuple[str, str]]:
        """Localized ``(label, value)`` rows for the data sent to the server."""
        if self._form is None:
            return [(str(key), str(value)) for key, value in values.items()]
        rows: list[tuple[str, str]] = []
        for field in self._form["fields"]:
            if str(field["type"] or "") == "hidden":
                continue
            var = str(field.get("var") or "")
            label = str(field.get("label", "") or var)
            value = field.get("value")
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            rows.append((label or var, str(value or "")))
        return rows

    def _save_config(self, jid: str, password: str) -> None:
        cfg = self._config
        cfg.jid = jid
        cfg.password = password
        cfg.save_password = True
        conn = cfg.connection
        override = self._override.isChecked()
        conn.override_host = override
        if override:
            conn.host = self._host.text().strip()
            conn.port = self._port.value()
        conn.tls_mode = self._tls.currentData()
        conn.starttls_mode = self._enc.currentData()
        conn.proxy_mode = self._proxy_mode.currentData()
        conn.proxy_host = self._proxy_host.text().strip()
        conn.proxy_port = self._proxy_port.value()
        cfg.save()

    def _set_status(self, text: str, color: str = "gray") -> None:
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color};")

    async def _close_client(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                logger.debug("Registration disconnect failed", exc_info=True)

    def closeEvent(self, event):
        if self._client is not None:
            asyncio.get_event_loop().create_task(self._close_client())
        super().closeEvent(event)
