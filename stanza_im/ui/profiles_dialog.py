"""Application profile manager dialog.

Lists the available profiles (one per account) and lets the user create,
apply and delete them.  Applying only emits :attr:`activated`; the window that
owns the config performs the switch (write the active account, drop the old
session and log in to the new one).
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr
from stanza_im.core import profiles
from stanza_im.include.constants import find_icon


def _icon(name: str) -> QtGui.QIcon:
    path = find_icon(name)
    return QtGui.QIcon(path) if path else QtGui.QIcon()


class ProfileDeleteDialog(QtWidgets.QDialog):
    """Confirmation with a choice: delete the data too, or only the entry."""

    def __init__(self, jid: str, parent=None):
        super().__init__(parent)
        self._with_data = False
        self.setWindowTitle(tr("profiles_delete_title"))
        self.setMinimumWidth(380)
        layout = QtWidgets.QVBoxLayout(self)
        question = QtWidgets.QLabel(tr("profiles_delete_question", jid=jid))
        question.setWordWrap(True)
        layout.addWidget(question)
        warning = QtWidgets.QLabel(tr("profiles_delete_data_warning", jid=jid))
        warning.setWordWrap(True)
        layout.addWidget(warning)

        with_data = QtWidgets.QPushButton(tr("profiles_delete_with_data"))
        with_data.setIcon(_icon("process-stop.png"))
        with_data.clicked.connect(lambda: self._pick(True))
        layout.addWidget(with_data)

        list_only = QtWidgets.QPushButton(tr("profiles_delete_list_only"))
        list_only.clicked.connect(lambda: self._pick(False))
        layout.addWidget(list_only)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        cancel = QtWidgets.QPushButton(tr("dialog_cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _pick(self, with_data: bool) -> None:
        self._with_data = with_data
        self.accept()

    def delete_with_data(self) -> bool:
        return self._with_data


class ProfilesDialog(QtWidgets.QDialog):
    """List, create, apply and delete application profiles."""

    activated = QtCore.pyqtSignal(str)  # jid

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle(tr("profiles_title"))
        self.resize(520, 360)
        self._build_ui()
        self.reload()

    # ── UI construction ─────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        left = QtWidgets.QVBoxLayout()
        left.addWidget(QtWidgets.QLabel(tr("profiles_list")))
        self._list = QtWidgets.QListWidget()
        self._list.itemSelectionChanged.connect(self._update_actions)
        self._list.itemDoubleClicked.connect(
            lambda _item: self._on_apply())
        left.addWidget(self._list, 1)
        top.addLayout(left, 1)

        right = QtWidgets.QVBoxLayout()
        self._create_btn = QtWidgets.QPushButton(tr("profiles_create"))
        self._create_btn.setIcon(_icon("add-user.png"))
        self._create_btn.clicked.connect(self._on_create)
        right.addWidget(self._create_btn)
        self._apply_btn = QtWidgets.QPushButton(tr("profiles_apply"))
        self._apply_btn.setIcon(_icon("ok.png"))
        self._apply_btn.clicked.connect(self._on_apply)
        right.addWidget(self._apply_btn)
        self._delete_btn = QtWidgets.QPushButton(tr("profiles_delete"))
        self._delete_btn.setIcon(_icon("process-stop.png"))
        self._delete_btn.clicked.connect(self._on_delete)
        right.addWidget(self._delete_btn)
        right.addStretch(1)
        top.addLayout(right)
        layout.addLayout(top, 1)

        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch(1)
        close = QtWidgets.QPushButton(tr("profiles_close"))
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        layout.addLayout(bottom)

    # ── List management ─────────────────────────────────────────

    def reload(self) -> None:
        """Rebuild the list from the registry (active account in bold)."""
        selected = self._selected_jid()
        self._list.clear()
        active = str(getattr(self._config, "jid", "") or "")
        for profile in profiles.load():
            item = QtWidgets.QListWidgetItem(profile.jid)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, profile.jid)
            if profile.jid == active:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setToolTip(tr("profiles_active"))
            self._list.addItem(item)
        if not self._list.count():
            placeholder = QtWidgets.QListWidgetItem(tr("profiles_none"))
            placeholder.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self._list.addItem(placeholder)
        elif selected:
            self._select(selected)
        self._update_actions()

    def _selected_jid(self) -> str:
        item = self._list.currentItem()
        if item is None:
            return ""
        return str(item.data(QtCore.Qt.ItemDataRole.UserRole) or "")

    def _select(self, jid: str) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(QtCore.Qt.ItemDataRole.UserRole) == jid:
                self._list.setCurrentItem(item)
                return

    def _update_actions(self) -> None:
        has = bool(self._selected_jid())
        self._apply_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)

    # ── Actions ─────────────────────────────────────────────────

    def _on_create(self) -> None:
        from stanza_im.ui.profile_source_dialog import ProfileSourceDialog
        source = ProfileSourceDialog(self)
        if source.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        if source.choice() == "register":
            self._create_registered()
        elif source.choice() == "existing":
            self._create_existing()

    def _create_registered(self) -> None:
        from stanza_im.ui.account_registration_dialog import (
            AccountRegistrationDialog)
        dialog = AccountRegistrationDialog(
            self._config, self, store_account=False)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        profile = dialog.result_profile()
        if profile is not None:
            profiles.upsert(profile)
            self.reload()

    def _create_existing(self) -> None:
        from stanza_im.ui.existing_account_dialog import ExistingAccountDialog
        dialog = ExistingAccountDialog(self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        profiles.upsert(dialog.profile())
        self.reload()

    def _on_apply(self) -> None:
        jid = self._selected_jid()
        if jid:
            self.activated.emit(jid)

    def _on_delete(self) -> None:
        jid = self._selected_jid()
        if not jid:
            return
        dialog = ProfileDeleteDialog(jid, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        if dialog.delete_with_data():
            profiles.delete_data(jid)
        profiles.remove(jid)
        self.reload()
