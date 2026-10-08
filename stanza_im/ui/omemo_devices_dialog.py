"""OMEMO device manager (XEP-0384).

Lists the devices known for an account (our own or a contact's) and lets the
user change trust, rename a device, copy its fingerprint and — for our own
account — delete a device.  All operations go through ``client.omemo``.
"""
from __future__ import annotations

import asyncio
import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from stanza_im.i18n import tr

logger = logging.getLogger("stanza_im.omemo")

_TRUST_LABELS = {
    "TRUSTED": "omemo_trust_trusted",
    "BLINDLY_TRUSTED": "omemo_trust_blindly",
    "UNDECIDED": "omemo_trust_undecided",
    "DISTRUSTED": "omemo_trust_distrusted",
}


def _trust_label(name: str) -> str:
    return tr(_TRUST_LABELS.get(name, "omemo_trust_undecided"))


class OmemoDevicesDialog(QtWidgets.QDialog):
    """Device & trust management for one account."""

    def __init__(self, client, jid: str, parent=None, own: bool = False):
        super().__init__(parent)
        self._client = client
        self._jid = str(jid).split("/")[0]
        self._own = bool(own)
        self._devices: list = []
        self.setWindowTitle(tr("omemo_devices_title", jid=self._jid))
        self.resize(560, 420)
        self._build_ui()
        self._reload()

    # ── UI ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self._status = QtWidgets.QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._list = QtWidgets.QListWidget()
        self._list.itemSelectionChanged.connect(self._update_actions)
        self._list.itemDoubleClicked.connect(lambda _i: self._on_copy())
        layout.addWidget(self._list, 1)

        row = QtWidgets.QHBoxLayout()
        self._trust_btn = QtWidgets.QPushButton(tr("omemo_trust_verify"))
        self._trust_btn.clicked.connect(self._on_trust)
        row.addWidget(self._trust_btn)
        self._distrust_btn = QtWidgets.QPushButton(tr("omemo_trust_distrust"))
        self._distrust_btn.clicked.connect(self._on_distrust)
        row.addWidget(self._distrust_btn)
        self._rename_btn = QtWidgets.QPushButton(tr("omemo_rename"))
        self._rename_btn.clicked.connect(self._on_rename)
        row.addWidget(self._rename_btn)
        self._copy_btn = QtWidgets.QPushButton(tr("omemo_copy_fingerprint"))
        self._copy_btn.clicked.connect(self._on_copy)
        row.addWidget(self._copy_btn)
        self._delete_btn = QtWidgets.QPushButton(tr("omemo_delete_device"))
        self._delete_btn.clicked.connect(self._on_delete)
        self._delete_btn.setVisible(self._own)
        row.addWidget(self._delete_btn)
        layout.addLayout(row)

        bottom = QtWidgets.QHBoxLayout()
        refresh = QtWidgets.QPushButton(tr("omemo_refresh"))
        refresh.clicked.connect(self._reload)
        bottom.addWidget(refresh)
        bottom.addStretch(1)
        close = QtWidgets.QPushButton(tr("dialog_close"))
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        layout.addLayout(bottom)

    # ── data ────────────────────────────────────────────────────

    def _reload(self) -> None:
        omemo = getattr(self._client, "omemo", None)
        if omemo is None or not getattr(omemo, "available", False):
            self._status.setText(tr("omemo_unavailable"))
            return
        self._status.setText(tr("omemo_loading"))
        try:
            asyncio.ensure_future(self._reload_async())
        except RuntimeError:
            # No running loop (tests): leave the list empty.
            self._status.setText("")

    async def _reload_async(self) -> None:
        omemo = self._client.omemo
        try:
            await omemo.refresh_device_lists([self._jid])
            devices = await omemo.devices(self._jid)
        except Exception as exc:  # noqa: BLE001
            logger.debug("OMEMO device load failed", exc_info=True)
            self._status.setText(tr("omemo_load_failed", error=str(exc)))
            return
        self._devices = sorted(devices, key=lambda d: int(d.device_id))
        self._status.setText(tr("omemo_devices_count", count=len(self._devices)))
        self._rebuild()

    def _rebuild(self) -> None:
        self._list.clear()
        omemo = self._client.omemo
        for device in self._devices:
            name = omemo.device_name(self._jid, int(device.device_id),
                                     str(getattr(device, "label", "") or ""))
            trust = _trust_label(omemo.trust_level_name(device))
            fp = omemo.fingerprint(device.identity_key)
            item = QtWidgets.QListWidgetItem(
                f"{name}  —  {trust}\n{device.device_id}  ·  {fp}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, device)
            self._list.addItem(item)
        self._update_actions()

    def _selected(self):
        item = self._list.currentItem()
        return item.data(QtCore.Qt.ItemDataRole.UserRole) if item else None

    def _update_actions(self) -> None:
        has = self._selected() is not None
        for button in (self._trust_btn, self._distrust_btn, self._rename_btn,
                       self._copy_btn):
            button.setEnabled(has)
        self._delete_btn.setEnabled(has)

    # ── actions ─────────────────────────────────────────────────

    def _set_trust(self, level: str) -> None:
        device = self._selected()
        if device is None:
            return
        asyncio.ensure_future(self._set_trust_async(device, level))

    async def _set_trust_async(self, device, level: str) -> None:
        try:
            await self._client.omemo.set_trust(
                device.bare_jid, device.identity_key, level)
        except Exception as exc:  # noqa: BLE001
            self._status.setText(tr("omemo_trust_failed", error=str(exc)))
            return
        await self._reload_async()

    def _on_trust(self) -> None:
        self._set_trust("TRUSTED")

    def _on_distrust(self) -> None:
        self._set_trust("DISTRUSTED")

    def _on_copy(self) -> None:
        device = self._selected()
        if device is None:
            return
        fp = self._client.omemo.fingerprint(device.identity_key)
        QtWidgets.QApplication.clipboard().setText(fp)
        self._status.setText(tr("omemo_fingerprint_copied"))

    def _on_rename(self) -> None:
        device = self._selected()
        if device is None:
            return
        omemo = self._client.omemo
        current = omemo.device_name(self._jid, int(device.device_id),
                                    str(getattr(device, "label", "") or ""))
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("omemo_rename"), tr("omemo_device_name"), text=current)
        if not ok:
            return
        omemo.set_device_alias(self._jid, int(device.device_id), name.strip())
        self._rebuild()

    def _on_delete(self) -> None:
        device = self._selected()
        if device is None:
            return
        reply = QtWidgets.QMessageBox.question(
            self, tr("omemo_delete_device"),
            tr("omemo_delete_confirm", device=device.device_id),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        asyncio.ensure_future(self._delete_async(device))

    async def _delete_async(self, device) -> None:
        try:
            await self._client.omemo.purge_device(device)
        except Exception as exc:  # noqa: BLE001
            self._status.setText(tr("omemo_delete_failed", error=str(exc)))
            return
        await self._reload_async()
