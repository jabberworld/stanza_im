"""Login widget — the first screen the user sees."""
from __future__ import annotations

import os

from PyQt6 import QtCore, QtWidgets, QtGui

from stanza_im.i18n import tr
from stanza_im.core.storage import Config


class LoginWidget(QtWidgets.QWidget):
    """Login form with JID, password, status, connect button."""

    login_requested = QtCore.pyqtSignal(str, str, str)  # jid, password, show
    register_requested = QtCore.pyqtSignal()            # "Create account" link

    def __init__(self, config: Config | None = None, parent=None):
        super().__init__(parent)
        self._config = config or Config()
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # Logo
        logo_label = QtWidgets.QLabel()
        logo_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        from stanza_im.include.constants import LOGO_PNG
        if os.path.isfile(LOGO_PNG):
            logo_label.setPixmap(QtGui.QPixmap(LOGO_PNG).scaled(
                96, 96,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            ))
        layout.addWidget(logo_label)
        layout.addSpacing(16)

        # JID
        layout.addWidget(QtWidgets.QLabel(tr("login_title")))
        self._jid_edit = QtWidgets.QLineEdit()
        self._jid_edit.setPlaceholderText("user@server")
        self._jid_edit.returnPressed.connect(self._on_connect)
        layout.addWidget(self._jid_edit)

        # Password
        layout.addWidget(QtWidgets.QLabel(tr("login_password")))
        self._pw_edit = QtWidgets.QLineEdit()
        self._pw_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._pw_edit.returnPressed.connect(self._on_connect)
        layout.addWidget(self._pw_edit)

        # Status
        status_row = QtWidgets.QHBoxLayout()
        status_row.addWidget(QtWidgets.QLabel(tr("login_status")))
        self._show_combo = QtWidgets.QComboBox()
        for key in ("online", "chat", "away", "xa", "dnd"):
            self._show_combo.addItem(self._make_status_icon(key), tr(f"status_{key}"), key)
        status_row.addWidget(self._show_combo)
        layout.addLayout(status_row)

        layout.addSpacing(8)

        # Options
        self._save_pw = QtWidgets.QCheckBox(tr("login_save_password"))
        self._auto_connect = QtWidgets.QCheckBox(tr("login_auto_connect"))
        self._auto_connect.setEnabled(False)
        self._save_pw.toggled.connect(self._auto_connect.setEnabled)
        layout.addWidget(self._save_pw)
        layout.addWidget(self._auto_connect)

        layout.addSpacing(8)

        # Connect
        self._connect_btn = QtWidgets.QPushButton(tr("login_connect"))
        self._connect_btn.setDefault(True)
        self._connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(self._connect_btn)

        # Create account link
        layout.addSpacing(14)
        self._create_label = QtWidgets.QLabel(
            f'<a href="create">{tr("login_create_account")}</a>')
        self._create_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._create_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._create_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._create_label.setOpenExternalLinks(False)
        self._create_label.linkActivated.connect(
            lambda _href: self.register_requested.emit())
        layout.addWidget(self._create_label)

        # Status label
        self._info_label = QtWidgets.QLabel("")
        self._info_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info_label)

        layout.addStretch()

    # ── helpers ──────────────────────────────────────────────────

    def _load_config(self):
        cfg = self._config
        if cfg.save_password:
            self._save_pw.setChecked(True)
            self._pw_edit.setText(cfg.password)
        self._jid_edit.setText(cfg.jid)
        last_status = cfg.last_status
        idx = self._show_combo.findData(last_status)
        if idx >= 0:
            self._show_combo.setCurrentIndex(idx)
        if cfg.auto_connect:
            self._auto_connect.setChecked(True)

    def _save_config(self, jid: str, password: str, show: str):
        cfg = self._config
        cfg.jid = jid
        cfg.password = password if self._save_pw.isChecked() else ""
        cfg.save_password = self._save_pw.isChecked()
        cfg.auto_connect = self._auto_connect.isChecked()
        cfg.last_status = show
        cfg.save()

    @staticmethod
    def _make_status_icon(show: str) -> QtGui.QIcon:
        from stanza_im.ui.icons import icons
        if icons:
            return QtGui.QIcon(icons.get_status_icon(show))
        return QtGui.QIcon()

    def _on_connect(self):
        jid = self._jid_edit.text().strip()
        pw = self._pw_edit.text()
        show = self._show_combo.currentData()
        if not jid or not pw:
            self.set_error("JID and password are required.")
            return
        self._save_config(jid, pw, show)
        self._connect_btn.setEnabled(False)
        self.set_status_text(tr("login_connecting"), "gray")
        self.login_requested.emit(jid, pw, show)

    def set_error(self, message: str):
        self._info_label.setText(message)
        self._info_label.setStyleSheet("color: red;")
        self._connect_btn.setEnabled(True)

    def set_status_text(self, message: str, color: str = "gray"):
        self._info_label.setText(message)
        self._info_label.setStyleSheet(f"color: {color};")

    def prefill(self, jid: str, password: str = "") -> None:
        """Fill the form after a successful account registration."""
        self._jid_edit.setText(jid or "")
        self._pw_edit.setText(password or "")
        if password:
            self._save_pw.setChecked(True)
        self.set_status_text("")
        self._connect_btn.setEnabled(True)

    @property
    def config(self) -> Config:
        return self._config

    def should_auto_connect(self) -> bool:
        """True when the saved config asks for automatic connection."""
        return bool(self._config.auto_connect) and (bool(self._config.jid) and bool(self._config.password))

    def get_credentials(self) -> tuple[str, str, str]:
        return (
            self._jid_edit.text().strip(),
            self._pw_edit.text(),
            self._show_combo.currentData(),
        )
