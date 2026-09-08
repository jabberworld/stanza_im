"""XEP-0050 ad-hoc command execution dialog."""
from __future__ import annotations

import asyncio

from PyQt6 import QtCore, QtWidgets

from jabbim.i18n import tr
from jabbim.ui.data_form_widget import DataFormWidget


class AdhocDialog(QtWidgets.QDialog):
    """Browse a service's ad-hoc commands, execute one and walk its form."""

    def __init__(self, client, jid: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._jid = jid
        self._current: dict | None = None
        self._form_widget: DataFormWidget | None = None
        self._commands_widget: QtWidgets.QTreeWidget | None = None
        self.setWindowTitle(tr("adhoc_title"))
        self.resize(520, 420)
        layout = QtWidgets.QVBoxLayout(self)
        self._status = QtWidgets.QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._body = QtWidgets.QVBoxLayout()
        layout.addLayout(self._body, 1)
        self._buttons = QtWidgets.QHBoxLayout()
        layout.addLayout(self._buttons)
        asyncio.get_event_loop().create_task(self._load_commands())

    async def _load_commands(self) -> None:
        try:
            commands = await self._client.get_commands_list(self._jid)
        except Exception as exc:
            self._status.setText(tr("adhoc_error", error=str(exc)))
            return
        if not commands:
            self._status.setText(tr("adhoc_none"))
            self._rebuild_buttons()
            return
        self._commands_widget = QtWidgets.QTreeWidget()
        self._commands_widget.setHeaderLabels([tr("service_name"),
                                               tr("service_jid")])
        self._commands_widget.setColumnWidth(0, 300)
        for command in commands:
            item = QtWidgets.QTreeWidgetItem(
                [command["name"], command.get("jid", self._jid)])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, command)
            self._commands_widget.addTopLevelItem(item)
        self._commands_widget.itemDoubleClicked.connect(self._on_command)
        self._body.addWidget(self._commands_widget)
        self._rebuild_buttons()

    def _on_command(self, item: QtWidgets.QTreeWidgetItem,
                    _column: int) -> None:
        command = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        asyncio.get_event_loop().create_task(self._execute(command))

    async def _execute(self, command: dict) -> None:
        self._set_loading(tr("adhoc_executing"))
        try:
            step = await self._client.start_command(
                command.get("jid", self._jid), command["node"])
        except Exception as exc:
            self._status.setText(tr("adhoc_error", error=str(exc)))
            self._rebuild_buttons()
            return
        self._remove_commands_widget()
        self._show_step(step)

    def _show_step(self, step: dict) -> None:
        self._current = step
        if self._form_widget is not None:
            self._form_widget.deleteLater()
            self._form_widget = None
        error = step.get("error")
        notes = step.get("notes") or []
        if error:
            message = tr("adhoc_error", error=error)
        elif step.get("status") == "completed":
            message = tr("adhoc_done")
        elif step.get("status") == "canceled":
            message = tr("adhoc_canceled")
        else:
            message = " | ".join(str(note) for _, note in notes)
        self._status.setText(message) if message else self._status.clear()
        form = step.get("form")
        if form is not None:
            self._form_widget = DataFormWidget(form)
            self._body.addWidget(self._form_widget)
        self._rebuild_buttons()

    def _remove_commands_widget(self) -> None:
        if self._commands_widget is not None:
            self._commands_widget.deleteLater()
            self._commands_widget = None

    def _send(self, action: str) -> None:
        if self._current is None:
            return
        asyncio.get_event_loop().create_task(self._continue(action))

    async def _continue(self, action: str) -> None:
        form = None
        if action != "cancel" and self._form_widget is not None:
            error = self._form_widget.validate()
            if error:
                self._status.setText(error)
                return
            self._form_widget.apply_to_form()
            form = self._current.get("form")
        self._set_loading(tr("adhoc_executing"))
        try:
            step = await self._client.continue_command(
                self._current["session"], action, form)
        except Exception as exc:
            self._status.setText(tr("adhoc_error", error=str(exc)))
            self._rebuild_buttons()
            return
        self._show_step(step)

    def _set_loading(self, message: str) -> None:
        self._status.setText(message)

    def _rebuild_buttons(self) -> None:
        while self._buttons.count():
            item = self._buttons.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        actions = set((self._current or {}).get("actions") or ())
        completed = (self._current or {}).get("status") in ("completed", "canceled")
        if self._current is not None and not completed:
            if "prev" in actions:
                self._add_button("adhoc_prev", lambda: self._send("prev"))
            if "next" in actions:
                self._add_button("adhoc_next", lambda: self._send("next"))
            if "complete" in actions:
                self._add_button("adhoc_complete", lambda: self._send("complete"))
            self._add_button("adhoc_cancel", lambda: self._send("cancel"))
        self._buttons.addStretch(1)
        close = QtWidgets.QPushButton(tr("dialog_close"))
        close.clicked.connect(self.reject)
        self._buttons.addWidget(close)

    def _add_button(self, key: str, handler) -> None:
        button = QtWidgets.QPushButton(tr(key))
        button.clicked.connect(handler)
        self._buttons.addWidget(button)