"""XEP-0191 blocking command: view and edit the server-side blocklist."""
from __future__ import annotations

import asyncio

from PyQt6 import QtCore, QtWidgets

from stanza_im.i18n import tr


class BlockedContactsDialog(QtWidgets.QDialog):
    """List, add and remove the JIDs blocked on the server (XEP-0191)."""

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self.setWindowTitle(tr("blocked_title"))
        self.setMinimumSize(480, 420)
        self._names: dict[str, str] = {}
        self._build_ui()
        self._names = self._roster_names()
        asyncio.create_task(self._load())

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        self._list = QtWidgets.QListWidget(self)
        self._list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self._list, 1)

        add_row = QtWidgets.QHBoxLayout()
        self._jid = QtWidgets.QComboBox(self)
        self._jid.setEditable(True)
        self._jid.addItems(self._roster_jids())
        self._jid.setMinimumWidth(240)
        add_row.addWidget(self._jid, 1)
        self._btn_block = QtWidgets.QPushButton(tr("blocked_block"), self)
        self._btn_block.clicked.connect(self._on_block)
        add_row.addWidget(self._btn_block)
        layout.addLayout(add_row)

        buttons = QtWidgets.QHBoxLayout()
        self._btn_unblock = QtWidgets.QPushButton(tr("blocked_unblock"), self)
        self._btn_unblock.clicked.connect(self._on_unblock)
        buttons.addWidget(self._btn_unblock)
        self._btn_report = QtWidgets.QPushButton(tr("blocked_report"), self)
        self._btn_report.setEnabled(self._client.supports_reports())
        self._btn_report.clicked.connect(self._on_report)
        buttons.addWidget(self._btn_report)
        buttons.addStretch(1)
        close = QtWidgets.QPushButton(tr("dialog_close"), self)
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._status = QtWidgets.QLabel("", self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

    def _roster_snapshot(self) -> list[dict]:
        try:
            return list(self._client.get_roster_snapshot())
        except Exception:
            return []

    def _roster_jids(self) -> list[str]:
        return sorted({str(i["jid"]) for i in self._roster_snapshot()})

    def _roster_names(self) -> dict[str, str]:
        return {str(i["jid"]): str(i.get("name") or "")
                for i in self._roster_snapshot()}

    def _display_name(self, jid: str) -> str:
        name = self._names.get(jid, "")
        return f"{name} <{jid}>" if name else jid

    async def _load(self) -> None:
        try:
            await self._client.get_blocked_jids()
        except Exception as exc:
            self._set_status(tr("blocked_error", error=str(exc)), True)
        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        blocked = sorted(getattr(self._client, "_blocked", set()))
        for jid in blocked:
            item = QtWidgets.QListWidgetItem(self._display_name(jid))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, jid)
            self._list.addItem(item)
        if not blocked:
            self._status.setText(tr("blocked_none"))
        else:
            self._status.setText(tr("blocked_count", count=len(blocked)))

    def _selected_jids(self) -> list[str]:
        return [str(item.data(QtCore.Qt.ItemDataRole.UserRole))
                for item in self._list.selectedItems()]

    def _set_status(self, text: str, error: bool = False) -> None:
        self._status.setText(text)
        self._status.setStyleSheet("color: #c0392b;" if error else "")

    def _on_block(self) -> None:
        jid = self._jid.currentText().strip()
        if not jid:
            self._set_status(tr("blocked_empty_jid"), True)
            return
        asyncio.create_task(self._block(jid))

    async def _block(self, jid: str) -> None:
        try:
            await self._client.block_contact(jid)
        except Exception as exc:
            self._set_status(tr("blocked_error", error=str(exc)), True)
            return
        self._jid.setCurrentText("")
        self._refresh()

    def _on_unblock(self) -> None:
        jids = self._selected_jids()
        if not jids:
            return
        asyncio.create_task(self._unblock(jids))

    async def _unblock(self, jids: list[str]) -> None:
        try:
            for jid in jids:
                await self._client.unblock_contact(jid)
        except Exception as exc:
            self._set_status(tr("blocked_error", error=str(exc)), True)
        self._refresh()

    def _on_report(self) -> None:
        jids = self._selected_jids()
        if not jids:
            return
        from stanza_im.ui.report_dialog import ReportDialog
        dialog = ReportDialog(jids[0], self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        asyncio.create_task(self._report(jids[0], dialog.reason(),
                                         dialog.text()))

    async def _report(self, jid: str, reason: str, text: str) -> None:
        try:
            await self._client.report_contact(jid, reason, text)
        except Exception as exc:
            self._set_status(tr("report_error", error=str(exc)), True)
            return
        self._set_status(tr("report_sent"))
        self._refresh()
