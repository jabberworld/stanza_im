"""MUC room management dialog (XEP-0045 affiliations + room configuration)."""
from __future__ import annotations

import asyncio

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr
from stanza_im.ui.data_form_widget import DataFormWidget

_AFFILIATIONS = ("owner", "admin", "member", "outcast")
_CATEGORY_KEYS = {
    "owner": "muc_config_owners",
    "admin": "muc_config_admins",
    "member": "muc_config_members",
    "outcast": "muc_config_outcasts",
}
_AFFILIATION_RANK = {"owner": 3, "admin": 2, "member": 1, "outcast": 0,
                     "none": 0, "": 0}


def can_change_affiliation(actor: str, original: str, new: str) -> bool:
    """Whether *actor* may change a participant from *original* to *new*.

    XEP-0045: owners may modify any list; admins only the member and outcast
    lists (and cannot grant admin/owner).
    """
    if actor == "owner":
        return True
    if actor == "admin":
        return (_AFFILIATION_RANK.get(original, 0) <= 1
                and _AFFILIATION_RANK.get(new, 0) <= 1)
    return False


class _ParticipantEditDialog(QtWidgets.QDialog):
    """Add or edit one affiliation entry: category, JID and note."""

    def __init__(self, parent=None, affiliation: str = "member",
                 jid: str = "", note: str = "",
                 title_key: str = "muc_config_add_title",
                 actor_affiliation: str = "",
                 original_affiliation: str = ""):
        super().__init__(parent)
        self._actor_affiliation = actor_affiliation
        self._original_affiliation = original_affiliation or "none"
        self.setWindowTitle(tr(title_key))
        form = QtWidgets.QFormLayout(self)
        self._category = QtWidgets.QComboBox()
        for aff in _AFFILIATIONS:
            self._category.addItem(tr(_CATEGORY_KEYS[aff]), aff)
        index = self._category.findData(affiliation)
        if index >= 0:
            self._category.setCurrentIndex(index)
        form.addRow(tr("muc_config_category"), self._category)
        self._jid = QtWidgets.QLineEdit(jid)
        form.addRow(tr("muc_config_jid"), self._jid)
        self._note = QtWidgets.QLineEdit(note)
        form.addRow(tr("muc_config_note"), self._note)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(
            tr("dialog_ok"))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(
            tr("dialog_cancel"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_accept(self) -> None:
        jid = self._jid.text().strip()
        if "@" not in jid and "." not in jid:
            QtWidgets.QMessageBox.warning(
                self, self.windowTitle(), tr("muc_config_invalid_jid"))
            return
        if not can_change_affiliation(
                self._actor_affiliation, self._original_affiliation,
                self._category.currentData()):
            QtWidgets.QMessageBox.warning(
                self, self.windowTitle(), tr("muc_config_no_permission"))
            return
        self.accept()

    def values(self) -> tuple[str, str, str]:
        return (self._category.currentData(), self._jid.text().strip(),
                self._note.text().strip())


class MucConfigDialog(QtWidgets.QDialog):
    """Room management: affiliation lists and (owner) room configuration."""

    def __init__(self, client, room: str, can_configure: bool = False,
                 parent=None, actor_affiliation: str = ""):
        super().__init__(parent)
        self._client = client
        self._room = room
        self._can_configure = bool(can_configure)
        self._actor_affiliation = actor_affiliation
        self._participants: dict[str, dict] = {}
        self._changes: dict[str, dict] = {}
        self._form = None
        self._form_widget: DataFormWidget | None = None
        self._initial_values: dict | None = None
        self._pending_values: dict | None = None
        self._busy = False

        self.setWindowTitle(tr("muc_config_title", room=room))
        self.resize(660, 470)
        layout = QtWidgets.QVBoxLayout(self)

        self._tabs = QtWidgets.QTabWidget()
        layout.addWidget(self._tabs, 1)

        # ── Participants ──────────────────────────────────────────
        participants = QtWidgets.QWidget()
        p_layout = QtWidgets.QVBoxLayout(participants)
        self._participants_status = QtWidgets.QLabel(tr("muc_config_loading"))
        self._participants_status.setWordWrap(True)
        p_layout.addWidget(self._participants_status)
        row = QtWidgets.QHBoxLayout()
        self._tree = QtWidgets.QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels([tr("muc_config_col_jid"),
                                    tr("muc_config_col_note")])
        self._tree.setColumnWidth(0, 340)
        self._tree.setRootIsDecorated(True)
        self._tree.itemSelectionChanged.connect(self._update_buttons)
        row.addWidget(self._tree, 1)
        side = QtWidgets.QVBoxLayout()
        self._add_btn = QtWidgets.QPushButton(tr("muc_config_add"))
        self._edit_btn = QtWidgets.QPushButton(tr("muc_config_edit"))
        self._delete_btn = QtWidgets.QPushButton(tr("muc_config_delete"))
        self._add_btn.clicked.connect(self._on_add)
        self._edit_btn.clicked.connect(self._on_edit)
        self._delete_btn.clicked.connect(self._on_delete)
        side.addWidget(self._add_btn)
        side.addWidget(self._edit_btn)
        side.addWidget(self._delete_btn)
        side.addStretch(1)
        row.addLayout(side)
        p_layout.addLayout(row, 1)
        self._tabs.addTab(participants, tr("muc_config_participants_tab"))

        # ── Settings ──────────────────────────────────────────────
        settings = QtWidgets.QWidget()
        s_layout = QtWidgets.QVBoxLayout(settings)
        self._settings_status = QtWidgets.QLabel("")
        self._settings_status.setWordWrap(True)
        s_layout.addWidget(self._settings_status)
        self._settings_body = QtWidgets.QVBoxLayout()
        s_layout.addLayout(self._settings_body, 1)
        self._tabs.addTab(settings, tr("muc_config_settings_tab"))
        self._tabs.setTabEnabled(1, self._can_configure)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self._ok_btn = buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self._cancel_btn = buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self._ok_btn.setText(tr("dialog_ok"))
        self._cancel_btn.setText(tr("dialog_cancel"))
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_buttons()
        self._start_task(self._load_participants())
        if self._can_configure:
            self._start_task(self._load_config())
        else:
            self._settings_status.setText(tr("muc_config_no_rights"))

    # ── Helpers ───────────────────────────────────────────────────

    def _start_task(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return None
        return loop.create_task(coro)

    def _selected_jid(self) -> str:
        item = self._tree.currentItem()
        if item is None or item.parent() is None:
            return ""
        return str(item.data(0, QtCore.Qt.ItemDataRole.UserRole) or "")

    def _update_buttons(self) -> None:
        has_row = bool(self._selected_jid())
        self._edit_btn.setEnabled(has_row)
        self._delete_btn.setEnabled(has_row)

    # ── Participants ──────────────────────────────────────────────

    async def _load_participants(self) -> None:
        try:
            data = await self._client.muc_get_affiliations(self._room)
        except Exception as exc:
            self._participants_status.setText(
                tr("muc_config_error", error=str(exc)))
            return
        self._participants = {}
        for aff, items in (data or {}).items():
            for item in items:
                jid = str(item.get("jid", "") or "")
                if jid:
                    self._participants[jid] = {
                        "affiliation": aff,
                        "note": str(item.get("reason", "") or ""),
                    }
        self._participants_status.setText("")
        self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        selected = self._selected_jid()
        self._tree.clear()
        for aff in _AFFILIATIONS:
            members = sorted(
                (jid for jid, entry in self._participants.items()
                 if entry.get("affiliation") == aff),
                key=str.lower)
            top = QtWidgets.QTreeWidgetItem(
                [f"{tr(_CATEGORY_KEYS[aff])} ({len(members)})", ""])
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            top.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self._tree.addTopLevelItem(top)
            for jid in members:
                child = QtWidgets.QTreeWidgetItem(
                    [jid, self._participants[jid].get("note", "")])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, jid)
                top.addChild(child)
                if jid == selected:
                    child.setSelected(True)
            top.setExpanded(True)
        self._update_buttons()

    def _on_add(self) -> None:
        dlg = _ParticipantEditDialog(
            self, affiliation="member",
            actor_affiliation=self._actor_affiliation,
            original_affiliation="none")
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        affiliation, jid, note = dlg.values()
        self._participants[jid] = {"affiliation": affiliation, "note": note}
        self._changes[jid] = {"affiliation": affiliation, "note": note}
        self._rebuild_tree()

    def _on_edit(self) -> None:
        jid = self._selected_jid()
        if not jid:
            return
        current = self._participants.get(jid, {})
        dlg = _ParticipantEditDialog(
            self, affiliation=current.get("affiliation", "member"), jid=jid,
            note=current.get("note", ""), title_key="muc_config_edit_title",
            actor_affiliation=self._actor_affiliation,
            original_affiliation=current.get("affiliation", "none"))
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        affiliation, new_jid, note = dlg.values()
        if new_jid != jid:
            self._participants.pop(jid, None)
            self._changes[jid] = {"affiliation": "none", "note": ""}
        self._participants[new_jid] = {"affiliation": affiliation, "note": note}
        self._changes[new_jid] = {"affiliation": affiliation, "note": note}
        self._rebuild_tree()

    def _on_delete(self) -> None:
        jid = self._selected_jid()
        if not jid:
            return
        answer = QtWidgets.QMessageBox.question(
            self, self.windowTitle(),
            tr("muc_config_confirm_delete", jid=jid),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No)
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._participants.pop(jid, None)
        self._changes[jid] = {"affiliation": "none", "note": ""}
        self._rebuild_tree()

    # ── Settings ──────────────────────────────────────────────────

    async def _load_config(self) -> None:
        try:
            form = await self._client.muc_get_config(self._room)
        except Exception as exc:
            self._settings_status.setText(
                tr("muc_config_error", error=str(exc)))
            self._tabs.setTabEnabled(1, False)
            return
        self._form = form
        self._form_widget = DataFormWidget(form)
        self._settings_body.addWidget(self._form_widget)
        self._settings_status.setText("")
        self._initial_values = self._form_widget.values()

    # ── Apply ─────────────────────────────────────────────────────

    def _on_ok(self) -> None:
        if self._busy:
            return
        values = None
        if self._can_configure and self._form_widget is not None:
            error = self._form_widget.validate()
            if error:
                QtWidgets.QMessageBox.warning(
                    self, self.windowTitle(), error)
                return
            current = self._form_widget.values()
            if current != self._initial_values:
                values = current
        if not self._changes and values is None:
            # Nothing actually changed: close without sending anything.
            self.accept()
            return
        self._pending_values = values
        self._busy = True
        self._ok_btn.setEnabled(False)
        self._start_task(self._apply())

    async def _apply(self) -> None:
        try:
            for jid, change in list(self._changes.items()):
                await self._client.muc_set_affiliation(
                    self._room, jid, change.get("affiliation", "none"),
                    change.get("note", ""))
            if self._pending_values is not None:
                await self._client.muc_set_config(
                    self._room, self._pending_values)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, self.windowTitle(),
                tr("muc_config_error", error=str(exc)))
            self._busy = False
            self._ok_btn.setEnabled(True)
            return
        self.accept()
