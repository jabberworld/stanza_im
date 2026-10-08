"""Dialog collecting the credentials and connection settings of an existing
account, used when creating a profile without registering a new one."""
from __future__ import annotations

from PyQt6 import QtWidgets

from stanza_im.i18n import tr
from stanza_im.core.profiles import Profile


class ExistingAccountDialog(QtWidgets.QDialog):
    """JID + password + optional host/port, encryption and proxy."""

    def __init__(self, parent=None, profile: Profile | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("profiles_existing_title"))
        self.setMinimumWidth(420)
        self._build_ui()
        if profile is not None:
            self._load(profile)

    # ── UI construction ─────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._jid = QtWidgets.QLineEdit()
        self._jid.setPlaceholderText("user@server")
        form.addRow(tr("login_title"), self._jid)

        self._password = QtWidgets.QLineEdit()
        self._password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        form.addRow(tr("login_password"), self._password)

        group = QtWidgets.QGroupBox(tr("prefs_section_connection"))
        gform = QtWidgets.QFormLayout(group)
        gform.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._override = QtWidgets.QCheckBox(tr("prefs_override_host"))
        gform.addRow(self._override)
        self._host = QtWidgets.QLineEdit()
        self._port = QtWidgets.QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(5222)
        self._host.setEnabled(False)
        self._port.setEnabled(False)
        self._override.toggled.connect(self._host.setEnabled)
        self._override.toggled.connect(self._port.setEnabled)
        gform.addRow(tr("prefs_host"), self._host)
        gform.addRow(tr("prefs_port"), self._port)

        self._tls = QtWidgets.QComboBox()
        for key, value in (("conn_mode_direct", "direct"),
                           ("conn_mode_prefer", "prefer"),
                           ("conn_mode_normal", "normal")):
            self._tls.addItem(tr(key), value)
        self._tls.setCurrentIndex(1)  # "Prefer TLS" (default; enables below)
        self._enc = QtWidgets.QComboBox()
        for key, value in (("enc_always", "always"),
                           ("enc_opportunistic", "opportunistic"),
                           ("enc_never", "never")):
            self._enc.addItem(tr(key), value)
        self._tls.currentIndexChanged.connect(self._sync_encryption)
        gform.addRow(tr("prefs_connection_mode"), self._tls)
        gform.addRow(tr("prefs_encryption"), self._enc)

        self._proxy_mode = QtWidgets.QComboBox()
        for key, value in (("prefs_proxy_none", "none"),
                           ("prefs_proxy_socks5", "socks5")):
            self._proxy_mode.addItem(tr(key), value)
        self._proxy_host = QtWidgets.QLineEdit()
        self._proxy_port = QtWidgets.QSpinBox()
        self._proxy_port.setRange(0, 65535)
        self._proxy_mode.currentIndexChanged.connect(self._sync_proxy)
        gform.addRow(tr("prefs_proxy_type"), self._proxy_mode)
        gform.addRow(tr("prefs_host"), self._proxy_host)
        gform.addRow(tr("prefs_port"), self._proxy_port)

        layout.addLayout(form)
        layout.addWidget(group)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: red;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        ok = QtWidgets.QPushButton(tr("dialog_ok"))
        ok.setDefault(True)
        ok.clicked.connect(self._on_ok)
        buttons.addWidget(ok)
        cancel = QtWidgets.QPushButton(tr("dialog_cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        self._sync_encryption()
        self._sync_proxy()

    def _sync_encryption(self) -> None:
        self._enc.setEnabled(self._tls.currentData() != "direct")

    def _sync_proxy(self) -> None:
        enabled = self._proxy_mode.currentData() == "socks5"
        self._proxy_host.setEnabled(enabled)
        self._proxy_port.setEnabled(enabled)

    # ── Data ────────────────────────────────────────────────────

    def _load(self, profile: Profile) -> None:
        self._jid.setText(profile.jid)
        self._password.setText(profile.password)
        self._override.setChecked(profile.override_host)
        self._host.setText(profile.host)
        self._port.setValue(profile.port or 5222)
        _set_combo(self._tls, profile.tls_mode)
        _set_combo(self._enc, profile.starttls_mode)
        _set_combo(self._proxy_mode, profile.proxy_mode)
        self._proxy_host.setText(profile.proxy_host)
        self._proxy_port.setValue(profile.proxy_port or 0)
        self._sync_encryption()
        self._sync_proxy()

    def _on_ok(self) -> None:
        if not self._jid.text().strip():
            self._status.setText(tr("profiles_jid_required"))
            return
        self.accept()

    def profile(self) -> Profile:
        return Profile(
            jid=self._jid.text().strip(),
            password=self._password.text(),
            save_password=True,
            override_host=self._override.isChecked(),
            host=self._host.text().strip(),
            port=self._port.value(),
            tls_mode=self._tls.currentData(),
            starttls_mode=self._enc.currentData(),
            proxy_mode=self._proxy_mode.currentData(),
            proxy_host=self._proxy_host.text().strip(),
            proxy_port=self._proxy_port.value(),
        )


def _set_combo(combo: QtWidgets.QComboBox, value: str) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)
