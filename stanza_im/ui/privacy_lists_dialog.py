"""XEP-0016 privacy-list manager dialog.

Top: the active list.  Below: the list editor (list selector + create /
rename / delete), the rules of the selected list (localized) with priority
arrows, and the rule operations (add / edit / delete / apply).
"""
from __future__ import annotations

import asyncio

from PyQt6 import QtGui, QtWidgets

from stanza_im.core import privacy
from stanza_im.i18n import tr
from stanza_im.ui.privacy_rule_dialog import PrivacyRuleDialog, describe_item


class PrivacyListsDialog(QtWidgets.QDialog):
    """Manage the account's privacy lists and their rules."""

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self._names: list[str] = []
        self._server_names: set[str] = set()
        self._active = ""
        self._default = ""
        self._current = ""
        self._items: list[dict] = []
        self._dirty = False
        self._loading = False
        self.setWindowTitle(tr("privacy_title"))
        self.setMinimumSize(560, 480)
        self._build_ui()
        asyncio.create_task(self._load())

    # ── UI ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        active_row = QtWidgets.QHBoxLayout()
        active_row.addWidget(QtWidgets.QLabel(tr("privacy_active_list")))
        self._active_combo = QtWidgets.QComboBox(self)
        self._active_combo.setMinimumWidth(220)
        self._active_combo.currentIndexChanged.connect(self._on_active_changed)
        active_row.addWidget(self._active_combo)
        active_row.addWidget(self._info_icon(tr("privacy_default_hint"), self))
        active_row.addStretch(1)
        layout.addLayout(active_row)

        default_row = QtWidgets.QHBoxLayout()
        default_row.addWidget(QtWidgets.QLabel(tr("privacy_default_list")))
        self._default_combo = QtWidgets.QComboBox(self)
        self._default_combo.setMinimumWidth(220)
        self._default_combo.currentIndexChanged.connect(
            self._on_default_changed)
        default_row.addWidget(self._default_combo)
        default_row.addStretch(1)
        layout.addLayout(default_row)

        group = QtWidgets.QGroupBox(tr("privacy_editor"), self)
        box = QtWidgets.QVBoxLayout(group)

        list_row = QtWidgets.QHBoxLayout()
        list_row.addWidget(QtWidgets.QLabel(tr("privacy_list")))
        self._list_combo = QtWidgets.QComboBox(self)
        self._list_combo.setMinimumWidth(180)
        self._list_combo.currentIndexChanged.connect(self._on_list_changed)
        list_row.addWidget(self._list_combo)
        self._btn_create = QtWidgets.QPushButton(tr("privacy_create"), group)
        self._btn_create.clicked.connect(self._on_create)
        self._btn_rename = QtWidgets.QPushButton(tr("privacy_rename"), group)
        self._btn_rename.clicked.connect(self._on_rename)
        self._btn_delete = QtWidgets.QPushButton(tr("privacy_delete"), group)
        self._btn_delete.clicked.connect(self._on_delete_list)
        for button in (self._btn_create, self._btn_rename, self._btn_delete):
            list_row.addWidget(button)
        list_row.addStretch(1)
        box.addLayout(list_row)

        rules_row = QtWidgets.QHBoxLayout()
        self._rules = QtWidgets.QListWidget(group)
        self._rules.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._rules.itemDoubleClicked.connect(lambda _item: self._on_edit_rule())
        rules_row.addWidget(self._rules, 1)
        arrows = QtWidgets.QVBoxLayout()
        self._btn_up = QtWidgets.QToolButton(group)
        self._btn_up.setIcon(self._arrow_icon("up"))
        self._btn_up.setToolTip(tr("privacy_move_up"))
        self._btn_up.clicked.connect(lambda: self._move_rule(-1))
        self._btn_down = QtWidgets.QToolButton(group)
        self._btn_down.setIcon(self._arrow_icon("down"))
        self._btn_down.setToolTip(tr("privacy_move_down"))
        self._btn_down.clicked.connect(lambda: self._move_rule(1))
        arrows.addWidget(self._btn_up)
        arrows.addWidget(self._btn_down)
        arrows.addStretch(1)
        rules_row.addLayout(arrows)
        box.addLayout(rules_row, 1)

        ops = QtWidgets.QHBoxLayout()
        for key, slot in (("privacy_add", self._on_add_rule),
                          ("privacy_edit", self._on_edit_rule),
                          ("privacy_remove", self._on_delete_rule)):
            button = QtWidgets.QPushButton(tr(key), group)
            button.clicked.connect(slot)
            ops.addWidget(button)
        ops.addStretch(1)
        self._btn_apply = QtWidgets.QPushButton(tr("privacy_apply"), group)
        self._btn_apply.clicked.connect(self._on_apply)
        ops.addWidget(self._btn_apply)
        box.addLayout(ops)
        layout.addWidget(group, 1)

        self._status = QtWidgets.QLabel("", self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        close = QtWidgets.QPushButton(tr("dialog_close"), self)
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    @staticmethod
    def _arrow_icon(direction: str) -> QtGui.QIcon:
        from stanza_im.include.constants import find_icon
        return QtGui.QIcon(find_icon(f"arrow-{direction}.svg"))

    @staticmethod
    def _info_icon(tooltip: str, parent=None) -> QtWidgets.QLabel:
        from stanza_im.include.constants import find_icon
        label = QtWidgets.QLabel(parent)
        icon = QtGui.QIcon(find_icon("info.svg"))
        if not icon.isNull():
            label.setPixmap(icon.pixmap(16, 16))
        label.setToolTip(tooltip)
        return label

    def _set_status(self, text: str, error: bool = False) -> None:
        self._status.setText(text)
        self._status.setStyleSheet("color: #c0392b;" if error else "")

    # ── data ────────────────────────────────────────────────────

    async def _load(self) -> None:
        self._loading = True
        try:
            data = await self._client.get_privacy_lists()
        except Exception as exc:
            self._loading = False
            self._set_status(tr("privacy_load_error", error=str(exc)), True)
            return
        self._active = data["active"]
        self._default = data["default"]
        self._names = list(data["lists"])
        self._server_names = set(self._names)
        self._refresh_combos()
        self._loading = False
        # Open the editor on the list that is actually applied (the active one,
        # or the default one when no active list is set — XEP-0016).
        effective = self._active or self._default
        if effective in self._names:
            self._select_list(effective)
        elif self._names:
            self._select_list(self._names[0])
        else:
            self._current = ""
            self._items = []
            self._refresh_rules()

    def _refresh_combos(self) -> None:
        self._active_combo.blockSignals(True)
        self._active_combo.clear()
        self._active_combo.addItem(tr("privacy_none"), "")
        for name in self._names:
            self._active_combo.addItem(name, name)
        index = self._active_combo.findData(self._active)
        self._active_combo.setCurrentIndex(max(index, 0))
        self._active_combo.blockSignals(False)

        self._default_combo.blockSignals(True)
        self._default_combo.clear()
        self._default_combo.addItem(tr("privacy_none"), "")
        for name in self._names:
            self._default_combo.addItem(name, name)
        index = self._default_combo.findData(self._default)
        self._default_combo.setCurrentIndex(max(index, 0))
        self._default_combo.blockSignals(False)

        self._list_combo.blockSignals(True)
        self._list_combo.clear()
        for name in self._names:
            self._list_combo.addItem(name, name)
        index = self._list_combo.findData(self._current)
        if index >= 0:
            self._list_combo.setCurrentIndex(index)
        self._list_combo.blockSignals(False)

    def _select_list(self, name: str) -> None:
        self._current = name
        index = self._list_combo.findData(name)
        if index >= 0:
            self._list_combo.blockSignals(True)
            self._list_combo.setCurrentIndex(index)
            self._list_combo.blockSignals(False)
        asyncio.create_task(self._load_items(name))

    async def _load_items(self, name: str) -> None:
        try:
            items = await self._client.get_privacy_list(name)
        except Exception as exc:
            self._set_status(tr("privacy_load_error", error=str(exc)), True)
            return
        self._items = privacy.sort_items(items)
        self._dirty = False
        self._refresh_rules()

    def _refresh_rules(self) -> None:
        self._rules.clear()
        for item in self._items:
            self._rules.addItem(describe_item(item))

    def _roster_jids(self) -> list[str]:
        try:
            return sorted({str(i["jid"]) for i in
                           self._client.get_roster_snapshot()})
        except Exception:
            return []

    def _roster_groups(self) -> list[str]:
        groups: set[str] = set()
        try:
            for entry in self._client.get_roster_snapshot():
                groups.update(str(g) for g in entry.get("groups") or [])
        except Exception:
            return []
        return sorted(groups)

    # ── list operations ─────────────────────────────────────────

    def _on_active_changed(self, _index: int) -> None:
        if self._loading:
            return
        name = str(self._active_combo.currentData() or "")
        asyncio.create_task(self._apply_active(name))

    async def _apply_active(self, name: str) -> None:
        try:
            await self._client.set_active_privacy_list(name)
        except Exception as exc:
            self._set_status(tr("privacy_load_error", error=str(exc)), True)
            return
        self._active = name
        self._set_status(tr("privacy_active_set", name=name or tr("privacy_none")))

    def _on_default_changed(self, _index: int) -> None:
        if self._loading:
            return
        name = str(self._default_combo.currentData() or "")
        asyncio.create_task(self._apply_default(name))

    async def _apply_default(self, name: str) -> None:
        try:
            await self._client.set_default_privacy_list(name)
        except Exception as exc:
            self._set_status(tr("privacy_load_error", error=str(exc)), True)
            return
        self._default = name
        self._set_status(tr("privacy_default_set", name=name or tr("privacy_none")))

    def _on_list_changed(self, _index: int) -> None:
        if self._loading:
            return
        name = str(self._list_combo.currentData() or "")
        if name == self._current:
            return
        if self._dirty:
            answer = QtWidgets.QMessageBox.question(
                self, tr("privacy_title"), tr("privacy_discard"))
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                self._select_list(self._current)
                return
        self._select_list(name)

    def _on_create(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("privacy_create"), tr("privacy_create_prompt"))
        name = name.strip()
        if not ok or not name or name in self._names:
            return
        self._names.append(name)
        self._refresh_combos()
        self._select_list(name)
        self._dirty = True

    def _on_rename(self) -> None:
        if not self._current:
            return
        old = self._current
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("privacy_rename"), tr("privacy_rename_prompt"), text=old)
        name = name.strip()
        if not ok or not name or name == old or name in self._names:
            return
        asyncio.create_task(self._rename(old, name))

    async def _rename(self, old: str, name: str) -> None:
        try:
            if self._items:
                await self._client.set_privacy_list(name, self._items)
                self._server_names.add(name)
            if old in self._server_names:
                await self._client.remove_privacy_list(old)
                self._server_names.discard(old)
            if self._active == old:
                await self._client.set_active_privacy_list(name)
                self._active = name
            if self._default == old:
                await self._client.set_default_privacy_list(name)
                self._default = name
        except Exception as exc:
            self._set_status(tr("privacy_load_error", error=str(exc)), True)
            return
        self._names = [name if n == old else n for n in self._names]
        self._current = name
        self._refresh_combos()
        self._set_status(tr("privacy_saved"))

    def _on_delete_list(self) -> None:
        if not self._current:
            return
        name = self._current
        answer = QtWidgets.QMessageBox.question(
            self, tr("privacy_delete"),
            tr("privacy_delete_confirm", name=name))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        asyncio.create_task(self._delete_list(name))

    async def _delete_list(self, name: str) -> None:
        try:
            if name in self._server_names:
                await self._client.remove_privacy_list(name)
        except Exception as exc:
            self._set_status(tr("privacy_load_error", error=str(exc)), True)
            return
        self._server_names.discard(name)
        self._names = [n for n in self._names if n != name]
        if self._active == name:
            self._active = ""
        if self._default == name:
            self._default = ""
        self._current = self._names[0] if self._names else ""
        self._refresh_combos()
        if self._current:
            self._select_list(self._current)
        else:
            self._items = []
            self._refresh_rules()
        self._set_status(tr("privacy_saved"))

    # ── rule operations ─────────────────────────────────────────

    def _selected_index(self) -> int:
        return self._rules.currentRow()

    def _on_add_rule(self) -> None:
        dialog = PrivacyRuleDialog(self._roster_jids(), self._roster_groups(),
                                   parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        item = dialog.result_item()
        item["order"] = privacy.next_order(self._items)
        self._items.insert(0, item)
        self._dirty = True
        self._refresh_rules()
        self._rules.setCurrentRow(0)

    def _on_edit_rule(self) -> None:
        index = self._selected_index()
        if index < 0 or index >= len(self._items):
            return
        current = self._items[index]
        dialog = PrivacyRuleDialog(self._roster_jids(), self._roster_groups(),
                                   current, parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        item = dialog.result_item()
        item["order"] = current.get("order", 0)
        self._items[index] = item
        self._dirty = True
        self._refresh_rules()
        self._rules.setCurrentRow(index)

    def _on_delete_rule(self) -> None:
        index = self._selected_index()
        if index < 0 or index >= len(self._items):
            return
        answer = QtWidgets.QMessageBox.question(
            self, tr("privacy_remove"), tr("privacy_remove_confirm"))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        del self._items[index]
        self._dirty = True
        self._refresh_rules()

    def _move_rule(self, delta: int) -> None:
        index = self._selected_index()
        target = index + delta
        if index < 0 or target < 0 or target >= len(self._items):
            return
        self._items[index], self._items[target] = (
            self._items[target], self._items[index])
        for position, item in enumerate(self._items):
            item["order"] = (position + 1) * 10
        self._dirty = True
        self._refresh_rules()
        self._rules.setCurrentRow(target)

    def _on_apply(self) -> None:
        if not self._current:
            return
        if not self._items:
            if self._current in self._server_names:
                answer = QtWidgets.QMessageBox.question(
                    self, tr("privacy_apply"), tr("privacy_apply_empty"))
                if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                    return
            else:
                self._set_status(tr("privacy_apply_empty"), True)
                return
        asyncio.create_task(self._apply())

    async def _apply(self) -> None:
        try:
            await self._client.set_privacy_list(self._current, self._items)
        except Exception as exc:
            self._set_status(tr("privacy_load_error", error=str(exc)), True)
            return
        self._server_names.add(self._current)
        self._dirty = False
        self._set_status(tr("privacy_saved"))

    def closeEvent(self, event) -> None:
        if self._dirty:
            answer = QtWidgets.QMessageBox.question(
                self, tr("privacy_title"), tr("privacy_discard"))
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        super().closeEvent(event)
