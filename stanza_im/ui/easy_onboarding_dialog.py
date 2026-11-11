"""Easy Onboarding: redeem an XEP-0401/0379 invitation."""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr


class EasyOnboardingDialog(QtWidgets.QDialog):
    """Offer login, registration on the inviter's server, or another server."""

    login_requested = QtCore.pyqtSignal()
    register_requested = QtCore.pyqtSignal(dict)

    def __init__(self, invite: dict, parent=None):
        super().__init__(parent)
        self._invite = dict(invite or {})
        self.setWindowTitle(tr("onboarding_title"))
        self.setMinimumWidth(460)
        layout = QtWidgets.QVBoxLayout(self)

        action = str(self._invite.get("action") or "")
        jid = str(self._invite.get("jid") or "")
        name = str(self._invite.get("name") or "")
        server = str(self._invite.get("server") or "")
        username = str(self._invite.get("username") or "")

        if action == "register":
            title = tr("onboarding_create_at", server=server)
        else:
            who = f"{name} ({jid})" if name and name != jid else jid
            title = tr("onboarding_invited_by", who=who)
        heading = QtWidgets.QLabel(title, self)
        heading.setWordWrap(True)
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)

        server_line = QtWidgets.QLabel(
            tr("onboarding_server", server=server), self)
        server_line.setWordWrap(True)
        layout.addWidget(server_line)
        if username:
            account_line = QtWidgets.QLabel(
                tr("onboarding_username", username=username), self)
            account_line.setWordWrap(True)
            layout.addWidget(account_line)
        if action == "roster" and self._invite.get("ibr"):
            layout.addWidget(QtWidgets.QLabel(
                tr("onboarding_ibr_available"), self))
        elif action == "roster":
            layout.addWidget(QtWidgets.QLabel(
                tr("onboarding_ibr_unavailable"), self))
        layout.addSpacing(8)

        if action != "register":
            login = QtWidgets.QPushButton(
                tr("onboarding_login_existing"), self)
            login.clicked.connect(self._login)
            layout.addWidget(login)

        can_register_server = (action == "register"
                               or bool(self._invite.get("ibr")))
        if can_register_server:
            register_server = QtWidgets.QPushButton(
                tr("onboarding_register_server", server=server), self)
            register_server.clicked.connect(
                lambda: self._register(server=server))
            layout.addWidget(register_server)

        if action == "roster":
            register_other = QtWidgets.QPushButton(
                tr("onboarding_register_other"), self)
            register_other.clicked.connect(
                lambda: self._register(server=""))
            layout.addWidget(register_other)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        cancel = QtWidgets.QPushButton(tr("dialog_cancel"), self)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _login(self) -> None:
        self.login_requested.emit()
        self.accept()

    def _register(self, server: str) -> None:
        action = str(self._invite.get("action") or "")
        username = str(self._invite.get("username") or "")
        # Only an explicit ``register`` URI reserves the account name; a
        # roster invitation with ``ibr=y`` may use any free name on the server.
        locked = bool(username and action == "register")
        use_preauth = (action == "register"
                       or (server and server == self._invite.get("server")))
        self.register_requested.emit({
            "server": str(server or ""),
            "username": username if locked else "",
            "username_locked": locked,
            "preauth": str(self._invite.get("token") or "") if use_preauth else "",
            "invite_uri": str(self._invite.get("uri") or ""),
            "action": action,
        })
        self.accept()
